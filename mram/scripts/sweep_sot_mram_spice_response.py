#!/usr/bin/env python3
"""Characterize the hierarchical SOT-MRAM read column over leakage and parasitic corners.

The output TSV is intentionally simple so the system-level Python model can
interpolate it without depending on a proprietary waveform format.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path


MEASURE_RE = re.compile(r"^\s*([a-z0-9_]+)\s*=\s*([-+0-9.eE]+)\s*$", re.MULTILINE)


def resolve_ngspice(explicit: str | None, base: Path) -> str:
    if explicit:
        path = Path(explicit)
        con = path.parent / "ngspice_con.exe"
        return str(con.resolve()) if con.is_file() else str(path)
    env = os.environ.get("NGSPICE")
    if env and Path(env).is_file():
        return env
    cfg = json.loads((base / "configs/pipeline_defaults.json").read_text(encoding="utf-8"))
    candidate = Path(str(cfg["ngspice_executable"]))
    con = candidate.parent / "ngspice_con.exe"
    return str(con.resolve()) if con.is_file() else str(candidate)


def parse_csv(text: str, cast=float) -> list:
    return [cast(value.strip()) for value in text.split(",") if value.strip()]


def set_param(source: str, name: str, value: float) -> str:
    pattern = re.compile(rf"(\.param\s+{re.escape(name)}=)([^\s]+)", re.IGNORECASE)
    updated, count = pattern.subn(rf"\g<1>{value}", source, count=1)
    if count != 1:
        raise RuntimeError(f"parameter {name} was not found exactly once")
    return updated


def strip_interactive_control(source: str) -> str:
    return re.sub(
        r"\n\.control\n.*?\n\.endc\n",
        "\n.control\nrun\nquit\n.endc\n",
        source,
        count=1,
        flags=re.DOTALL | re.IGNORECASE,
    )


def run_corner(
    template: str,
    circuit_dir: Path,
    ngspice: str,
    n_present: float,
    parasitic_scale: float,
    dvth_sa_mv: float,
    sa_enable_ns: float,
    sense_delay_ns: float,
) -> dict[str, float]:
    source = set_param(template, "NPRESENT", n_present)
    source = set_param(source, "PAR_SCALE", parasitic_scale)
    source = set_param(source, "DVTH_SA_MV", dvth_sa_mv)
    source = set_param(source, "TSAEN", f"{sa_enable_ns}n")
    source = set_param(source, "TDEVELOP", f"{sa_enable_ns - 0.05}n")
    source = set_param(source, "TSENSE", f"{sa_enable_ns + sense_delay_ns}n")
    source = strip_interactive_control(source)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".cir", prefix="mram_char_", delete=False
    ) as handle:
        handle.write(source)
        temporary_netlist = Path(handle.name)
    try:
        completed = subprocess.run(
            [ngspice, "-b", str(temporary_netlist)],
            cwd=circuit_dir,
            text=True,
            capture_output=True,
            check=False,
        )
        log = completed.stdout + "\n" + completed.stderr
        if completed.returncode != 0:
            raise RuntimeError(f"ngspice failed for {temporary_netlist.name}:\n{log[-2000:]}")
        measures = {name.lower(): float(value) for name, value in MEASURE_RE.findall(log)}
        required = {"d0_diff_dev", "d1_diff_dev", "out0_sense", "out1_sense"}
        missing = required - measures.keys()
        if missing:
            raise RuntimeError(f"missing measures {sorted(missing)}:\n{log[-2000:]}")
        return measures
    finally:
        temporary_netlist.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--netlist", default="sot_mram_hierarchical_senseamp.cir")
    parser.add_argument("--ngspice", default=None)
    parser.add_argument(
        "--n-present",
        default="0,32,64,96,112,120,128,136,144,160,192,224,255",
        help="unselected present NMOS count on the selected 256-row segment",
    )
    parser.add_argument("--sa-enable-ns", default="1.65")
    parser.add_argument(
        "--sense-delay-ns",
        type=float,
        default=0.25,
        help="deadline after SA enable; TSENSE=TSAEN+this value",
    )
    parser.add_argument("--parasitic-scale", default="0.5,1,2")
    parser.add_argument(
        "--dvth-sa-mv",
        default="0",
        help="deterministic SA mismatch sweep; for negative lists use --dvth-sa-mv=-20,0,20",
    )
    parser.add_argument("--output", default="results/mram_spice_response.tsv")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    ngspice = resolve_ngspice(args.ngspice, root)
    circuit_dir = root / "netlists"
    netlist = (circuit_dir / args.netlist).resolve()
    output = (root / args.output).resolve()
    template = netlist.read_text(encoding="utf-8")
    vdd_match = re.search(r"\.param\s+VDDVAL=([^\s]+)", template, re.IGNORECASE)
    if not vdd_match:
        raise RuntimeError("VDDVAL was not found in the netlist")
    vdd_v = float(vdd_match.group(1))

    rows: list[dict[str, float]] = []
    for scale in parse_csv(args.parasitic_scale):
        for n_present in parse_csv(args.n_present):
            for dvth_sa_mv in parse_csv(args.dvth_sa_mv):
                for sa_enable_ns in parse_csv(args.sa_enable_ns):
                    m = run_corner(
                        template,
                        circuit_dir,
                        ngspice,
                        n_present,
                        scale,
                        dvth_sa_mv,
                        sa_enable_ns,
                        args.sense_delay_ns,
                    )
                    d0_margin_mv = 1.0e3 * m["d0_diff_dev"]
                    d1_margin_mv = 1.0e3 * m["d1_diff_dev"]
                    read0_ok = m.get("read0_ok", float(m["out0_sense"] < 0.5))
                    read1_ok = m.get("read1_ok", float(m["out1_sense"] > 0.5))
                    rows.append(
                        {
                            "parasitic_scale": scale,
                            "vdd_v": vdd_v,
                            "n_present": n_present,
                            "dvth_sa_mv": dvth_sa_mv,
                            "sa_enable_ns": sa_enable_ns,
                            "sense_time_ns": sa_enable_ns + args.sense_delay_ns,
                            "access_from_preoff_ns": sa_enable_ns + args.sense_delay_ns - 1.0,
                            "d0_margin_mv": d0_margin_mv,
                            "d1_margin_mv": d1_margin_mv,
                            # Effective margin is negative when the fixed TSENSE
                            # deadline is missed even though the pre-SA differential
                            # still has the correct polarity.
                            "d0_effective_margin_mv": d0_margin_mv if read0_ok else -d0_margin_mv,
                            "d1_effective_margin_mv": d1_margin_mv if read1_ok else -d1_margin_mv,
                            "min_margin_mv": min(d0_margin_mv, d1_margin_mv),
                            "out0_v": m["out0_sense"],
                            "out1_v": m["out1_sense"],
                            "read0_ok": read0_ok,
                            "read1_ok": read1_ok,
                        }
                    )

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} corners to {output}")


if __name__ == "__main__":
    main()
