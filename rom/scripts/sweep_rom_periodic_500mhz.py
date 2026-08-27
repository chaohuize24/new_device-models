#!/usr/bin/env python3
"""Run repeated MASK NOR-ROM reads and joint pre-layout envelope sweeps.

This driver converts the single-read hierarchical netlist into a periodic
precharge/evaluate/sense waveform.  The default period is 2 ns (500 MHz).
It does not claim foundry PVT: voltage, temperature, DELVTO mismatch, mobility,
TID-leakage and parasitic factors are explicit engineering envelope inputs.
"""

from __future__ import annotations

import argparse
import csv
import re
import subprocess
import tempfile
from pathlib import Path


MEASURE_RE = re.compile(r"^\s*([a-z0-9_]+)\s*=\s*([-+0-9.eE]+)\s*$", re.MULTILINE)

TID_CORNERS = {
    "none": (0.0, 0.0, 1.0, 1.0),
    "central": (0.0, 0.0, 1.0, 1.001938786),
    "conservative": (-1.0, -1.0, 0.99, 2.0),
    "stress": (-3.0, -3.0, 0.98, 10.0),
}


def parse_csv(text: str, cast=float) -> list:
    return [cast(value.strip()) for value in text.split(",") if value.strip()]


def set_param(source: str, name: str, value: str | float) -> str:
    pattern = re.compile(rf"(\.param\s+{re.escape(name)}=)([^\s]+)", re.IGNORECASE)
    updated, count = pattern.subn(rf"\g<1>{value}", source, count=1)
    if count != 1:
        raise RuntimeError(f"parameter {name} was not found exactly once")
    return updated


def add_global_device_envelope(
    source: str,
    dvth_n_mv: float,
    dvth_p_mv: float,
    mobility_scale: float,
    leakage_multiplier: float,
) -> str:
    parameter_block = (
        f"\n.param DVTH_GLOBAL_N_MV={dvth_n_mv}\n"
        f".param DVTH_GLOBAL_P_MV={dvth_p_mv}\n"
        f".param MU_GLOBAL_SCALE={mobility_scale}\n"
        f".param LEAK_GLOBAL_MULT={leakage_multiplier}\n"
    )
    source, parameter_count = re.subn(
        r"(\.param\s+DVTH_SA_MV=[^\s]+\n)",
        r"\1" + parameter_block,
        source,
        count=1,
        flags=re.IGNORECASE,
    )
    if parameter_count != 1:
        raise RuntimeError("DVTH_SA_MV parameter line was not found")

    transformed: list[str] = []
    for line in source.splitlines():
        if line.startswith("M") and (" nmos " in line or " pmos " in line):
            global_name = "DVTH_GLOBAL_N_MV" if " nmos " in line else "DVTH_GLOBAL_P_MV"
            if "DELVTO={" in line:
                line = re.sub(
                    r"DELVTO=\{([^}]*)\}",
                    rf"DELVTO={{(\1)+{global_name}*1m}}",
                    line,
                    count=1,
                )
            else:
                line += f" DELVTO={{{global_name}*1m}}"
            if "MULU0=" not in line:
                line += " MULU0={MU_GLOBAL_SCALE}"
        transformed.append(line)
    source = "\n".join(transformed) + "\n"

    # Add only the leakage needed to reach LEAK_GLOBAL_MULT.  This is a TID
    # envelope term for the unselected present-cell population, not a physical
    # STI compact model.
    leakage_block = """
VLEAK_UNIT leak_unit 0 {VDDVAL}
MLEAK_UNIT leak_unit 0 0 0 nmos W={WN} L={LCH} AD=0 AS=0 PD=0 PS=0 DELVTO={DVTH_GLOBAL_N_MV*1m} MULU0={MU_GLOBAL_SCALE}
BEXTRA_D0 lbl_d0 0 I={NOFF*max((LEAK_GLOBAL_MULT-1)*(-i(VLEAK_UNIT)),0)}
BEXTRA_R0 lbl_r0 0 I={NOFF*max((LEAK_GLOBAL_MULT-1)*(-i(VLEAK_UNIT)),0)}
BEXTRA_D1 lbl_d1 0 I={NOFF*max((LEAK_GLOBAL_MULT-1)*(-i(VLEAK_UNIT)),0)}
BEXTRA_R1 lbl_r1 0 I={NOFF*max((LEAK_GLOBAL_MULT-1)*(-i(VLEAK_UNIT)),0)}
"""
    return source.replace("VDD vdd 0 {VDDVAL}\n", "VDD vdd 0 {VDDVAL}\n" + leakage_block, 1)


def periodic_timing_block(period_ns: float) -> str:
    scale = period_ns / 2.0
    tr = 0.05 * scale
    return f"""VPRE pre 0 PULSE(0 {{VDDVAL}} {0.60*scale}n {tr}n {tr}n {1.15*scale}n {period_ns}n)
VSEG segsel 0 PULSE(0 {{VDDVAL}} {0.35*scale}n {tr}n {tr}n {1.35*scale}n {period_ns}n)
VSEGB segselb 0 PULSE({{VDDVAL}} 0 {0.35*scale}n {tr}n {tr}n {1.35*scale}n {period_ns}n)
VCOL colsel 0 PULSE(0 {{VDDVAL}} {0.35*scale}n {tr}n {tr}n {1.35*scale}n {period_ns}n)
VCOLB colselb 0 PULSE({{VDDVAL}} 0 {0.35*scale}n {tr}n {tr}n {1.35*scale}n {period_ns}n)
VWL wl 0 PULSE(0 {{VDDVAL}} {0.70*scale}n {tr}n {tr}n {0.85*scale}n {period_ns}n)
VSAEN saen 0 PULSE(0 {{VDDVAL}} {1.25*scale}n {tr}n {tr}n {0.35*scale}n {period_ns}n)
VSAENB saenb 0 PULSE({{VDDVAL}} 0 {1.25*scale}n {tr}n {tr}n {0.35*scale}n {period_ns}n)"""


def periodic_analysis_block(period_ns: float, cycles: int, temperature_c: float) -> str:
    scale = period_ns / 2.0
    sample_phase = 1.55 * scale
    develop_phase = 1.20 * scale
    precheck_phase = 0.55 * scale
    lines = [f".temp {temperature_c}", f".tran 1p {period_ns*cycles}n"]
    for cycle in range(cycles):
        base = cycle * period_ns
        sample = base + sample_phase
        develop = base + develop_phase
        precheck = base + precheck_phase
        index = cycle + 1
        lines.extend(
            [
                f".measure tran OUT0_C{index} FIND v(data_out0) AT={sample}n",
                f".measure tran OUT1_C{index} FIND v(data_out1) AT={sample}n",
                f".measure tran D0DIN_C{index} FIND v(din0) AT={develop}n",
                f".measure tran D0RIN_C{index} FIND v(rin0) AT={develop}n",
                f".measure tran D1DIN_C{index} FIND v(din1) AT={develop}n",
                f".measure tran D1RIN_C{index} FIND v(rin1) AT={develop}n",
                f".measure tran PRE0_C{index} FIND v(gbl_d0) AT={precheck}n",
                f".measure tran PRE1_C{index} FIND v(gbl_d1) AT={precheck}n",
            ]
        )
    lines.extend([".control", "run", "quit", ".endc"])
    return "\n".join(lines)


def build_periodic_source(
    template: str,
    period_ns: float,
    cycles: int,
    vdd_v: float,
    temperature_c: float,
    n_present: float,
    parasitic_scale: float,
    dvth_sa_mv: float,
    tid_corner: str,
) -> str:
    source = set_param(template, "VDDVAL", vdd_v)
    source = set_param(source, "NPRESENT", n_present)
    source = set_param(source, "PAR_SCALE", parasitic_scale)
    source = set_param(source, "DVTH_SA_MV", dvth_sa_mv)
    dvn, dvp, mu, leak = TID_CORNERS[tid_corner]
    source = add_global_device_envelope(source, dvn, dvp, mu, leak)
    source, timing_count = re.subn(
        r"^VPRE pre 0 .*?^VSAENB saenb 0 .*?$",
        periodic_timing_block(period_ns),
        source,
        count=1,
        flags=re.MULTILINE | re.DOTALL,
    )
    if timing_count != 1:
        raise RuntimeError("single-read timing-source block was not found")
    source, analysis_count = re.subn(
        r"^\.tran 1p 2\.4n\n.*?^\.endc$",
        periodic_analysis_block(period_ns, cycles, temperature_c),
        source,
        count=1,
        flags=re.MULTILINE | re.DOTALL,
    )
    if analysis_count != 1:
        raise RuntimeError("single-read analysis block was not found")
    return source


def run_corner(source: str, circuit_dir: Path, cycles: int, vdd_v: float) -> dict[str, float]:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".cir", prefix="rom_periodic_", delete=False
    ) as handle:
        handle.write(source)
        netlist = Path(handle.name)
    try:
        completed = subprocess.run(
            ["ngspice", "-b", str(netlist)],
            cwd=circuit_dir,
            text=True,
            capture_output=True,
            check=False,
        )
        log = completed.stdout + "\n" + completed.stderr
        if completed.returncode != 0:
            raise RuntimeError(log[-3000:])
        measures = {name.lower(): float(value) for name, value in MEASURE_RE.findall(log)}
        expected = {f"out{logic}_c{cycle}" for logic in (0, 1) for cycle in range(1, cycles + 1)}
        missing = expected - measures.keys()
        if missing:
            raise RuntimeError(f"missing measures {sorted(missing)}:\n{log[-3000:]}")
        return measures
    finally:
        netlist.unlink(missing_ok=True)


def summarize(measures: dict[str, float], cycles: int, vdd_v: float) -> dict[str, float]:
    out0 = [measures[f"out0_c{i}"] for i in range(1, cycles + 1)]
    out1 = [measures[f"out1_c{i}"] for i in range(1, cycles + 1)]
    precharge = [
        measures[f"pre{logic}_c{i}"]
        for logic in (0, 1)
        for i in range(1, cycles + 1)
    ]
    d0_margin = [
        measures[f"d0rin_c{i}"] - measures[f"d0din_c{i}"]
        for i in range(1, cycles + 1)
    ]
    d1_margin = [
        measures[f"d1din_c{i}"] - measures[f"d1rin_c{i}"]
        for i in range(1, cycles + 1)
    ]
    ok = all(value < 0.5 * vdd_v for value in out0) and all(
        value > 0.5 * vdd_v for value in out1
    )
    return {
        "all_cycles_ok": float(ok),
        "out0_max_v": max(out0),
        "out1_min_v": min(out1),
        "precharge_min_v": min(precharge),
        "precharge_min_ratio": min(precharge) / vdd_v,
        "d0_develop_margin_min_mv": 1.0e3 * min(d0_margin),
        "d1_develop_margin_min_mv": 1.0e3 * min(d1_margin),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--netlist", default="rom_hierarchical_senseamp.cir")
    parser.add_argument("--period-ns", type=float, default=2.0)
    parser.add_argument("--cycles", type=int, default=3)
    parser.add_argument("--vdd", default="0.9,1.0,1.1")
    parser.add_argument("--temperature-c", default="-40,27,85")
    parser.add_argument("--n-present", default="128,255")
    parser.add_argument("--parasitic-scale", default="0.5,1,2")
    parser.add_argument("--dvth-sa-mv", default="-12,0,12")
    parser.add_argument(
        "--tid-corner",
        default="none,central,conservative,stress",
        help="comma-separated: none, central, conservative, stress",
    )
    parser.add_argument("--output", default="results/rom_periodic_500mhz_envelope.tsv")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    circuit_dir = root / "netlists"
    template = (circuit_dir / args.netlist).read_text(encoding="utf-8")
    tid_corners = parse_csv(args.tid_corner, str)
    unknown = set(tid_corners) - TID_CORNERS.keys()
    if unknown:
        raise ValueError(f"unknown TID corners: {sorted(unknown)}")

    rows: list[dict[str, float | str]] = []
    for vdd_v in parse_csv(args.vdd):
        for temperature_c in parse_csv(args.temperature_c):
            for n_present in parse_csv(args.n_present):
                for parasitic_scale in parse_csv(args.parasitic_scale):
                    for dvth_sa_mv in parse_csv(args.dvth_sa_mv):
                        for tid_corner in tid_corners:
                            source = build_periodic_source(
                                template,
                                args.period_ns,
                                args.cycles,
                                vdd_v,
                                temperature_c,
                                n_present,
                                parasitic_scale,
                                dvth_sa_mv,
                                tid_corner,
                            )
                            measures = run_corner(source, circuit_dir, args.cycles, vdd_v)
                            rows.append(
                                {
                                    "period_ns": args.period_ns,
                                    "frequency_mhz": 1.0e3 / args.period_ns,
                                    "cycles": args.cycles,
                                    "vdd_v": vdd_v,
                                    "temperature_c": temperature_c,
                                    "n_present": n_present,
                                    "parasitic_scale": parasitic_scale,
                                    "dvth_sa_mv": dvth_sa_mv,
                                    "tid_corner": tid_corner,
                                    **summarize(measures, args.cycles, vdd_v),
                                }
                            )

    output = (root / args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    failures = sum(float(row["all_cycles_ok"]) < 0.5 for row in rows)
    print(f"wrote {len(rows)} corners to {output}; failures={failures}")


if __name__ == "__main__":
    main()
