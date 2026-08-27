#!/usr/bin/env python3
"""Integrate MRAM read-periphery proton upset using Qcrit samples + SPENVIS proton spectrum.

Uses the same RPP charge-collection envelope as the heavy-ion read chain, with
proton energy mapped to an approximate silicon LET via ``proton_deposition_proxy.json``.
This fills the ``transient_read`` proton sub-channel; it does not model MTJ storage flips.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(REPO / "sram/src"))
sys.path.insert(0, str(REPO / "mram/scripts"))

from sram_check.io import load_spectrum  # noqa: E402
from sot_mram_heavy_ion_pipeline import (  # noqa: E402
    Q_E_C,
    SI_EH_EV,
    beta_interval,
    charge_fc_from_let,
    load_levels,
    read_tsv,
    sample_efficiency,
    write_tsv,
)


def _trapz(y: np.ndarray, x: np.ndarray) -> float:
    return float(np.trapezoid(y, x))


def proton_let_mev_cm2_mg(energy_mev: np.ndarray, points: list[list[float]]) -> np.ndarray:
    table = np.asarray(points, dtype=float)
    x = table[:, 0]
    y = table[:, 1]
    log_x = np.log10(np.maximum(energy_mev, x[0] * 0.5))
    log_table_x = np.log10(x)
    log_table_y = np.log10(y)
    return 10 ** np.interp(log_x, log_table_x, log_table_y, left=y[0], right=y[-1])


def proton_charge_fc(energy_mev: np.ndarray, depth_um: float, efficiency: np.ndarray, let_points: list) -> np.ndarray:
    let_proxy = proton_let_mev_cm2_mg(energy_mev, let_points)
    return charge_fc_from_let(let_proxy, depth_um, efficiency)


def proton_cross_section_curve(
    qrows: list[dict[str, str]],
    levels: dict,
    rng: np.random.Generator,
    energy_grid: np.ndarray,
    let_points: list,
) -> list[dict]:
    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in qrows:
        grouped[(row["level"], row["node"])].append(float(row["qcrit_fc"]))
    populations: dict[tuple[str, str], tuple[np.ndarray, np.ndarray]] = {}
    for key, values in grouped.items():
        qcrit = np.asarray(values, dtype=float)
        populations[key] = (qcrit, sample_efficiency(levels[key[0]], rng, qcrit.size))
    out: list[dict] = []
    for level_name in sorted({key[0] for key in grouped}):
        level = levels[level_name]
        for energy in energy_grid:
            total_sigma = total_low = total_high = 0.0
            total_trials = total_failures = 0
            for node in ("gbl", "sa"):
                qcrit, efficiency = populations[(level_name, node)]
                qcol = proton_charge_fc(np.full(qcrit.size, energy), level["sensitive_depth_um"], efficiency, let_points)
                failures = int(np.count_nonzero(qcol >= qcrit))
                probability = failures / qcrit.size
                p_low, p_high = beta_interval(failures, qcrit.size)
                area_cm2 = level[f"{node}_sensitive_area_um2"] * 1e-8
                total_sigma += area_cm2 * probability
                total_low += area_cm2 * p_low
                total_high += area_cm2 * p_high
                total_trials += qcrit.size
                total_failures += failures
            out.append(
                {
                    "level": level_name,
                    "proton_energy_mev": energy,
                    "sigma_cm2_per_active_read_bit": total_sigma,
                    "sigma_ci95_low": total_low,
                    "sigma_ci95_high": total_high,
                    "failed_joint_samples": total_failures,
                    "joint_samples": total_trials,
                    "model": "ngspice_Qcrit_plus_RPP_proton_LET_proxy",
                }
            )
    return out


def integrate_proton_spectrum(
    curve: list[dict],
    proton_spectrum,
    read_window_ns: float,
    qrows: list[dict[str, str]],
    levels: dict,
    rng: np.random.Generator,
    let_points: list,
) -> list[dict]:
    energy = np.asarray(proton_spectrum.x, dtype=float)
    dflux = np.asarray(proton_spectrum.differential_flux, dtype=float)
    segment_integrals = 0.5 * (dflux[:-1] + dflux[1:]) * np.diff(energy)
    cumulative_above = np.zeros_like(energy)
    cumulative_above[:-1] = np.cumsum(segment_integrals[::-1])[::-1]

    rates: list[dict] = []
    for level_name in sorted({row["level"] for row in curve}):
        sub = [row for row in curve if row["level"] == level_name]
        x = np.asarray([row["proton_energy_mev"] for row in sub])
        sigma = np.asarray([row["sigma_cm2_per_active_read_bit"] for row in sub])
        sigma_low = np.asarray([row["sigma_ci95_low"] for row in sub])
        sigma_high = np.asarray([row["sigma_ci95_high"] for row in sub])

        def integrate(values: np.ndarray) -> float:
            interp = np.interp(energy, x, values, left=values[0], right=values[-1])
            return _trapz(dflux * interp, energy)

        curve_rate = integrate(sigma)
        rate_low = integrate(sigma_low)
        rate_high = integrate(sigma_high)

        level = levels[level_name]
        sample_rows: dict[int, dict[str, float]] = defaultdict(dict)
        for row in qrows:
            if row["level"] == level_name:
                sample_rows[int(row["sample"])][row["node"]] = float(row["qcrit_fc"])

        per_sample: list[float] = []
        for sample in sorted(sample_rows):
            total = 0.0
            for node in ("gbl", "sa"):
                qcrit = sample_rows[sample][node]
                efficiency = float(sample_efficiency(level, rng, 1)[0])
                charge_per_energy = float(
                    proton_charge_fc(np.asarray([1.0]), level["sensitive_depth_um"], np.asarray([efficiency]), let_points)[0]
                )
                threshold_energy = qcrit / max(charge_per_energy, 1e-30)
                flux_above = float(np.interp(threshold_energy, energy, cumulative_above, left=cumulative_above[0], right=0.0))
                area_cm2 = level[f"{node}_sensitive_area_um2"] * 1e-8
                total += flux_above * area_cm2
            per_sample.append(total)
        per_sample_arr = np.asarray(per_sample, dtype=float)
        sample_rate = float(np.median(per_sample_arr))
        if curve_rate <= 0.0 and sample_rate > 0.0:
            curve_rate = sample_rate
            rate_low = float(np.quantile(per_sample_arr, 0.05))
            rate_high = float(np.quantile(per_sample_arr, 0.95))
        p_window = read_window_ns * 1e-9
        rates.append(
            {
                "level": level_name,
                "proton_event_rate_per_active_read_bit_s": curve_rate,
                "proton_event_rate_ci95_low": rate_low,
                "proton_event_rate_ci95_high": rate_high,
                "proton_read_window_s": p_window,
                "proton_read_error_probability_lower_bound": rate_low * p_window,
                "proton_read_error_probability_nominal": curve_rate * p_window,
                "proton_read_error_probability_ci95_high": rate_high * p_window,
                "sample_median_rate_per_active_read_bit_s": sample_rate,
                "sample_p05_rate_per_active_read_bit_s": float(np.quantile(per_sample_arr, 0.05)),
                "sample_p95_rate_per_active_read_bit_s": float(np.quantile(per_sample_arr, 0.95)),
                "spectrum_source": proton_spectrum.source,
                "spectrum_normalization": proton_spectrum.normalization,
                "model": "step_response_above_threshold_energy",
            }
        )
    return rates


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qcrit", default="results/mram_joint_qcrit_samples.tsv")
    parser.add_argument("--envelopes", default="configs/statistical_envelopes.json")
    parser.add_argument("--proton-proxy", default="configs/proton_deposition_proxy.json")
    parser.add_argument("--spectrum", default="../environment/target_orbit/average_LET_proton_and_ion_spectra.txt")
    parser.add_argument("--read-window-ns", type=float, default=0.72)
    parser.add_argument("--energy-min", type=float, default=0.5)
    parser.add_argument("--energy-max", type=float, default=200.0)
    parser.add_argument("--energy-points", type=int, default=40)
    parser.add_argument("--seed", type=int, default=20260827)
    parser.add_argument("--cross-section-out", default="results/mram_proton_cross_section.tsv")
    parser.add_argument("--rate-out", default="results/mram_spenvis_proton_rate.tsv")
    parser.add_argument("--summary-out", default="results/mram_proton_read_summary.json")
    args = parser.parse_args()

    base = ROOT
    qrows = read_tsv((base / args.qcrit).resolve())
    levels = load_levels((base / args.envelopes).resolve())
    proxy = json.loads((base / args.proton_proxy).read_text(encoding="utf-8"))
    let_points = proxy["let_mev_cm2_mg_points"]
    rng = np.random.default_rng(args.seed)

    spectrum_path = (ROOT.parent / "environment/target_orbit/average_LET_proton_and_ion_spectra.txt").resolve()
    proton_spec = load_spectrum(
        {
            "type": "spenvis_proton_text",
            "path": str(spectrum_path),
            "solid_angle_sr": 4 * math.pi,
        },
        ROOT.parent,
    )
    energy_grid = np.geomspace(args.energy_min, args.energy_max, args.energy_points)
    curve = proton_cross_section_curve(qrows, levels, rng, energy_grid, let_points)
    rates = integrate_proton_spectrum(curve, proton_spec, args.read_window_ns, qrows, levels, rng, let_points)

    write_tsv((base / args.cross_section_out).resolve(), curve)
    write_tsv((base / args.rate_out).resolve(), rates)

    by_level = {row["level"]: row for row in rates}
    summary = {
        "schema_version": 1,
        "read_window_ns": args.read_window_ns,
        "proton_deposition_proxy": str((base / args.proton_proxy).resolve().relative_to(REPO)),
        "spectrum": args.spectrum,
        "transient_read_proton_lower_bound": {
            level: row["proton_read_error_probability_lower_bound"]
            for level, row in by_level.items()
        },
        "transient_read_proton_nominal": {
            level: row["proton_read_error_probability_nominal"]
            for level, row in by_level.items()
        },
        "claim_boundary": (
            "CMOS read periphery only; proton LET proxy + pre-layout RPP; "
            "not MTJ storage flip; do not add to HI read probability without union model"
        ),
        "rates": rates,
    }
    (base / args.summary_out).resolve().write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary["transient_read_proton_lower_bound"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
