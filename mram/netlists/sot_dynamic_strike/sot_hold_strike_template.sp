* SOT-MRAM hold-state collected-charge screening deck (1T1MTJ, WL off, no SOT pulse).

.include "__MODEL_PATH__"

.param VDDVAL=__VDD__
.param LCH=32n
.param R_MTJ=__R_MTJ__
.param CMTJ=__C_MTJ__
.param MUSCALE=__MU_SCALE__
.param QFC=__QFC__
.param TSTRIKE=1n
.param TAUR=__TAUR_PS__p
.param TAUF=__TAUF_PS__p
.param I0STK={QFC*1e-15/(TAUF-TAUR)}

VSUPPLY vdd 0 {VDDVAL}
VWL wl 0 0

MACC bl wl mtj 0 nmos W=__W_ACC_NM__n L={LCH} DELVTO=__TID_DVN__ MULU0={MUSCALE}
RMTJ mtj 0 {R_MTJ}
CMTJ_CELL mtj 0 {CMTJ}
CBL bl 0 100f
CMEXTRA mtj 0 5f

BSTRIKE __STRIKE_SOURCE__ __STRIKE_SINK__ I={I0STK*(exp(-max(time-TSTRIKE,0)/TAUF)-exp(-max(time-TSTRIKE,0)/TAUR))*(time>=TSTRIKE)}

.ic v(bl)=__BL_INIT_V__ v(mtj)=__MTJ_INIT_V__
.temp __TEMP_C__
.options reltol=2e-5 abstol=1e-14 chgtol=1e-18 method=gear
.tran 0.5p 4n uic

.measure tran VBL_FINAL FIND v(bl) AT=3.9n
.measure tran VMTJ_FINAL FIND v(mtj) AT=3.9n
.end
