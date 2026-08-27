* Generic PTM32 LP 6T SRAM read-access engineering testbench.
* 128-row local BL -> 4:1 column-mux proxy -> global BL -> latch sense amplifier.
* PTM and all mismatch/TID values are engineering inputs, not a foundry PDK.

.include "__MODEL_PATH__"

.param VDDVAL=__VDD__
.param LCH=32n
.param CNODE=__CNODE_FF__f
.param CBL=__CBL_FF__f
.param CGBL=__CGBL_FF__f
.param NUNSEL=127
.param MUSCALE=__MU_SCALE__

VSUPPLY vdd 0 {VDDVAL}
VPRE pre 0 PWL(0 0 0.33n 0 0.35n {VDDVAL} 1.30n {VDDVAL})
VEQ eq 0 PWL(0 {VDDVAL} 0.33n {VDDVAL} 0.35n 0 1.30n 0)
VCOL col 0 PWL(0 0 0.36n 0 0.38n {VDDVAL} 1.20n {VDDVAL} 1.22n 0 1.30n 0)
VCOLB colb 0 PWL(0 {VDDVAL} 0.36n {VDDVAL} 0.38n 0 1.20n 0 1.22n {VDDVAL} 1.30n {VDDVAL})
VWL wl 0 PWL(0 0 0.43n 0 0.45n {VDDVAL} 1.20n {VDDVAL} 1.22n 0 1.30n 0)
VSAEN saen 0 PWL(0 0 __SAEN_LOW_NS__n 0 __SAEN_HIGH_NS__n {VDDVAL} 1.20n {VDDVAL} 1.22n 0 1.30n 0)
VSAENB saenb 0 PWL(0 {VDDVAL} __SAEN_LOW_NS__n {VDDVAL} __SAEN_HIGH_NS__n 0 1.20n 0 1.22n {VDDVAL} 1.30n {VDDVAL})

* 6T cell; Q is the logical stored bit.
MPQ  q  qb vdd vdd pmos W=__W_PQ_NM__n  L={LCH} DELVTO=__DVTH_PQ__  MULU0={MUSCALE}
MNQ  q  qb 0   0   nmos W=__W_NQ_NM__n  L={LCH} DELVTO=__DVTH_NQ__  MULU0={MUSCALE}
MPQB qb q  vdd vdd pmos W=__W_PQB_NM__n L={LCH} DELVTO=__DVTH_PQB__ MULU0={MUSCALE}
MNQB qb q  0   0   nmos W=__W_NQB_NM__n L={LCH} DELVTO=__DVTH_NQB__ MULU0={MUSCALE}
MAXQ  q  wl bl  0 nmos W=__W_AXQ_NM__n  L={LCH} DELVTO=__DVTH_AXQ__  MULU0={MUSCALE}
MAXQB qb wl blb 0 nmos W=__W_AXQB_NM__n L={LCH} DELVTO=__DVTH_AXQB__ MULU0={MUSCALE}
CQ q 0 {CNODE}
CQB qb 0 {CNODE}

* Local and global differential bitlines.
CBL bl 0 {CBL}
CBLB blb 0 {CBL}
CGBL gbl 0 {CGBL}
CGBLB gblb 0 {CGBL}

MPRE_BL bl pre vdd vdd pmos W=__W_PRE_PM__n L={LCH} DELVTO=__DVTH_PRE_BL__ MULU0={MUSCALE}
MPRE_BLB blb pre vdd vdd pmos W=__W_PRE_PM__n L={LCH} DELVTO=__DVTH_PRE_BLB__ MULU0={MUSCALE}
MEQ_BL bl eq blb 0 nmos W=__W_EQ_NM__n L={LCH} DELVTO=__DVTH_EQ__ MULU0={MUSCALE}
MPRE_GBL gbl pre vdd vdd pmos W=__W_PRE_PM__n L={LCH} DELVTO=__DVTH_PRE_GBL__ MULU0={MUSCALE}
MPRE_GBLB gblb pre vdd vdd pmos W=__W_PRE_PM__n L={LCH} DELVTO=__DVTH_PRE_GBLB__ MULU0={MUSCALE}
MEQ_GBL gbl eq gblb 0 nmos W=__W_EQ_NM__n L={LCH} DELVTO=__DVTH_EQG__ MULU0={MUSCALE}

* One selected branch of a 4:1 column mux. Other branch loading is in CGBL.
* The switch is a finite-resistance pre-layout proxy; target PEX must replace it.
SCOL_BL gbl bl col 0 SWMUX
SCOL_BLB gblb blb col 0 SWMUX
.model SWMUX SW(Ron=200 Roff=1e12 Vt=0.45 Vh=0.01)

* CBL includes the aggregate unselected-cell/wire capacitance. Pattern-dependent
* unselected-cell leakage remains outside this access-probability proxy.

* Clocked cross-coupled voltage latch SA on the global bitlines.
MSAP_GBL gbl gblb psa vdd pmos W=__W_SAP_PM__n L={LCH} DELVTO=__DVTH_SAP_GBL__ MULU0={MUSCALE}
MSAP_GBLB gblb gbl psa vdd pmos W=__W_SAP_PM__n L={LCH} DELVTO=__DVTH_SAP_GBLB__ MULU0={MUSCALE}
MSAN_GBL gbl gblb nsa 0 nmos W=__W_SAN_NM__n L={LCH} DELVTO=__DVTH_SAN_GBL__ MULU0={MUSCALE}
MSAN_GBLB gblb gbl nsa 0 nmos W=__W_SAN_NM__n L={LCH} DELVTO=__DVTH_SAN_GBLB__ MULU0={MUSCALE}
MSA_PSUP psa saenb vdd vdd pmos W=__W_SA_SUP_PM__n L={LCH} DELVTO=__TID_DVP__ MULU0={MUSCALE}
MSA_TAIL nsa saen 0 0 nmos W=__W_SA_TAIL_NM__n L={LCH} DELVTO=__TID_DVN__ MULU0={MUSCALE}

.ic v(q)=__Q_INIT_V__ v(qb)=__QB_INIT_V__ v(bl)={VDDVAL} v(blb)={VDDVAL} v(gbl)={VDDVAL} v(gblb)={VDDVAL}
.temp __TEMP_C__
.options reltol=3e-5 abstol=1e-13 chgtol=1e-18 method=gear
.tran 2p 1.30n uic

.measure tran VGBL_PRE FIND v(gbl) AT=__PRE_SENSE_NS__n
.measure tran VGBLB_PRE FIND v(gblb) AT=__PRE_SENSE_NS__n
.measure tran VGBL_SENSE FIND v(gbl) AT=1.15n
.measure tran VGBLB_SENSE FIND v(gblb) AT=1.15n
.measure tran VQ_CELL_FINAL FIND v(q) AT=1.15n
.measure tran VQB_CELL_FINAL FIND v(qb) AT=1.15n
.end
