#!/usr/bin/env python3
"""Run HI/proton read-window delivery for fab_led_2024 electrical proxy.

Does not overwrite the §7.1 default Qcrit/rate tables. Writes parallel
results under results/*_fab_led_2024.* and a comparison JSON.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
NGSPICE_DEFAULT = (
    "C:/Users/思源/OneDrive/Desktop/太空计算课题组/Spice64/bin/ngspice_con.exe"
)


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, cwd=ROOT)


def read_rate_table(path: Path) -> dict[str, dict[str, float]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    out: dict[str, dict[str, float]] = {}
    for row in rows:
        level = row["level"]
        if "probability_per_active_bit_read" in row:
            out[level] = {
                "probability_per_active_bit_read": float(row["probability_per_active_bit_read"]),
                "rate_per_bit_s": float(row["heavy_ion_set_rate_per_continuously_sensitive_bit_s"]),
            }
        else:
            out[level] = {
                "probability_lower_bound": float(row["proton_read_error_probability_lower_bound"]),
                "probability_nominal": float(row["proton_read_error_probability_nominal"]),
                "rate_per_bit_s": float(row["proton_event_rate_per_active_read_bit_s"]),
            }
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=64)
    parser.add_argument("--ngspice", default=NGSPICE_DEFAULT)
    parser.add_argument("--skip-characterize", action="store_true")
    args = parser.parse_args()
    py = sys.executable
    pipeline = SCRIPTS / "sot_mram_heavy_ion_pipeline.py"
    proton = SCRIPTS / "run_mram_proton_read_integration.py"

    qcrit = "results/mram_joint_qcrit_samples_fab_led_2024.tsv"
    hi_xs = "results/mram_heavy_ion_cross_section_fab_led_2024.tsv"
    hi_rate = "results/mram_spenvis_heavy_ion_rate_fab_led_2024.tsv"
    p_xs = "results/mram_proton_cross_section_fab_led_2024.tsv"
    p_rate = "results/mram_spenvis_proton_rate_fab_led_2024.tsv"
    p_sum = "results/mram_proton_read_summary_fab_led_2024.json"

    if not args.skip_characterize:
        run(
            [
                py,
                str(pipeline),
                "characterize",
                "--ngspice",
                args.ngspice,
                "--netlist",
                "sot_mram_hierarchical_senseamp_fab_led_2024.cir",
                "--samples",
                str(args.samples),
                "--sa-times-ns",
                "2.05,2.15,2.25,2.35,2.42",
                "--output",
                qcrit,
            ]
        )

    run(
        [
            py,
            str(pipeline),
            "cross-section",
            "--qcrit-input",
            qcrit,
            "--heavy-ion-output",
            hi_xs,
            "--rate-output",
            hi_rate,
        ]
    )
    run(
        [
            py,
            str(proton),
            "--qcrit",
            qcrit,
            "--cross-section-out",
            p_xs,
            "--rate-out",
            p_rate,
            "--summary-out",
            p_sum,
        ]
    )

    hi_fab = read_rate_table(ROOT / hi_rate)
    p_fab = read_rate_table(ROOT / p_rate)
    hi_71 = read_rate_table(ROOT / "results/mram_spenvis_heavy_ion_rate.tsv")
    p_71 = read_rate_table(ROOT / "results/mram_spenvis_proton_rate.tsv")

    comparison = {
        "schema_version": 1,
        "workpoint": "fab_led_2024",
        "netlist": "sot_mram_hierarchical_senseamp_fab_led_2024.cir",
        "electrical": {
            "R_P_ohm": 10890.0,
            "R_AP_ohm": 23849.1,
            "R_REF_ohm": 16110.0,
            "TMR_percent": 119.0,
            "source": "Yang IEEE EDL 2024 / arXiv:2404.09125",
        },
        "samples_per_level": args.samples,
        "read_window_ns": 0.72,
        "heavy_ion_probability_per_active_bit_read": {
            level: hi_fab[level]["probability_per_active_bit_read"] for level in sorted(hi_fab)
        },
        "proton_probability_lower_bound": {
            level: p_fab[level]["probability_lower_bound"] for level in sorted(p_fab)
        },
        "proton_probability_nominal": {
            level: p_fab[level]["probability_nominal"] for level in sorted(p_fab)
        },
        "vs_general_sot_7_1": {
            "heavy_ion_nominal_fab": hi_fab["nominal"]["probability_per_active_bit_read"],
            "heavy_ion_nominal_7_1": hi_71["nominal"]["probability_per_active_bit_read"],
            "heavy_ion_nominal_ratio_fab_over_7_1": (
                hi_fab["nominal"]["probability_per_active_bit_read"]
                / hi_71["nominal"]["probability_per_active_bit_read"]
            ),
            "proton_lower_bound_nominal_fab": p_fab["nominal"]["probability_lower_bound"],
            "proton_lower_bound_nominal_7_1": p_71["nominal"]["probability_lower_bound"],
            "proton_lower_bound_nominal_ratio_fab_over_7_1": (
                p_fab["nominal"]["probability_lower_bound"]
                / p_71["nominal"]["probability_lower_bound"]
            ),
        },
        "claim": (
            "fab_led_2024 read-window rates use measured R/TMR with the same RPP/SPENVIS chain; "
            "default delivery remains general_sot_7_1 unless explicitly switched"
        ),
        "files": {
            "qcrit": qcrit,
            "heavy_ion_cross_section": hi_xs,
            "heavy_ion_rate": hi_rate,
            "proton_cross_section": p_xs,
            "proton_rate": p_rate,
            "proton_summary": p_sum,
        },
    }
    out = ROOT / "results/fab_led_2024_read_delivery_comparison.json"
    out.write_text(json.dumps(comparison, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(comparison["vs_general_sot_7_1"], ensure_ascii=False, indent=2))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
