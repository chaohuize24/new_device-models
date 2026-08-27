#!/usr/bin/env python3
"""Run PTM32 6T SRAM write/read engineering Monte Carlo access tests.

The output probabilities are population fractions under declared mismatch
priors, conditional on deterministic PVT/TID corners.  They are not foundry
yield data and do not include temporal electrical noise.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import statistics
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "configs/ptm32_access_engineering_mc.json"
DEFAULT_WRITE_TEMPLATE = ROOT / "netlists/ptm32_access/sram6t_write_template.sp"
DEFAULT_READ_TEMPLATE = ROOT / "netlists/ptm32_access/sram6t_read_template.sp"
DEFAULT_OUTPUT = ROOT / "results/access_screen"
MEASURE_RE = re.compile(r"^([a-z0-9_]+)\s*=\s*([-+0-9.eE]+)", re.MULTILINE)


def truncated_gaussian(rng: random.Random, sigma: float, limit: float) -> float:
    while True:
        value = rng.gauss(0.0, sigma)
        if abs(value) <= limit * sigma:
            return value


def varied_positive(rng: random.Random, nominal: float, sigma: float, limit: float) -> float:
    return nominal * (1.0 + truncated_gaussian(rng, sigma, limit))


def make_sample(config: dict, pvt_name: str, tid_name: str, sample_id: int) -> dict:
    pvt_index = list(config["conditional_pvt_corners"]).index(pvt_name)
    tid_index = list(config["tid_corners_at_14p32_krad_si"]).index(tid_name)
    seed = int(config["random_seed"]) + 100_003 * pvt_index + 10_007 * tid_index + sample_id
    rng = random.Random(seed)
    stats = config["statistical_assumptions"]
    cell = config["cell"]
    periphery = config["periphery"]
    pvt = config["conditional_pvt_corners"][pvt_name]
    tid = config["tid_corners_at_14p32_krad_si"][tid_name]
    limit = float(stats["truncation_sigma"])
    width_sigma = float(stats["device_width_relative_sigma"])
    tid_n = float(tid["nmos_delta_vth_v"])
    tid_p = float(tid["pmos_signed_delta_vth_v"])

    sample: dict[str, float | int | str] = {
        "pvt_corner": pvt_name,
        "tid_corner": tid_name,
        "condition_id": f"{pvt_name}__tid_{tid_name}",
        "sample_id": sample_id,
        "seed": seed,
        "vdd_v": float(pvt["vdd_v"]),
        "temperature_c": float(pvt["temperature_c"]),
        "tid_dvn_v": tid_n,
        "tid_dvp_v": tid_p,
        "mobility_scale": float(tid["mobility_scale"]),
        "cnode_ff": varied_positive(
            rng,
            float(cell["external_node_capacitance_ff"]),
            float(stats["node_capacitance_relative_sigma"]),
            limit,
        ),
        "cbl_ff": varied_positive(
            rng,
            float(periphery["local_bitline_capacitance_ff"]),
            float(stats["bitline_capacitance_relative_sigma"]),
            limit,
        ),
        "cgbl_ff": varied_positive(
            rng,
            float(periphery["global_bitline_capacitance_ff"]),
            float(stats["bitline_capacitance_relative_sigma"]),
            limit,
        ),
    }
    for name in ("nq", "nqb", "axq", "axqb"):
        sample[f"dvth_{name}_v"] = tid_n + truncated_gaussian(
            rng, float(stats["cell_nmos_sigma_vth_v"]), limit
        )
    for name in ("pq", "pqb"):
        sample[f"dvth_{name}_v"] = tid_p + truncated_gaussian(
            rng, float(stats["cell_pmos_sigma_abs_vth_v"]), limit
        )
    for name in ("san_gbl", "san_gblb"):
        sample[f"dvth_{name}_v"] = tid_n + truncated_gaussian(
            rng, float(stats["sense_nmos_sigma_vth_v"]), limit
        )
    for name in ("sap_gbl", "sap_gblb"):
        sample[f"dvth_{name}_v"] = tid_p + truncated_gaussian(
            rng, float(stats["sense_pmos_sigma_abs_vth_v"]), limit
        )
    for name in ("muxn_d", "muxn_db", "eq", "eqg"):
        sample[f"dvth_{name}_v"] = tid_n + truncated_gaussian(
            rng, float(stats["periphery_nmos_sigma_vth_v"]), limit
        )
    for name in ("muxp_d", "muxp_db", "pre_bl", "pre_blb", "pre_gbl", "pre_gblb"):
        sample[f"dvth_{name}_v"] = tid_p + truncated_gaussian(
            rng, float(stats["periphery_pmos_sigma_abs_vth_v"]), limit
        )

    nominal_widths = {
        "nq": float(cell["pull_down_width_nm"]),
        "nqb": float(cell["pull_down_width_nm"]),
        "pq": float(cell["pull_up_width_nm"]),
        "pqb": float(cell["pull_up_width_nm"]),
        "axq": float(cell["access_width_nm"]),
        "axqb": float(cell["access_width_nm"]),
    }
    for name, nominal in nominal_widths.items():
        sample[f"w_{name}_nm"] = varied_positive(rng, nominal, width_sigma, limit)
    return sample


def fmt(value: float) -> str:
    return f"{float(value):.12g}"


def common_replacements(config: dict, model: Path, sample: dict) -> dict[str, str]:
    periphery = config["periphery"]
    timing = config["timing"]
    replacements = {
        "__MODEL_PATH__": str(model.resolve()),
        "__VDD__": fmt(sample["vdd_v"]),
        "__TEMP_C__": fmt(sample["temperature_c"]),
        "__CNODE_FF__": fmt(sample["cnode_ff"]),
        "__CBL_FF__": fmt(sample["cbl_ff"]),
        "__CGBL_FF__": fmt(sample["cgbl_ff"]),
        "__MU_SCALE__": fmt(sample["mobility_scale"]),
        "__TID_DVN__": fmt(sample["tid_dvn_v"]),
        "__TID_DVP__": fmt(sample["tid_dvp_v"]),
        "__W_AX_NOM_NM__": fmt(config["cell"]["access_width_nm"]),
        "__W_PRE_PM__": fmt(periphery["precharge_pmos_width_nm"]),
        "__W_EQ_NM__": fmt(periphery["equalizer_nmos_width_nm"]),
        "__W_MUX_NM__": fmt(periphery["mux_nmos_width_nm"]),
        "__W_MUX_PM__": fmt(periphery["mux_pmos_width_nm"]),
        "__W_SAN_NM__": fmt(periphery["sense_nmos_width_nm"]),
        "__W_SAP_PM__": fmt(periphery["sense_pmos_width_nm"]),
        "__W_SA_TAIL_NM__": fmt(periphery["sense_tail_nmos_width_nm"]),
        "__W_SA_SUP_PM__": fmt(periphery["sense_supply_pmos_width_nm"]),
        "__SAEN_LOW_NS__": fmt(timing["sense_enable_low_ns"]),
        "__SAEN_HIGH_NS__": fmt(timing["sense_enable_high_ns"]),
        "__PRE_SENSE_NS__": fmt(timing["pre_sense_sample_ns"]),
    }
    for name in ("pq", "nq", "pqb", "nqb", "axq", "axqb"):
        replacements[f"__W_{name.upper()}_NM__"] = fmt(sample[f"w_{name}_nm"])
        replacements[f"__DVTH_{name.upper()}__"] = fmt(sample[f"dvth_{name}_v"])
    for name in (
        "muxn_d", "muxn_db", "muxp_d", "muxp_db", "eq", "eqg",
        "pre_bl", "pre_blb", "pre_gbl", "pre_gblb",
        "san_gbl", "san_gblb", "sap_gbl", "sap_gblb",
    ):
        replacements[f"__DVTH_{name.upper()}__"] = fmt(sample[f"dvth_{name}_v"])
    return replacements


def render(template: str, replacements: dict[str, str]) -> str:
    for token, value in replacements.items():
        template = template.replace(token, value)
    unresolved = sorted(set(re.findall(r"__[A-Z0-9_]+__", template)))
    if unresolved:
        raise ValueError(f"unresolved template tokens: {unresolved}")
    return template


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
        raise RuntimeError(f"ngspice failed for {stem} ({proc.returncode}):\n{proc.stderr}\n{log}")
    values = {name: float(value) for name, value in MEASURE_RE.findall(log)}
    if not values:
        raise RuntimeError(f"no measurements parsed for {stem}:\n{log}")
    return values


def run_sample(
    ngspice: str,
    write_template: str,
    read_template: str,
    model: Path,
    config: dict,
    sample: dict,
) -> list[dict]:
    rows: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="ptm32_access_mc_") as tmp:
        work = Path(tmp)
        common = common_replacements(config, model, sample)
        vdd = float(sample["vdd_v"])
        for desired_bit in (0, 1):
            replacements = dict(common)
            replacements.update(
                {
                    "__DATA_V__": "0" if desired_bit == 0 else "{VDDVAL}",
                    "__DATAB_V__": "{VDDVAL}" if desired_bit == 0 else "0",
                    "__Q_INIT_V__": "{VDDVAL}" if desired_bit == 0 else "0",
                    "__QB_INIT_V__": "0" if desired_bit == 0 else "{VDDVAL}",
                }
            )
            values = simulate(
                ngspice,
                render(write_template, replacements),
                work,
                f"write{desired_bit}",
            )
            margin = (
                values["vq_final"] - values["vqb_final"]
                if desired_bit == 1
                else values["vqb_final"] - values["vq_final"]
            )
            rows.append(
                {
                    **sample,
                    "operation": "write",
                    "stored_or_desired_bit": desired_bit,
                    "decision_margin_v": margin,
                    "pre_sense_margin_v": "",
                    "operation_error": margin <= 0.0,
                    "read_error_given_correct_state": "",
                    "read_error_given_wrong_state": "",
                    "read_disturb": "",
                    "rail_margin_over_vdd": margin / vdd,
                }
            )

        for stored_bit in (0, 1):
            replacements = dict(common)
            replacements.update(
                {
                    "__Q_INIT_V__": "0" if stored_bit == 0 else "{VDDVAL}",
                    "__QB_INIT_V__": "{VDDVAL}" if stored_bit == 0 else "0",
                }
            )
            values = simulate(
                ngspice,
                render(read_template, replacements),
                work,
                f"read{stored_bit}",
            )
            decision = 1 if values["vgbl_sense"] > values["vgblb_sense"] else 0
            correct_error = decision != stored_bit
            wrong_desired = 1 - stored_bit
            wrong_error = decision != wrong_desired
            pre_margin = (
                values["vgbl_pre"] - values["vgblb_pre"]
                if stored_bit == 1
                else values["vgblb_pre"] - values["vgbl_pre"]
            )
            sense_margin = (
                values["vgbl_sense"] - values["vgblb_sense"]
                if stored_bit == 1
                else values["vgblb_sense"] - values["vgbl_sense"]
            )
            cell_margin = (
                values["vq_cell_final"] - values["vqb_cell_final"]
                if stored_bit == 1
                else values["vqb_cell_final"] - values["vq_cell_final"]
            )
            rows.append(
                {
                    **sample,
                    "operation": "read",
                    "stored_or_desired_bit": stored_bit,
                    "decision_margin_v": sense_margin,
                    "pre_sense_margin_v": pre_margin,
                    "operation_error": correct_error,
                    "read_error_given_correct_state": correct_error,
                    "read_error_given_wrong_state": wrong_error,
                    "read_disturb": cell_margin <= 0.0,
                    "rail_margin_over_vdd": sense_margin / vdd,
                }
            )
    return rows


def wilson_interval(failures: int, trials: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if trials <= 0:
        raise ValueError("trials must be positive")
    p = failures / trials
    denominator = 1.0 + z * z / trials
    center = (p + z * z / (2.0 * trials)) / denominator
    half = z * math.sqrt(p * (1.0 - p) / trials + z * z / (4.0 * trials * trials)) / denominator
    return max(0.0, center - half), min(1.0, center + half)


def summarize_probability(rows: list[dict], field: str) -> dict[str, float | int]:
    values = [bool(row[field]) for row in rows if row[field] != ""]
    failures = sum(values)
    low, high = wilson_interval(failures, len(values))
    return {
        "failures": failures,
        "trials": len(values),
        "probability": failures / len(values),
        "wilson95_low": low,
        "wilson95_high": high,
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--write-template", type=Path, default=DEFAULT_WRITE_TEMPLATE)
    parser.add_argument("--read-template", type=Path, default=DEFAULT_READ_TEMPLATE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--samples-per-condition", type=int)
    parser.add_argument("--jobs", type=int, default=min(12, os.cpu_count() or 1))
    parser.add_argument("--ngspice", default=shutil.which("ngspice") or "ngspice")
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    model = (args.config.parent / config["model"]).resolve()
    if not model.exists():
        raise FileNotFoundError(model)
    write_template = args.write_template.read_text(encoding="utf-8")
    read_template = args.read_template.read_text(encoding="utf-8")
    sample_count = args.samples_per_condition or int(config["default_samples_per_condition"])
    if sample_count < 1:
        raise ValueError("samples-per-condition must be positive")

    samples = [
        make_sample(config, pvt, tid, sample_id)
        for pvt in config["conditional_pvt_corners"]
        for tid in config["tid_corners_at_14p32_krad_si"]
        for sample_id in range(sample_count)
    ]
    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = [
            pool.submit(
                run_sample,
                args.ngspice,
                write_template,
                read_template,
                model,
                config,
                sample,
            )
            for sample in samples
        ]
        for index, future in enumerate(as_completed(futures), start=1):
            rows.extend(future.result())
            if index % max(1, sample_count) == 0 or index == len(futures):
                print(f"completed {index}/{len(futures)} mismatch samples", flush=True)
    rows.sort(key=lambda row: (row["condition_id"], row["sample_id"], row["operation"], row["stored_or_desired_bit"]))

    summaries = []
    electrical_scenarios = []
    for pvt_name in config["conditional_pvt_corners"]:
        for tid_name in config["tid_corners_at_14p32_krad_si"]:
            condition_id = f"{pvt_name}__tid_{tid_name}"
            condition_rows = [row for row in rows if row["condition_id"] == condition_id]
            writes = [row for row in condition_rows if row["operation"] == "write"]
            reads = [row for row in condition_rows if row["operation"] == "read"]
            write_stats = summarize_probability(writes, "operation_error")
            correct_stats = summarize_probability(reads, "read_error_given_correct_state")
            wrong_stats = summarize_probability(reads, "read_error_given_wrong_state")
            disturb_stats = summarize_probability(reads, "read_disturb")
            pre_margins = [float(row["pre_sense_margin_v"]) for row in reads]
            sense_margins = [float(row["decision_margin_v"]) for row in reads]
            summary_row = {
                "condition_id": condition_id,
                "pvt_corner": pvt_name,
                "tid_corner": tid_name,
                "samples": sample_count,
                "write_trials": write_stats["trials"],
                "write_failures": write_stats["failures"],
                "post_write_wrong_probability": write_stats["probability"],
                "post_write_wrong_wilson95_low": write_stats["wilson95_low"],
                "post_write_wrong_wilson95_high": write_stats["wilson95_high"],
                "read_correct_trials": correct_stats["trials"],
                "read_correct_failures": correct_stats["failures"],
                "read_error_given_correct_state": correct_stats["probability"],
                "read_correct_wilson95_low": correct_stats["wilson95_low"],
                "read_correct_wilson95_high": correct_stats["wilson95_high"],
                "read_wrong_trials": wrong_stats["trials"],
                "read_wrong_errors": wrong_stats["failures"],
                "read_error_given_wrong_state": wrong_stats["probability"],
                "read_wrong_wilson95_low": wrong_stats["wilson95_low"],
                "read_wrong_wilson95_high": wrong_stats["wilson95_high"],
                "read_disturb_failures": disturb_stats["failures"],
                "read_disturb_probability": disturb_stats["probability"],
                "minimum_pre_sense_margin_v": min(pre_margins),
                "median_pre_sense_margin_v": statistics.median(pre_margins),
                "minimum_final_sense_margin_v": min(sense_margins),
                "median_final_sense_margin_v": statistics.median(sense_margins),
                "probability_semantics": config["probability_semantics"],
                "is_foundry_pdk_result": False,
                "is_total_target_ber": False,
            }
            summaries.append(summary_row)
            electrical_scenarios.append(
                {
                    "id": f"ptm32_access_{condition_id}",
                    "post_write_wrong_probability": write_stats["probability"],
                    "read_error_given_correct_state": correct_stats["probability"],
                    "read_error_given_wrong_state": wrong_stats["probability"],
                    "source": "ngspice PTM32 6T access engineering Monte Carlo",
                    "source_condition_id": condition_id,
                    "is_ngspice_derived": True,
                    "is_total_target_ber": False,
                    "statistical_semantics": config["probability_semantics"],
                }
            )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "access_trials.csv", rows)
    write_csv(args.output_dir / "conditional_probability_summary.csv", summaries)
    scenario_payload = {
        "schema_version": 1,
        "electrical_condition_scenarios": electrical_scenarios,
        "source_config": "sram/configs/ptm32_access_engineering_mc.json",
        "model": "models/PTM_bulk/32nm_LP.pm",
        "samples_per_condition": sample_count,
        "probability_semantics": config["probability_semantics"],
        "is_foundry_pdk_result": False,
        "is_total_target_ber": False,
    }
    (args.output_dir / "electrical_condition_scenarios.json").write_text(
        json.dumps(scenario_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report = """# PTM32 6T SRAM access engineering Monte Carlo

This run measures two write directions and two stored-state read directions for every mismatch sample. The read path includes a 128-row local bitline proxy, one selected branch of a 4:1 column mux, global bitline capacitance and a clocked differential latch sense amplifier.

The probabilities below are population fractions under the declared engineering mismatch priors, conditional on each PVT/TID corner. They are not per-access temporal-noise BER, foundry yield, or target-macro confidence bounds.

| Condition | write wrong | read error given correct state | read error given wrong state | read disturb | min pre-SA margin (mV) |
|---|---:|---:|---:|---:|---:|
"""
    for row in summaries:
        report += (
            f"| {row['condition_id']} | {row['post_write_wrong_probability']:.6g} | "
            f"{row['read_error_given_correct_state']:.6g} | {row['read_error_given_wrong_state']:.6g} | "
            f"{row['read_disturb_probability']:.6g} | {1000.0*row['minimum_pre_sense_margin_v']:.3f} |\n"
        )
    report += """

Zero observed failures means only that none occurred at the reported sample count. Use the Wilson bounds in `conditional_probability_summary.csv` as finite-sample detection limits; do not interpret zero as a proven zero BER.
"""
    (args.output_dir / "README.md").write_text(report, encoding="utf-8")
    print(json.dumps(summaries, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
