# 14.32 krad(Si) 的 28 nm TID 工程包络

公开资料不足以建立目标 MASK ROM 的 foundry-calibrated TID compact model。多数 28 nm bulk CMOS 实验从约 0.5 Mrad(SiO2) 起测，明显高于本任务 14.32 krad(Si)，因此本工程只使用三档条件角：

| corner | NMOS ΔVth | |PMOS Vth|变化 | mobility scale | off-current multiplier | 含义 |
|---|---:|---:|---:|---:|---|
| central_data_consistent | 0 mV | 0 mV | 1.00 | 1× | 低剂量中心 |
| conservative | -1 mV | +1 mV | 0.99 | 2× | 工程不确定性 |
| stress_not_a_fit | -3 mV | +3 mV | 0.98 | 10× | 压力筛选，不是拟合 |

机器值在 `../configs/TID_28nm_parameter_envelope.json`。三档都应运行；它们没有统计权重，也不能称为置信区间或实测退化系数。

在网表中的用法：

- 通过 BSIM4 instance `DELVTO` 加阈值偏移；
- 通过 `MULU0` 缩放迁移率；
- STI 额外漏电作为未选单元数量相关的附加列电流处理，不强迫主沟道模型拟合未测的隔离区机制；
- 对每档重跑 read-0/read-1、裕量、时序和 Qcrit。

文献锚点：

- https://doi.org/10.1088/1748-0221/12/02/C02003
- https://doi.org/10.1109/TNS.2017.2746719
- https://doi.org/10.1109/TNS.2018.2878105
- https://indico.cern.ch/event/1317761/attachments/2958649/5203176/NSREC_2024_short_course.pdf

最接近几何的 28 nm nMOS STI 漏电功率律外推得到 14.32 krad 下约 `1.001938786×`，但该剂量低于论文首个实测点，故只作为中心锚点。更高两档用于敏感性筛选，不表示它们更可能发生。
