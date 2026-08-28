#!/usr/bin/env python3
"""Screen SOT-MRAM write-window collected-charge vulnerability (post_write channel).

Compares minimum collected charge that corrupts an SOT-assisted BL write against
hold-state Qcrit on the 1T1MTJ cell.  This is a selected-path electrical
screen, not an absolute dynamic write cross section.
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
import statistics
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(REPO / "mram/scripts"))
from sot_mram_heavy_ion_pipeline import resolve_ngspice  # noqa: E402

DEFAULT_CONFIG = ROOT / "configs/sot_write_strike_screen.json"
DEFAULT_WRITE = ROOT / "netlists/sot_dynamic_strike/sot_write_strike_template.sp"
DEFAULT_HOLD = ROOT / "netlists/sot_dynamic_strike/sot_hold_strike_template.sp"
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
    high_for_bit1 = {"bl", "mtj"}
    high_for_bit0 = {"blb"}
    if node == "sot_top":
        return "0", node, "sot_channel_injection"
    if desired_bit == 1:
        if node in high_for_bit1:
            return node, "0", "high_charge_removal"
        return "0", node, "low_node_charge_injection"
    if node in high_for_bit0:
        return node, "0", "high_charge_removal"
    return "0", node, "low_node_charge_injection"


def common_replacements(config: dict, model: Path, mtj: dict, pvt_name: str, tid_name: str) -> dict[str, str]:
    cell = config["cell"]
    pvt = config["conditional_pvt_corners"][pvt_name]
    tid = config["tid_corners_at_14p32_krad_si"][tid_name]
    strike = config["strike"]
    timing = config["timing"]
    return {
        "__MODEL_PATH__": str(model.resolve()),
        "__VDD__": fmt(pvt["vdd_v"]),
        "__TEMP_C__": fmt(pvt["temperature_c"]),
        "__R_P__": fmt(cell.get("r_p_ohm", cell.get("r_p_ohm_read_proxy", 10000.0))),
        "__R_AP__": fmt(cell.get("r_ap_ohm", cell.get("r_ap_ohm_read_proxy", 20000.0))),
        "__R_SOT__": fmt(cell["r_sot_ohm"]),
        "__C_MTJ__": f"{cell['c_mtj_fF']:.12g}f",
        "__MU_SCALE__": fmt(tid["mobility_scale"]),
        "__TID_DVN__": fmt(tid["nmos_delta_vth_v"]),
        "__TID_DVP__": fmt(tid["pmos_signed_delta_vth_v"]),
        "__W_ACC_NM__": fmt(cell["access_width_nm"]),
        "__W_DRV_NM__": fmt(cell["write_driver_nmos_width_nm"]),
        "__W_DRV_PM__": fmt(cell["write_driver_pmos_width_nm"]),
        "__IWRITE_A__": fmt(cell["i_write_a"]),
        "__TAUR_PS__": fmt(strike["rise_time_ps"]),
        "__TAUF_PS__": fmt(strike["fall_time_ps"]),
        "__TFINAL_NS__": fmt(timing["final_decision_ns"]),
        "__TSTOP_NS__": fmt(timing["transient_end_ns"]),
    }


def write_replacements(
    common: dict[str, str],
    desired_bit: int,
    node: str,
    strike_time_ns: float,
    q_fc: float,
    vdd: float,
) -> dict[str, str]:
    source, sink, polarity = adverse_strike_term(node, desired_bit)
    threshold = 0.5 * vdd
    if desired_bit == 0:
        bld_v, bldb_v = vdd, 0.0
        bl_init, blb_init, mtj_init = vdd * 0.9, vdd * 0.1, threshold * 0.8
        r_mtj_val = common["_R_P"]
    else:
        bld_v, bldb_v = 0.0, vdd
        bl_init, blb_init, mtj_init = vdd * 0.1, vdd * 0.9, threshold * 1.2
        r_mtj_val = common["_R_AP"]
    return {
        **{k: v for k, v in common.items() if not k.startswith("_") or k.startswith("__")},
        "__R_MTJ__": r_mtj_val,
        "__BLD_V__": fmt(bld_v),
        "__BLDB_V__": fmt(bldb_v),
        "__BL_INIT_V__": fmt(bl_init),
        "__BLB_INIT_V__": fmt(blb_init),
        "__MTJ_INIT_V__": fmt(mtj_init),
        "__STRIKE_SOURCE__": source,
        "__STRIKE_SINK__": sink,
        "__TSTRIKE_NS__": fmt(strike_time_ns),
        "__QFC__": fmt(q_fc),
    }


def hold_replacements(common: dict[str, str], stored_bit: int, node: str, q_fc: float, vdd: float) -> dict[str, str]:
    source, sink, polarity = adverse_strike_term(node, stored_bit)
    threshold = 0.5 * vdd
    if stored_bit == 0:
        r_mtj, mtj_init = common["_HOLD_R"], threshold * 0.35
        bl_init = threshold * 0.45
    else:
        r_mtj, mtj_init = common["_HOLD_R"], threshold * 1.15
        bl_init = threshold * 1.55
    return {
        **{k: v for k, v in common.items() if not k.startswith("_") or k.startswith("__")},
        "__R_MTJ__": r_mtj,
        "__BL_INIT_V__": fmt(bl_init),
        "__MTJ_INIT_V__": fmt(mtj_init),
        "__STRIKE_SOURCE__": source,
        "__STRIKE_SINK__": sink,
        "__QFC__": fmt(q_fc),
    }


def simulate(ngspice: str, deck: str, work: Path, tag: str) -> dict[str, float]:
    netlist = work / f"{tag}.sp"
    netlist.write_text(deck, encoding="utf-8")
    completed = subprocess.run(
        [ngspice, "-b", str(netlist)],
        cwd=work,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    log = completed.stdout + "\n" + completed.stderr
    if completed.returncode != 0:
        raise RuntimeError(log[-2500:])
    return {name.lower(): float(value) for name, value in MEASURE_RE.findall(log)}


def write_failed(values: dict[str, float], desired_bit: int, vdd: float) -> bool:
    v_bl = values.get("vbl_final", values.get("v_bl_final", 0.0))
    v_mtj = values.get("vmtj_final", values.get("v_mtj_final", 0.0))
    if desired_bit == 0:
        return v_bl > 0.05 or v_mtj > 0.5 * vdd
    return v_bl < 0.95 * vdd or v_mtj < 0.5 * vdd


def hold_failed(values: dict[str, float], stored_bit: int, vdd: float) -> bool:
    threshold = 0.5 * vdd
    v_mtj = values.get("vmtj_final", values.get("v_mtj_final", 0.0))
    v_bl = values.get("vbl_final", values.get("v_bl_final", 0.0))
    if stored_bit == 0:
        return v_mtj > threshold or v_bl > threshold
    return v_mtj < threshold or v_bl < threshold


def search_qcrit(evaluate, initial_high: float, maximum: float, tolerance: float) -> dict:
    if evaluate(0.0):
        return {"qcrit_fc": 0.0, "status": "baseline_failed"}
    if not evaluate(maximum):
        return {"qcrit_fc": maximum, "status": "not_bracketed"}
    lo, hi = 0.0, initial_high
    while not evaluate(hi):
        hi *= 2.0
        if hi >= maximum:
            return {"qcrit_fc": maximum, "status": "not_bracketed"}
    while hi - lo > tolerance:
        mid = 0.5 * (lo + hi)
        if evaluate(mid):
            lo = mid
        else:
            hi = mid
    return {"qcrit_fc": hi, "status": "bracketed"}


def run_write_case(task: dict, config: dict, model: Path, template: str, ngspice: str, mtj: dict) -> dict:
    pvt = config["conditional_pvt_corners"][task["pvt_corner"]]
    vdd = float(pvt["vdd_v"])
    common = common_replacements(config, model, mtj, task["pvt_corner"], task["tid_corner"])
    common["_R_P"] = fmt(config["cell"].get("r_p_ohm", config["cell"].get("r_p_ohm_read_proxy", 10000.0)))
    common["_R_AP"] = fmt(config["cell"].get("r_ap_ohm", config["cell"].get("r_ap_ohm_read_proxy", 20000.0)))
    common["_HOLD_R"] = fmt(config["cell"].get("hold_screen_r_mtj_ohm", 50000.0))
    source, sink, polarity = adverse_strike_term(task["node"], task["desired_bit"])
    strike = config["strike"]
    with tempfile.TemporaryDirectory(prefix="sot_write_strike_") as tmp:
        work = Path(tmp)
        counter = 0

        def evaluate(q_fc: float) -> bool:
            nonlocal counter
            counter += 1
            deck = render(
                template,
                write_replacements(common, task["desired_bit"], task["node"], task["strike_time_ns"], q_fc, vdd),
            )
            values = simulate(ngspice, deck, work, f"w{counter}")
            return write_failed(values, task["desired_bit"], vdd)

        result = search_qcrit(
            evaluate,
            float(strike["qcrit_initial_high_fc"]),
            float(strike["qcrit_max_fc"]),
            float(strike["qcrit_tolerance_fc"]),
        )
    return {**task, "strike_source": source, "strike_sink": sink, "adverse_polarity": polarity, **result}


def run_hold_case(task: dict, config: dict, model: Path, template: str, ngspice: str, mtj: dict) -> dict:
    pvt = config["conditional_pvt_corners"][task["pvt_corner"]]
    vdd = float(pvt["vdd_v"])
    common = common_replacements(config, model, mtj, task["pvt_corner"], task["tid_corner"])
    common["_R_P"] = fmt(config["cell"].get("r_p_ohm", config["cell"].get("r_p_ohm_read_proxy", 10000.0)))
    common["_R_AP"] = fmt(config["cell"].get("r_ap_ohm", config["cell"].get("r_ap_ohm_read_proxy", 20000.0)))
    common["_HOLD_R"] = fmt(config["cell"].get("hold_screen_r_mtj_ohm", 50000.0))
    source, sink, polarity = adverse_strike_term(task["node"], task["stored_bit"])
    strike = config["strike"]
    with tempfile.TemporaryDirectory(prefix="sot_hold_strike_") as tmp:
        work = Path(tmp)
        counter = 0

        def evaluate(q_fc: float) -> bool:
            nonlocal counter
            counter += 1
            deck = render(template, hold_replacements(common, task["stored_bit"], task["node"], q_fc, vdd))
            values = simulate(ngspice, deck, work, f"h{counter}")
            return hold_failed(values, task["stored_bit"], vdd)

        result = search_qcrit(
            evaluate,
            float(strike["qcrit_initial_high_fc"]),
            float(strike["qcrit_max_fc"]),
            float(strike["qcrit_tolerance_fc"]),
        )
    return {**task, "strike_source": source, "strike_sink": sink, "adverse_polarity": polarity, **result}


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--write-template", type=Path, default=DEFAULT_WRITE)
    parser.add_argument("--hold-template", type=Path, default=DEFAULT_HOLD)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 1))
    parser.add_argument("--ngspice", default=None)
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    model = (args.config.parent / config["model"]).resolve()
    mtj_path = (args.config.parent / config["mtj_parameters"]).resolve()
    mtj = json.loads(mtj_path.read_text(encoding="utf-8"))
    ngspice = resolve_ngspice(args.ngspice, ROOT)
    write_template = args.write_template.read_text(encoding="utf-8")
    hold_template = args.hold_template.read_text(encoding="utf-8")

    pvt_names = list(config["conditional_pvt_corners"])
    tid_names = list(config["tid_corners_at_14p32_krad_si"])
    strike_times = list(config["timing"]["strike_times_ns"])
    write_nodes = list(config["strike"]["write_nodes"])
    if args.quick:
        pvt_names = ["nominal"]
        tid_names = ["central"]
        strike_times = [0.16, 0.80, 1.60, 2.14]
        write_nodes = ["bl", "mtj", "sot_top"]

    write_tasks = [
        {
            "pvt_corner": pvt,
            "tid_corner": tid,
            "desired_bit": bit,
            "node": node,
            "strike_time_ns": strike_time,
        }
        for pvt in pvt_names
        for tid in tid_names
        for bit in (0, 1)
        for node in write_nodes
        for strike_time in strike_times
    ]
    hold_tasks = [
        {"pvt_corner": pvt, "tid_corner": tid, "stored_bit": bit, "node": node}
        for pvt in pvt_names
        for tid in tid_names
        for bit in (0, 1)
        for node in config["strike"]["hold_nodes"]
    ]

    write_rows: list[dict] = []
    hold_rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {
            pool.submit(run_write_case, task, config, model, write_template, ngspice, mtj): "write"
            for task in write_tasks
        }
        futures.update(
            {
                pool.submit(run_hold_case, task, config, model, hold_template, ngspice, mtj): "hold"
                for task in hold_tasks
            }
        )
        for index, future in enumerate(as_completed(futures), start=1):
            kind = futures[future]
            row = future.result()
            (write_rows if kind == "write" else hold_rows).append(row)
            if index % 20 == 0 or index == len(futures):
                print(f"completed {index}/{len(futures)} Qcrit cases", flush=True)

    write_rows.sort(key=lambda r: (r["pvt_corner"], r["tid_corner"], r["desired_bit"], r["node"], r["strike_time_ns"]))
    hold_rows.sort(key=lambda r: (r["pvt_corner"], r["tid_corner"], r["stored_bit"], r["node"]))
    bracketed_write = [float(r["qcrit_fc"]) for r in write_rows if r["status"] == "bracketed"]
    bracketed_hold = [float(r["qcrit_fc"]) for r in hold_rows if r["status"] == "bracketed"]
    if not bracketed_write or not bracketed_hold:
        raise RuntimeError("screen did not produce bracketed write and hold Qcrit values")

    worst_ratio = min(bracketed_write) / min(bracketed_hold)
    overall = {
        "method": "SOT-MRAM 1T1MTJ + SOT-channel write-window Qcrit screen",
        "write_cases": len(write_rows),
        "hold_cases": len(hold_rows),
        "minimum_write_qcrit_fc": min(bracketed_write),
        "median_write_qcrit_fc": statistics.median(bracketed_write),
        "minimum_hold_qcrit_fc": min(bracketed_hold),
        "median_hold_qcrit_fc": statistics.median(bracketed_hold),
        "min_write_over_min_hold_qcrit": worst_ratio,
        "not_bracketed_write_cases": sum(r["status"] == "not_bracketed" for r in write_rows),
        "baseline_failed_write_cases": sum(r["status"] == "baseline_failed" for r in write_rows),
        "claim_boundary": config["claim_boundary"],
        "literature_write_current_a": config["cell"]["i_write_a"],
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "write_qcrit_cases.csv", write_rows)
    write_csv(args.output_dir / "hold_qcrit_cases.csv", hold_rows)
    payload = {
        "schema_version": 1,
        "config": config,
        "resolved_model": str(model.relative_to(REPO)) if model.is_relative_to(REPO) else str(model),
        "summary": overall,
        "files": {
            "write_cases": "mram/results/write_strike_screen/write_qcrit_cases.csv",
            "hold_cases": "mram/results/write_strike_screen/hold_qcrit_cases.csv",
        },
    }
    (args.output_dir / "summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = f"""# SOT-MRAM dynamic write strike screening

Selected-path electrical vulnerability screen for the SOT write window (not absolute dynamic write BER).

- Write Qcrit cases: {len(write_rows)}
- Hold Qcrit cases: {len(hold_rows)}
- Minimum write Qcrit: {overall['minimum_write_qcrit_fc']:.6g} fC
- Minimum hold Qcrit: {overall['minimum_hold_qcrit_fc']:.6g} fC
- min(write)/min(hold): {worst_ratio:.6g}
- Write pulse anchor: {config['cell']['i_write_a']*1e6:.0f} uA @ {config['cell'].get('write_pulse_width_ns', 1.0):g} ns (参数汇总 §7.1)

Does not include address decoder, control logic, or intrinsic stochastic WER.
"""
    (args.output_dir / "README.md").write_text(report, encoding="utf-8")
    print(json.dumps(overall, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
