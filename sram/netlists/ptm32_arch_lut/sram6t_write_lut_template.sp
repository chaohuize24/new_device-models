* PTM32 LP 6T SRAM selected write path for architecture LUT.

.include "__MODEL_PATH__"

.param VDDVAL=__VDD__
.param LCH=32n
.param CNODE=__CNODE_FF__f
.param CBL=__CBL_FF__f
.param MUSCALE=__MU_SCALE__

VSUPPLY vdd 0 {VDDVAL}
VDATA d 0 __DATA_V__
VDATAB db 0 __DATAB_V__
VWL wl 0 PWL(0 0 0.23n 0 0.25n {VDDVAL} 1.70n {VDDVAL} 1.72n 0 2.40n 0)
VWREN wren 0 PWL(0 0 0.13n 0 0.15n {VDDVAL} 1.70n {VDDVAL} 1.72n 0 2.40n 0)
VWRENB wrenb 0 PWL(0 {VDDVAL} 0.13n {VDDVAL} 0.15n 0 1.70n 0 1.72n {VDDVAL} 2.40n {VDDVAL})

MPQ  q  qb vdd vdd pmos W=__W_PQ_NM__n  L={LCH} DELVTO=__TID_DVP__ MULU0={MUSCALE}
MNQ  q  qb 0   0   nmos W=__W_NQ_NM__n  L={LCH} DELVTO=__TID_DVN__ MULU0={MUSCALE}
MPQB qb q  vdd vdd pmos W=__W_PQB_NM__n L={LCH} DELVTO=__TID_DVP__ MULU0={MUSCALE}
MNQB qb q  0   0   nmos W=__W_NQB_NM__n L={LCH} DELVTO=__TID_DVN__ MULU0={MUSCALE}
MAXQ  q  wl bl  0 nmos W=__W_AXQ_NM__n  L={LCH} DELVTO=__TID_DVN__ MULU0={MUSCALE}
MAXQB qb wl blb 0 nmos W=__W_AXQB_NM__n L={LCH} DELVTO=__TID_DVN__ MULU0={MUSCALE}
CQ q 0 {CNODE}
CQB qb 0 {CNODE}
CBL bl 0 {CBL}
CBLB blb 0 {CBL}

SW_D bl d wren 0 SWMUX
SW_DB blb db wren 0 SWMUX
.model SWMUX SW(Ron=__RON_OHM__ Roff=1e12 Vt=0.45 Vh=0.01)

.ic v(q)=__Q_INIT_V__ v(qb)=__QB_INIT_V__ v(bl)={VDDVAL} v(blb)={VDDVAL}
.temp __TEMP_C__
.options reltol=3e-5 abstol=1e-13 chgtol=1e-18 method=gear
.tran 2p 2.40n uic

.measure tran WRITE_LATENCY TRIG v(wl) VAL='VDDVAL/2' RISE=1 TARG v(q) VAL='VDDVAL/2' __WRITE_EDGE__=1
.measure tran VQ_FINAL FIND v(q) AT=1.20n
.measure tran VQB_FINAL FIND v(qb) AT=1.20n
.measure tran ACCESS_ENERGY INTEG par('-(v(vdd)*i(VSUPPLY)+v(d)*i(VDATA)+v(db)*i(VDATAB)+v(wl)*i(VWL)+v(wren)*i(VWREN)+v(wrenb)*i(VWRENB))') FROM=0 TO=2.30n
.end
