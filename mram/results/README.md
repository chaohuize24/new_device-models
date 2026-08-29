# SOT-MRAM 重离子读窗口结果

## 可直接引用的结果（默认：§7.1）

目标环境为 400 km、51.6°、5 年、1.0 g/cm² 铝等效屏蔽。读窗口 0.72 ns。

电气/Qcrit 默认基线：**参数汇总 §7.1**（10 kΩ / 20 kΩ），array-tuned 读网表。characterize：64 samples/level（2026-08-28）。

| 场景 | 连续敏感重离子率 (/bit/s) | 0.72 ns active-bit 读窗口概率 |
|---|---:|---:|
| low | 1.929e-17 | 1.389e-26 |
| **nominal** | **1.968e-15** | **1.417e-24** |
| high | 2.192e-10 | 1.578e-19 |

建议正文采用 **nominal**：`1.417e-24`。质子下界 nominal：`3.04e-19`。

## 流片轨对照（fab_led_2024，方案二）

同一方法，电阻改为 10.89 / 23.85 kΩ（TMR 119%），2026-08-29：

| 场景 | HI 读窗口概率 | 相对 §7.1 |
|---|---:|---:|
| **nominal** | **1.296e-24** | **0.915×** |
| 质子下界 nominal | 3.026e-19 | 0.994× |

详见 `dual_track_fab_vs_7_1.md`、`fab_led_2024_read_delivery_comparison.json`。

## 指标定义

- 只对 **CMOS 读外围**（GBL/SA）做 Qcrit + RPP + LET 积分；MTJ 用电阻读代理。
- 与 ROM 同方法论；与 SRAM 驻留 BER **不可直接比较**。
- `low / nominal / high` 是工程包络，不是统计置信区间。

## 复现

```bash
# 默认 §7.1
python mram/scripts/run_sot_mram_delivery.py
python mram/scripts/run_mram_proton_read_integration.py

# 流片轨（不覆盖上面的表）
python mram/scripts/run_fab_led_2024_read_delivery.py
```
