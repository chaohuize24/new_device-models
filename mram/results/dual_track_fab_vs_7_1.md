# SOT-MRAM 流片双轨对照（阶段 B）

更新日期：2026-08-28

## 目的

同时保留两套工作点，避免把 **电路 compact 仿真电流（§7.1，80–100 μA）** 与 **300 mm 流片实测 Ic（680/880 μA@2 ns）** 混成一个“真值”。

| 轨道 | ID | 回答的问题 | HI/质子 Qcrit |
|---|---|---|---|
| Circuit compact | `general_sot_7_1` | 电路/variation/读 BER 下界 | **是（默认交付）** |
| Fab anchor | `fab_led_2024` | 器件物理量级、写窗口电学脆弱性对照 | **否**（未重跑 characterize） |

文献：Yang et al., IEEE EDL 2024, [doi:10.1109/LED.2024.3454609](https://doi.org/10.1109/LED.2024.3454609)（arXiv:2404.09125）。

## 参数对照

| 量 | §7.1 compact | fab_led_2024 |
|---|---:|---:|
| TMR | 100% | 119% |
| R_P / R_AP | 10 / 20 kΩ | 10.89 / 23.85 kΩ |
| R_SOT | 776 Ω（共用通道电阻） | 776 Ω（实测均值） |
| I_C | 80 μA | 680 μA (P→AP) / 880 μA (AP→P) @ 2 ns |
| I_write（筛选） | 100 μA | 1020 μA (=1.5×680) |
| 写脉冲 | 1 ns | 2 ns |
| 写驱动 NMOS/PMOS | 400 / 800 nm | 1200 / 2400 nm |

流片原文使用 **B_ext = ±20 mT** 辅助场；本 ngspice 代理**未建模**外场。

## 读路径功能筛选

`python mram/scripts/run_read_path_sensitivity.py`

| variant | functional_pass | min_diff_dev (V) |
|---|---:|---:|
| general_sot_7_1 | ✓ | ~0.038 |
| fab_led_2024 | ✓ | （见 TSV） |
| fab_led_2024_array_tuned | ✓ | （见 TSV） |
| optimized_nature_7_2 | ✓ | |
| array_tuned_7_1 | ✓ | |
| legacy_scaled_proxy | ✗ | |

详表：`results/read_path_sensitivity.tsv`、`read_path_sensitivity_summary.json`。

## 写窗口 Qcrit 快筛（`--quick`）

```bash
# §7.1
python mram/scripts/run_sot_write_strike_screen.py --quick \
  --output-dir results/write_strike_screen

# fab
python mram/scripts/run_sot_write_strike_screen.py --quick \
  --config configs/sot_write_strike_screen_fab_led_2024.json \
  --output-dir results/write_strike_screen_fab_led_2024
```

| 轨道 | min write Qcrit | min hold Qcrit | write/hold | write bound |
|---|---:|---:|---:|---|
| general_sot_7_1 | 0.00625 fC | 0.00625 fC | **1.0** | bracketed |
| fab_led_2024 | **512 fC** | 0.00625 fC | **>81920** | right-censored（至 512 fC 未翻） |

解读（screening_only）：

- Hold 侧两轨相近（同为高阻 MTJ hold 代理）。
- Fab 轨在更强写电流 + 加宽驱动下，写窗口对双指数注入在 512 fC 内**未观察到翻转** → 写相对 hold 更“硬”，比值是**稳健性下界**，不是 WER。
- §7.1 轨写/hold ≈ 1，与低裕量 compact 电流一致，适合 variation/电路灵敏度叙事。

## 复现入口

| 文件 | 用途 |
|---|---|
| `models/MTJ/sot_mtj_parameters.json` → `workpoints.fab_led_2024` | 参数源 |
| `models/MTJ/SOURCE.md` | 双轨说明 |
| `configs/read_path_variants.json` | 读变体 |
| `configs/sot_write_strike_screen.json` | §7.1 写筛选 |
| `configs/sot_write_strike_screen_fab_led_2024.json` | fab 写筛选 |
| `interfaces/mram_device_delivery.json` → `post_write.results` | 双轨机器可读结果 |

**不要**用 fab 轨数字替换 HI/质子 delivery，除非重新 `characterize` 流片电阻网表。
