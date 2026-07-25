FUNCTION_BLOCK FB_XDual
(* FB_XDual — M1/M2 独立速度 + FB_XLineTrack；无 Virtual/Gear。
   走距：平均相对位移；不做 |PosM1-PosM2| 联锁。 *)
VAR_IN_OUT
    AxisM1 : AXIS_REF_SM3;
    AxisM2 : AXIS_REF_SM3;
END_VAR
VAR_INPUT
    xEnable : BOOL;
    xStop : BOOL;
    xResetFault : BOOL;
    xJogPos : BOOL;
    xJogNeg : BOOL;
    xSpinLeft : BOOL;
    xSpinRight : BOOL;
    xMoveRel : BOOL;
    rMoveDist : REAL;
    rMoveVel : REAL;
    rJogVel : REAL;
    rSpinVel : REAL;
    rHeadingErr : REAL;
    rKpTrack : REAL;
    rAcc : REAL;
    rDec : REAL;
    rTrimMax : REAL;        (* 纠偏限幅；接 Cfg_rPhaseMax *)
END_VAR
VAR_OUTPUT
    xMoveDone : BOOL;
    rPosV : REAL;           (* 平均位置，兼容旧 rPosX 名 *)
    rSyncErr : REAL;        (* 恒 0 *)
    rVelFactor : REAL;      (* 恒 0 *)
    xCoupled : BOOL;        (* 恒 FALSE *)
    xInGearM1 : BOOL;
    xInGearM2 : BOOL;
    xPoweredV : BOOL;
    xSyncWarn : BOOL;
    xSyncFault : BOOL;
    iState : INT;           (* 恒 0 *)
    rVelCmdM1 : REAL;
    rVelCmdM2 : REAL;
    rPosM1 : REAL;
    rPosM2 : REAL;
    xMovingM1 : BOOL;
    xMovingM2 : BOOL;
    xStandstillM1 : BOOL;
    xStandstillM2 : BOOL;
    xPoweredM1 : BOOL;
    xPoweredM2 : BOOL;
    xReadyM1 : BOOL;
    xReadyM2 : BOOL;
    xFaultM1 : BOOL;
    xFaultM2 : BOOL;
END_VAR
VAR
    fbTrack : FB_XLineTrack;
    fbM1 : FB_Servo;
    fbM2 : FB_Servo;
    eMode : INT;
    rBase : REAL;
    xMovePrev : BOOL;
    xArmed : BOOL;
    rStart : REAL;
    rAvg : REAL;
END_VAR

(* 废弃同步输出 *)
rSyncErr := 0.0;
rVelFactor := 0.0;
iState := 0;
xCoupled := FALSE;
xInGearM1 := FALSE;
xInGearM2 := FALSE;
xPoweredV := FALSE;
xSyncWarn := FALSE;
xSyncFault := FALSE;

(* 模式：Stop > Spin > Jog/MoveRel（与 tools/x_dual_logic.py 一致；用 IF 避免 SEL 真假序陷阱） *)
IF xStop OR NOT xEnable THEN
    eMode := 0;
    rBase := 0.0;
ELSIF xSpinLeft XOR xSpinRight THEN
    IF xSpinLeft THEN
        eMode := 2;
    ELSE
        eMode := 3;
    END_IF;
    rBase := 0.0;
ELSIF (xJogPos XOR xJogNeg) OR xMoveRel THEN
    eMode := 1;
    IF xMoveRel THEN
        IF rMoveDist >= 0.0 THEN
            rBase := ABS(rMoveVel);
        ELSE
            rBase := -ABS(rMoveVel);
        END_IF;
    ELSIF xJogPos THEN
        rBase := ABS(rJogVel);
    ELSE
        rBase := -ABS(rJogVel);
    END_IF;
ELSE
    eMode := 0;
    rBase := 0.0;
END_IF;

fbTrack(
    xEnable := xEnable,
    xStop := xStop,
    eMode := eMode,
    rBaseVel := rBase,
    rSpinVel := rSpinVel,
    rHeadingErr := rHeadingErr,
    rKpTrack := rKpTrack,
    rTrimMax := rTrimMax
);
rVelCmdM1 := fbTrack.rVelM1;
rVelCmdM2 := fbTrack.rVelM2;

fbM1(
    Axis := AxisM1,
    xEnable := xEnable,
    xStop := xStop,
    xResetFault := xResetFault,
    xUseVelCmd := TRUE,
    rVelCmd := rVelCmdM1,
    rAcc := rAcc,
    rDec := rDec,
    xLimEn := FALSE
);
fbM2(
    Axis := AxisM2,
    xEnable := xEnable,
    xStop := xStop,
    xResetFault := xResetFault,
    xUseVelCmd := TRUE,
    rVelCmd := rVelCmdM2,
    rAcc := rAcc,
    rDec := rDec,
    xLimEn := FALSE
);

rPosM1 := LREAL_TO_REAL(fbM1.rActPos);
rPosM2 := LREAL_TO_REAL(fbM2.rActPos);
rAvg := (rPosM1 + rPosM2) * 0.5;
rPosV := rAvg;
xMovingM1 := fbM1.xMoving;
xMovingM2 := fbM2.xMoving;
xStandstillM1 := fbM1.xStandstill;
xStandstillM2 := fbM2.xStandstill;
xPoweredM1 := fbM1.xPowered;
xPoweredM2 := fbM2.xPowered;
xReadyM1 := fbM1.xReady;
xReadyM2 := fbM2.xReady;
xFaultM1 := fbM1.xFault;
xFaultM2 := fbM2.xFault;

(* 走距完成：上升沿锁平均位；|Δavg|≥|dist| 保持 done，直至撤销/Stop（对齐 move_done_update） *)
IF xStop OR NOT xEnable OR NOT xMoveRel THEN
    xArmed := FALSE;
    xMoveDone := FALSE;
ELSE
    IF xMoveRel AND NOT xMovePrev THEN
        xArmed := TRUE;
        rStart := rAvg;
    END_IF;
    xMoveDone := xArmed AND (ABS(rAvg - rStart) >= ABS(rMoveDist));
END_IF;
xMovePrev := xMoveRel;
