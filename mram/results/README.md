# SOT-MRAM 重离子读窗口结果

## 可直接引用的结果

目标环境为 400 km、51.6°、5 年、1.0 g/cm² 铝等效屏蔽。读窗口 0.72 ns（SA 使能宽度代理）。

| 场景 | 连续敏感重离子率 (/bit/s) | 0.72 ns active-bit 读窗口概率 |
|---|---:|---:|
| low | 1.654e-17 | 1.191e-26 |
| **nominal** | **1.500e-15** | **1.080e-24** |
| high | 5.424e-13 | 3.905e-22 |

建议正文采用 **nominal**：单 active bit/次读取瞬态 SET 工程下界为 `1.080e-24`。

## 指标定义

- 只对 **CMOS 读外围**（GBL/SA）做 Qcrit + RPP + LET 积分；MTJ 用电阻读代理，不含磁翻转。
- 与 ROM 同方法论；与 SRAM 驻留 BER **不可直接比较**。
- `low / nominal / high` 是工程包络，不是统计置信区间。

## 复现

```bash
python mram/scripts/sot_mram_heavy_ion_pipeline.py characterize --samples 64 --tolerance-fc 0.5
python mram/scripts/sot_mram_heavy_ion_pipeline.py cross-section
python mram/scripts/summarize_read_ber.py
```

ngspice 默认路径见 `configs/pipeline_defaults.json`（`Spice64/bin/ngspice_con.exe`）。
