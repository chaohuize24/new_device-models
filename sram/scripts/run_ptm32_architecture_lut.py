#!/usr/bin/env python3
"""Generate a pre-layout SRAM latency/energy/area architecture LUT.

ngspice is run only for unique selected electrical paths defined by local
bitline depth, column-mux fan-in and PVT/TID. Total rows and physical columns
are then expanded analytically because they change capacity, output width,
peripheral counts, word energy and area, not the already isolated selected
path in this segmented proxy.
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
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "configs/ptm32_architecture_lut.json"
DEFAULT_READ = ROOT / "netlists/ptm32_arch_lut/sram6t_read_lut_template.sp"
DEFAULT_WRITE = ROOT / "netlists/ptm32_arch_lut/sram6t_write_lut_template.sp"
DEFAULT_OUTPUT = ROOT / "results/architecture_lut"
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


def simulate(ngspice: str, deck: str, stem: str) -> dict[str, float]:
    with tempfile.TemporaryDirectory(prefix="ptm32_arch_lut_") as tmp:
        work = Path(tmp)
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
        return values


def path_replacements(config: dict, model: Path, local_rows: int, mux: int, pvt_name: str, tid_name: str) -> dict[str, str]:
    cell = config["cell"]
    periphery = config["periphery"]
    scaling = config["parasitic_scaling"]
    pvt = config["conditional_pvt_corners"][pvt_name]
    tid = config["tid_corners_at_14p32_krad_si"][tid_name]
    cbl_ff = float(scaling["local_bitline_fixed_ff"]) + local_rows * float(scaling["local_bitline_per_row_ff"])
    cgbl_ff = float(scaling["global_bitline_fixed_ff"]) + mux * float(scaling["global_bitline_per_mux_input_ff"])
    return {
        "__MODEL_PATH__": str(model.resolve()),
        "__VDD__": fmt(pvt["vdd_v"]),
        "__TEMP_C__": fmt(pvt["temperature_c"]),
        "__CNODE_FF__": fmt(cell["external_node_capacitance_ff"]),
        "__CBL_FF__": fmt(cbl_ff),
        "__CGBL_FF__": fmt(cgbl_ff),
        "__MU_SCALE__": fmt(tid["mobility_scale"]),
        "__TID_DVN__": fmt(tid["nmos_delta_vth_v"]),
        "__TID_DVP__": fmt(tid["pmos_signed_delta_vth_v"]),
        "__RON_OHM__": fmt(periphery["mux_switch_ron_ohm"]),
        "__W_PQ_NM__": fmt(cell["pull_up_width_nm"]),
        "__W_PQB_NM__": fmt(cell["pull_up_width_nm"]),
        "__W_NQ_NM__": fmt(cell["pull_down_width_nm"]),
        "__W_NQB_NM__": fmt(cell["pull_down_width_nm"]),
        "__W_AXQ_NM__": fmt(cell["access_width_nm"]),
        "__W_AXQB_NM__": fmt(cell["access_width_nm"]),
        "__W_PRE_PM__": fmt(periphery["precharge_pmos_width_nm"]),
        "__W_EQ_NM__": fmt(periphery["equalizer_nmos_width_nm"]),
        "__W_SAN_NM__": fmt(periphery["sense_nmos_width_nm"]),
        "__W_SAP_PM__": fmt(periphery["sense_pmos_width_nm"]),
        "__W_SA_TAIL_NM__": fmt(periphery["sense_tail_nmos_width_nm"]),
        "__W_SA_SUP_PM__": fmt(periphery["sense_supply_pmos_width_nm"]),
    }


def run_trial(task: dict, config: dict, model: Path, read_template: str, write_template: str, ngspice: str) -> dict:
    common = path_replacements(
        config, model, task["local_rows"], task["mux"], task["pvt_corner"], task["tid_corner"]
    )
    bit = task["bit"]
    replacements = dict(common)
    if task["operation"] == "read":
        replacements.update({
            "__Q_INIT_V__": "0" if bit == 0 else "{VDDVAL}",
            "__QB_INIT_V__": "{VDDVAL}" if bit == 0 else "0",
            "__READ_LOW_NODE__": "gbl" if bit == 0 else "gblb",
        })
        values = simulate(ngspice, render(read_template, replacements), f"read_{bit}")
        required = {"read_latency", "vgbl_pre", "vgblb_pre", "vgbl_sense", "vgblb_sense", "vq_final", "vqb_final", "access_energy"}
        missing = required - values.keys()
        if missing:
            raise RuntimeError(f"read measurement failure for {task}: {sorted(missing)}")
        decision = 1 if values["vgbl_sense"] > values["vgblb_sense"] else 0
        pre_margin = values["vgblb_pre"] - values["vgbl_pre"] if bit == 0 else values["vgbl_pre"] - values["vgblb_pre"]
        final_margin = values["vgblb_sense"] - values["vgbl_sense"] if bit == 0 else values["vgbl_sense"] - values["vgblb_sense"]
        cell_margin = values["vqb_final"] - values["vq_final"] if bit == 0 else values["vq_final"] - values["vqb_final"]
        correct = decision == bit and cell_margin > 0.0 and final_margin > 0.0
        latency_s = values["read_latency"]
    else:
        replacements.update({
            "__DATA_V__": "0" if bit == 0 else "{VDDVAL}",
            "__DATAB_V__": "{VDDVAL}" if bit == 0 else "0",
            "__Q_INIT_V__": "{VDDVAL}" if bit == 0 else "0",
            "__QB_INIT_V__": "0" if bit == 0 else "{VDDVAL}",
            "__WRITE_EDGE__": "FALL" if bit == 0 else "RISE",
        })
        values = simulate(ngspice, render(write_template, replacements), f"write_{bit}")
        required = {"write_latency", "vq_final", "vqb_final", "access_energy"}
        missing = required - values.keys()
        if missing:
            raise RuntimeError(f"write measurement failure for {task}: {sorted(missing)}")
        cell_margin = values["vqb_final"] - values["vq_final"] if bit == 0 else values["vq_final"] - values["vqb_final"]
        pre_margin = ""
        final_margin = cell_margin
        correct = cell_margin > 0.0
        latency_s = values["write_latency"]
    if not math.isfinite(values["access_energy"]) or values["access_energy"] <= 0.0:
        raise RuntimeError(f"non-positive access energy for {task}: {values['access_energy']}")
    return {
        **task,
        "vdd_v": float(config["conditional_pvt_corners"][task["pvt_corner"]]["vdd_v"]),
        "temperature_c": float(config["conditional_pvt_corners"][task["pvt_corner"]]["temperature_c"]),
        "cbl_ff": float(common["__CBL_FF__"]),
        "cgbl_ff": float(common["__CGBL_FF__"]),
        "latency_s": latency_s,
        "access_energy_j": values["access_energy"],
        "pre_sense_margin_v": pre_margin,
        "final_margin_v": final_margin,
        "operation_correct": correct,
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def aggregate_paths(trials: list[dict], config: dict) -> list[dict]:
    grouped: dict[tuple, list[dict]] = {}
    for row in trials:
        key = (row["local_rows"], row["mux"], row["pvt_corner"], row["tid_corner"])
        grouped.setdefault(key, []).append(row)
    summaries = []
    timing = config["timing"]
    for (local_rows, mux, pvt_corner, tid_corner), rows in sorted(grouped.items()):
        reads = [row for row in rows if row["operation"] == "read"]
        writes = [row for row in rows if row["operation"] == "write"]
        if len(reads) != 2 or len(writes) != 2:
            raise ValueError("each path requires read0/read1/write0/write1")
        read_latency = max(float(row["latency_s"]) for row in reads)
        write_latency = max(float(row["latency_s"]) for row in writes)
        cycle_proxy = (
            float(timing["wordline_rise_ns"]) * 1e-9
            + max(read_latency, write_latency)
            + float(timing["cycle_recovery_margin_ns"]) * 1e-9
        )
        summaries.append({
            "path_id": f"r{local_rows}_m{mux}_{pvt_corner}__tid_{tid_corner}",
            "rows_per_local_bitline": local_rows,
            "column_mux_ratio": mux,
            "pvt_corner": pvt_corner,
            "tid_model_corner": tid_corner,
            "vdd_v": reads[0]["vdd_v"],
            "temperature_c": reads[0]["temperature_c"],
            "tid_krad_si": 14.32,
            "local_bitline_capacitance_ff": reads[0]["cbl_ff"],
            "global_bitline_capacitance_ff": reads[0]["cgbl_ff"],
            "read_latency_s": read_latency,
            "write_latency_s": write_latency,
            "selected_read_path_energy_j": sum(float(row["access_energy_j"]) for row in reads) / 2.0,
            "selected_write_path_energy_j": sum(float(row["access_energy_j"]) for row in writes) / 2.0,
            "minimum_pre_sense_margin_v": min(float(row["pre_sense_margin_v"]) for row in reads),
            "minimum_final_read_margin_v": min(float(row["final_margin_v"]) for row in reads),
            "minimum_final_write_margin_v": min(float(row["final_margin_v"]) for row in writes),
            "read_correct_both_values": all(row["operation_correct"] for row in reads),
            "write_correct_both_values": all(row["operation_correct"] for row in writes),
            "timing_proxy_cycle_s": cycle_proxy,
            "timing_proxy_max_frequency_hz": 1.0 / cycle_proxy,
            "configured_500mhz_feasible": cycle_proxy <= float(timing["configured_cycle_time_ns"]) * 1e-9,
            "is_stress_not_a_fit": tid_corner == "stress_not_a_fit",
        })
    return summaries


def area_components(config: dict, total_rows: int, physical_columns: int, local_rows: int, mux: int) -> dict[str, float]:
    area = config["area_proxy"]
    cell_area = float(area["cell_area_um2"])
    capacity = total_rows * physical_columns
    segments = total_rows // local_rows
    outputs = physical_columns // mux
    core = capacity * cell_area
    sa = outputs * float(area["sense_amp_cell_equivalents_per_output_bit"]) * cell_area
    precharge = physical_columns * float(area["precharge_cell_equivalents_per_physical_column"]) * cell_area
    column_mux = physical_columns * float(area["column_mux_cell_equivalents_per_physical_column"]) * cell_area
    segment = physical_columns * segments * float(area["segment_select_cell_equivalents_per_segment_column"]) * cell_area
    decoder = total_rows * float(area["row_decoder_cell_equivalents_per_row"]) * cell_area
    subtotal = core + sa + precharge + column_mux + segment + decoder
    total = subtotal * float(area["routing_and_control_overhead_factor"])
    return {
        "core_area_um2": core,
        "sense_amp_area_um2": sa,
        "precharge_area_um2": precharge,
        "column_mux_area_um2": column_mux,
        "segment_select_area_um2": segment,
        "row_decoder_area_um2": decoder,
        "area_mm2_proxy": total * 1e-6,
        "periphery_area_fraction": 1.0 - core / total,
    }


def expand_architecture_lut(path_rows: list[dict], config: dict) -> list[dict]:
    grid = config["architecture_grid"]
    lookup = {
        (row["rows_per_local_bitline"], row["column_mux_ratio"], row["pvt_corner"], row["tid_model_corner"]): row
        for row in path_rows
    }
    result = []
    for total_rows in grid["total_rows"]:
        for physical_columns in grid["physical_columns"]:
            for local_rows in grid["rows_per_local_bitline"]:
                if total_rows % local_rows:
                    continue
                for mux in grid["column_mux_ratio"]:
                    if physical_columns % mux:
                        continue
                    for pvt_corner in config["conditional_pvt_corners"]:
                        for tid_corner in config["tid_corners_at_14p32_krad_si"]:
                            path = lookup[(local_rows, mux, pvt_corner, tid_corner)]
                            word_bits = physical_columns // mux
                            cbl_f = path["local_bitline_capacitance_ff"] * 1e-15
                            extra_local_energy = max(0, physical_columns - word_bits) * cbl_f * path["vdd_v"] ** 2
                            read_word_energy = path["selected_read_path_energy_j"] * word_bits + extra_local_energy
                            write_word_energy = path["selected_write_path_energy_j"] * word_bits
                            area = area_components(config, total_rows, physical_columns, local_rows, mux)
                            feasible = bool(path["read_correct_both_values"] and path["write_correct_both_values"])
                            result.append({
                                "architecture_id": f"sram_r{total_rows}_c{physical_columns}_lr{local_rows}_m{mux}_{pvt_corner}__tid_{tid_corner}",
                                "total_rows": total_rows,
                                "physical_columns": physical_columns,
                                "capacity_bits": total_rows * physical_columns,
                                "rows_per_local_bitline": local_rows,
                                "segments_per_column": total_rows // local_rows,
                                "column_mux_ratio": mux,
                                "output_word_bits": word_bits,
                                "banks": int(grid["banks"]),
                                "pvt_corner": pvt_corner,
                                "tid_model_corner": tid_corner,
                                "vdd_v": path["vdd_v"],
                                "temperature_c": path["temperature_c"],
                                "tid_krad_si": path["tid_krad_si"],
                                "local_bitline_capacitance_ff": path["local_bitline_capacitance_ff"],
                                "global_bitline_capacitance_ff": path["global_bitline_capacitance_ff"],
                                "read_latency_s": path["read_latency_s"],
                                "write_latency_s": path["write_latency_s"],
                                "read_energy_per_word_j": read_word_energy,
                                "write_energy_per_word_j": write_word_energy,
                                "read_energy_per_output_bit_j": read_word_energy / word_bits,
                                "write_energy_per_output_bit_j": write_word_energy / word_bits,
                                "timing_proxy_cycle_s": path["timing_proxy_cycle_s"],
                                "timing_proxy_max_frequency_hz": path["timing_proxy_max_frequency_hz"],
                                "configured_500mhz_feasible": path["configured_500mhz_feasible"],
                                "minimum_pre_sense_margin_v": path["minimum_pre_sense_margin_v"],
                                "minimum_final_read_margin_v": path["minimum_final_read_margin_v"],
                                "minimum_final_write_margin_v": path["minimum_final_write_margin_v"],
                                **area,
                                "electrical_access_feasible": feasible,
                                "search_eligible": feasible and not path["is_stress_not_a_fit"],
                                "performance_grade": "engineering_envelope",
                                "area_grade": "engineering_envelope",
                                "absolute_target_macro_valid": False,
                            })
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--read-template", type=Path, default=DEFAULT_READ)
    parser.add_argument("--write-template", type=Path, default=DEFAULT_WRITE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--ngspice", default=shutil.which("ngspice") or "ngspice")
    parser.add_argument("--jobs", type=int, default=min(12, os.cpu_count() or 1))
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    model = (args.config.parent / config["model"]).resolve()
    if not model.exists():
        raise FileNotFoundError(model)
    read_template = args.read_template.read_text(encoding="utf-8")
    write_template = args.write_template.read_text(encoding="utf-8")
    grid = config["architecture_grid"]
    tasks = [
        {"local_rows": local_rows, "mux": mux, "pvt_corner": pvt, "tid_corner": tid, "operation": operation, "bit": bit}
        for local_rows in grid["rows_per_local_bitline"]
        for mux in grid["column_mux_ratio"]
        for pvt in config["conditional_pvt_corners"]
        for tid in config["tid_corners_at_14p32_krad_si"]
        for operation in ("read", "write")
        for bit in (0, 1)
    ]
    trials = []
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = [pool.submit(run_trial, task, config, model, read_template, write_template, args.ngspice) for task in tasks]
        for index, future in enumerate(as_completed(futures), start=1):
            trials.append(future.result())
            if index % 120 == 0 or index == len(futures):
                print(f"completed {index}/{len(futures)} ngspice access trials", flush=True)
    trials.sort(key=lambda row: (row["local_rows"], row["mux"], row["pvt_corner"], row["tid_corner"], row["operation"], row["bit"]))
    path_rows = aggregate_paths(trials, config)
    lut_rows = expand_architecture_lut(path_rows, config)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "electrical_path_lut.csv", path_rows)
    write_csv(args.output_dir / "architecture_performance_lut.csv", lut_rows)
    summary = {
        "schema_version": 1,
        "claim_scope": config["scope"],
        "ngspice_trials": len(trials),
        "unique_electrical_paths": len(path_rows),
        "architecture_rows": len(lut_rows),
        "search_eligible_rows": sum(bool(row["search_eligible"]) for row in lut_rows),
        "all_accesses_functional": all(bool(row["electrical_access_feasible"]) for row in lut_rows),
        "ranges": {
            "read_latency_s": [min(row["read_latency_s"] for row in lut_rows), max(row["read_latency_s"] for row in lut_rows)],
            "write_latency_s": [min(row["write_latency_s"] for row in lut_rows), max(row["write_latency_s"] for row in lut_rows)],
            "read_energy_per_word_j": [min(row["read_energy_per_word_j"] for row in lut_rows), max(row["read_energy_per_word_j"] for row in lut_rows)],
            "write_energy_per_word_j": [min(row["write_energy_per_word_j"] for row in lut_rows), max(row["write_energy_per_word_j"] for row in lut_rows)],
            "area_mm2_proxy": [min(row["area_mm2_proxy"] for row in lut_rows), max(row["area_mm2_proxy"] for row in lut_rows)],
            "timing_proxy_max_frequency_hz": [min(row["timing_proxy_max_frequency_hz"] for row in lut_rows), max(row["timing_proxy_max_frequency_hz"] for row in lut_rows)],
        },
        "validity": {
            "latency_energy": "PTM32 LP + declared pre-layout parasitic scaling; no foundry PDK/PEX/decoder/global-wire extraction",
            "area": config["area_proxy"]["status"],
            "tid": "14.32 krad(Si) central/conservative engineering assumptions plus stress_not_a_fit; not measured 32 nm macro degradation",
            "absolute_target_macro_valid": False,
            "mbu_included": False,
        },
        "source_config": "sram/configs/ptm32_architecture_lut.json",
        "model": "models/PTM_bulk/32nm_LP.pm",
    }
    (args.output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
