# SOT-MRAM 交付

## 直接使用

- 联合 Qcrit 样本：`results/mram_joint_qcrit_samples.tsv`
- 重离子截面曲线：`results/mram_heavy_ion_cross_section.tsv`
- 目标 LET 谱积分：`results/mram_spenvis_heavy_ion_rate.tsv`
- 质子读瞬态积分：`results/mram_spenvis_proton_rate.tsv`、`results/mram_proton_read_summary.json`
- 不同逻辑读取宽度：`results/mram_read_ber_by_width.tsv`
- 读路径裕量扫描：`results/mram_spice_response.tsv`
- 读路径文献/代理变体：`results/read_path_sensitivity.tsv`
- SOT 写窗口 Qcrit 筛选：`results/write_strike_screen/summary.json`
- 机器接口：`../interfaces/mram_device_delivery.json`

## 电路

`netlists/sot_mram_hierarchical_senseamp.cir` 是当前主网表：2048×128 阵列的代表性一列，**1T1MTJ** 读单元（P/AP 电阻代理 + C_MTJ），256 行/局部段，CMOS 分段选择，4:1 列选，全局差分位线，参考 dummy MTJ 和时钟差分锁存感放。

MTJ 电学参数见 `../models/MTJ/sot_mtj_parameters.json` 与 `../models/MTJ/SOURCE.md`。文献锚点为 arXiv:2404.09125（300 mm SOT-MTJ：TMR 119%、R_P 10.89 kΩ）；网表读路径使用 **5 kΩ / 10.95 kΩ** 缩放代理以匹配阵列 BL 负载（见 SOURCE.md）。

SOT 写路径（独立 SOT 通道、Ic≈680–880 μA @ 2 ns）已提供 **写窗口 Qcrit 筛选**（`post_write` 通道，`screening_only`），见 `netlists/sot_dynamic_strike/` 与 `scripts/run_sot_write_strike_screen.py`。不是绝对动态写截面或 intrinsic WER。

读路径除 scaled proxy 外，`configs/read_path_variants.json` 记录了文献 R/C 变体；`scripts/run_read_path_sensitivity.py` 验证四类变体在 0.72 ns 读窗口内均可功能读通。

## 运行（需要 ngspice）

默认 ngspice 路径在 `configs/pipeline_defaults.json`（指向 `Spice64/bin`）。也可设置环境变量 `NGSPICE` 或传 `--ngspice`。

```bash
python mram/scripts/sot_mram_heavy_ion_pipeline.py characterize --samples 64 --tolerance-fc 0.5
python mram/scripts/sot_mram_heavy_ion_pipeline.py cross-section
python mram/scripts/summarize_read_ber.py
python mram/scripts/sweep_sot_mram_spice_response.py
python mram/scripts/run_read_path_sensitivity.py
python mram/scripts/run_mram_proton_read_integration.py
python mram/scripts/run_sot_write_strike_screen.py --quick
```

或一键：

```bash
python mram/scripts/run_sot_mram_delivery.py
```

## 结果边界

- **已实现**：CMOS 读外围重离子 + 质子读窗口工程下界（`transient_read`，分 HI/质子子结果，不可直接相加）；读路径文献变体功能筛选；SOT 写窗口 Qcrit 比（`post_write`，`screening_only`）。
- **未实现**：MTJ 存储态翻转率；译码/控制 SET；SOT 写路径绝对动态截面 / intrinsic WER。
- 绝对截面仍受 RPP 面积/深度/收集效率支配，`search_ready=false`。

## 与 SRAM/ROM 的关系

- 环境谱共用 `environment/target_orbit/`。
- 不可与 SRAM 驻留 BER 或 ROM 掩膜通道直接排序；必须按 v2 接口分通道消费。
