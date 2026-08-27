* SOT-MRAM dynamic write collected-charge screening deck (1T1MTJ + SOT channel proxy).

.include "__MODEL_PATH__"

.param VDDVAL=__VDD__
.param LCH=32n
.param R_P=__R_P__
.param R_AP=__R_AP__
.param R_SOT=__R_SOT__
.param CMTJ=__C_MTJ__
.param R_MTJ=__R_MTJ__
.param MUSCALE=__MU_SCALE__
.param QFC=__QFC__
.param TSTRIKE=__TSTRIKE_NS__n
.param TAUR=__TAUR_PS__p
.param TAUF=__TAUF_PS__p
.param TFINAL=__TFINAL_NS__n
.param TSTOP=__TSTOP_NS__n
.param IWRITE=__IWRITE_A__
.param I0STK={QFC*1e-15/(TAUF-TAUR)}

VSUPPLY vdd 0 {VDDVAL}
VWL wl 0 0

* Complementary write enables aligned with the SOT pulse window.
VBLD bld 0 PWL(0 0 0.15n 0 0.17n __BLD_V__ 2.15n __BLD_V__ 2.17n 0 3.0n 0)
VBLDB bldb 0 PWL(0 0 0.15n 0 0.17n __BLDB_V__ 2.15n __BLDB_V__ 2.17n 0 3.0n 0)

VSOT sot_drv 0 PWL(0 0 0.15n 0 0.17n {IWRITE} 2.15n {IWRITE} 2.17n 0 3.0n 0)
RSOT sot_drv sot_top {R_SOT}
RSOTR sot_top 0 1

MACC bl wl mtj 0 nmos W=__W_ACC_NM__n L={LCH} DELVTO=__TID_DVN__ MULU0={MUSCALE}
RMTJ mtj 0 {R_MTJ}
CMTJ_CELL mtj 0 {CMTJ}

MPDRV bl bld vdd vdd pmos W=__W_DRV_PM__n L={LCH} DELVTO=__TID_DVP__ MULU0={MUSCALE}
MNDRV bl bld 0 0 nmos W=__W_DRV_NM__n L={LCH} DELVTO=__TID_DVN__ MULU0={MUSCALE}
MPDRV_B blb bldb vdd vdd pmos W=__W_DRV_PM__n L={LCH} DELVTO=__TID_DVP__ MULU0={MUSCALE}
MNDRV_B blb bldb 0 0 nmos W=__W_DRV_NM__n L={LCH} DELVTO=__TID_DVN__ MULU0={MUSCALE}
CBL bl 0 100f
CBLB blb 0 100f
CMTOP sot_top 0 5f

BSTRIKE __STRIKE_SOURCE__ __STRIKE_SINK__ I={I0STK*(exp(-max(time-TSTRIKE,0)/TAUF)-exp(-max(time-TSTRIKE,0)/TAUR))*(time>=TSTRIKE)}

.ic v(bl)=__BL_INIT_V__ v(blb)=__BLB_INIT_V__ v(mtj)=__MTJ_INIT_V__
.temp __TEMP_C__
.options reltol=2e-5 abstol=1e-14 chgtol=1e-18 method=gear
.tran 0.5p {TSTOP} uic

.measure tran VBL_FINAL FIND v(bl) AT={TFINAL}
.measure tran VMTJ_FINAL FIND v(mtj) AT={TFINAL}
.end
