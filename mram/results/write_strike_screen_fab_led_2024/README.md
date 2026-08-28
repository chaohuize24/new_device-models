# SOT-MRAM dynamic write strike screening

Selected-path electrical vulnerability screen for the SOT write window (not absolute dynamic write BER).

- Workpoint: `fab_led_2024`
- Write Qcrit cases: 18
- Hold Qcrit cases: 4
- Minimum write Qcrit: 512 fC (right_censored_gt_qcrit_max)
- Minimum hold Qcrit: 0.00625 fC
- min(write)/min(hold): 81920
- Write pulse anchor: 1020 uA @ 2 ns
- I_CSOT anchor: 680 uA

Does not include address decoder, control logic, or intrinsic stochastic WER.
