PROGRAM PRG_Axis_Control
VAR
    fbX : FB_XDual;
    fbY : FB_Servo;
    fbZ : FB_Servo;
    fbR : FB_Servo;
    fbForce : FB_Force;
    fbFF : FB_ForceFollow;
END_VAR

(* PRG_Axis_Control — 运动独立任务(ETHERCAT 4ms)。只读 AxisCmd_*，写 AxisFb_*/rForceAct。
   禁止被其它 POU CALL；禁止写 HMI_*/报警。
   X：FB_XDual（LineTrack + 双 FB_Servo，无 Virtual/Gear）；Y/Z/R 仍 FB_Servo。 *)

(* ===== 力传感转换（本 POU 拥有 rForceAct） ===== *)
fbForce(wRaw := Force_wInRaw, rScale := Force_rScale, xEnable := Force_xEnable,
    xTare := HMI_xForceTare OR Logic_xForceTare, xUntare := HMI_xForceUntare);
Force_iRaw := fbForce.iRaw;
(* 力通讯状态由 PRG_Force485 的收发回文状态机唯一判定；
   不再用 FB_Force 的“原始值 2s 不变”看门狗覆盖，避免力稳定时误报 1005。 *)
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
    rTrimMax := Cfg_rPhaseMax,
    (* 0.60 视觉直控：绕过内部差速，直接给 M1/M2 速度 *)
    xDirectMode := AxisCmd_xDirectVel,
    rVelM1Direct := AxisCmd_rVelM1Set, rVelM2Direct := AxisCmd_rVelM2Set);
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

(* 0.60 视觉直控反馈（回给 PRG_TcpHmi 编码到状态镜像 + 视觉侧回读） *)
Direct_xActive := fbX.xDirectActive;
Direct_rVelM1Act := fbX.rVelActM1Out;
Direct_rVelM2Act := fbX.rVelActM2Out;

(* 0.63 通用双电机实际速度透传（供 PRG_TcpHmi 编码到状态 word32..38） *)
AxisFb_rVelActM1 := fbX.rVelActM1Out;
AxisFb_rVelActM2 := fbX.rVelActM2Out;

(* ===== Y：回零 > 绝对(归位) > 相对(横移) > 点动；硬限位 [Cfg_rLimYNeg, Cfg_rLimYPos] ===== *)
fbY(Axis := Axis_2, xEnable := AxisCmd_xPower, xStop := AxisCmd_xStopAll, xResetFault := AxisCmd_xResetFault,
    xHome := AxisCmd_xHomeY,
    xMoveAbs := AxisCmd_xMoveAbsY OR AxisCmd_xDirectAbsY,
    rTargetPos := SEL(AxisCmd_xMoveAbsY, AxisCmd_rDirectAbsY, AxisCmd_rMoveAbsPosY),
    xMoveRel := AxisCmd_xMoveRelY OR AxisCmd_xDirectRelY,
    rDist := SEL(AxisCmd_xMoveRelY, AxisCmd_rDirectRelY, AxisCmd_rMoveDistY),
    xUseVelCmd := AxisCmd_xDirectVelY, rVelCmd := AxisCmd_rDirectVelY,
    xJogPos := AxisCmd_xJogYPos, xJogNeg := AxisCmd_xJogYNeg, rJogVel := AxisCmd_rJogVelY,
    rVel := SEL(AxisCmd_xDirectAbsY OR AxisCmd_xDirectRelY, AxisCmd_rMoveVelY, AxisCmd_rDirectVelY),
    rAcc := AxisCmd_rAccY, rDec := AxisCmd_rDecY,
    xLimEn := TRUE, rLimPos := Cfg_rLimYPos, rLimNeg := Cfg_rLimYNeg);
AxisFb_xMoveDoneY := fbY.xMoveRelDone;

(* ===== Z：力跟随速度 > 回零 > 点动；硬限位 [Cfg_rLimZNeg, Cfg_rLimZPos] ===== *)
fbFF(rForceSet := AxisCmd_rForceSet, rForceAct := rForceAct, rKp := AxisCmd_rForceKp,
    rVelMax := AxisCmd_rForceVelMax, rDeadband := 0.5, rPosZ := fbZ.rActPos,
    rLimPos := Cfg_rLimZPos, rLimNeg := Cfg_rLimZNeg,
    xEnable := AxisCmd_xForceFollow, xInvert := FALSE);
fbZ(Axis := Axis_3, xEnable := AxisCmd_xPower, xStop := AxisCmd_xStopAll, xResetFault := AxisCmd_xResetFault,
    xHome := AxisCmd_xHomeZ,
    xMoveAbs := AxisCmd_xDirectAbsZ, rTargetPos := AxisCmd_rDirectAbsZ,
    xMoveRel := AxisCmd_xDirectRelZ, rDist := AxisCmd_rDirectRelZ,
    xUseVelCmd := AxisCmd_xForceFollow OR AxisCmd_xDirectVelZ,
    rVelCmd := SEL(AxisCmd_xForceFollow, AxisCmd_rDirectVelZ, fbFF.rZVelCmd),
    xJogPos := AxisCmd_xJogZPos, xJogNeg := AxisCmd_xJogZNeg, rJogVel := AxisCmd_rJogVelZ,
    rVel := AxisCmd_rDirectVelZ,
    rAcc := AxisCmd_rAccZ, rDec := AxisCmd_rDecZ,
    xLimEn := TRUE, rLimPos := Cfg_rLimZPos, rLimNeg := Cfg_rLimZNeg);

(* ===== R：回零 > 保持角(绝对) > 点动；M5 门控；硬限位 [Cfg_rLimRNeg, Cfg_rLimRPos] ===== *)
fbR(Axis := Axis_4, xEnable := AxisCmd_xPower AND xM5Ready, xStop := AxisCmd_xStopAll, xResetFault := AxisCmd_xResetFault,
    xHome := AxisCmd_xHomeR,
    xMoveAbs := AxisCmd_xHoldR OR AxisCmd_xDirectAbsR,
    rTargetPos := SEL(AxisCmd_xHoldR, AxisCmd_rDirectAbsR, AxisCmd_rRHoldPos),
    xMoveRel := AxisCmd_xDirectRelR, rDist := AxisCmd_rDirectRelR,
    xUseVelCmd := AxisCmd_xDirectVelR, rVelCmd := AxisCmd_rDirectVelR,
    xJogPos := AxisCmd_xJogRPos, xJogNeg := AxisCmd_xJogRNeg, rJogVel := AxisCmd_rJogVelR,
    rVel := SEL(AxisCmd_xDirectAbsR OR AxisCmd_xDirectRelR, AxisCmd_rJogVelR, AxisCmd_rDirectVelR),
    rAcc := AxisCmd_rAccR, rDec := AxisCmd_rDecR,
    xLimEn := TRUE, rLimPos := Cfg_rLimRPos, rLimNeg := Cfg_rLimRNeg);

(* ===== Y/Z/R 反馈回写 ===== *)
AxisFb_rPosY := fbY.rActPos; AxisFb_rPosZ := fbZ.rActPos; AxisFb_rPosR := fbR.rActPos;
AxisFb_xMovingY := fbY.xMoving; AxisFb_xMovingZ := fbZ.xMoving; AxisFb_xMovingR := fbR.xMoving;
AxisFb_xStandstillY := fbY.xStandstill; AxisFb_xStandstillZ := fbZ.xStandstill; AxisFb_xStandstillR := fbR.xStandstill;
AxisFb_xPoweredY := fbY.xPowered; AxisFb_xPoweredZ := fbZ.xPowered; AxisFb_xPoweredR := fbR.xPowered;
AxisFb_xReadyY := fbY.xReady; AxisFb_xReadyZ := fbZ.xReady; AxisFb_xReadyR := fbR.xReady;
AxisFb_xHomedY := fbY.xHomed; AxisFb_xHomedZ := fbZ.xHomed; AxisFb_xHomedR := fbR.xHomed;
AxisFb_xFaultY := fbY.xFault; AxisFb_xFaultZ := fbZ.xFault; AxisFb_xFaultR := fbR.xFault;
(* 0.68 全轴直控：Y/Z/R 实际速度回读（状态镜像 word39..41） *)
AxisFb_rVelActY := fbY.rVelAct;
AxisFb_rVelActZ := fbZ.rVelAct;
AxisFb_rVelActR := fbR.rVelAct;
AxisFb_xReady := AxisFb_xReadyM1 AND AxisFb_xReadyM2 AND fbY.xReady AND fbZ.xReady
    AND (NOT xM5Ready OR fbR.xReady);
