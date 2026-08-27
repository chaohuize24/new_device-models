* Generic PTM32 LP 6T SRAM write-access engineering testbench.
* One selected cell, 128-row local-bitline loading proxy and TG write mux.
* PTM and all mismatch/TID values are engineering inputs, not a foundry PDK.

.include "__MODEL_PATH__"

.param VDDVAL=__VDD__
.param LCH=32n
.param CNODE=__CNODE_FF__f
.param CBL=__CBL_FF__f
.param NUNSEL=127
.param MUSCALE=__MU_SCALE__

VSUPPLY vdd 0 {VDDVAL}
VDATA d 0 __DATA_V__
VDATAB db 0 __DATAB_V__
VWL wl 0 PWL(0 0 0.23n 0 0.25n {VDDVAL} 0.83n {VDDVAL} 0.85n 0 1.30n 0)
VWREN wren 0 PWL(0 0 0.13n 0 0.15n {VDDVAL} 0.93n {VDDVAL} 0.95n 0 1.30n 0)
VWRENB wrenb 0 PWL(0 {VDDVAL} 0.13n {VDDVAL} 0.15n 0 0.93n 0 0.95n {VDDVAL} 1.30n {VDDVAL})

* 6T cell; Q is the logical stored bit.
MPQ  q  qb vdd vdd pmos W=__W_PQ_NM__n  L={LCH} DELVTO=__DVTH_PQ__  MULU0={MUSCALE}
MNQ  q  qb 0   0   nmos W=__W_NQ_NM__n  L={LCH} DELVTO=__DVTH_NQ__  MULU0={MUSCALE}
MPQB qb q  vdd vdd pmos W=__W_PQB_NM__n L={LCH} DELVTO=__DVTH_PQB__ MULU0={MUSCALE}
MNQB qb q  0   0   nmos W=__W_NQB_NM__n L={LCH} DELVTO=__DVTH_NQB__ MULU0={MUSCALE}
MAXQ  q  wl bl  0 nmos W=__W_AXQ_NM__n  L={LCH} DELVTO=__DVTH_AXQ__  MULU0={MUSCALE}
MAXQB qb wl blb 0 nmos W=__W_AXQB_NM__n L={LCH} DELVTO=__DVTH_AXQB__ MULU0={MUSCALE}

CQ q 0 {CNODE}
CQB qb 0 {CNODE}
CBL bl 0 {CBL}
CBLB blb 0 {CBL}

* Full-swing write driver through a finite-resistance column-select switch.
* The switch is a pre-layout mux resistance proxy; target PEX must replace it.
SW_D  bl  d  wren 0 SWMUX
SW_DB blb db wren 0 SWMUX
.model SWMUX SW(Ron=200 Roff=1e12 Vt=0.45 Vh=0.01)

* CBL includes the aggregate unselected-cell/wire capacitance. Pattern-dependent
* unselected-cell leakage remains outside this access-probability proxy.

.ic v(q)=__Q_INIT_V__ v(qb)=__QB_INIT_V__ v(bl)={VDDVAL} v(blb)={VDDVAL}
.temp __TEMP_C__
.options reltol=3e-5 abstol=1e-13 chgtol=1e-18 method=gear
.tran 2p 1.30n uic

.measure tran VQ_FINAL FIND v(q) AT=1.20n
.measure tran VQB_FINAL FIND v(qb) AT=1.20n
.measure tran VBL_FINAL FIND v(bl) AT=1.20n
.measure tran VBLB_FINAL FIND v(blb) AT=1.20n
.end
