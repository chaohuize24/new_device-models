# SRAM joint measured-proxy radiation/state package

## Result

The target SPENVIS LET and proton spectra were integrated against measured 28 nm memory-class proxy responses. Particle-channel rates are added as Poisson arrival intensities; circuit and radiation error probabilities are **not** combined by an independent union.

| Scenario | Heavy-ion rate (/bit/s) | Proton rate (/bit/s) | Total (/bit/s) | Upsets/bit/day |
|---|---:|---:|---:|---:|
| partial_low | 7.667869e-15 | 4.971390e-14 | 5.738177e-14 | 4.957785e-09 |
| engineering_nominal | 1.061244e-13 | 6.565021e-14 | 1.717746e-13 | 1.484132e-08 |
| engineering_high | 8.078259e-13 | 9.612594e-14 | 9.039518e-13 | 7.810144e-08 |


`partial_low` is a measured-energy-band partial contribution, not a target lower bound. `engineering_nominal` bridges an unmeasured 8-80 MeV interval across two different technologies. `engineering_high` deliberately applies the 80 MeV Kintex-7 value across that gap. None of the three is a confidence interval or one physical device response curve.

## Joint state/read model

The active electrical table is loaded from the PTM32 ngspice access Monte Carlo. Its point estimates are population fractions under declared engineering mismatch priors. They are not temporal-noise BER, foundry yield, or target-macro confidence bounds. The selected report row is `ptm32_access_nominal__tid_central`. A total target claim still requires:

- foundry PDK statistical models and target PEX;
- sufficient rare-event sampling or validated tail/importance sampling;
- temporal-noise and target timing distributions.

Selected joint raw-bit error probabilities (the current PTM32 point estimates add no observed circuit failures):

| Scenario | 1500 s scrub | 86400 s rewrite |
|---|---:|---:|
| partial_low | 4.303630e-11 | 2.478892e-09 |
| engineering_nominal | 1.288309e-10 | 7.420662e-09 |
| engineering_high | 6.779639e-10 | 3.905072e-08 |


## Hard boundary

The proton package combines a 28 nm FDSOI standalone SRAM at 2-8 MeV with a 28 nm bulk Kintex-7 configuration SRAM at 80-184 MeV. It is an explicit cross-device engineering proxy. Package/BEOL penetration, the 8-80 MeV response, target layout MBU mapping, SEL/SEFI, target-specific TID electrical behavior and target PDK statistics remain unresolved.
