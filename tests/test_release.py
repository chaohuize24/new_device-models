from __future__ import annotations

import csv
import json
import math
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sram/src"))

from sram_check.system_state import (  # noqa: E402
    bit_wrong_probability_after_reset,
    mean_bit_wrong_probability_uniform_reads,
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def test_sram_final_delivery_matches_state_equations() -> None:
    rows = read_csv(ROOT / "sram/results/final_ber/final_read_write_ber.csv")
    assert len(rows) == 3
    for row in rows:
        rate = float(row["total_sbu_toggle_rate_per_bit_s"])
        interval = float(row["refresh_interval_s"])
        assert math.isclose(
            float(row["single_read_ber_mean_uniform_in_refresh_interval"]),
            mean_bit_wrong_probability_uniform_reads(rate, interval),
            rel_tol=1e-12,
        )
        assert math.isclose(
            float(row["single_read_ber_at_refresh_endpoint"]),
            bit_wrong_probability_after_reset(rate, interval),
            rel_tol=1e-12,
        )


def test_sram_nominal_value() -> None:
    rows = read_csv(ROOT / "sram/results/final_ber/final_read_write_ber.csv")
    nominal = next(row for row in rows if row["scenario"] == "engineering_nominal")
    assert math.isclose(
        float(nominal["single_read_ber_mean_uniform_in_refresh_interval"]),
        1.2883093759230154e-10,
        rel_tol=1e-12,
    )


def test_xte_independent_order_check() -> None:
    rows = read_csv(ROOT / "sram/validation/xte/validation_summary.csv")
    ratios = [float(row["predicted_over_published"]) for row in rows]
    assert math.isclose(ratios[0], 1.630963, rel_tol=2e-6)
    assert math.isclose(ratios[1], 2.088289, rel_tol=2e-6)
    assert all(row["within_one_order_of_magnitude"] == "True" for row in rows)


def test_rom_heavy_ion_curve_is_monotone() -> None:
    path = ROOT / "rom/results/rom_heavy_ion_cross_section.tsv"
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    for level in {row["level"] for row in rows}:
        values = [
            float(row["sigma_cm2_per_active_read_bit"])
            for row in rows
            if row["level"] == level
        ]
        assert all(b >= a for a, b in zip(values, values[1:]))


def test_mram_heavy_ion_curve_is_monotone() -> None:
    path = ROOT / "mram/results/mram_heavy_ion_cross_section.tsv"
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    for level in {row["level"] for row in rows}:
        values = [
            float(row["sigma_cm2_per_active_read_bit"])
            for row in rows
            if row["level"] == level
        ]
        assert all(b >= a for a, b in zip(values, values[1:]))


def test_interfaces_separate_channels() -> None:
    expected = {
        "persistent_state",
        "transient_read",
        "post_write",
        "correlated_macro_event",
        "permanent_failure",
    }
    for name in ("sram_device_delivery.json", "rom_device_delivery.json", "mram_device_delivery.json"):
        payload = json.loads((ROOT / "interfaces" / name).read_text(encoding="utf-8"))
        assert payload["schema_version"] == 2
        assert set(payload["channels"]) == expected
    rom = json.loads((ROOT / "interfaces/rom_device_delivery.json").read_text(encoding="utf-8"))
    assert rom["channels"]["transient_read"]["search_ready"] is False
    mram = json.loads((ROOT / "interfaces/mram_device_delivery.json").read_text(encoding="utf-8"))
    assert mram["channels"]["transient_read"]["search_ready"] is False
    assert mram["channels"]["persistent_state"]["status"] == "missing"
    assert mram["channels"]["post_write"]["status"] == "screening_only"
    assert mram["channels"]["transient_read"]["results"]["proton_lower_bound_nominal"] > 0
    post = mram["channels"]["post_write"]["results"]
    assert "general_sot_7_1" in post and "fab_led_2024" in post
    assert post["fab_led_2024"]["write_pulse_width_ns"] == 2.0
    assert post["general_sot_7_1"]["write_pulse_width_ns"] == 1.0
    fab_read = mram["channels"]["transient_read"]["results"]["fab_led_2024"]
    assert fab_read["heavy_ion_lower_bound_nominal"] > 0
    assert 0.5 < fab_read["heavy_ion_nominal_ratio_vs_7_1"] < 1.5
    sram = json.loads((ROOT / "interfaces/sram_device_delivery.json").read_text(encoding="utf-8"))
    assert sram["channels"]["persistent_state"]["search_ready"] is True
    assert sram["channels"]["transient_read"]["status"] == "missing"


def test_release_hygiene() -> None:
    forbidden_names = {"__pycache__", ".pytest_cache", ".DS_Store", "tmp", "work", "tools"}
    for path in ROOT.rglob("*"):
        assert path.name not in forbidden_names


def test_all_json_files_parse() -> None:
    for path in ROOT.rglob("*.json"):
        json.loads(path.read_text(encoding="utf-8"))
