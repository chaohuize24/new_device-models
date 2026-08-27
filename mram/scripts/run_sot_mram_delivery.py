#!/usr/bin/env python3
"""Run the full SOT-MRAM heavy-ion read-window delivery chain."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=64)
    parser.add_argument("--ngspice", default=None)
    parser.add_argument("--skip-characterize", action="store_true")
    args = parser.parse_args()
    py = sys.executable
    pipeline = SCRIPTS / "sot_mram_heavy_ion_pipeline.py"
    common = [py, str(pipeline)]
    if args.ngspice:
        common.extend(["--ngspice", args.ngspice])
    if not args.skip_characterize:
        run(common + ["characterize", "--samples", str(args.samples)])
    run(common + ["cross-section"])
    run([py, str(SCRIPTS / "summarize_read_ber.py")])
    delivery = ROOT / "results" / "final_delivery.json"
    rates = ROOT / "results" / "mram_spenvis_heavy_ion_rate.tsv"
    summary = {
        "device": "SOT_MRAM_1T1MTJ",
        "workflow": "Qcrit characterize -> RPP cross-section -> SPENVIS integrate -> width aggregate",
        "rate_table": str(rates.relative_to(ROOT)),
        "interface": "../../interfaces/mram_device_delivery.json",
    }
    delivery.parent.mkdir(parents=True, exist_ok=True)
    delivery.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {delivery}")


if __name__ == "__main__":
    main()
