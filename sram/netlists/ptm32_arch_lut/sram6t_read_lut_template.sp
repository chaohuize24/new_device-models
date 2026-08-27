* PTM32 LP 6T SRAM selected read path for architecture LUT.
* Includes local/global bitline, finite mux switch, latch SA and re-precharge.

.include "__MODEL_PATH__"

.param VDDVAL=__VDD__
.param LCH=32n
.param CNODE=__CNODE_FF__f
.param CBL=__CBL_FF__f
.param CGBL=__CGBL_FF__f
.param MUSCALE=__MU_SCALE__

VSUPPLY vdd 0 {VDDVAL}
VPRE pre 0 PWL(0 0 0.33n 0 0.35n {VDDVAL} 1.70n {VDDVAL} 1.72n 0 2.40n 0)
VEQ eq 0 PWL(0 {VDDVAL} 0.33n {VDDVAL} 0.35n 0 1.70n 0 1.72n {VDDVAL} 2.40n {VDDVAL})
VCOL col 0 PWL(0 0 0.36n 0 0.38n {VDDVAL} 1.70n {VDDVAL} 1.72n 0 2.40n 0)
VCOLB colb 0 PWL(0 {VDDVAL} 0.36n {VDDVAL} 0.38n 0 1.70n 0 1.72n {VDDVAL} 2.40n {VDDVAL})
VWL wl 0 PWL(0 0 0.43n 0 0.45n {VDDVAL} 1.70n {VDDVAL} 1.72n 0 2.40n 0)
VSAEN saen 0 PWL(0 0 0.78n 0 0.80n {VDDVAL} 1.70n {VDDVAL} 1.72n 0 2.40n 0)
VSAENB saenb 0 PWL(0 {VDDVAL} 0.78n {VDDVAL} 0.80n 0 1.70n 0 1.72n {VDDVAL} 2.40n {VDDVAL})

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
CGBL gbl 0 {CGBL}
CGBLB gblb 0 {CGBL}
MPRE_BL bl pre vdd vdd pmos W=__W_PRE_PM__n L={LCH} DELVTO=__TID_DVP__ MULU0={MUSCALE}
MPRE_BLB blb pre vdd vdd pmos W=__W_PRE_PM__n L={LCH} DELVTO=__TID_DVP__ MULU0={MUSCALE}
MEQ_BL bl eq blb 0 nmos W=__W_EQ_NM__n L={LCH} DELVTO=__TID_DVN__ MULU0={MUSCALE}
MPRE_GBL gbl pre vdd vdd pmos W=__W_PRE_PM__n L={LCH} DELVTO=__TID_DVP__ MULU0={MUSCALE}
MPRE_GBLB gblb pre vdd vdd pmos W=__W_PRE_PM__n L={LCH} DELVTO=__TID_DVP__ MULU0={MUSCALE}
MEQ_GBL gbl eq gblb 0 nmos W=__W_EQ_NM__n L={LCH} DELVTO=__TID_DVN__ MULU0={MUSCALE}

SCOL_BL gbl bl col 0 SWMUX
SCOL_BLB gblb blb col 0 SWMUX
.model SWMUX SW(Ron=__RON_OHM__ Roff=1e12 Vt=0.45 Vh=0.01)

MSAP_GBL gbl gblb psa vdd pmos W=__W_SAP_PM__n L={LCH} DELVTO=__TID_DVP__ MULU0={MUSCALE}
MSAP_GBLB gblb gbl psa vdd pmos W=__W_SAP_PM__n L={LCH} DELVTO=__TID_DVP__ MULU0={MUSCALE}
MSAN_GBL gbl gblb nsa 0 nmos W=__W_SAN_NM__n L={LCH} DELVTO=__TID_DVN__ MULU0={MUSCALE}
MSAN_GBLB gblb gbl nsa 0 nmos W=__W_SAN_NM__n L={LCH} DELVTO=__TID_DVN__ MULU0={MUSCALE}
MSA_PSUP psa saenb vdd vdd pmos W=__W_SA_SUP_PM__n L={LCH} DELVTO=__TID_DVP__ MULU0={MUSCALE}
MSA_TAIL nsa saen 0 0 nmos W=__W_SA_TAIL_NM__n L={LCH} DELVTO=__TID_DVN__ MULU0={MUSCALE}

.ic v(q)=__Q_INIT_V__ v(qb)=__QB_INIT_V__ v(bl)={VDDVAL} v(blb)={VDDVAL} v(gbl)={VDDVAL} v(gblb)={VDDVAL}
.temp __TEMP_C__
.options reltol=3e-5 abstol=1e-13 chgtol=1e-18 method=gear
.tran 2p 2.40n uic

.measure tran READ_LATENCY TRIG v(wl) VAL='VDDVAL/2' RISE=1 TARG v(__READ_LOW_NODE__) VAL='VDDVAL/2' FALL=1
.measure tran VGBL_PRE FIND v(gbl) AT=0.79n
.measure tran VGBLB_PRE FIND v(gblb) AT=0.79n
.measure tran VGBL_SENSE FIND v(gbl) AT=1.20n
.measure tran VGBLB_SENSE FIND v(gblb) AT=1.20n
.measure tran VQ_FINAL FIND v(q) AT=1.20n
.measure tran VQB_FINAL FIND v(qb) AT=1.20n
.measure tran ACCESS_ENERGY INTEG par('-(v(vdd)*i(VSUPPLY)+v(pre)*i(VPRE)+v(eq)*i(VEQ)+v(col)*i(VCOL)+v(colb)*i(VCOLB)+v(wl)*i(VWL)+v(saen)*i(VSAEN)+v(saenb)*i(VSAENB))') FROM=0 TO=2.30n
.end
