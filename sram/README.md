# SRAM 交付

## 直接使用

- 最终单 bit 结果：`results/final_ber/final_read_write_ber.csv`
- 驻留/重写时间扫描：`results/final_ber/refresh_interval_sweep.csv`
- 物理率分量：`results/radiation/physical_rate_scenarios.csv`
- 架构延时/能量/面积表：`results/architecture_lut/SRAM_latency_energy_area_LUT.xlsx`
- 机器接口：`../interfaces/sram_device_delivery.json`

## 代码与电路

- `scripts/run_sram_joint_proxy_chain.py`：目标 LET/质子谱与公开实测代理响应积分。
- `scripts/build_sram_target_orbit_final_ber.py`：把 SBU toggle rate 转成给定驻留/重写间隔的错态概率。
- `scripts/run_ptm32_access_engineering_mc.py`：6T 单元、局部/全局差分位线、列选、预充均衡和锁存感放的条件功能扫描。
- `scripts/run_ptm32_architecture_lut.py`：阵列尺寸、局部位线深度、列复用和运行角的相对延时/能量/面积 LUT。
- `scripts/run_ptm32_write_strike_screen.py`：有限 CMOS 写驱动与 transmission-gate 选中支路上的双指数电荷注入筛选。

## 外围结构

基准组织为 128 行/局部位线、4:1 列复用。每个复用后输出 bit 配一个差分锁存感放；128 个物理列在 4:1 复用下对应 32 个并行输出与 32 个感放。网表显式包含选中路径，不包含完整地址译码、控制树、未选 mux 分支和 PEX。

结果中的电路“零失败”是工程先验条件下的功能筛选，不得作为 per-access 电噪声 BER。绝对辐射结果目前只对 persistent-state 通道给出跨器件数量级包络。
