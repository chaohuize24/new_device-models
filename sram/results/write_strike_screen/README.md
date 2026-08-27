# PTM32 SRAM dynamic-write strike screening

This is a selected-path electrical vulnerability screen, not an absolute dynamic write BER calculation.

- Write Qcrit cases: 288
- Hold Qcrit cases: 32
- Minimum bracketed write Qcrit: 1.02812 fC
- Minimum hold Qcrit: 1.04688 fC
- Worst non-stress condition min(write Qcrit)/min(hold Qcrit): 0.930097
- Write cases with no failure up to 12.8 fC: 204
- Baseline write failures: 0

The transient deck includes finite CMOS write drivers and a transistor-level selected transmission-gate column branch. It does not include address decoders, address latches, clock distribution, unselected mux branches, target PEX, MBU or SEFI.

`Qcrit_write/Qcrit_hold` is only a vulnerability ratio. A dynamic cross section still requires target layout/charge collection or dynamic beam data.
