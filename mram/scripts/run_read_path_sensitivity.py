#!/usr/bin/env python3
"""Evaluate read-path parameter variants against functional criteria and record margins.

Documents the gap between literature MTJ parameters and the scaled read proxy used
in v1 Qcrit characterization.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from sweep_sot_mram_spice_response import resolve_ngspice, run_corner, set_param


def set_grouped_param(source: str, name: str, value: str | float) -> str:
    pattern = re.compile(rf"(\b{re.escape(name)}=)([^\s]+)", re.IGNORECASE)
    updated, count = pattern.subn(rf"\g<1>{value}", source, count=1)
    if count != 1:
        raise RuntimeError(f"parameter {name} was not found exactly once")
    return updated


def spice_ohm(value: float) -> str:
    if value >= 1000.0:
        scaled = value / 1000.0
        text = f"{scaled:.12g}"
        return f"{text}k" if "." not in text else f"{scaled:.6g}k"
    return f"{value:.12g}"


def set_netlist_variant(template: str, variant: dict) -> str:
    source = set_grouped_param(template, "R_P", spice_ohm(variant["r_p_ohm"]))
    source = set_grouped_param(source, "R_AP", spice_ohm(variant["r_ap_ohm"]))
    source = set_grouped_param(source, "R_REF", spice_ohm(variant["r_ref_ohm"]))
    source = set_grouped_param(source, "C_MTJ", f"{variant['c_mtj_fF']}f")
    source = set_grouped_param(source, "WN", f"{variant['access_width_nm']}n")
    tsense_ns = float(variant["sa_enable_ns"]) + float(variant["sense_delay_ns"])
    tstop_ns = max(2.4, tsense_ns + 0.2)
    source = set_grouped_param(source, "TSAEN", f"{variant['sa_enable_ns']}n")
    source = set_grouped_param(source, "TSENSE", f"{tsense_ns}n")
    source = re.sub(r"(\.tran\s+\S+\s+)([\d.]+n)", rf"\g<1>{tstop_ns}n", source, count=1)
    return source


def nominal_read_check(source: str, circuit_dir: Path, ngspice: str, variant: dict) -> dict:
    measures = run_corner(
        source,
        circuit_dir,
        ngspice,
        n_present=32.0,
        parasitic_scale=1.0,
        dvth_sa_mv=0.0,
        sa_enable_ns=float(variant["sa_enable_ns"]),
        sense_delay_ns=float(variant["sense_delay_ns"]),
    )
    read0_ok = measures.get("read0_ok", float(measures["out0_sense"] < 0.5))
    read1_ok = measures.get("read1_ok", float(measures["out1_sense"] > 0.5))
    min_diff = min(measures["d0_diff_dev"], measures["d1_diff_dev"])
    return {
        **measures,
        "read0_ok": read0_ok,
        "read1_ok": read1_ok,
        "min_diff_dev_v": min_diff,
        "functional_pass": bool(read0_ok and read1_ok and min_diff >= 0.005),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variants", default="configs/read_path_variants.json")
    parser.add_argument("--netlist", default="sot_mram_hierarchical_senseamp.cir")
    parser.add_argument("--ngspice", default=None)
    parser.add_argument("--output", default="results/read_path_sensitivity.tsv")
    parser.add_argument("--summary-out", default="results/read_path_sensitivity_summary.json")
    args = parser.parse_args()

    ngspice = resolve_ngspice(args.ngspice, ROOT)
    circuit_dir = ROOT / "netlists"
    template = (circuit_dir / args.netlist).read_text(encoding="utf-8")
    cfg = json.loads((ROOT / args.variants).read_text(encoding="utf-8"))
    criteria = cfg["functional_criteria"]

    rows: list[dict] = []
    for variant_id, variant in cfg["variants"].items():
        netlist = set_netlist_variant(template, variant)
        result = nominal_read_check(netlist, circuit_dir, ngspice, variant)
        rows.append(
            {
                "variant_id": variant_id,
                "label": variant["label"],
                "literature_basis": variant["literature_basis"],
                "r_p_ohm": variant["r_p_ohm"],
                "r_ap_ohm": variant["r_ap_ohm"],
                "c_mtj_fF": variant["c_mtj_fF"],
                "access_width_nm": variant["access_width_nm"],
                "sa_enable_ns": variant["sa_enable_ns"],
                "sense_delay_ns": variant["sense_delay_ns"],
                "read_window_ns": variant["read_window_ns"],
                "d0_diff_dev_v": result["d0_diff_dev"],
                "d1_diff_dev_v": result["d1_diff_dev"],
                "min_diff_dev_v": result["min_diff_dev_v"],
                "read0_ok": int(result["read0_ok"]),
                "read1_ok": int(result["read1_ok"]),
                "functional_pass": int(result["functional_pass"]),
            }
        )

    output = (ROOT / args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    recommended = next((r for r in rows if r["variant_id"] == "general_sot_7_1" and r["functional_pass"]), None)
    if recommended is None:
        recommended = next((r for r in rows if r["functional_pass"]), None)
    literature_pass = [
        r["variant_id"]
        for r in rows
        if r["variant_id"]
        in ("optimized_nature_7_2", "array_tuned_7_1", "fab_led_2024", "fab_led_2024_array_tuned")
        and r["functional_pass"]
    ]
    summary = {
        "schema_version": 2,
        "parameter_source": "SOT-MRAM辐照错误建模参数汇总.md + Yang IEEE EDL 2024",
        "variants_tested": len(rows),
        "functional_pass_count": sum(r["functional_pass"] for r in rows),
        "recommended_variant_for_qcrit": recommended["variant_id"] if recommended else "general_sot_7_1",
        "literature_aligned_functional_variants": literature_pass,
        "v1_baseline": "general_sot_7_1",
        "fab_anchor": "fab_led_2024",
        "legacy_qcrit_baseline": "legacy_scaled_proxy",
        "claim": (
            "general_sot_7_1 remains the HI/proton Qcrit baseline; "
            "fab_led_2024 is the 300 mm measured electrical/write dual-track anchor"
        ),
        "rows": rows,
    }
    (ROOT / args.summary_out).resolve().write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({r["variant_id"]: r["functional_pass"] for r in rows}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
