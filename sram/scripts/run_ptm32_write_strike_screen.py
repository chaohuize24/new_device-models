#!/usr/bin/env python3
"""Screen PTM32 SRAM write-path collected-charge vulnerability.

This is deliberately a selected-path electrical screen.  It compares the
minimum collected charge that corrupts a write against hold-state Qcrit.  It
does not convert Qcrit to a dynamic particle cross section and does not model
the address decoder or SEFI mechanisms.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import json
import math
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "configs/ptm32_write_strike_screen.json"
DEFAULT_WRITE = ROOT / "netlists/ptm32_dynamic_strike/sram6t_write_strike_template.sp"
DEFAULT_HOLD = ROOT / "netlists/ptm32_dynamic_strike/sram6t_hold_strike_template.sp"
DEFAULT_OUTPUT = ROOT / "results/write_strike_screen"
MEASURE_RE = re.compile(r"^([a-z0-9_]+)\s*=\s*([-+0-9.eE]+)", re.MULTILINE)


def fmt(value: float) -> str:
    return f"{float(value):.12g}"


def render(template: str, replacements: dict[str, str]) -> str:
    for token, value in replacements.items():
        template = template.replace(token, value)
    unresolved = sorted(set(re.findall(r"__[A-Z0-9_]+__", template)))
    if unresolved:
        raise ValueError(f"unresolved template tokens: {unresolved}")
    return template


def adverse_strike_term(node: str, desired_bit: int) -> tuple[str, str, str]:
    """Return source, sink and nominal logic level for an adverse pulse."""
    if node not in {"q", "qb", "bl", "blb", "d", "db"}:
        raise ValueError(f"unsupported strike node: {node}")
    high_nodes = {"q", "bl", "d"} if desired_bit == 1 else {"qb", "blb", "db"}
    if node in high_nodes:
        return node, "0", "high_charge_removal"
    return "0", node, "low_node_charge_injection"


def common_replacements(config: dict, model: Path, pvt_name: str, tid_name: str) -> dict[str, str]:
    cell = config["cell"]
    path = config["selected_write_path"]
    pvt = config["conditional_pvt_corners"][pvt_name]
    tid = config["tid_corners_at_14p32_krad_si"][tid_name]
    strike = config["strike"]
    timing = config["timing"]
    return {
        "__MODEL_PATH__": str(model.resolve()),
        "__VDD__": fmt(pvt["vdd_v"]),
        "__TEMP_C__": fmt(pvt["temperature_c"]),
        "__CNODE_FF__": fmt(cell["external_node_capacitance_ff"]),
        "__CBL_FF__": fmt(path["local_bitline_capacitance_ff"]),
        "__MU_SCALE__": fmt(tid["mobility_scale"]),
        "__TID_DVN__": fmt(tid["nmos_delta_vth_v"]),
        "__TID_DVP__": fmt(tid["pmos_signed_delta_vth_v"]),
        "__W_PQ_NM__": fmt(cell["pull_up_width_nm"]),
        "__W_PQB_NM__": fmt(cell["pull_up_width_nm"]),
        "__W_NQ_NM__": fmt(cell["pull_down_width_nm"]),
        "__W_NQB_NM__": fmt(cell["pull_down_width_nm"]),
        "__W_AXQ_NM__": fmt(cell["access_width_nm"]),
        "__W_AXQB_NM__": fmt(cell["access_width_nm"]),
        "__W_DRV_NM__": fmt(path["write_driver_nmos_width_nm"]),
        "__W_DRV_PM__": fmt(path["write_driver_pmos_width_nm"]),
        "__W_MUX_NM__": fmt(path["column_mux_nmos_width_nm"]),
        "__W_MUX_PM__": fmt(path["column_mux_pmos_width_nm"]),
        "__TAUR_PS__": fmt(strike["rise_time_ps"]),
        "__TAUF_PS__": fmt(strike["fall_time_ps"]),
        "__TFINAL_NS__": fmt(timing["final_decision_ns"]),
        "__TSTOP_NS__": fmt(timing["transient_end_ns"]),
    }


def case_replacements(
    common: dict[str, str], desired_bit: int, node: str, strike_time_ns: float, q_fc: float
) -> dict[str, str]:
    source, sink, polarity = adverse_strike_term(node, desired_bit)
    del polarity
    result = dict(common)
    result.update(
        {
            "__QFC__": fmt(q_fc),
            "__TSTRIKE_NS__": fmt(strike_time_ns),
            "__STRIKE_SOURCE__": source,
            "__STRIKE_SINK__": sink,
            "__DIN_V__": "{VDDVAL}" if desired_bit == 0 else "0",
            "__DINB_V__": "0" if desired_bit == 0 else "{VDDVAL}",
            "__Q_INIT_V__": "{VDDVAL}" if desired_bit == 0 else "0",
            "__QB_INIT_V__": "0" if desired_bit == 0 else "{VDDVAL}",
            "__D_INIT_V__": "0" if desired_bit == 0 else "{VDDVAL}",
            "__DB_INIT_V__": "{VDDVAL}" if desired_bit == 0 else "0",
        }
    )
    return result


def hold_replacements(common: dict[str, str], stored_bit: int, node: str, q_fc: float) -> dict[str, str]:
    source, sink, polarity = adverse_strike_term(node, stored_bit)
    del polarity
    result = dict(common)
    result.update(
        {
            "__QFC__": fmt(q_fc),
            "__STRIKE_SOURCE__": source,
            "__STRIKE_SINK__": sink,
            "__Q_INIT_V__": "0" if stored_bit == 0 else "{VDDVAL}",
            "__QB_INIT_V__": "{VDDVAL}" if stored_bit == 0 else "0",
        }
    )
    return result


def simulate(ngspice: str, deck: str, work: Path, stem: str) -> dict[str, float]:
    deck_path = work / f"{stem}.sp"
    log_path = work / f"{stem}.log"
    deck_path.write_text(deck, encoding="utf-8")
    proc = subprocess.run(
        [ngspice, "-b", "-o", str(log_path), str(deck_path)],
        cwd=work,
        text=True,
        capture_output=True,
        check=False,
    )
    log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    if proc.returncode != 0:
        raise RuntimeError(f"ngspice failed for {stem}:\n{proc.stderr}\n{log}")
    values = {name: float(value) for name, value in MEASURE_RE.findall(log)}
    if not {"vq_final", "vqb_final"}.issubset(values):
        raise RuntimeError(f"missing final cell measurements for {stem}:\n{log}")
    return values


def operation_failed(values: dict[str, float], desired_bit: int) -> bool:
    margin = values["vq_final"] - values["vqb_final"]
    return margin <= 0.0 if desired_bit == 1 else margin >= 0.0


def search_qcrit(
    simulate_q,
    initial_high_fc: float,
    max_fc: float,
    tolerance_fc: float,
) -> dict:
    baseline = simulate_q(0.0)
    if baseline:
        return {"status": "baseline_failed", "qcrit_fc": 0.0, "lower_no_fail_fc": 0.0, "upper_fail_fc": 0.0, "iterations": 0}
    low = 0.0
    high = initial_high_fc
    iterations = 0
    while high <= max_fc and not simulate_q(high):
        low = high
        high *= 2.0
        iterations += 1
    if high > max_fc:
        if simulate_q(max_fc):
            high = max_fc
        else:
            return {
                "status": "not_bracketed",
                "qcrit_fc": None,
                "lower_no_fail_fc": max_fc,
                "upper_fail_fc": None,
                "iterations": iterations + 1,
            }
    while high - low > tolerance_fc:
        mid = (low + high) / 2.0
        if simulate_q(mid):
            high = mid
        else:
            low = mid
        iterations += 1
    return {
        "status": "bracketed",
        "qcrit_fc": (low + high) / 2.0,
        "lower_no_fail_fc": low,
        "upper_fail_fc": high,
        "iterations": iterations,
    }


def run_write_case(task: dict, config: dict, model: Path, template: str, ngspice: str) -> dict:
    common = common_replacements(config, model, task["pvt_corner"], task["tid_corner"])
    source, sink, polarity = adverse_strike_term(task["node"], task["desired_bit"])
    strike = config["strike"]
    with tempfile.TemporaryDirectory(prefix="ptm32_write_strike_") as tmp:
        work = Path(tmp)
        counter = 0

        def evaluate(q_fc: float) -> bool:
            nonlocal counter
            counter += 1
            deck = render(
                template,
                case_replacements(
                    common,
                    task["desired_bit"],
                    task["node"],
                    task["strike_time_ns"],
                    q_fc,
                ),
            )
            values = simulate(ngspice, deck, work, f"q{counter}")
            return operation_failed(values, task["desired_bit"])

        result = search_qcrit(
            evaluate,
            float(strike["qcrit_initial_high_fc"]),
            float(strike["qcrit_max_fc"]),
            float(strike["qcrit_tolerance_fc"]),
        )
    return {
        **task,
        "strike_source": source,
        "strike_sink": sink,
        "adverse_polarity": polarity,
        **result,
    }


def run_hold_case(task: dict, config: dict, model: Path, template: str, ngspice: str) -> dict:
    common = common_replacements(config, model, task["pvt_corner"], task["tid_corner"])
    source, sink, polarity = adverse_strike_term(task["node"], task["stored_bit"])
    strike = config["strike"]
    with tempfile.TemporaryDirectory(prefix="ptm32_hold_strike_") as tmp:
        work = Path(tmp)
        counter = 0

        def evaluate(q_fc: float) -> bool:
            nonlocal counter
            counter += 1
            deck = render(template, hold_replacements(common, task["stored_bit"], task["node"], q_fc))
            values = simulate(ngspice, deck, work, f"q{counter}")
            return operation_failed(values, task["stored_bit"])

        result = search_qcrit(
            evaluate,
            float(strike["qcrit_initial_high_fc"]),
            float(strike["qcrit_max_fc"]),
            float(strike["qcrit_tolerance_fc"]),
        )
    return {
        **task,
        "strike_source": source,
        "strike_sink": sink,
        "adverse_polarity": polarity,
        **result,
    }


def mean_hold_wrong_probability(rate: float, interval: float) -> float:
    x = 2.0 * rate * interval
    if x == 0.0:
        return 0.0
    # Average of 0.5*(1-exp(-2*rate*t)) for uniform reads in [0, interval].
    # The direct expression loses all precision for the sub-attosecond
    # probabilities used by the target-orbit microsecond cases.
    if abs(x) < 1.0e-5:
        return x / 4.0 - x * x / 12.0 + x * x * x / 48.0
    return 0.5 * (1.0 + math.expm1(-x) / x)


def at_least_one(rate: float, interval: float) -> float:
    return -math.expm1(-rate * interval)


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lo = int(math.floor(position))
    hi = int(math.ceil(position))
    if lo == hi:
        return ordered[lo]
    weight = position - lo
    return ordered[lo] * (1.0 - weight) + ordered[hi] * weight


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--write-template", type=Path, default=DEFAULT_WRITE)
    parser.add_argument("--hold-template", type=Path, default=DEFAULT_HOLD)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--jobs", type=int, default=min(12, os.cpu_count() or 1))
    parser.add_argument("--ngspice", default=shutil.which("ngspice") or "ngspice")
    parser.add_argument("--quick", action="store_true", help="run nominal/central and four representative strike times")
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    model = (args.config.parent / config["model"]).resolve()
    if not model.exists():
        raise FileNotFoundError(model)
    write_template = args.write_template.read_text(encoding="utf-8")
    hold_template = args.hold_template.read_text(encoding="utf-8")

    pvt_names = list(config["conditional_pvt_corners"])
    tid_names = list(config["tid_corners_at_14p32_krad_si"])
    strike_times = list(config["timing"]["strike_times_ns"])
    if args.quick:
        pvt_names = ["nominal"]
        tid_names = ["central"]
        strike_times = [0.16, 0.26, 0.80, 1.69]
    task_keys: set[tuple[str, str, int, str, float]] = set()
    if args.quick:
        for pvt in pvt_names:
            for tid in tid_names:
                for bit in (0, 1):
                    for node in config["strike"]["nodes"]:
                        for strike_time in strike_times:
                            task_keys.add((pvt, tid, bit, node, float(strike_time)))
    else:
        strategy = config["screen_strategy"]
        full = strategy["full_phase_condition"]
        for bit in (0, 1):
            for node in config["strike"]["nodes"]:
                for strike_time in strike_times:
                    task_keys.add((full["pvt_corner"], full["tid_corner"], bit, node, float(strike_time)))
        for pvt in pvt_names:
            for tid in tid_names:
                for bit in strategy["all_corner_desired_bits"]:
                    for node in strategy["all_corner_nodes"]:
                        for strike_time in strategy["all_corner_strike_times_ns"]:
                            task_keys.add((pvt, tid, bit, node, float(strike_time)))
    write_tasks = [
        {
            "pvt_corner": pvt,
            "tid_corner": tid,
            "desired_bit": bit,
            "node": node,
            "strike_time_ns": strike_time,
        }
        for pvt, tid, bit, node, strike_time in sorted(task_keys)
    ]
    hold_keys = {
        (pvt, tid, 1, node)
        for pvt in pvt_names
        for tid in tid_names
        for node in ("q", "qb")
    }
    # The nominal pair explicitly verifies the expected Q/QB and 0/1 symmetry.
    hold_keys.update({("nominal", "central", 0, node) for node in ("q", "qb")})
    hold_tasks = [
        {"pvt_corner": pvt, "tid_corner": tid, "stored_bit": bit, "node": node}
        for pvt, tid, bit, node in sorted(hold_keys)
    ]

    write_rows: list[dict] = []
    hold_rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {
            pool.submit(run_write_case, task, config, model, write_template, args.ngspice): "write"
            for task in write_tasks
        }
        futures.update(
            {
                pool.submit(run_hold_case, task, config, model, hold_template, args.ngspice): "hold"
                for task in hold_tasks
            }
        )
        for index, future in enumerate(as_completed(futures), start=1):
            kind = futures[future]
            row = future.result()
            (write_rows if kind == "write" else hold_rows).append(row)
            if index % 100 == 0 or index == len(futures):
                print(f"completed {index}/{len(futures)} Qcrit cases", flush=True)

    write_rows.sort(key=lambda r: (r["pvt_corner"], r["tid_corner"], r["desired_bit"], r["node"], r["strike_time_ns"]))
    hold_rows.sort(key=lambda r: (r["pvt_corner"], r["tid_corner"], r["stored_bit"], r["node"]))
    bracketed_write = [float(row["qcrit_fc"]) for row in write_rows if row["status"] == "bracketed"]
    bracketed_hold = [float(row["qcrit_fc"]) for row in hold_rows if row["status"] == "bracketed"]
    if not bracketed_write or not bracketed_hold:
        raise RuntimeError("screen did not produce bracketed write and hold Qcrit values")

    condition_rows = []
    for pvt in pvt_names:
        for tid in tid_names:
            w = [float(row["qcrit_fc"]) for row in write_rows if row["pvt_corner"] == pvt and row["tid_corner"] == tid and row["status"] == "bracketed"]
            h = [float(row["qcrit_fc"]) for row in hold_rows if row["pvt_corner"] == pvt and row["tid_corner"] == tid and row["status"] == "bracketed"]
            condition_rows.append(
                {
                    "condition_id": f"{pvt}__tid_{tid}",
                    "write_bracketed_cases": len(w),
                    "write_not_bracketed_cases": sum(
                        row["pvt_corner"] == pvt and row["tid_corner"] == tid and row["status"] == "not_bracketed"
                        for row in write_rows
                    ),
                    "minimum_write_qcrit_fc": min(w),
                    "median_write_qcrit_fc": statistics.median(w),
                    "minimum_hold_qcrit_fc": min(h),
                    "median_hold_qcrit_fc": statistics.median(h),
                    "minimum_write_over_minimum_hold": min(w) / min(h),
                }
            )

    importance = config["importance_screen"]
    rate = float(importance["nominal_radiation_rate_per_bit_s"])
    write_window = float(importance["write_window_s"])
    static_window_proxy = at_least_one(rate, write_window)
    importance_rows = []
    for residence in importance["residence_times_s"]:
        hold_probability = mean_hold_wrong_probability(rate, float(residence))
        importance_rows.append(
            {
                "residence_time_s": residence,
                "mean_hold_state_error_probability": hold_probability,
                "static_cross_section_write_window_proxy": static_window_proxy,
                "dynamic_to_hold_cross_section_multiplier_needed_for_equal_contribution": hold_probability / static_window_proxy,
            }
        )

    valid_decision_conditions = [row for row in condition_rows if not row["condition_id"].endswith("stress_not_a_fit")]
    worst_ratio = min(float(row["minimum_write_over_minimum_hold"]) for row in valid_decision_conditions)
    overall = {
        "method": "PTM32 selected-path double-exponential collected-charge Qcrit screen",
        "write_cases": len(write_rows),
        "hold_cases": len(hold_rows),
        "minimum_write_qcrit_fc": min(bracketed_write),
        "p05_write_qcrit_fc": quantile(bracketed_write, 0.05),
        "median_write_qcrit_fc": statistics.median(bracketed_write),
        "minimum_hold_qcrit_fc": min(bracketed_hold),
        "median_hold_qcrit_fc": statistics.median(bracketed_hold),
        "worst_nonstress_min_write_over_hold_qcrit": worst_ratio,
        "not_bracketed_write_cases": sum(row["status"] == "not_bracketed" for row in write_rows),
        "baseline_failed_write_cases": sum(row["status"] == "baseline_failed" for row in write_rows),
        "address_decoder_in_transient_netlist": False,
        "address_decoder_only_in_area_proxy": True,
        "claim_boundary": config["claim_boundary"],
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "write_qcrit_cases.csv", write_rows)
    write_csv(args.output_dir / "hold_qcrit_cases.csv", hold_rows)
    write_csv(args.output_dir / "qcrit_by_condition.csv", condition_rows)
    write_csv(args.output_dir / "importance_thresholds.csv", importance_rows)
    payload = {
        "schema_version": 1,
        "config": config,
        "resolved_model": "models/PTM_bulk/32nm_LP.pm",
        "summary": overall,
        "condition_summary": condition_rows,
        "importance_thresholds": importance_rows,
        "files": {
            "write_cases": "sram/results/write_strike_screen/write_qcrit_cases.csv",
            "hold_cases": "sram/results/write_strike_screen/hold_qcrit_cases.csv",
            "condition_summary": "sram/results/write_strike_screen/qcrit_by_condition.csv",
            "importance_thresholds": "sram/results/write_strike_screen/importance_thresholds.csv",
        },
    }
    (args.output_dir / "summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = f"""# PTM32 SRAM dynamic-write strike screening

This is a selected-path electrical vulnerability screen, not an absolute dynamic write BER calculation.

- Write Qcrit cases: {len(write_rows)}
- Hold Qcrit cases: {len(hold_rows)}
- Minimum bracketed write Qcrit: {overall['minimum_write_qcrit_fc']:.6g} fC
- Minimum hold Qcrit: {overall['minimum_hold_qcrit_fc']:.6g} fC
- Worst non-stress condition min(write Qcrit)/min(hold Qcrit): {worst_ratio:.6g}
- Write cases with no failure up to {config['strike']['qcrit_max_fc']} fC: {overall['not_bracketed_write_cases']}
- Baseline write failures: {overall['baseline_failed_write_cases']}

The transient deck includes finite CMOS write drivers and a transistor-level selected transmission-gate column branch. It does not include address decoders, address latches, clock distribution, unselected mux branches, target PEX, MBU or SEFI.

`Qcrit_write/Qcrit_hold` is only a vulnerability ratio. A dynamic cross section still requires target layout/charge collection or dynamic beam data.
"""
    (args.output_dir / "README.md").write_text(report, encoding="utf-8")
    print(json.dumps(overall, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
