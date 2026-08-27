* PTM32 LP 6T SRAM hold-state collected-charge screening deck.

.include "__MODEL_PATH__"

.param VDDVAL=__VDD__
.param LCH=32n
.param CNODE=__CNODE_FF__f
.param MUSCALE=__MU_SCALE__
.param QFC=__QFC__
.param TSTRIKE=1n
.param TAUR=__TAUR_PS__p
.param TAUF=__TAUF_PS__p

VSUPPLY vdd 0 {VDDVAL}
VWL wl 0 0
VBL bl 0 {VDDVAL}
VBLB blb 0 {VDDVAL}

MPQ  q  qb vdd vdd pmos W=__W_PQ_NM__n  L={LCH} DELVTO=__TID_DVP__ MULU0={MUSCALE}
MNQ  q  qb 0   0   nmos W=__W_NQ_NM__n  L={LCH} DELVTO=__TID_DVN__ MULU0={MUSCALE}
MPQB qb q  vdd vdd pmos W=__W_PQB_NM__n L={LCH} DELVTO=__TID_DVP__ MULU0={MUSCALE}
MNQB qb q  0   0   nmos W=__W_NQB_NM__n L={LCH} DELVTO=__TID_DVN__ MULU0={MUSCALE}
MAXQ  q  wl bl  0 nmos W=__W_AXQ_NM__n  L={LCH} DELVTO=__TID_DVN__ MULU0={MUSCALE}
MAXQB qb wl blb 0 nmos W=__W_AXQB_NM__n L={LCH} DELVTO=__TID_DVN__ MULU0={MUSCALE}
CQ q 0 {CNODE}
CQB qb 0 {CNODE}

BSTRIKE __STRIKE_SOURCE__ __STRIKE_SINK__ I = (time<TSTRIKE) ? 0 :
+ (QFC*1e-15)/(TAUF-TAUR)
+ *(exp(-(time-TSTRIKE)/TAUF)-exp(-(time-TSTRIKE)/TAUR))

.ic v(q)=__Q_INIT_V__ v(qb)=__QB_INIT_V__
.temp __TEMP_C__
.options reltol=2e-5 abstol=1e-14 chgtol=1e-18 method=gear
.tran 0.5p 4n uic

.measure tran VQ_FINAL FIND v(q) AT=3.9n
.measure tran VQB_FINAL FIND v(qb) AT=3.9n
.end
