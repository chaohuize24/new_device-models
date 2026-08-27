# MASK NOR-ROM 交付

## 直接使用

- 联合 Qcrit 样本：`results/rom_joint_qcrit_samples.tsv`
- 重离子截面曲线：`results/rom_heavy_ion_cross_section.tsv`
- 目标 LET 谱积分：`results/rom_spenvis_heavy_ion_rate.tsv`
- 不同逻辑读取宽度：`results/rom_read_ber_by_width.tsv`
- code-pattern/寄生裕量：`results/rom_code_pattern_margin.tsv`
- 500 MHz 单角 smoke：`results/rom_500mhz_smoke.tsv`
- 机器接口：`../interfaces/rom_device_delivery.json`

## 电路

`netlists/rom_hierarchical_senseamp.cir` 是当前主网表：2048×128 阵列的代表性一列，256 行/局部段，CMOS 分段选择，4:1 CMOS 列选，全局差分位线，dummy reference 和时钟差分锁存感放。`NPRESENT` 表示选中局部段内已制造下拉 NMOS 的未选单元数量，用于扫描 ROM code pattern 对漏电和裕量的影响。

正式功能与 Qcrit 表都使用主网表和 `scripts/rom_heavy_ion_pipeline.py`；发布版不携带已经被主网表取代的辅助网表。

## 结果边界

本目录只实现重离子读窗口工程下界。代码没有动态质子分支，也不产生可被误当成完整 ROM BER 的合并值。敏感面积、深度和收集效率仍是版图前假设，机器接口因此保持 `search_ready=false`。
