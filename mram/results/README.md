# SOT-MRAM 重离子读窗口结果

## 可直接引用的结果

目标环境为 400 km、51.6°、5 年、1.0 g/cm² 铝等效屏蔽。读窗口 0.72 ns（SA 使能宽度代理）。

电气/Qcrit 基线：**参数汇总 §7.1**（R_P=10 kΩ、R_AP=20 kΩ），层次化读网表 **array-tuned**（TSAEN=2.05 ns）。characterize：64 samples/level（2026-08-28）。

| 场景 | 连续敏感重离子率 (/bit/s) | 0.72 ns active-bit 读窗口概率 |
|---|---:|---:|
| low | 1.929e-17 | 1.389e-26 |
| **nominal** | **1.968e-15** | **1.417e-24** |
| high | 2.192e-10 | 1.578e-19 |

建议正文采用 **nominal**：单 active bit/次读取瞬态 SET 工程下界为 `1.417e-24`。

质子读窗口（同 Qcrit 样本，LET 代理）：nominal 下界 `3.04e-19`，见 `mram_proton_read_summary.json`。

## 指标定义

- 只对 **CMOS 读外围**（GBL/SA）做 Qcrit + RPP + LET 积分；MTJ 用电阻读代理，不含磁翻转。
- 与 ROM 同方法论；与 SRAM 驻留 BER **不可直接比较**。
- `low / nominal / high` 是工程包络，不是统计置信区间。

## 复现

```bash
python mram/scripts/run_sot_mram_delivery.py
python mram/scripts/run_mram_proton_read_integration.py
```

ngspice 默认路径见 `configs/pipeline_defaults.json`（`Spice64/bin/ngspice_con.exe`）。
