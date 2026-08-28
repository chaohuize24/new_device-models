# SOT-MTJ compact parameters provenance

Primary source: **`SOT-MRAM辐照错误建模参数汇总.md`** (课题组参数汇总表).  
Machine-readable mirror: `sot_mtj_parameters.json`.

This release uses a **resistor-capacitor proxy** for the MTJ in ngspice read-path simulations. It is not a micromagnetic or STT/SOT switching compact model.

## Baseline workpoint (§7.1 通用 SOT-MRAM 模型)

| Parameter | Value | Summary reference |
|---|---:|---|
| TMR | 100% | §7.1 |
| R_P (R_L) | 10 kΩ | §7.1 / §2 |
| R_AP (R_H) | 20 kΩ | §7.1 / §2 |
| R_REF | 14.14 kΩ | √(R_P×R_AP) |
| Δ | 32 | §7.1 |
| I_write | 100 μA | §7.1 / §3 |
| I_read | 30 μA | §7.1 / §3 |
| I_CSOT | 80 μA | §7.1 |
| T_switch | 1 ns | §7.1 / §3 |
| RSD | 8% | §7.1 |
| σ_VOS (SA) | 6 mV | §7.1 |
| V_PRE | 0.3 V | §7.1 |
| μ_SM / σ_SM | 45 mV / 10 mV | §3 |
| R_load | 50 kΩ | §3 (hold/write screen proxy) |

Hierarchical read netlist uses **array_tuned_7_1**: same R/TMR, WN=1200 nm, extended SA timing for 2048×128 BL loading.

## Optimized variant (§7.2 Nat. Commun.)

| Parameter | Value |
|---|---:|
| TMR | 150% |
| R_P | 8 kΩ |
| R_AP | 20 kΩ |
| Δ | 50 |
| I_CSOT | 45 μA |
| RSD | 6% |
| σ_VOS | 4 mV |
| V_PRE | 0.25 V |

See `mram/configs/read_path_variants.json` for functional screens.

## Radiation modeling scope (from summary §1, §5)

- **Modeled in v2 pipeline:** CMOS read periphery SEE (Qcrit + RPP + SPENVIS); SOT write-window Qcrit screen.
- **Not modeled:** MTJ storage flip σ; SEFI/SEL; TID TMR(I) analytic curves (§5.1) — TID corners remain CMOS electrical only.
- **Reference SEE default:** σ_SEU = 1×10⁻¹² cm²/bit (summary §5.2, not converted to absolute rate in v1).

## Supplementary fab anchor (not default baseline)

| Parameter | Value | Source |
|---|---:|---|
| TMR | 119% | arXiv:2404.09125 (300 mm demo) |
| R_P | 10.89 kΩ | Same |
| I_c @ 2 ns | 680 / 880 μA | Same |

Kept in `supplementary_fab_anchors`; superseded for default workpoint by summary §7.1.

## Legacy note

Previous **5 kΩ / 10.95 kΩ** scaled proxy (`legacy_scaled_proxy`) matches the **existing Qcrit TSV** until `characterize` is re-run at §7.1 parameters.

Replace R/C proxy with foundry PDK + PEX + micromagnetic MTJ before silicon-level absolute claims.
