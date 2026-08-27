#!/usr/bin/env python3
"""Build the final target-orbit SRAM radiation-only BER delivery package.

The package reports raw SBU toggle rates, refresh-aware read BER, and a
conservative write-window radiation-event proxy.  It deliberately does not
turn finite ngspice mismatch samples into a per-access temporal BER.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sram_check.system_state import (  # noqa: E402
    bit_wrong_probability_after_reset,
    mean_bit_wrong_probability_uniform_reads,
)


DEFAULT_CONFIG = ROOT / "configs/sram_target_orbit_final_ber.json"
DEFAULT_OUTPUT = ROOT / "results/final_ber"
SECONDS_PER_DAY = 86400.0


def resolve(config_path: Path, text: str) -> Path:
    return (config_path.parent / text).resolve()


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError(f"cannot write empty table: {path}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def at_least_one_event_probability(rate_per_s: float, interval_s: float) -> float:
    return -math.expm1(-float(rate_per_s) * float(interval_s))


def independent_word_error_probability(bit_error_probability: float, bits: int) -> float:
    p = float(bit_error_probability)
    if p <= 0.0:
        return 0.0
    if p >= 1.0:
        return 1.0
    return -math.expm1(int(bits) * math.log1p(-p))


def build(config_path: Path, output_dir: Path) -> dict:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    rates_path = resolve(config_path, config["radiation_rate_input"]["path"])
    rate_rows = load_csv(rates_path)
    by_id = {row["radiation_scenario"]: row for row in rate_rows}
    order = config["radiation_rate_input"]["scenario_order"]
    if set(order) != set(by_id):
        raise ValueError(f"scenario mismatch: expected {order}, got {sorted(by_id)}")

    operation = config["operation_model"]
    refresh_s = float(operation["fixed_refresh_interval_s"])
    write_window_s = float(operation["write_vulnerable_window_s"])
    read_window_s = float(operation["read_sense_window_s"])
    word_bits = int(operation["example_word_bits"])
    array_bits = int(operation["example_array_bits"])

    final_rows = []
    for scenario_id in order:
        source = by_id[scenario_id]
        rate = float(source["total_physical_toggle_rate_per_bit_s"])
        read_mean = mean_bit_wrong_probability_uniform_reads(rate, refresh_s)
        read_endpoint = bit_wrong_probability_after_reset(rate, refresh_s)
        write_upper = at_least_one_event_probability(rate, write_window_s)
        read_window_upper = at_least_one_event_probability(rate, read_window_s)
        final_rows.append(
            {
                "scenario": scenario_id,
                "heavy_ion_rate_per_bit_s": float(source["heavy_ion_rate_per_bit_s"]),
                "proton_rate_per_bit_s": float(source["proton_rate_per_bit_s"]),
                "total_sbu_toggle_rate_per_bit_s": rate,
                "upsets_per_bit_day": rate * SECONDS_PER_DAY,
                "refresh_interval_s": refresh_s,
                "single_read_ber_mean_uniform_in_refresh_interval": read_mean,
                "single_read_ber_at_refresh_endpoint": read_endpoint,
                "single_32bit_word_read_error_mean_independent_bits": independent_word_error_probability(read_mean, word_bits),
                "single_write_radiation_ber_upper_proxy": write_upper,
                "single_32bit_word_write_error_upper_proxy": independent_word_error_probability(write_upper, word_bits),
                "radiation_event_probability_during_read_window_upper_proxy": read_window_upper,
                "expected_wrong_bits_at_refresh_endpoint_for_262144bit_array": array_bits * read_endpoint,
                "is_statistical_confidence_bound": False,
                "interpretation": source["interpretation"],
            }
        )

    sweep_rows = []
    for interval_s in operation["residence_time_scan_s"]:
        for row in final_rows:
            rate = float(row["total_sbu_toggle_rate_per_bit_s"])
            mean_read = mean_bit_wrong_probability_uniform_reads(rate, interval_s)
            endpoint_read = bit_wrong_probability_after_reset(rate, interval_s)
            sweep_rows.append(
                {
                    "scenario": row["scenario"],
                    "refresh_interval_s": interval_s,
                    "single_read_ber_mean_uniform": mean_read,
                    "single_read_ber_endpoint": endpoint_read,
                    "single_32bit_word_read_error_mean_independent_bits": independent_word_error_probability(mean_read, word_bits),
                    "single_write_radiation_ber_upper_proxy": row["single_write_radiation_ber_upper_proxy"],
                    "expected_wrong_bits_at_endpoint_for_262144bit_array": array_bits * endpoint_read,
                }
            )

    result = {
        "schema_version": 1,
        "claim_scope": config["claim_scope"],
        "target_orbit": config["target_orbit"],
        "fixed_operation_assumptions": operation,
        "peripheral_design": config["peripheral_design"],
        "final_per_bit_results": final_rows,
        "recommended_report_row": next(row for row in final_rows if row["scenario"] == "engineering_nominal"),
        "engineering_envelope": {
            "low_scenario": "partial_low",
            "central_scenario": "engineering_nominal",
            "high_scenario": "engineering_high",
            "statistical_confidence_level": None,
            "reason": "cross-device measured-proxy and unsupported-energy-gap scenario envelope, not repeated measurements of one target device",
        },
        "electrical_boundary": config["electrical_boundary"],
        "excluded": config["excluded"],
        "source_files": {
            "physical_rates": "sram/results/radiation/physical_rate_scenarios.csv",
            "heavy_ion_curve": "sram/results/radiation/heavy_ion_curve_and_spectrum.csv",
            "proton_curve": "sram/results/radiation/proton_curve_and_spectrum.csv",
            "spenvis_spectrum": "environment/target_orbit/average_LET_proton_and_ion_spectra.txt",
        },
        "validation_status": {
            "numeric_integration": "matched SPENVIS same-response integration within 0.1% in RXTE validation",
            "in_orbit_quantity_of_order": "RXTE HM628128 blind anchors were overpredicted by factors 1.631 and 2.088; one of two preregistered factor-of-two gates passed",
            "target_28nm_absolute_prediction": False,
        },
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "final_read_write_ber.csv", final_rows)
    write_csv(output_dir / "refresh_interval_sweep.csv", sweep_rows)
    (output_dir / "final_delivery.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    nominal = result["recommended_report_row"]
    low = final_rows[0]
    high = final_rows[-1]
    readme = f"""# 目标轨道SRAM辐射BER最终交付

## 可直接引用的结果

目标环境为400 km、51.6°、5年任务、1.0 g/cm²铝等效屏蔽。固定刷新周期为{refresh_s:g} s；假设每次刷新把目标bit恢复为正确状态，读取时刻在刷新区间内均匀分布。

| 场景 | 原始SBU率 (/bit/s) | 单次读BER（区间平均） | 单次读BER（刷新前） | 单次写辐射BER上界代理 |
|---|---:|---:|---:|---:|
"""
    for row in final_rows:
        readme += (
            f"| {row['scenario']} | {row['total_sbu_toggle_rate_per_bit_s']:.6e} | "
            f"{row['single_read_ber_mean_uniform_in_refresh_interval']:.6e} | "
            f"{row['single_read_ber_at_refresh_endpoint']:.6e} | "
            f"{row['single_write_radiation_ber_upper_proxy']:.6e} |\n"
        )
    readme += f"""

建议正文采用`engineering_nominal`：原始SBU率为{nominal['total_sbu_toggle_rate_per_bit_s']:.6e} /bit/s，单次随机时刻读取BER为{nominal['single_read_ber_mean_uniform_in_refresh_interval']:.6e}，刷新前最坏时刻为{nominal['single_read_ber_at_refresh_endpoint']:.6e}。工程场景范围为{low['single_read_ber_mean_uniform_in_refresh_interval']:.6e}--{high['single_read_ber_mean_uniform_in_refresh_interval']:.6e}。

## 指标定义

- 读BER是“存储状态在读取时已经错误”的概率；不包含感测放大器瞬态截面。
- 写BER列是假设当前外围网表的写使能窗口{write_window_s:.3e} s内任一已计入SBU事件都会破坏写入所得的条件化窗口代理。当前没有动态写入截面，因此它不是实测写BER或对未知写入机制的严格上界。
- `partial_low / engineering_nominal / engineering_high`是跨器件工程包络，不是任何置信水平下的统计置信区间。
- 结果不含MBU、ECC、SEL、SEFI和永久故障。

## 可信度边界

积分实现与SPENVIS同响应曲线结果相差小于0.1%。RXTE/HM628128在轨盲比较中，本地预测相对两个在轨锚点分别为1.631倍和2.088倍；因此该链条支持数量级估计，但不支持把本表解释成目标28 nm宏的高精度绝对BER。
"""
    (output_dir / "README.md").write_text(readme, encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = build(args.config.resolve(), args.output_dir.resolve())
    print(json.dumps(result["recommended_report_row"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
