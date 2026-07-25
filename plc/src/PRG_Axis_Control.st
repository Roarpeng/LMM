PROGRAM PRG_Axis_Control
(* PRG_Axis_Control — 运动独立任务(ETHERCAT 4ms)。只读 AxisCmd_*，写 AxisFb_*/rForceAct。
   禁止被其它 POU CALL；禁止写 HMI_*/报警。
   X：FB_XDual（LineTrack + 双 FB_Servo，无 Virtual/Gear）；Y/Z/R 仍 FB_Servo。 *)
VAR
    fbX : FB_XDual;
    fbY : FB_Servo;
    fbZ : FB_Servo;
    fbR : FB_Servo;
    fbForce : FB_Force;
    fbFF : FB_ForceFollow;
END_VAR

(* ===== 力传感转换（本 POU 拥有 rForceAct） ===== *)
fbForce(wRaw := Force_wInRaw, rScale := Force_rScale, xEnable := Force_xEnable,
    xTare := HMI_xForceTare OR Logic_xForceTare, xUntare := HMI_xForceUntare);
Force_iRaw := fbForce.iRaw;
Force_xCommOk := fbForce.xCommOk;
Force_xTimeout := fbForce.xTimeout;
IF NOT HMI_xForceSimEnable THEN
    rForceAct := fbForce.rForceN;
END_IF;

(* ===== X：FB_XDual（LineTrack + 双 Servo；无 Virtual/Gear） ===== *)
fbX(
    AxisM1 := Axis, AxisM2 := Axis_1,
    xEnable := AxisCmd_xPower, xStop := AxisCmd_xStopAll, xResetFault := AxisCmd_xResetFault,
    xJogPos := AxisCmd_xJogXPos, xJogNeg := AxisCmd_xJogXNeg,
    xSpinLeft := AxisCmd_xSpinLeft, xSpinRight := AxisCmd_xSpinRight,
    xMoveRel := AxisCmd_xMoveRelX, rMoveDist := AxisCmd_rMoveDistX, rMoveVel := AxisCmd_rMoveVelX,
    rJogVel := AxisCmd_rJogVelX, rSpinVel := AxisCmd_rSpinVel,
    rHeadingErr := AxisCmd_rHeadingErr, rKpTrack := AxisCmd_rTrackKp,
    rAcc := AxisCmd_rAccX, rDec := AxisCmd_rDecX,
    rTrimMax := Cfg_rPhaseMax);
AxisFb_xMoveDoneX := fbX.xMoveDone;
AxisFb_rPosX := fbX.rPosV;
AxisFb_rSyncErr := fbX.rSyncErr;
AxisFb_rVelFactorX := fbX.rVelFactor;
AxisFb_xGantryCoupled := fbX.xCoupled;
AxisFb_xInGearM1 := fbX.xInGearM1;
AxisFb_xInGearM2 := fbX.xInGearM2;
AxisFb_xPoweredV := fbX.xPoweredV;
AxisFb_xSyncWarn := fbX.xSyncWarn;
AxisFb_xSyncFault := fbX.xSyncFault;
AxisFb_iGantryState := fbX.iState;
AxisFb_rVelCmdM1 := fbX.rVelCmdM1;
AxisFb_rVelCmdM2 := fbX.rVelCmdM2;
AxisFb_rPosM1 := fbX.rPosM1;
AxisFb_rPosM2 := fbX.rPosM2;
AxisFb_xMovingM1 := fbX.xMovingM1;
AxisFb_xMovingM2 := fbX.xMovingM2;
AxisFb_xStandstill1 := fbX.xStandstillM1;
AxisFb_xStandstill2 := fbX.xStandstillM2;
AxisFb_xPoweredM1 := fbX.xPoweredM1;
AxisFb_xPoweredM2 := fbX.xPoweredM2;
AxisFb_xReadyM1 := fbX.xReadyM1;
AxisFb_xReadyM2 := fbX.xReadyM2;
AxisFb_xFaultM1 := fbX.xFaultM1;
AxisFb_xFaultM2 := fbX.xFaultM2;

(* ===== Y：回零 > 绝对(归位) > 相对(横移) > 点动；硬限位 [Cfg_rLimYNeg, Cfg_rLimYPos] ===== *)
fbY(Axis := Axis_2, xEnable := AxisCmd_xPower, xStop := AxisCmd_xStopAll, xResetFault := AxisCmd_xResetFault,
    xHome := AxisCmd_xHomeY,
    xMoveAbs := AxisCmd_xMoveAbsY, rTargetPos := AxisCmd_rMoveAbsPosY,
    xMoveRel := AxisCmd_xMoveRelY, rDist := AxisCmd_rMoveDistY,
    xJogPos := AxisCmd_xJogYPos, xJogNeg := AxisCmd_xJogYNeg, rJogVel := AxisCmd_rJogVelY,
    rVel := AxisCmd_rMoveVelY, rAcc := AxisCmd_rAccY, rDec := AxisCmd_rDecY,
    xLimEn := TRUE, rLimPos := Cfg_rLimYPos, rLimNeg := Cfg_rLimYNeg);
AxisFb_xMoveDoneY := fbY.xMoveRelDone;

(* ===== Z：力跟随速度 > 回零 > 点动；硬限位 [Cfg_rLimZNeg, Cfg_rLimZPos] ===== *)
fbFF(rForceSet := AxisCmd_rForceSet, rForceAct := rForceAct, rKp := AxisCmd_rForceKp,
    rVelMax := AxisCmd_rForceVelMax, rDeadband := 0.5, rPosZ := fbZ.rActPos,
    rLimPos := Cfg_rLimZPos, rLimNeg := Cfg_rLimZNeg,
    xEnable := AxisCmd_xForceFollow, xInvert := FALSE);
fbZ(Axis := Axis_3, xEnable := AxisCmd_xPower, xStop := AxisCmd_xStopAll, xResetFault := AxisCmd_xResetFault,
    xHome := AxisCmd_xHomeZ,
    xUseVelCmd := AxisCmd_xForceFollow, rVelCmd := fbFF.rZVelCmd,
    xJogPos := AxisCmd_xJogZPos, xJogNeg := AxisCmd_xJogZNeg, rJogVel := AxisCmd_rJogVelZ,
    rAcc := AxisCmd_rAccZ, rDec := AxisCmd_rDecZ,
    xLimEn := TRUE, rLimPos := Cfg_rLimZPos, rLimNeg := Cfg_rLimZNeg);

(* ===== R：回零 > 保持角(绝对) > 点动；M5 门控；硬限位 [Cfg_rLimRNeg, Cfg_rLimRPos] ===== *)
fbR(Axis := Axis_4, xEnable := AxisCmd_xPower AND xM5Ready, xStop := AxisCmd_xStopAll, xResetFault := AxisCmd_xResetFault,
    xHome := AxisCmd_xHomeR,
    xMoveAbs := AxisCmd_xHoldR, rTargetPos := AxisCmd_rRHoldPos,
    xJogPos := AxisCmd_xJogRPos, xJogNeg := AxisCmd_xJogRNeg, rJogVel := AxisCmd_rJogVelR,
    rVel := AxisCmd_rJogVelR, rAcc := AxisCmd_rAccR, rDec := AxisCmd_rDecR,
    xLimEn := TRUE, rLimPos := Cfg_rLimRPos, rLimNeg := Cfg_rLimRNeg);

(* ===== Y/Z/R 反馈回写 ===== *)
AxisFb_rPosY := fbY.rActPos; AxisFb_rPosZ := fbZ.rActPos; AxisFb_rPosR := fbR.rActPos;
AxisFb_xMovingY := fbY.xMoving; AxisFb_xMovingZ := fbZ.xMoving; AxisFb_xMovingR := fbR.xMoving;
AxisFb_xStandstillY := fbY.xStandstill; AxisFb_xStandstillZ := fbZ.xStandstill; AxisFb_xStandstillR := fbR.xStandstill;
AxisFb_xPoweredY := fbY.xPowered; AxisFb_xPoweredZ := fbZ.xPowered; AxisFb_xPoweredR := fbR.xPowered;
AxisFb_xReadyY := fbY.xReady; AxisFb_xReadyZ := fbZ.xReady; AxisFb_xReadyR := fbR.xReady;
AxisFb_xHomedY := fbY.xHomed; AxisFb_xHomedZ := fbZ.xHomed; AxisFb_xHomedR := fbR.xHomed;
AxisFb_xFaultY := fbY.xFault; AxisFb_xFaultZ := fbZ.xFault; AxisFb_xFaultR := fbR.xFault;
AxisFb_xReady := AxisFb_xReadyM1 AND AxisFb_xReadyM2 AND fbY.xReady AND fbZ.xReady
    AND (NOT xM5Ready OR fbR.xReady);
