# SOT-MTJ compact parameters provenance

Primary source: **`SOT-MRAM辐照错误建模参数汇总.md`** (课题组参数汇总表).  
Machine-readable mirror: `sot_mtj_parameters.json`.

This release uses a **resistor-capacitor proxy** for the MTJ in ngspice read-path simulations. It is not a micromagnetic or STT/SOT switching compact model.

## Dual track (2026-08-28)

| Track | ID | Role | Key numbers |
|---|---|---|---|
| **Circuit compact (default)** | `general_sot_7_1` | HI/proton Qcrit + delivery JSON | TMR 100%, 10/20 kΩ, I_W=100 μA, I_C=80 μA, 1 ns |
| **Fab anchor** | `fab_led_2024` | Device-physics dual track (read + write screen) | TMR 119%, 10.89/23.85 kΩ, I_C=680/880 μA@2 ns, I_W=1020 μA |

Do **not** mix write currents across tracks. Fab paper uses external assist field (±20 mT); ngspice proxy does not model B_ext.

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

## Fab workpoint (`fab_led_2024`)

Source: Yang et al., *IEEE Electron Device Letters* 2024 ([doi:10.1109/LED.2024.3454609](https://doi.org/10.1109/LED.2024.3454609)), arXiv:2404.09125.

| Parameter | Value |
|---|---:|
| TMR | 119% |
| R_P | 10.89 kΩ |
| R_AP | 23.849 kΩ (= R_P×(1+TMR)) |
| R_SOT | 776 Ω |
| I_c P→AP / AP→P @ 2 ns | 680 / 880 μA |
| I_write (screen) | 1020 μA (=1.5×680) |
| Write pulse | 2 ns |

Configs: `mram/configs/sot_write_strike_screen_fab_led_2024.json`, read variants `fab_led_2024` / `fab_led_2024_array_tuned`.

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

## Radiation modeling scope

- **Modeled:** CMOS read periphery SEE (Qcrit + RPP + SPENVIS) on **§7.1** netlist; SOT write-window Qcrit screen on **both** tracks.
- **Not modeled:** MTJ storage flip σ; SEFI/SEL; fab B_ext; absolute write BER.
- **Reference SEE default:** σ_SEU = 1×10⁻¹² cm²/bit (summary §5.2, not converted to absolute rate in v1).

Replace R/C proxy with foundry PDK + PEX + micromagnetic MTJ before silicon-level absolute claims.
