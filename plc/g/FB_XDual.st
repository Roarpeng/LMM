FUNCTION_BLOCK FB_XDual
(* ==============================================================================
 * FB_XDual — X 轴双驱（g 线 0.31）：双速度 MoveVelocity + SoftHold
 * 铁律：X 轴（Axis/Axis_1）只允许经本 FB 驱动；FB_Servo 不得持有 X 轴实例。
 * 架构：
 *   - M1/M2 同构：MC_MoveVelocity（废除 M1 MC_Jog）
 *   - 直行：Vel2 = Vel1 - 2*视觉trim + 轻同步trim（同号钳位）
 *   - 换向：符号变化撤 Execute 一拍再重触发（对齐 FB_Servo）
 *   - 松手：立刻撤 Execute → MC_Halt（禁止零速保持 Execute）
 *   - SoftHold：保持调节器；空闲无速度 FB；退出沿 Reset
 *   - 同步误差：线轴直接差分（无 ±180 折算）
 * ============================================================================== *)
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
    rTrimMax : REAL;
    xSyncEnable : BOOL := TRUE;
END_VAR
VAR_OUTPUT
    xMoveDone : BOOL;
    rPosV : REAL;
    rSyncErr : REAL;
    rVelFactor : REAL;
    xCoupled : BOOL;
    xInGearM1 : BOOL;
    xInGearM2 : BOOL;
    xPoweredV : BOOL;
    xSyncWarn : BOOL;
    xSyncFault : BOOL;
    iState : INT;
    iHoldState : INT;
    eSlaveMode : INT;
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
    xVelReqM1 : BOOL;
    xVelReqM2 : BOOL;
    xVelBusyM1 : BOOL;
    xVelBusyM2 : BOOL;
    xErrPowerM1 : BOOL;
    xErrPowerM2 : BOOL;
    xErrVelM1 : BOOL;
    xErrVelM2 : BOOL;
END_VAR
VAR
    fbPowerM1 : MC_Power;
    fbPowerM2 : MC_Power;
    fbResetM1 : MC_Reset;
    fbResetM2 : MC_Reset;
    fbVelM1 : MC_MoveVelocity;
    fbVelM2 : MC_MoveVelocity;
    fbHaltM1 : MC_Halt;
    fbHaltM2 : MC_Halt;
    fbStopM1 : MC_Stop;
    fbStopM2 : MC_Stop;
    eDirM1 : MC_DIRECTION;
    eDirM2 : MC_DIRECTION;
    eMode : INT;
    eModePrev : INT;
    rBase : REAL;
    rVelActM1 : REAL;
    rVelActM2 : REAL;
    rTrim : REAL;
    rTrimPos : REAL;
    rKpSync : REAL := 0.1;   (* 0.31：轻 P，防拉扯 *)
    rKdSync : REAL := 0.0;
    rSyncDeadband : REAL := 0.05;
    rTrimPosMax : REAL := 0.15; (* 0.31：同步修正上限 *)
    rTrimPosStep : REAL := 0.02;
    rTrimPosTgt : REAL;
    rTrimPosLast : REAL;
    rTrimInt : REAL;
    rKiSync : REAL := 0.0;
    tonStillM1 : TON;
    tonStillM2 : TON;
    tonHoldFallback : TON;
    rHoldVelMax : REAL := 0.5;
    xSoftHold : BOOL;
    xSoftHoldPrev : BOOL;
    xSoftHoldExit : BOOL;
    xSoftHoldLatched : BOOL;
    fbSetPosM1 : MC_SetPosition;
    fbSetPosM2 : MC_SetPosition;
    xZeroGate : BOOL;
    tonZeroDelay : TON;
    xZeroReady : BOOL;
    xZeroPulsePrev : BOOL;
    xSetPosReq : BOOL;
    xPosZeroed : BOOL;
    xErrSetPosM1 : BOOL;
    xErrSetPosM2 : BOOL;
    xResetEdge : BOOL;
    xResetPrev : BOOL;
    xVelRaw : BOOL;
    xDirFlipM1 : BOOL;
    xDirFlipM2 : BOOL;
    xVelRunPrevM1 : BOOL;
    xVelRunPrevM2 : BOOL;
    rVelInPrevM1 : REAL;
    rVelInPrevM2 : REAL;
    rVelTgtM1 : REAL;
    rVelTgtM2 : REAL;
    rVelApplM1 : REAL;
    rVelApplM2 : REAL;
    rAccUse : REAL;
    rDecUse : REAL;
    rAccSoftMin : REAL := 0.8;
    (* 0.31：取消 Acc 上限钳位，rAccUse 跟随 HMI rAcc / rDec *)
    rCycleSec : REAL := 0.004;   (* ETHERCAT 任务 4ms *)
    rVelStepMax : REAL;
    rSyncScale : REAL;
    xM1Decel : BOOL;
    xM2Decel : BOOL;
    xBothPowered : BOOL;
    xPowerGate : BOOL;
    xReqVelM1 : BOOL;
    xReqVelM2 : BOOL;
    xNeedStopM1 : BOOL;
    xNeedStopM2 : BOOL;
    xHaltM1Prev : BOOL;
    xHaltM2Prev : BOOL;
    xMovePrev : BOOL;
    xArmed : BOOL;
    rStart : REAL;
    rAvg : REAL;
    rSyncWarnLevel : REAL := 0.05;
    rSyncFaultLevel : REAL := 0.15;
    tonSyncFault : TON;
END_VAR

rVelFactor := 0.0;
xCoupled := FALSE;
xInGearM1 := FALSE;
xInGearM2 := FALSE;
xPoweredV := FALSE;
eSlaveMode := 0;

(* ------------------- 1. 模式 ------------------- *)
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
iState := eMode;
IF eMode <> eModePrev THEN
    rTrimPosLast := 0.0;
    rTrimPos := 0.0;
    rTrimInt := 0.0;
END_IF;
eModePrev := eMode;

(* ------------------- 2. 回读 + SoftHold ------------------- *)
rPosM1 := LREAL_TO_REAL(AxisM1.fActPosition);
rPosM2 := LREAL_TO_REAL(AxisM2.fActPosition);
rVelActM1 := LREAL_TO_REAL(AxisM1.fActVelocity);
rVelActM2 := LREAL_TO_REAL(AxisM2.fActVelocity);
rAvg := (rPosM1 + rPosM2) * 0.5;
rPosV := rAvg;
rSyncErr := rPosM1 - rPosM2;

xStandstillM1 := AxisM1.nAxisState = SMC_AXIS_STATE.standstill;
xStandstillM2 := AxisM2.nAxisState = SMC_AXIS_STATE.standstill;
xMovingM1 := AxisM1.fActVelocity > 0.01 OR AxisM1.fActVelocity < -0.01;
xMovingM2 := AxisM2.fActVelocity > 0.01 OR AxisM2.fActVelocity < -0.01;

tonStillM1(IN := NOT xMovingM1, PT := T#200MS);
tonStillM2(IN := NOT xMovingM2, PT := T#200MS);
tonHoldFallback(IN := (eMode = 0) AND NOT xStop AND xEnable
                    AND (ABS(rVelActM1) < rHoldVelMax) AND (ABS(rVelActM2) < rHoldVelMax),
                PT := T#2S);
IF xStop OR NOT xEnable OR (eMode <> 0) THEN
    iHoldState := 0;
    xSoftHoldLatched := FALSE;
ELSIF xSoftHoldLatched THEN
    iHoldState := 2;
ELSIF (tonStillM1.Q AND tonStillM2.Q) OR tonHoldFallback.Q THEN
    iHoldState := 2;
    xSoftHoldLatched := TRUE;
ELSE
    iHoldState := 1;
END_IF;
xSoftHoldExit := xSoftHoldPrev AND NOT (iHoldState = 2);
xSoftHold := iHoldState = 2;
xSoftHoldPrev := xSoftHold;

xSyncWarn := ABS(rSyncErr) > rSyncWarnLevel;
tonSyncFault(IN := ABS(rSyncErr) > rSyncFaultLevel, PT := T#500MS);
IF tonSyncFault.Q THEN
    xSyncFault := TRUE;
END_IF;

(* ------------------- 3. 复位 ------------------- *)
(* 0.31：Reset 仅手动。禁止 Error 时持续 Reset——会与 xReqVel 因 Error 关断形成死锁，Jog 完全不动 *)
fbResetM1(Axis := AxisM1, Execute := xResetFault);
fbResetM2(Axis := AxisM2, Execute := xResetFault);
IF xResetFault THEN
    xSyncFault := FALSE;
END_IF;

(* ------------------- 4. 使能（SoftHold 保持调节器） ------------------- *)
fbPowerM1(Axis := AxisM1, Enable := xEnable AND NOT xStop,
          bRegulatorOn := xEnable AND NOT xStop, bDriveStart := TRUE);
fbPowerM2(Axis := AxisM2, Enable := xEnable AND NOT xStop,
          bRegulatorOn := xEnable AND NOT xStop, bDriveStart := TRUE);

xPoweredM1 := fbPowerM1.Status OR xSoftHold;
xPoweredM2 := fbPowerM2.Status OR xSoftHold;
xFaultM1 := AxisM1.bError AND NOT (xSoftHold OR (iHoldState = 1));
xFaultM2 := AxisM2.bError AND NOT (xSoftHold OR (iHoldState = 1));
xReadyM1 := xPoweredM1 AND NOT xFaultM1;
xReadyM2 := xPoweredM2 AND NOT xFaultM2;
xBothPowered := xPoweredM1 AND xPoweredM2;
xPowerGate := (xEnable AND NOT xStop AND NOT xFaultM1 AND NOT xFaultM2) OR xM1Decel OR xM2Decel;

(* ------------------- 5. 置零 ------------------- *)
xZeroGate := xEnable AND xBothPowered AND NOT xPosZeroed;
tonZeroDelay(IN := xZeroGate, PT := T#500MS);
xZeroReady := tonZeroDelay.Q AND NOT xZeroPulsePrev;
xZeroPulsePrev := tonZeroDelay.Q;

xResetEdge := xResetFault AND NOT xResetPrev;
xResetPrev := xResetFault;

IF xZeroReady OR xResetEdge THEN
    xSetPosReq := TRUE;
END_IF;
fbSetPosM1(Axis := AxisM1, Execute := xSetPosReq, Position := 0.0);
fbSetPosM2(Axis := AxisM2, Execute := xSetPosReq, Position := 0.0);
xErrSetPosM1 := fbSetPosM1.Error;
xErrSetPosM2 := fbSetPosM2.Error;
IF xSetPosReq THEN
    IF (fbSetPosM1.Done AND fbSetPosM2.Done) OR fbSetPosM1.Error OR fbSetPosM2.Error THEN
        xSetPosReq := FALSE;
        xPosZeroed := TRUE;
        rTrimPosLast := 0.0;
        rTrimPos := 0.0;
        rTrimInt := 0.0;
    END_IF;
END_IF;

(* ------------------- 6. 指令计算（目标速度） ------------------- *)
CASE eMode OF
    1:
        rVelTgtM1 := rBase;
    2:
        rVelTgtM1 := ABS(rSpinVel);
    3:
        rVelTgtM1 := -ABS(rSpinVel);
ELSE
    rVelTgtM1 := 0.0;
END_CASE;

(* 轻同步：到速后才满增益，爬升阶段按进度放开，减少超调拧架 *)
IF (eMode = 1) AND xSyncEnable THEN
    IF ABS(rBase) > 0.001 THEN
        IF (ABS(rVelActM1) >= (0.7 * ABS(rBase))) AND (ABS(rVelActM2) >= (0.7 * ABS(rBase))) THEN
            rSyncScale := 1.0;
        ELSE
            IF ABS(rVelActM1) < ABS(rVelActM2) THEN
                rSyncScale := ABS(rVelActM1) / (0.7 * ABS(rBase));
            ELSE
                rSyncScale := ABS(rVelActM2) / (0.7 * ABS(rBase));
            END_IF;
            IF rSyncScale < 0.0 THEN
                rSyncScale := 0.0;
            END_IF;
            IF rSyncScale > 1.0 THEN
                rSyncScale := 1.0;
            END_IF;
        END_IF;
    ELSE
        rSyncScale := 0.0;
    END_IF;
    IF ABS(rSyncErr) > rSyncDeadband THEN
        rTrimPosTgt := rKpSync * rSyncErr * rSyncScale;
    ELSE
        rTrimPosTgt := 0.0;
    END_IF;
    IF ABS(rBase) > 0.001 THEN
        IF ABS(rTrimPosTgt) > (0.4 * ABS(rBase)) THEN
            IF rTrimPosTgt > 0.0 THEN
                rTrimPosTgt := 0.4 * ABS(rBase);
            ELSE
                rTrimPosTgt := -0.4 * ABS(rBase);
            END_IF;
        END_IF;
    END_IF;
    rTrimPosTgt := LIMIT(-ABS(rTrimPosMax), rTrimPosTgt, ABS(rTrimPosMax));
    rTrimPos := LIMIT(rTrimPosLast - rTrimPosStep, rTrimPosTgt, rTrimPosLast + rTrimPosStep);
    rTrimPosLast := rTrimPos;
    rTrimInt := 0.0;
ELSE
    rTrimPos := 0.0;
    rTrimPosLast := 0.0;
    rTrimInt := 0.0;
    rSyncScale := 0.0;
END_IF;

IF eMode = 1 THEN
    rTrim := LIMIT(-ABS(rTrimMax), rKpTrack * rHeadingErr, ABS(rTrimMax));
    rVelTgtM1 := rBase + rTrim - 0.5 * rTrimPos;
    rVelTgtM2 := rBase - rTrim + 0.5 * rTrimPos;
    IF ABS(rBase) > 0.001 THEN
        IF rBase > 0.0 THEN
            IF rVelTgtM1 < 0.0 THEN
                rVelTgtM1 := 0.0;
            END_IF;
            IF rVelTgtM2 < 0.0 THEN
                rVelTgtM2 := 0.0;
            END_IF;
        ELSE
            IF rVelTgtM1 > 0.0 THEN
                rVelTgtM1 := 0.0;
            END_IF;
            IF rVelTgtM2 > 0.0 THEN
                rVelTgtM2 := 0.0;
            END_IF;
        END_IF;
    END_IF;
ELSIF (eMode = 2) OR (eMode = 3) THEN
    rTrim := 0.0;
    rVelTgtM2 := -rVelTgtM1;
ELSE
    rTrim := 0.0;
    rVelTgtM1 := 0.0;
    rVelTgtM2 := 0.0;
END_IF;
IF xStop OR NOT xEnable THEN
    rVelTgtM1 := 0.0;
    rVelTgtM2 := 0.0;
    rTrimPosLast := 0.0;
    rTrimPos := 0.0;
    rTrimInt := 0.0;
END_IF;

(* 0.31：Acc 软钳位 + 指令斜坡——柔和且双侧同斜坡；SoftMotion Acc 略高于斜坡以便跟紧不超调 *)
(* 0.31：rAccUse/rDecUse 跟随输入，仅保底下限，不再钳到 4 *)
rAccUse := ABS(rAcc);
IF rAccUse < rAccSoftMin THEN
    rAccUse := rAccSoftMin;
END_IF;
rDecUse := ABS(rDec);
IF rDecUse < rAccSoftMin THEN
    rDecUse := rAccSoftMin;
END_IF;

IF ABS(rVelTgtM1) >= ABS(rVelApplM1) THEN
    rVelStepMax := rAccUse * rCycleSec;
ELSE
    rVelStepMax := rDecUse * rCycleSec;
END_IF;
IF ABS(rVelTgtM1 - rVelApplM1) <= rVelStepMax THEN
    rVelApplM1 := rVelTgtM1;
ELSIF rVelTgtM1 > rVelApplM1 THEN
    rVelApplM1 := rVelApplM1 + rVelStepMax;
ELSE
    rVelApplM1 := rVelApplM1 - rVelStepMax;
END_IF;

IF ABS(rVelTgtM2) >= ABS(rVelApplM2) THEN
    rVelStepMax := rAccUse * rCycleSec;
ELSE
    rVelStepMax := rDecUse * rCycleSec;
END_IF;
IF ABS(rVelTgtM2 - rVelApplM2) <= rVelStepMax THEN
    rVelApplM2 := rVelTgtM2;
ELSIF rVelTgtM2 > rVelApplM2 THEN
    rVelApplM2 := rVelApplM2 + rVelStepMax;
ELSE
    rVelApplM2 := rVelApplM2 - rVelStepMax;
END_IF;

rVelCmdM1 := rVelApplM1;
rVelCmdM2 := rVelApplM2;

(* ------------------- 7. 双轴 MoveVelocity（同构） ------------------- *)
(* SoftHold 期间不发速度；斜坡未到 0 时继续 Execute 柔停 *)
xVelRaw := xPowerGate AND NOT xSoftHold AND NOT xStop AND xEnable;

IF (NOT xVelRaw) OR ((ABS(rVelApplM1) <= 0.001) AND (ABS(rVelTgtM1) <= 0.001)) THEN
    xReqVelM1 := FALSE;
ELSE
    xReqVelM1 := TRUE;
END_IF;

IF (NOT xVelRaw) OR ((ABS(rVelApplM2) <= 0.001) AND (ABS(rVelTgtM2) <= 0.001)) THEN
    xReqVelM2 := FALSE;
ELSE
    xReqVelM2 := TRUE;
END_IF;

xM1Decel := (NOT xReqVelM1) AND xPowerGate AND xMovingM1 AND NOT xStop AND NOT xSoftHold;
xM2Decel := (NOT xReqVelM2) AND xPowerGate AND xMovingM2 AND NOT xStop AND NOT xSoftHold;

IF rVelApplM1 >= 0.0 THEN
    eDirM1 := positive;
ELSE
    eDirM1 := negative;
END_IF;
IF rVelApplM2 >= 0.0 THEN
    eDirM2 := positive;
ELSE
    eDirM2 := negative;
END_IF;

xDirFlipM1 := xReqVelM1 AND xVelRunPrevM1 AND ((rVelApplM1 >= 0.0) <> (rVelInPrevM1 >= 0.0));
xDirFlipM2 := xReqVelM2 AND xVelRunPrevM2 AND ((rVelApplM2 >= 0.0) <> (rVelInPrevM2 >= 0.0));

fbVelM1(Axis := AxisM1, Execute := xReqVelM1 AND NOT xDirFlipM1,
        Velocity := ABS(rVelApplM1), Direction := eDirM1,
        Acceleration := rAccUse * 1.5, Deceleration := rDecUse * 1.5);
fbVelM2(Axis := AxisM2, Execute := xReqVelM2 AND NOT xDirFlipM2,
        Velocity := ABS(rVelApplM2), Direction := eDirM2,
        Acceleration := rAccUse * 1.5, Deceleration := rDecUse * 1.5);

xVelRunPrevM1 := xReqVelM1;
xVelRunPrevM2 := xReqVelM2;
rVelInPrevM1 := rVelApplM1;
rVelInPrevM2 := rVelApplM2;

(* ------------------- 8. 停车：松手立刻 Halt ------------------- *)
fbStopM1(Axis := AxisM1, Execute := xStop, Deceleration := rDec);
fbStopM2(Axis := AxisM2, Execute := xStop, Deceleration := rDec);

xNeedStopM1 := xPowerGate AND NOT xSoftHold AND NOT xStop AND NOT xReqVelM1;
xNeedStopM2 := xPowerGate AND NOT xSoftHold AND NOT xStop AND NOT xReqVelM2;
fbHaltM1(Axis := AxisM1, Execute := xNeedStopM1 AND xMovingM1 AND NOT xHaltM1Prev,
         Deceleration := rDec);
fbHaltM2(Axis := AxisM2, Execute := xNeedStopM2 AND xMovingM2 AND NOT xHaltM2Prev,
         Deceleration := rDec);
xHaltM1Prev := xNeedStopM1 AND (xMovingM1 OR NOT tonStillM1.Q);
xHaltM2Prev := xNeedStopM2 AND (xMovingM2 OR NOT tonStillM2.Q);

(* ------------------- 9. 诊断与走距完成 ------------------- *)
xVelReqM1 := xReqVelM1;
xVelReqM2 := xReqVelM2;
xVelBusyM1 := fbVelM1.Busy;
xVelBusyM2 := fbVelM2.Busy;
xErrPowerM1 := fbPowerM1.Error;
xErrPowerM2 := fbPowerM2.Error;
xErrVelM1 := fbVelM1.Error;
xErrVelM2 := fbVelM2.Error;

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
