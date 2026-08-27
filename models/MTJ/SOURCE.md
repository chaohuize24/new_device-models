# SOT-MTJ compact parameters provenance

This release uses a **resistor-capacitor proxy** for the magnetic tunnel junction in ngspice read-path simulations. It is not a micromagnetic or STT/SOT switching compact model.

## Primary literature anchors

| Parameter | Value | Source |
|---|---:|---|
| TMR | 119% | Perpendicular SOT-MTJ on 300 mm wafer, mean of 234 devices (arXiv:2404.09125) |
| R_P (parallel) | 10.89 kΩ | Same |
| R_AP (antiparallel) | 23.85 kΩ | Derived: R_P × (1 + TMR/100) |
| I_c P→AP @ 2 ns | 680 μA | Same |
| I_c AP→P @ 2 ns | 880 μA | Same |
| R_SOT channel | 776 Ω | Same (write path; not in read Qcrit netlist) |
| Δ (thermal stability) | ~59 | IEEE VLSI-TSA 2023 co-optimization paper (order-of-magnitude anchor) |
| Write pulse (demo) | 2 ns | arXiv:2404.09125 minimum demonstrated pulse width |

## Engineering substitutes (no layout / no foundry PDK)

| Parameter | Value | Rationale |
|---|---:|---|
| C_MTJ (read Qcrit) | 5 fF | Scaled read proxy for 256-row BL loading (`read_proxy_v1`) |
| C_MTJ (literature order) | 40 fF | Typical order-of-magnitude MTJ capacitance (`literature_capacitance` variant) |
| R_REF | 7.416 kΩ (proxy) / 16.17 kΩ (literature) | Midpoint √(R_P×R_AP) per variant |
| Access WN | 480 nm (proxy) / up to 1200 nm (literature-tuned) | Read margin vs arXiv:2404.09125 R_P loading |
| NLEAK | 127.5 | Average unselected-cell leakage count on 256-row local BL (same proxy as ROM `NPRESENT`) |

## Read-path variant screen (`mram/results/read_path_sensitivity.tsv`)

All four documented variants pass nominal READ0/READ1 at 0.72 ns after timing tuning:

- **read_proxy_v1** — characterized Qcrit baseline (scaled R/C).
- **literature_resistance** — measured R_P/R_AP + widened access.
- **literature_capacitance** — 40 fF C_MTJ order-of-magnitude.
- **literature_combined_tuned** — literature R + 1200 nm access + extended SA timing.

Re-characterizing Qcrit at literature R remains future work; functional screen shows read margin is recoverable without abandoning literature resistance anchors.

## Write-path screen (`post_write` channel)

Separate netlists in `mram/netlists/sot_dynamic_strike/`:

- SOT current pulse 800 µA / 2 ns (literature order: 680/880 µA, arXiv:2404.09125).
- Double-exponential collected-charge Qcrit during write vs hold on 1T1MTJ cell.
- Hold screen uses high-Z MTJ proxy (500 kΩ); not a storage flip model.

## Radiation literature (not converted to σ curves in v1)

- MTJ storage is reported intrinsically tolerant to heavy-ion bit flips; failures concentrate in CMOS periphery (IEEE TMAG 2018.2830701; APCCAS 2022 STT-MRAM; TNS 2025 SOT-MRAM arrays).
- TNS 2025 reports stable I_c/TMR/BER under Bi/Ta/Kr irradiation, with occasional MgO short-circuit failures at extreme LET — not modeled as per-bit toggle in v1.

Replace this proxy with target-process PDK + PEX + calibrated Verilog-A / micromagnetic MTJ before silicon-level absolute claims.
