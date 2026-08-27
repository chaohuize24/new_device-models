# PTM32 6T SRAM access engineering Monte Carlo

This run measures two write directions and two stored-state read directions for every mismatch sample. The read path includes a 128-row local bitline proxy, one selected branch of a 4:1 column mux, global bitline capacitance and a clocked differential latch sense amplifier.

The probabilities below are population fractions under the declared engineering mismatch priors, conditional on each PVT/TID corner. They are not per-access temporal-noise BER, foundry yield, or target-macro confidence bounds.

| Condition | write wrong | read error given correct state | read error given wrong state | read disturb | min pre-SA margin (mV) |
|---|---:|---:|---:|---:|---:|
| low_vdd_cold__tid_central | 0 | 0 | 1 | 0 | 209.844 |
| low_vdd_cold__tid_conservative | 0 | 0 | 1 | 0 | 208.363 |
| low_vdd_cold__tid_stress_not_a_fit | 0 | 0 | 1 | 0 | 215.142 |
| low_vdd_hot__tid_central | 0 | 0 | 1 | 0 | 56.161 |
| low_vdd_hot__tid_conservative | 0 | 0 | 1 | 0 | 60.659 |
| low_vdd_hot__tid_stress_not_a_fit | 0 | 0 | 1 | 0 | 62.773 |
| nominal__tid_central | 0 | 0 | 1 | 0 | 162.060 |
| nominal__tid_conservative | 0 | 0 | 1 | 0 | 172.750 |
| nominal__tid_stress_not_a_fit | 0 | 0 | 1 | 0 | 166.284 |
| high_vdd_cold__tid_central | 0 | 0 | 1 | 0 | 443.798 |
| high_vdd_cold__tid_conservative | 0 | 0 | 1 | 0 | 438.102 |
| high_vdd_cold__tid_stress_not_a_fit | 0 | 0 | 1 | 0 | 445.093 |
| high_vdd_hot__tid_central | 0 | 0 | 1 | 0 | 155.222 |
| high_vdd_hot__tid_conservative | 0 | 0 | 1 | 0 | 158.502 |
| high_vdd_hot__tid_stress_not_a_fit | 0 | 0 | 1 | 0 | 152.348 |


Zero observed failures means only that none occurred at the reported sample count. Use the Wilson bounds in `conditional_probability_summary.csv` as finite-sample detection limits; do not interpret zero as a proven zero BER.
