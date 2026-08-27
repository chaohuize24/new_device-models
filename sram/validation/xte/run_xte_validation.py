#!/usr/bin/env python3
"""Check the spectrum-response-rate chain against published RXTE daily anchors.

The 250/day and 70/day values are published month-average rate anchors, not
literal one-day Poisson experiments.  This script therefore reports ratios and
does not manufacture count confidence intervals from those averages.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys


SRAM_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SRAM_ROOT / "src"))

from sram_check.core import CrossSectionModel, integrate_spectrum_cross_section  # noqa: E402
from sram_check.io import load_spectrum  # noqa: E402


HERE = Path(__file__).resolve().parent
BITS_PER_SSR = 1_174_405_120
SECONDS_PER_DAY = 86_400.0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reproduce the RXTE spectrum-response-rate order check."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=HERE,
        help="output directory (default: the validation/xte directory)",
    )
    return parser


def load_response() -> CrossSectionModel:
    path = HERE / "response/hm628128_proton_response_dense.csv"
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    return CrossSectionModel(
        kind="table",
        variable="proton_energy_mev",
        normalization="per_bit",
        source="Poivey et al. 2004 Figure 8; independent ground-test datasets",
        x=tuple(float(row["proton_energy_mev"]) for row in rows),
        sigma=tuple(float(row["sigma_nominal_cm2_per_bit"]) for row in rows),
        sigma_low=tuple(float(row["sigma_envelope_low_cm2_per_bit"]) for row in rows),
        sigma_high=tuple(float(row["sigma_envelope_high_cm2_per_bit"]) for row in rows),
        below_range="zero",
        above_range="hold",
    )


def main() -> int:
    args = build_parser().parse_args()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    response = load_response()
    cases = [
        {
            "case": "RXTE_1996_07",
            "spectrum": HERE / "1996/average_LET_proton_and_ion_spectra.txt",
            "observed_daily_anchor": 250.0,
            "environment": "573 km, 23 deg, AP-8 MIN, 200 mil Al",
        },
        {
            "case": "RXTE_2002_07",
            "spectrum": HERE / "2002/average_LET_proton_and_ion_spectra.txt",
            "observed_daily_anchor": 70.0,
            "environment": "520 km, 23 deg, AP-8 MAX, 200 mil Al",
        },
    ]
    output = []
    for case in cases:
        spectrum = load_spectrum(
            {
                "type": "spenvis_proton_text",
                "path": str(case["spectrum"]),
                "solid_angle_sr": 12.566370614359172,
            },
            HERE,
        )
        integrated = integrate_spectrum_cross_section(spectrum, response)
        predicted = integrated.rate_per_normalization_s * BITS_PER_SSR * SECONDS_PER_DAY
        low = integrated.rate_low_per_normalization_s * BITS_PER_SSR * SECONDS_PER_DAY
        high = integrated.rate_high_per_normalization_s * BITS_PER_SSR * SECONDS_PER_DAY
        output.append(
            {
                "case": case["case"],
                "environment": case["environment"],
                "published_month_average_upsets_per_ssr_day": case["observed_daily_anchor"],
                "predicted_upsets_per_ssr_day": predicted,
                "response_envelope_low": low,
                "response_envelope_high": high,
                "predicted_over_published": predicted / case["observed_daily_anchor"],
                "within_one_order_of_magnitude": 0.1 <= predicted / case["observed_daily_anchor"] <= 10.0,
            }
        )

    with (output_dir / "validation_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(output[0]))
        writer.writeheader()
        writer.writerows(output)
    (output_dir / "validation_summary.json").write_text(
        json.dumps(
            {
                "claim": "independent order-of-magnitude check of spectrum-response-rate integration",
                "target_device_validation": False,
                "daily_anchor_semantics": "published month-average daily rates; no fabricated Poisson count interval",
                "results": output,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    for row in output:
        print(f"{row['case']}: predicted/published={row['predicted_over_published']:.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
