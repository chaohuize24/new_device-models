* PTM32 LP 6T SRAM dynamic-write collected-charge screening deck.
* Finite CMOS write drivers and one transistor-level TG column branch are used.
* Address decoders and target PEX are deliberately outside this selected path.

.include "__MODEL_PATH__"

.param VDDVAL=__VDD__
.param LCH=32n
.param CNODE=__CNODE_FF__f
.param CBL=__CBL_FF__f
.param MUSCALE=__MU_SCALE__
.param QFC=__QFC__
.param TSTRIKE=__TSTRIKE_NS__n
.param TAUR=__TAUR_PS__p
.param TAUF=__TAUF_PS__p
.param TFINAL=__TFINAL_NS__n
.param TSTOP=__TSTOP_NS__n

VSUPPLY vdd 0 {VDDVAL}
VDIN din 0 __DIN_V__
VDINB dinb 0 __DINB_V__
VWL wl 0 PWL(0 0 0.23n 0 0.25n {VDDVAL} 1.70n {VDDVAL} 1.72n 0 2.40n 0)
VWREN wren 0 PWL(0 0 0.13n 0 0.15n {VDDVAL} 1.70n {VDDVAL} 1.72n 0 2.40n 0)
VWRENB wrenb 0 PWL(0 {VDDVAL} 0.13n {VDDVAL} 0.15n 0 1.70n 0 1.72n {VDDVAL} 2.40n {VDDVAL})

* 6T cell; Q is the logical stored bit.
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

* Finite complementary write drivers. DIN is the inverter input for D;
* DINB is the inverter input for DB.
MPDRV_D d din vdd vdd pmos W=__W_DRV_PM__n L={LCH} DELVTO=__TID_DVP__ MULU0={MUSCALE}
MNDRV_D d din 0 0 nmos W=__W_DRV_NM__n L={LCH} DELVTO=__TID_DVN__ MULU0={MUSCALE}
MPDRV_DB db dinb vdd vdd pmos W=__W_DRV_PM__n L={LCH} DELVTO=__TID_DVP__ MULU0={MUSCALE}
MNDRV_DB db dinb 0 0 nmos W=__W_DRV_NM__n L={LCH} DELVTO=__TID_DVN__ MULU0={MUSCALE}

* One selected branch of a transmission-gate column mux.
MNMUX_D bl wren d 0 nmos W=__W_MUX_NM__n L={LCH} DELVTO=__TID_DVN__ MULU0={MUSCALE}
MPMUX_D bl wrenb d vdd pmos W=__W_MUX_PM__n L={LCH} DELVTO=__TID_DVP__ MULU0={MUSCALE}
MNMUX_DB blb wren db 0 nmos W=__W_MUX_NM__n L={LCH} DELVTO=__TID_DVN__ MULU0={MUSCALE}
MPMUX_DB blb wrenb db vdd pmos W=__W_MUX_PM__n L={LCH} DELVTO=__TID_DVP__ MULU0={MUSCALE}

* The rendered source/sink orientation applies the adverse polarity.
BSTRIKE __STRIKE_SOURCE__ __STRIKE_SINK__ I = (time<TSTRIKE) ? 0 :
+ (QFC*1e-15)/(TAUF-TAUR)
+ *(exp(-(time-TSTRIKE)/TAUF)-exp(-(time-TSTRIKE)/TAUR))

.ic v(q)=__Q_INIT_V__ v(qb)=__QB_INIT_V__ v(bl)={VDDVAL} v(blb)={VDDVAL} v(d)=__D_INIT_V__ v(db)=__DB_INIT_V__
.temp __TEMP_C__
.options reltol=2e-5 abstol=1e-14 chgtol=1e-18 method=gear
.tran 0.5p {TSTOP} uic

.measure tran VQ_FINAL FIND v(q) AT={TFINAL}
.measure tran VQB_FINAL FIND v(qb) AT={TFINAL}
.measure tran VD_FINAL FIND v(d) AT={TFINAL}
.measure tran VDB_FINAL FIND v(db) AT={TFINAL}
.end
