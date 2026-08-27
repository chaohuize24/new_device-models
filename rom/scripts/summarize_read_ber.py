#!/usr/bin/env python3
"""Convert per-active-bit radiation probability into access/row-read BER.

This is a width aggregation only.  Changing row depth, segment depth or column
mux changes the circuit/Qcrit and therefore requires re-running characterize.
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path


def any_error_probability(p_bit: float, decisions: int) -> float:
    if decisions <= 0:
        raise ValueError("decisions must be positive")
    return -math.expm1(decisions * math.log1p(-p_bit))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rate-input", default="results/rom_spenvis_heavy_ion_rate.tsv")
    parser.add_argument("--physical-columns", type=int, default=128)
    parser.add_argument("--column-mux-ratio", type=int, default=4)
    parser.add_argument("--total-rows", type=int, default=2048)
    parser.add_argument("--segment-rows", type=int, default=256)
    parser.add_argument("--word-widths", default="8,16,32,64,128,256,512")
    parser.add_argument("--output", default="results/rom_read_ber_by_width.tsv")
    args = parser.parse_args()

    if args.physical_columns % args.column_mux_ratio:
        raise ValueError("physical_columns must be divisible by column_mux_ratio")
    base = Path(__file__).resolve().parents[1]
    with (base / args.rate_input).open(newline="", encoding="utf-8") as handle:
        rates = list(csv.DictReader(handle, delimiter="\t"))
    widths = [int(x) for x in args.word_widths.split(",") if x.strip()]
    simultaneous = args.physical_columns // args.column_mux_ratio
    rows: list[dict] = []
    for rate in rates:
        p = float(rate["probability_per_active_bit_read"])
        p_lo = float(rate["probability_ci95_bootstrap_low"])
        p_hi = float(rate["probability_ci95_bootstrap_high"])
        for width in widths:
            rows.append({
                "level": rate["level"],
                "total_rows": args.total_rows,
                "segment_rows": args.segment_rows,
                "physical_columns": args.physical_columns,
                "column_mux_ratio": args.column_mux_ratio,
                "simultaneous_output_bits_per_cycle": simultaneous,
                "logical_bits_covered": width,
                "minimum_column_select_cycles": math.ceil(width / simultaneous),
                "probability_any_radiation_read_error": any_error_probability(p, width),
                "within_envelope_bootstrap_ci95_low": any_error_probability(p_lo, width),
                "within_envelope_bootstrap_ci95_high": any_error_probability(p_hi, width),
                "scope": (
                    "heavy-ion read-window SET only; Qcrit input must have been characterized "
                    f"for {args.total_rows}x{args.physical_columns}, "
                    f"{args.segment_rows}-row segments, {args.column_mux_ratio}:1 mux"
                ),
            })
    output = (base / args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} rows to {output}")


if __name__ == "__main__":
    main()
