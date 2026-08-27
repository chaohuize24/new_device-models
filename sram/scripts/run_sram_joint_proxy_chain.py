#!/usr/bin/env python3
"""Build an architecture-facing SRAM radiation/state proxy package.

The script deliberately separates three operations:

1. add physical Poisson arrival *rates* from proton and heavy-ion channels;
2. evolve one stored-bit state through radiation toggles after a write/scrub;
3. condition the electrical read decision on that state.

It never combines circuit and radiation error probabilities with an
independent-union formula.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import statistics
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sram_check.core import CrossSectionModel, integrate_spectrum_cross_section, trapezoid  # noqa: E402
from sram_check.io import load_spectrum  # noqa: E402
from sram_check.system_state import (  # noqa: E402
    cumulative_expected_upset_events,
    mean_bit_wrong_probability_uniform_reads_from_initial,
    mean_joint_read_error_probability_uniform_reads,
    mean_joint_secded_uncorrectable_probability_uniform_reads,
)


DEFAULT_CONFIG = ROOT / "configs/sram_joint_proxy_chain.json"
DEFAULT_OUTPUT = ROOT / "results/radiation"
SECONDS_PER_DAY = 86400.0


def resolve(config_path: Path, text: str) -> Path:
    return (config_path.parent / text).resolve()


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError(f"cannot write empty table: {path}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def load_heavy_ion_proxies(path: Path) -> list[tuple[dict[str, str], CrossSectionModel]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    result = []
    for row in rows:
        result.append(
            (
                row,
                CrossSectionModel(
                    kind="weibull",
                    variable="let_mev_cm2_mg",
                    normalization="per_bit",
                    source=f"doi:{row['source_doi']}",
                    sigma_sat=float(row["sigma_sat_cm2_per_bit"]),
                    threshold=float(row["threshold_let_mev_cm2_mg"]),
                    width=float(row["width_mev_cm2_mg"]),
                    shape=float(row["shape"]),
                ),
            )
        )
    if len(result) < 2:
        raise ValueError("at least two heavy-ion measured proxies are required")
    return result


def load_proton_points(path: Path) -> dict[str, list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(row["response_id"], []).append(row)
    for values in grouped.values():
        values.sort(key=lambda row: float(row["energy_mev"]))
    required = {
        "st28_fdsoi_sram_low_energy",
        "kintex7_configuration_sram_high_energy",
    }
    if set(grouped) != required:
        raise ValueError(f"expected proton response groups {sorted(required)}, got {sorted(grouped)}")
    return grouped


def load_electrical_scenarios(config_path: Path, system_config: dict) -> list[dict]:
    table = system_config.get("electrical_condition_table")
    if table:
        payload = json.loads(resolve(config_path, table["path"]).read_text(encoding="utf-8"))
        scenarios = payload.get("electrical_condition_scenarios", [])
    else:
        scenarios = system_config.get("electrical_condition_scenarios", [])
    if not scenarios:
        raise ValueError("at least one electrical condition scenario is required")
    required = {
        "id",
        "post_write_wrong_probability",
        "read_error_given_correct_state",
        "read_error_given_wrong_state",
        "is_ngspice_derived",
        "is_total_target_ber",
    }
    for scenario in scenarios:
        missing = required - scenario.keys()
        if missing:
            raise ValueError(f"electrical scenario {scenario.get('id')} lacks {sorted(missing)}")
    return scenarios


def loglog_interpolate(points: list[tuple[float, float]], energy: float) -> float:
    if energy < points[0][0]:
        return 0.0
    if energy >= points[-1][0]:
        return points[-1][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= energy < x1:
            fraction = math.log(energy / x0) / math.log(x1 / x0)
            return math.exp(math.log(y0) + fraction * math.log(y1 / y0))
    raise RuntimeError("unreachable proton interpolation interval")


def proton_scenario_values(
    grouped: dict[str, list[dict[str, str]]], energy: float
) -> dict[str, float]:
    low_points = [
        (float(row["energy_mev"]), float(row["sigma_nominal_cm2_per_bit"]))
        for row in grouped["st28_fdsoi_sram_low_energy"]
    ]
    high_points = [
        (float(row["energy_mev"]), float(row["sigma_nominal_cm2_per_bit"]))
        for row in grouped["kintex7_configuration_sram_high_energy"]
    ]
    if low_points[0][0] <= energy <= low_points[-1][0]:
        measured_bands = loglog_interpolate(low_points, energy)
    elif energy >= high_points[0][0]:
        measured_bands = loglog_interpolate(high_points, energy)
    else:
        measured_bands = 0.0
    combined = low_points + high_points
    bridge = loglog_interpolate(combined, energy)
    if low_points[0][0] <= energy <= low_points[-1][0]:
        plateau = loglog_interpolate(low_points, energy)
    elif low_points[-1][0] < energy < high_points[0][0]:
        plateau = high_points[0][1]
    elif energy >= high_points[0][0]:
        plateau = loglog_interpolate(high_points, energy)
    else:
        plateau = 0.0
    return {
        "measured_bands_partial": measured_bands,
        "cross_technology_log_bridge": bridge,
        "gap_plateau_ceiling": plateau,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    let_cfg = dict(config["spectra"]["let"])
    proton_cfg = dict(config["spectra"]["proton"])
    let_cfg["path"] = str(resolve(args.config, let_cfg["path"]))
    proton_cfg["path"] = str(resolve(args.config, proton_cfg["path"]))
    let_spectrum = load_spectrum(let_cfg, ROOT)
    proton_spectrum = load_spectrum(proton_cfg, ROOT)

    heavy_proxies = load_heavy_ion_proxies(
        resolve(args.config, config["heavy_ion_proxy_table"]["path"])
    )
    proton_groups = load_proton_points(
        resolve(args.config, config["proton_proxy_table"]["path"])
    )

    heavy_curve_rows = []
    for index, let_value in enumerate(let_spectrum.x):
        values = {row["proxy_id"]: model.evaluate(let_value) for row, model in heavy_proxies}
        ordered = sorted(values.values())
        heavy_curve_rows.append(
            {
                "let_mev_cm2_mg": let_value,
                "differential_flux_cm2_s_per_mev_cm2_mg": let_spectrum.differential_flux[index],
                **{f"{name}_sigma_cm2_per_bit": value for name, value in values.items()},
                "pointwise_low_sigma_cm2_per_bit": ordered[0],
                "pointwise_median_sigma_cm2_per_bit": statistics.median(ordered),
                "pointwise_high_sigma_cm2_per_bit": ordered[-1],
            }
        )

    heavy_rates: dict[str, float] = {}
    for name in ("low", "median", "high"):
        heavy_rates[name] = trapezoid(
            [
                row["differential_flux_cm2_s_per_mev_cm2_mg"]
                * row[f"pointwise_{name}_sigma_cm2_per_bit"]
                for row in heavy_curve_rows
            ],
            let_spectrum.x,
        )

    proton_curve_rows = []
    for energy, flux in zip(proton_spectrum.x, proton_spectrum.differential_flux):
        values = proton_scenario_values(proton_groups, energy)
        proton_curve_rows.append(
            {
                "proton_energy_mev": energy,
                "differential_flux_cm2_s_mev": flux,
                **{f"{name}_sigma_cm2_per_bit": value for name, value in values.items()},
            }
        )
    proton_rates: dict[str, float] = {}
    for name in (
        "measured_bands_partial",
        "cross_technology_log_bridge",
        "gap_plateau_ceiling",
    ):
        proton_rates[name] = trapezoid(
            [
                row["differential_flux_cm2_s_mev"]
                * row[f"{name}_sigma_cm2_per_bit"]
                for row in proton_curve_rows
            ],
            proton_spectrum.x,
        )

    paired_rates = []
    paired_rate_by_id: dict[str, float] = {}
    for scenario in config["paired_radiation_scenarios"]:
        heavy_rate = heavy_rates[scenario["heavy_ion"]]
        proton_rate = proton_rates[scenario["proton"]]
        total_rate = heavy_rate + proton_rate
        paired_rate_by_id[scenario["id"]] = total_rate
        paired_rates.append(
            {
                "radiation_scenario": scenario["id"],
                "heavy_ion_response_scenario": scenario["heavy_ion"],
                "proton_response_scenario": scenario["proton"],
                "heavy_ion_rate_per_bit_s": heavy_rate,
                "proton_rate_per_bit_s": proton_rate,
                "total_physical_toggle_rate_per_bit_s": total_rate,
                "upsets_per_bit_day": total_rate * SECONDS_PER_DAY,
                "interpretation": scenario["interpretation"],
                "is_target_confidence_bound": False,
            }
        )

    system = config["system_scenarios"]
    codeword_bits = int(system["secded_codeword_bits"])
    electrical_scenarios = load_electrical_scenarios(args.config, system)
    state_rows = []
    for radiation in paired_rates:
        rate = float(radiation["total_physical_toggle_rate_per_bit_s"])
        for electrical in electrical_scenarios:
            p0 = float(electrical["post_write_wrong_probability"])
            p_read_correct = float(electrical["read_error_given_correct_state"])
            p_read_wrong = float(electrical["read_error_given_wrong_state"])
            for interval in system["reset_or_scrub_intervals_s"]:
                state_wrong = mean_bit_wrong_probability_uniform_reads_from_initial(
                    rate, interval, p0
                )
                read_error = mean_joint_read_error_probability_uniform_reads(
                    rate, interval, p0, p_read_correct, p_read_wrong
                )
                due = mean_joint_secded_uncorrectable_probability_uniform_reads(
                    rate,
                    interval,
                    codeword_bits,
                    p0,
                    p_read_correct,
                    p_read_wrong,
                )
                state_rows.append(
                    {
                        "radiation_scenario": radiation["radiation_scenario"],
                        "electrical_scenario": electrical["id"],
                        "reset_or_scrub_interval_s": interval,
                        "physical_toggle_rate_per_bit_s": rate,
                        "post_write_wrong_probability": p0,
                        "read_error_given_correct_state": p_read_correct,
                        "read_error_given_wrong_state": p_read_wrong,
                        "mean_stored_state_wrong_probability_per_read": state_wrong,
                        "joint_raw_bit_read_error_probability": read_error,
                        "secded_codeword_bits": codeword_bits,
                        "joint_independent_bit_secded_due_probability": due,
                        "combination_rule": "condition read on evolved stored state",
                        "is_ngspice_derived": electrical["is_ngspice_derived"],
                        "is_total_target_ber": electrical["is_total_target_ber"],
                    }
                )

    array_rows = []
    for scenario_id, rate in paired_rate_by_id.items():
        for bits in system["array_bits"]:
            array_rows.append(
                {
                    "radiation_scenario": scenario_id,
                    "array_bits": int(bits),
                    "expected_physical_toggle_arrivals_per_day": cumulative_expected_upset_events(
                        rate, int(bits), SECONDS_PER_DAY
                    ),
                    "interpretation": "physical arrivals before write/scrub/ECC",
                }
            )

    let_qc = (
        let_spectrum.integrated_flux / let_spectrum.integral_flux_reference - 1.0
        if let_spectrum.integral_flux_reference
        else None
    )
    proton_qc = (
        proton_spectrum.integrated_flux / proton_spectrum.integral_flux_reference - 1.0
        if proton_spectrum.integral_flux_reference
        else None
    )
    summary = {
        "claim_scope": config["claim_scope"],
        "spectrum": {
            "let_integrated_flux_cm2_s": let_spectrum.integrated_flux,
            "let_differential_integral_qc": let_qc,
            "proton_integrated_flux_cm2_s": proton_spectrum.integrated_flux,
            "proton_differential_integral_qc": proton_qc,
            "source": "environment/target_orbit/average_LET_proton_and_ion_spectra.txt",
        },
        "heavy_ion_rate_per_bit_s": heavy_rates,
        "proton_rate_per_bit_s": proton_rates,
        "paired_physical_rates": paired_rates,
        "combination_policy": config["output_policy"],
        "electrical_status": {
            "active_scenarios": electrical_scenarios,
            "required_for_total_ber": system["required_for_total_ber"],
        },
        "decision": "architecture-ready joint scenario package; PTM32 engineering Monte Carlo is connected, but absolute target BER still requires target PDK/PEX and rare-event statistics",
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "heavy_ion_curve_and_spectrum.csv", heavy_curve_rows)
    write_csv(args.output_dir / "proton_curve_and_spectrum.csv", proton_curve_rows)
    write_csv(args.output_dir / "physical_rate_scenarios.csv", paired_rates)
    write_csv(args.output_dir / "joint_state_read_scenarios.csv", state_rows)
    write_csv(args.output_dir / "array_physical_events.csv", array_rows)
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    selected_rows = {
        (
            row["radiation_scenario"],
            row["electrical_scenario"],
            float(row["reset_or_scrub_interval_s"]),
        ): row
        for row in state_rows
    }
    report_electrical_id = system.get(
        "report_electrical_scenario_id", electrical_scenarios[0]["id"]
    )
    readme = f"""# SRAM joint measured-proxy radiation/state package

## Result

The target SPENVIS LET and proton spectra were integrated against measured 28 nm memory-class proxy responses. Particle-channel rates are added as Poisson arrival intensities; circuit and radiation error probabilities are **not** combined by an independent union.

| Scenario | Heavy-ion rate (/bit/s) | Proton rate (/bit/s) | Total (/bit/s) | Upsets/bit/day |
|---|---:|---:|---:|---:|
"""
    for row in paired_rates:
        readme += (
            f"| {row['radiation_scenario']} | {row['heavy_ion_rate_per_bit_s']:.6e} | "
            f"{row['proton_rate_per_bit_s']:.6e} | {row['total_physical_toggle_rate_per_bit_s']:.6e} | "
            f"{row['upsets_per_bit_day']:.6e} |\n"
        )
    readme += f"""

`partial_low` is a measured-energy-band partial contribution, not a target lower bound. `engineering_nominal` bridges an unmeasured 8-80 MeV interval across two different technologies. `engineering_high` deliberately applies the 80 MeV Kintex-7 value across that gap. None of the three is a confidence interval or one physical device response curve.

## Joint state/read model

The active electrical table is loaded from the PTM32 ngspice access Monte Carlo. Its point estimates are population fractions under declared engineering mismatch priors. They are not temporal-noise BER, foundry yield, or target-macro confidence bounds. The selected report row is `{report_electrical_id}`. A total target claim still requires:

- foundry PDK statistical models and target PEX;
- sufficient rare-event sampling or validated tail/importance sampling;
- temporal-noise and target timing distributions.

Selected joint raw-bit error probabilities (the current PTM32 point estimates add no observed circuit failures):

| Scenario | 1500 s scrub | 86400 s rewrite |
|---|---:|---:|
"""
    for scenario in ("partial_low", "engineering_nominal", "engineering_high"):
        p1500 = selected_rows[(scenario, report_electrical_id, 1500.0)]["joint_raw_bit_read_error_probability"]
        p86400 = selected_rows[(scenario, report_electrical_id, 86400.0)]["joint_raw_bit_read_error_probability"]
        readme += f"| {scenario} | {p1500:.6e} | {p86400:.6e} |\n"
    readme += """

## Hard boundary

The proton package combines a 28 nm FDSOI standalone SRAM at 2-8 MeV with a 28 nm bulk Kintex-7 configuration SRAM at 80-184 MeV. It is an explicit cross-device engineering proxy. Package/BEOL penetration, the 8-80 MeV response, target layout MBU mapping, SEL/SEFI, target-specific TID electrical behavior and target PDK statistics remain unresolved.
"""
    (args.output_dir / "README.md").write_text(readme, encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
