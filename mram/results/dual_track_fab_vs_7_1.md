# SOT-MRAM 流片双轨对照

更新日期：2026-08-29

## 目的

同时保留两套工作点，避免把 **电路 compact 仿真电流（§7.1，80–100 μA）** 与 **300 mm 流片实测 Ic（680/880 μA@2 ns）** 混成一个“真值”。

| 轨道 | ID | 回答的问题 | HI/质子读窗 |
|---|---|---|---|
| Circuit compact | `general_sot_7_1` | 电路/variation/默认交付 | **已算（默认）** |
| Fab anchor | `fab_led_2024` | 流片 R/TMR 电学敏感性 + 写筛选 | **已算（对照）** |

文献：Yang et al., IEEE EDL 2024, [doi:10.1109/LED.2024.3454609](https://doi.org/10.1109/LED.2024.3454609)（arXiv:2404.09125）。

## 参数对照

| 量 | §7.1 compact | fab_led_2024 |
|---|---:|---:|
| TMR | 100% | 119% |
| R_P / R_AP | 10 / 20 kΩ | 10.89 / 23.85 kΩ |
| R_SOT | 776 Ω | 776 Ω（实测均值） |
| I_C | 80 μA | 680 / 880 μA @ 2 ns |
| I_write（写筛选） | 100 μA | 1020 μA |
| 写脉冲 | 1 ns | 2 ns |

流片原文 B_ext=±20 mT **未建模**。

## 读窗口 HI / 质子（方案二，2026-08-29）

同一套 RPP + SPENVIS；仅 MTJ 电阻/TMR 换成流片值。64 samples/level。

| 量 | §7.1 | fab_led_2024 | fab / §7.1 |
|---|---:|---:|---:|
| HI nominal（0.72 ns） | **1.417×10⁻²⁴** | **1.296×10⁻²⁴** | **0.915** |
| HI low | 1.389×10⁻²⁶ | 1.285×10⁻²⁶ | ~0.93 |
| HI high | 1.578×10⁻¹⁹ | 1.577×10⁻¹⁹ | ~1.00 |
| 质子下界 nominal | 3.044×10⁻¹⁹ | 3.026×10⁻¹⁹ | **0.994** |

**解读：** 换成流片电阻后，中心读错误下界几乎不变（HI 约低 8.5%，质子几乎相同）。说明当前读窗结果对 **10k 级 R / ~100% TMR** 不敏感；**默认交付仍用 §7.1**。写电流量级差异（80 μA vs 680 μA）不在本读链里消除。

机器可读对照：`results/fab_led_2024_read_delivery_comparison.json`。

复现：

```bash
python mram/scripts/run_fab_led_2024_read_delivery.py
```

## 读路径功能筛选

| variant | functional_pass |
|---|---|
| general_sot_7_1 / fab_led_2024 / fab_led_2024_array_tuned / §7.2 / array_tuned_7_1 | ✓ |
| legacy_scaled_proxy | ✗ |

## 写窗口 Qcrit 快筛

| 轨道 | min write Qcrit | min hold | write/hold | bound |
|---|---:|---:|---:|---|
| general_sot_7_1 | 0.00625 fC | 0.00625 fC | **1.0** | bracketed |
| fab_led_2024 | **≥512 fC** | 0.00625 fC | **>81920** | right-censored |

## 文件入口

| 文件 | 用途 |
|---|---|
| `netlists/sot_mram_hierarchical_senseamp_fab_led_2024.cir` | 流片电阻读网表 |
| `scripts/run_fab_led_2024_read_delivery.py` | 流片轨 HI/质子一键链 |
| `results/*_fab_led_2024.*` | 流片轨结果（不覆盖 §7.1 表） |
| `interfaces/mram_device_delivery.json` | 默认 §7.1 + `transient_read.results.fab_led_2024` 对照 |
