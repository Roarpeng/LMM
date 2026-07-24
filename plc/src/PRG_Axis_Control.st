PROGRAM PRG_Axis_Control
(* PRG_Axis_Control — 运动独立任务(ETHERCAT 4ms)。只读 AxisCmd_*，写 AxisFb_*/rForceAct。
   禁止被其它 POU CALL；禁止写 HMI_*/报警。 *)
VAR
    fbM1 : FB_Servo;
    fbM2 : FB_Servo;
    fbY : FB_Servo;
    fbZ : FB_Servo;
    fbR : FB_Servo;
    fbForce : FB_Force;
    fbFF : FB_ForceFollow;
    fbTrack : FB_XLineTrack;
    iTrackMode : INT;
    rXBase : REAL;
    rXStart : LREAL;
    xMoveRelXPrev : BOOL;
    xXVelActive : BOOL;
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

(* ===== X 直线纠偏 / 原地转（速度模式 + 里程判完成） ===== *)
iTrackMode := 0;
rXBase := 0.0;
IF AxisCmd_xMoveRelX THEN
    iTrackMode := 1;
    (* 方向由走距符号决定，速度取绝对值 *)
    IF AxisCmd_rMoveDistX >= 0.0 THEN
        rXBase := ABS(AxisCmd_rMoveVelX);
    ELSE
        rXBase := -ABS(AxisCmd_rMoveVelX);
    END_IF;
ELSIF AxisCmd_xSpinLeft THEN
    iTrackMode := 2;
ELSIF AxisCmd_xSpinRight THEN
    iTrackMode := 3;
ELSIF AxisCmd_xJogXPos THEN
    iTrackMode := 1;
    rXBase := ABS(AxisCmd_rJogVelX);
ELSIF AxisCmd_xJogXNeg THEN
    iTrackMode := 1;
    rXBase := -ABS(AxisCmd_rJogVelX);
END_IF;

IF AxisCmd_xMoveRelX AND NOT xMoveRelXPrev THEN
    rXStart := fbM1.rActPos;
    AxisFb_xMoveDoneX := FALSE;
END_IF;
xMoveRelXPrev := AxisCmd_xMoveRelX;
IF AxisCmd_xMoveRelX THEN
    IF ABS(fbM1.rActPos - rXStart) >= ABS(AxisCmd_rMoveDistX) THEN
        AxisFb_xMoveDoneX := TRUE;
    END_IF;
ELSE
    AxisFb_xMoveDoneX := FALSE;
END_IF;

xXVelActive := (iTrackMode <> 0) AND NOT (AxisCmd_xMoveRelX AND AxisFb_xMoveDoneX);

fbTrack(xEnable := AxisCmd_xPower, xStop := AxisCmd_xStopAll, eMode := iTrackMode,
    rBaseVel := rXBase, rSpinVel := AxisCmd_rSpinVel,
    rHeadingErr := AxisCmd_rHeadingErr, rKpTrack := AxisCmd_rTrackKp, rTrimMax := 0.2);

fbM1(Axis := Axis, xEnable := AxisCmd_xPower, xStop := AxisCmd_xStopAll, xResetFault := AxisCmd_xResetFault,
    xUseVelCmd := xXVelActive, rVelCmd := fbTrack.rVelM1, rAcc := AxisCmd_rAcc, rDec := AxisCmd_rDec,
    xLimEn := FALSE, rLimPos := 0.0, rLimNeg := 0.0);
fbM2(Axis := Axis_1, xEnable := AxisCmd_xPower, xStop := AxisCmd_xStopAll, xResetFault := AxisCmd_xResetFault,
    xUseVelCmd := xXVelActive, rVelCmd := fbTrack.rVelM2, rAcc := AxisCmd_rAcc, rDec := AxisCmd_rDec,
    xLimEn := FALSE, rLimPos := 0.0, rLimNeg := 0.0);

(* ===== Y：回零 > 绝对(归位) > 相对(横移) > 点动；硬限位 [Cfg_rLimYNeg, Cfg_rLimYPos] ===== *)
fbY(Axis := Axis_2, xEnable := AxisCmd_xPower, xStop := AxisCmd_xStopAll, xResetFault := AxisCmd_xResetFault,
    xHome := AxisCmd_xHomeY,
    xMoveAbs := AxisCmd_xMoveAbsY, rTargetPos := AxisCmd_rMoveAbsPosY,
    xMoveRel := AxisCmd_xMoveRelY, rDist := AxisCmd_rMoveDistY,
    xJogPos := AxisCmd_xJogYPos, xJogNeg := AxisCmd_xJogYNeg, rJogVel := AxisCmd_rJogVelY,
    rVel := AxisCmd_rMoveVelY, rAcc := AxisCmd_rAcc, rDec := AxisCmd_rDec,
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
    rAcc := AxisCmd_rAcc, rDec := AxisCmd_rDec,
    xLimEn := TRUE, rLimPos := Cfg_rLimZPos, rLimNeg := Cfg_rLimZNeg);

(* ===== R：回零 > 保持角(绝对) > 点动；M5 门控；硬限位 [Cfg_rLimRNeg, Cfg_rLimRPos] ===== *)
fbR(Axis := Axis_4, xEnable := AxisCmd_xPower AND xM5Ready, xStop := AxisCmd_xStopAll, xResetFault := AxisCmd_xResetFault,
    xHome := AxisCmd_xHomeR,
    xMoveAbs := AxisCmd_xHoldR, rTargetPos := AxisCmd_rRHoldPos,
    xJogPos := AxisCmd_xJogRPos, xJogNeg := AxisCmd_xJogRNeg, rJogVel := AxisCmd_rJogVelR,
    rVel := AxisCmd_rJogVelR, rAcc := AxisCmd_rAcc, rDec := AxisCmd_rDec,
    xLimEn := TRUE, rLimPos := Cfg_rLimRPos, rLimNeg := Cfg_rLimRNeg);

(* ===== 反馈回写 ===== *)
AxisFb_rVelCmdM1 := fbTrack.rVelM1;
AxisFb_rVelCmdM2 := fbTrack.rVelM2;
AxisFb_rPosM1 := fbM1.rActPos; AxisFb_rPosM2 := fbM2.rActPos;
AxisFb_rPosY := fbY.rActPos; AxisFb_rPosZ := fbZ.rActPos; AxisFb_rPosR := fbR.rActPos;
AxisFb_xMovingM1 := fbM1.xMoving; AxisFb_xMovingM2 := fbM2.xMoving;
AxisFb_xMovingY := fbY.xMoving; AxisFb_xMovingZ := fbZ.xMoving; AxisFb_xMovingR := fbR.xMoving;
AxisFb_xStandstill1 := fbM1.xStandstill; AxisFb_xStandstill2 := fbM2.xStandstill;
AxisFb_xStandstillY := fbY.xStandstill; AxisFb_xStandstillZ := fbZ.xStandstill; AxisFb_xStandstillR := fbR.xStandstill;
AxisFb_xPoweredM1 := fbM1.xPowered; AxisFb_xPoweredM2 := fbM2.xPowered;
AxisFb_xPoweredY := fbY.xPowered; AxisFb_xPoweredZ := fbZ.xPowered; AxisFb_xPoweredR := fbR.xPowered;
AxisFb_xReadyM1 := fbM1.xReady; AxisFb_xReadyM2 := fbM2.xReady;
AxisFb_xReadyY := fbY.xReady; AxisFb_xReadyZ := fbZ.xReady; AxisFb_xReadyR := fbR.xReady;
AxisFb_xHomedY := fbY.xHomed; AxisFb_xHomedZ := fbZ.xHomed; AxisFb_xHomedR := fbR.xHomed;
AxisFb_xFaultM1 := fbM1.xFault; AxisFb_xFaultM2 := fbM2.xFault;
AxisFb_xFaultY := fbY.xFault; AxisFb_xFaultZ := fbZ.xFault; AxisFb_xFaultR := fbR.xFault;
AxisFb_xReady := fbM1.xReady AND fbM2.xReady AND fbY.xReady AND fbZ.xReady AND (NOT xM5Ready OR fbR.xReady);
