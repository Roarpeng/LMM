(* ==============================================================================
 * FB_XDual — X 轴双驱（g 线 0.56）：点动期间 Execute 闭锁，Status 闪烁不重爬
 * 铁律：X 轴只经本 FB；FB_Servo 不得持有 X 轴实例。
 *
 *   0.44 根因：Enable 和调节器一起关 → Power FB 停转，驱动收不到卸使能；
 *   运动中切使能 + 刚上使能就 Execute → 连冲、Error 锁死第二次点动。
 *   对齐 FB_Servo：Enable 保持，bRegulatorOn/bDriveStart 跟 xRegOn；
 *   松手 Halt 脉冲刹停，双轴 standstill 后才卸调节器；2s 未静止改发 Stop。
 *   冷启动等 Status 约 80ms 且双轴 standstill 再出速度；短窗内再按不再等。
 *   0.47：禁止 300ms 超时在减速中卸使能（运动中送掉使能报错）。
 *   0.50：幅值差速不撤 Execute。必须重触发的只有换向。
 *   0.51：0.50 仍三次过冲——使能后 20ms 就 Execute（失败连打）+ 爬坡每拍改 Velocity。
 *         上使能后等 Status 80ms；Error 锁 150ms；爬坡只吃基速，到速后再跟 trim。
 *   0.52：xErrVel 不跳仍冲三次+忽快忽慢。根因是 0.51 把 xPowerSettled 绑在 standstill：
 *         轴一动就掉 Execute，松手前 Acc/Dec 反复爬。闭锁一次后保持；残差 P 降增益。
 *   0.53：xVelReq 一直 TRUE 仍冲三次。请求≠Execute；Acc=Jog 时 SM3 梯形拐点 + 使能冲击叠成三次。
 *         PLC 按用户 Acc 爬 FB 速度，SM3 Acc 抬到 ≥10 只负责跟上；松手仍 Halt。
 *   0.54：0.53 不过冲也不走。本机 Execute 保持时 Velocity 不刷新，第一拍 ~0 被锁死。
 *         上升沿一次写入目标速度 + 用户 Acc；爬坡中不改输入；到速后再跟 trim。
 *   0.55：三次过冲=Execute 被拉了三次。PRG_Logic 先清 AxisCmd 再置位，ETHERCAT(prio0)
 *         在 FALSE 空窗采到松手→Halt→再加速。第一次点动 Logic 超时约 3 拍。去抖+一次写入。
 *   0.56：偶发三次过冲。0.55 去抖保了 eMode，但 Power.Status 闪一下仍清 xStartReady，
 *         Execute 掉、锁存清 0，再启动就是又一次过冲。点动中 Execute 闭锁到松开。
 * ============================================================================== *)

rVelFactor := 0.0;
xCoupled := FALSE;
xInGearM1 := FALSE;
xInGearM2 := FALSE;
xPoweredV := FALSE;
eSlaveMode := 0;

(* ------------------- 1. 模式 ------------------- *)
(* 点动 FALSE 短于 40ms 视为空窗，不 Halt、不撤 Execute *)
xJogRaw := (xJogPos XOR xJogNeg) OR xMoveRel;
tonJogOff(IN := xJogHeld AND NOT xJogRaw AND xEnable AND NOT xStop
           AND NOT (xSpinLeft XOR xSpinRight), PT := T#40MS);
IF xStop OR NOT xEnable THEN
    eMode := 0;
    rBase := 0.0;
    xJogHeld := FALSE;
ELSIF xSpinLeft XOR xSpinRight THEN
    IF xSpinLeft THEN
        eMode := 2;
    ELSE
        eMode := 3;
    END_IF;
    rBase := 0.0;
    xJogHeld := FALSE;
ELSIF xJogRaw THEN
    eMode := 1;
    xJogHeld := TRUE;
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
ELSIF xJogHeld AND NOT tonJogOff.Q THEN
    eMode := 1;
ELSE
    eMode := 0;
    rBase := 0.0;
    xJogHeld := FALSE;
END_IF;
iState := eMode;
xStraightEdge := (eMode = 1) AND (eModePrev <> 1);

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
xMovingM1 := (NOT xStandstillM1) OR (ABS(rVelActM1) > 0.01);
xMovingM2 := (NOT xStandstillM2) OR (ABS(rVelActM2) > 0.01);

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
xSoftHold := iHoldState = 2;
xSoftHoldPrev := xSoftHold;
(* 再按起步 300ms 内隐藏 SoftHold/Halt 残留 bError，避免 Fault→StopAll 发肉 *)
tonJogGrace(IN := (eMode <> 0), PT := T#300MS);

xSyncWarn := ABS(rSyncErr) > rSyncWarnLevel;
tonSyncFault(IN := ABS(rSyncErr) > rSyncFaultLevel, PT := T#500MS);
IF tonSyncFault.Q THEN
    xSyncFault := TRUE;
END_IF;

(* ------------------- 3. 复位仅手动 ------------------- *)
fbResetM1(Axis := AxisM1, Execute := xResetFault);
fbResetM2(Axis := AxisM2, Execute := xResetFault);
IF xResetFault THEN
    xSyncFault := FALSE;
END_IF;

(* ------------------- 4. 使能：Power.Enable 常开，只切调节器 ------------------- *)
(* 松手保持调节器直到双轴 standstill。300ms 超时会在减速未完时卸使能（0.46 报错）。 *)
xWasStopping := xStopping;
IF xStop OR NOT xEnable THEN
    xStopping := FALSE;
ELSIF eMode <> 0 THEN
    xStopping := FALSE;
ELSIF xRegOnPrev THEN
    xStopping := TRUE;
END_IF;
tonHaltWin(IN := xStopping AND (eMode = 0) AND xEnable AND NOT xStop, PT := T#2S);
IF xStopping AND (eMode = 0) AND xStandstillM1 AND xStandstillM2 THEN
    xStopping := FALSE;
END_IF;
xRegOn := xEnable AND NOT xStop AND ((eMode <> 0) OR xStopping);
xStopFallback := xStopping AND tonHaltWin.Q AND NOT (xStandstillM1 AND xStandstillM2);
(* Enable 恒 TRUE，卸使能只走调节器（对齐 FB_Servo；0.44 关 Enable 导致驱动收不到） *)
fbPowerM1(Axis := AxisM1, Enable := TRUE,
          bRegulatorOn := xRegOn, bDriveStart := xRegOn);
fbPowerM2(Axis := AxisM2, Enable := TRUE,
          bRegulatorOn := xRegOn, bDriveStart := xRegOn);

xPoweredM1 := fbPowerM1.Status;
xPoweredM2 := fbPowerM2.Status;
xFaultM1 := AxisM1.bError AND xRegOn AND NOT (xSoftHold OR (iHoldState = 1) OR xStopping OR ((eMode <> 0) AND NOT tonJogGrace.Q));
xFaultM2 := AxisM2.bError AND xRegOn AND NOT (xSoftHold OR (iHoldState = 1) OR xStopping OR ((eMode <> 0) AND NOT tonJogGrace.Q));
(* 故意停调节器时仍报就绪，避免 Logic 1007 *)
xReadyM1 := xEnable AND NOT xStop AND NOT xFaultM1;
xReadyM2 := xEnable AND NOT xStop AND NOT xFaultM2;
xBothPowered := xPoweredM1 AND xPoweredM2;
xPowerGate := xEnable AND NOT xStop AND NOT xFaultM1 AND NOT xFaultM2;
tonPowerOk(IN := xRegOn AND xBothPowered AND (eMode <> 0), PT := T#80MS);
(* 冷启动闭锁一次。Status 闪烁不得清 xStartReady，否则 Execute 掉了再爬。 *)
IF (eMode = 0) OR NOT xRegOn OR xStop THEN
    xStartReady := FALSE;
ELSIF xWasStopping OR xExecHold THEN
    xStartReady := TRUE;
ELSIF tonPowerOk.Q AND xStandstillM1 AND xStandstillM2 THEN
    xStartReady := TRUE;
END_IF;
xPowerSettled := xRegOn AND (eMode <> 0) AND xStartReady
                 AND (xBothPowered OR xExecHold);

(* 置零：点动/短窗禁止；空闲自动置零会和 Halt 抢轴，只保留手动 Reset *)
IF (eMode <> 0) OR xStopping OR xStop OR NOT xEnable THEN
    xSetPosReq := FALSE;
END_IF;
xZeroGate := FALSE;
tonZeroDelay(IN := FALSE, PT := T#300MS);
xZeroReady := FALSE;
xZeroPulsePrev := FALSE;
xResetEdge := xResetFault AND NOT xResetPrev;
xResetPrev := xResetFault;
IF xResetEdge AND (eMode = 0) AND NOT xStopping THEN
    xSetPosReq := TRUE;
END_IF;
fbSetPosM1(Axis := AxisM1, Execute := xSetPosReq AND (eMode = 0) AND NOT xStopping, Position := 0.0);
fbSetPosM2(Axis := AxisM2, Execute := xSetPosReq AND (eMode = 0) AND NOT xStopping, Position := 0.0);
xErrSetPosM1 := fbSetPosM1.Error;
xErrSetPosM2 := fbSetPosM2.Error;
IF xSetPosReq THEN
    IF (fbSetPosM1.Done AND fbSetPosM2.Done) OR fbSetPosM1.Error OR fbSetPosM2.Error THEN
        xSetPosReq := FALSE;
        xPosZeroed := TRUE;
    END_IF;
END_IF;

(* ------------------- 6. 基速跟手 + 视觉差速 ------------------- *)
rAccUse := ABS(rAcc);
IF rAccUse < rAccSoftMin THEN
    rAccUse := rAccSoftMin;
END_IF;
rDecUse := ABS(rDec);
IF rDecUse < rAccSoftMin THEN
    rDecUse := rAccSoftMin;
END_IF;
rVelStepMax := rAccUse * rCycleSec;

(* 0.36：禁止 PLC 再爬 rVelAppl。按下即目标速度，松开即 0，停靠 Halt。 *)
IF (eMode = 0) OR xStop OR NOT xEnable THEN
    rVelAppl := 0.0;
ELSIF eMode = 1 THEN
    rVelAppl := rBase;
ELSE
    rVelAppl := 0.0;
END_IF;

(* 视觉：同一条基速上 ±trim，不是第二次运动，不撤 Execute *)
rTrimRaw := 0.0;
rCorrPos := 0.0;
rCorrV1 := 0.0;
rCorrV2 := 0.0;
rUseRatioM1 := rRatioM1;
IF rUseRatioM1 < 0.1 THEN
    rUseRatioM1 := 0.1;
END_IF;
rUseRatioM2 := rRatioM2;
IF rUseRatioM2 < 0.1 THEN
    rUseRatioM2 := 0.1;
END_IF;
IF eMode = 1 THEN
    IF ABS(rHeadingErr) > ABS(rHeadingDeadband) THEN
        IF rHeadingErr > 0.0 THEN
            rTrimRaw := (rHeadingErr - ABS(rHeadingDeadband)) * rKpTrack;
        ELSE
            rTrimRaw := (rHeadingErr + ABS(rHeadingDeadband)) * rKpTrack;
        END_IF;
        rTrimRaw := LIMIT(-ABS(rTrimMax), rTrimRaw, ABS(rTrimMax));
    END_IF;
    IF rTrimFilterTc > 0.001 THEN
        rAlphaFilter := rCycleSec / (rTrimFilterTc + rCycleSec);
        rTrimFiltered := rTrimFiltered + rAlphaFilter * (rTrimRaw - rTrimFiltered);
    ELSE
        rTrimFiltered := rTrimRaw;
    END_IF;
    rTrim := rTrimFiltered;
    IF xStraightEdge THEN
        rSyncExpect := rPosM1 - rPosM2;
        rTrimFiltered := 0.0;
        rTrim := 0.0;
        xRampLock := TRUE;
    END_IF;
    rSyncExpect := rSyncExpect + (2.0 * rTrim * rCycleSec);
    rSyncResid := (rPosM1 - rPosM2) - rSyncExpect;
    rCorrLim := ABS(rCorrPosMax);
    IF ABS(rVelAppl) > 0.001 THEN
        IF (0.25 * ABS(rVelAppl)) < rCorrLim THEN
            rCorrLim := 0.25 * ABS(rVelAppl);
        END_IF;
    END_IF;
    IF xSyncEnable AND (ABS(rVelAppl) > 0.001) THEN
        IF ABS(rSyncResid) > rSyncDeadband THEN
            rCorrPos := LIMIT(-rCorrLim, rKpSync * rSyncResid, rCorrLim);
        END_IF;
        rCorrV1 := LIMIT(-ABS(rCorrVelMax), rKvSync * ((rVelAppl + rTrim) - rVelActM1), ABS(rCorrVelMax));
        rCorrV2 := LIMIT(-ABS(rCorrVelMax), rKvSync * ((rVelAppl - rTrim) - rVelActM2), ABS(rCorrVelMax));
    END_IF;
    rVelFF1 := rVelAppl + rTrim;
    rVelFF2 := rVelAppl - rTrim;
    rVelCmdM1 := (rVelFF1 - 0.5 * rCorrPos + rCorrV1) * rUseRatioM1;
    rVelCmdM2 := (rVelFF2 + 0.5 * rCorrPos + rCorrV2) * rUseRatioM2;
    IF ABS(rVelAppl) > 0.001 THEN
        IF rVelAppl > 0.0 THEN
            IF rVelCmdM1 < 0.0 THEN
                rVelCmdM1 := 0.0;
            END_IF;
            IF rVelCmdM2 < 0.0 THEN
                rVelCmdM2 := 0.0;
            END_IF;
        ELSE
            IF rVelCmdM1 > 0.0 THEN
                rVelCmdM1 := 0.0;
            END_IF;
            IF rVelCmdM2 > 0.0 THEN
                rVelCmdM2 := 0.0;
            END_IF;
        END_IF;
    END_IF;
ELSIF (eMode = 2) OR (eMode = 3) THEN
    rTrimFiltered := 0.0;
    IF eMode = 2 THEN
        rVelCmdM1 := ABS(rSpinVel) * rUseRatioM1;
    ELSE
        rVelCmdM1 := -ABS(rSpinVel) * rUseRatioM1;
    END_IF;
    rVelCmdM2 := -rVelCmdM1 * (rUseRatioM2 / rUseRatioM1);
ELSE
    rTrimFiltered := 0.0;
    rVelCmdM1 := rVelAppl;
    rVelCmdM2 := rVelAppl;
END_IF;
IF xStop OR NOT xEnable THEN
    rVelCmdM1 := 0.0;
    rVelCmdM2 := 0.0;
END_IF;
IF eMode <> 1 THEN
    xRampLock := FALSE;
ELSIF xRampLock THEN
    IF (ABS(rVelAppl) > 0.001)
            AND (ABS(rVelActM1) >= 0.8 * ABS(rVelAppl))
            AND (ABS(rVelActM2) >= 0.8 * ABS(rVelAppl)) THEN
        xRampLock := FALSE;
    END_IF;
END_IF;
tonRampLock(IN := xRampLock AND (eMode = 1), PT := T#800MS);
IF tonRampLock.Q THEN
    xRampLock := FALSE;
END_IF;
IF (eMode = 1) AND xRampLock THEN
    rVelFbM1 := rVelAppl * rUseRatioM1;
    rVelFbM2 := rVelAppl * rUseRatioM2;
ELSE
    rVelFbM1 := rVelCmdM1;
    rVelFbM2 := rVelCmdM2;
END_IF;
IF (eMode <> 1) OR xStraightEdge THEN
    rVelFbHoldM1 := rVelFbM1;
    rVelFbHoldM2 := rVelFbM2;
ELSE
    IF ABS(rVelFbM1 - rVelFbHoldM1) < 0.004 THEN
        rVelFbM1 := rVelFbHoldM1;
    ELSE
        rVelFbHoldM1 := rVelFbM1;
    END_IF;
    IF ABS(rVelFbM2 - rVelFbHoldM2) < 0.004 THEN
        rVelFbM2 := rVelFbHoldM2;
    ELSE
        rVelFbHoldM2 := rVelFbM2;
    END_IF;
END_IF;

(* ------------------- 7. 双轴 MoveVelocity ------------------- *)
(* 0.56：上升沿锁目标。点动中 Execute 闭锁；Halt 未结束不开速度。 *)
xHaltBusy := fbHaltM1.Busy OR fbHaltM2.Busy OR fbStopM1.Busy OR fbStopM2.Busy;
IF (eMode = 1) AND xPowerGate AND xPowerSettled AND (ABS(rVelAppl) > 0.001)
        AND NOT xHaltBusy THEN
    xReqVelM1 := TRUE;
    xReqVelM2 := TRUE;
ELSIF ((eMode = 2) OR (eMode = 3)) AND xPowerGate AND xPowerSettled AND NOT xHaltBusy THEN
    IF ABS(rVelCmdM1) > 0.001 THEN
        xReqVelM1 := TRUE;
    ELSE
        xReqVelM1 := FALSE;
    END_IF;
    IF ABS(rVelCmdM2) > 0.001 THEN
        xReqVelM2 := TRUE;
    ELSE
        xReqVelM2 := FALSE;
    END_IF;
ELSE
    xReqVelM1 := FALSE;
    xReqVelM2 := FALSE;
END_IF;

xM1Decel := (NOT xReqVelM1) AND xPowerGate AND xMovingM1 AND NOT xStop AND NOT xSoftHold;
xM2Decel := (NOT xReqVelM2) AND xPowerGate AND xMovingM2 AND NOT xStop AND NOT xSoftHold;

IF ABS(rVelFbM1) > 0.001 THEN
    IF rVelFbM1 >= 0.0 THEN
        eDirM1 := positive;
    ELSE
        eDirM1 := negative;
    END_IF;
END_IF;
IF ABS(rVelFbM2) > 0.001 THEN
    IF rVelFbM2 >= 0.0 THEN
        eDirM2 := positive;
    ELSE
        eDirM2 := negative;
    END_IF;
END_IF;

xDirFlipM1 := xReqVelM1 AND xVelRunPrevM1
              AND (ABS(rVelFbM1) > 0.001) AND (ABS(rVelInPrevM1) > 0.001)
              AND ((rVelFbM1 >= 0.0) <> (rVelInPrevM1 >= 0.0));
xDirFlipM2 := xReqVelM2 AND xVelRunPrevM2
              AND (ABS(rVelFbM2) > 0.001) AND (ABS(rVelInPrevM2) > 0.001)
              AND ((rVelFbM2 >= 0.0) <> (rVelInPrevM2 >= 0.0));
xDirFlipAny := xDirFlipM1 OR xDirFlipM2;

IF (xErrVelM1 OR xErrVelM2) AND NOT xErrVelPrev THEN
    xVelHoldOff := TRUE;
END_IF;
tonVelHold(IN := xVelHoldOff, PT := T#150MS);
IF tonVelHold.Q THEN
    xVelHoldOff := FALSE;
END_IF;
xErrVelPrev := xErrVelM1 OR xErrVelM2;

xHaltTrig := xStopping AND (eMode = 0) AND NOT xStop AND NOT xStopFallback
             AND (xMovingM1 OR xMovingM2);
xNeedHaltM1 := xHaltTrig AND NOT xHaltPrev;
xNeedHaltM2 := xNeedHaltM1;
IF xStop OR NOT xEnable OR (eMode = 0) THEN
    xExecHold := FALSE;
ELSIF xReqVelM1 THEN
    xExecHold := TRUE;
END_IF;
xExecBoth := NOT xDirFlipAny AND NOT xNeedHaltM1 AND NOT xVelHoldOff;
xExecM1 := xExecHold AND xExecBoth;
IF xExecM1 AND NOT xExecPrev THEN
    iVelExecRise := iVelExecRise + 1;
    rVelLatchM1 := ABS(rVelFbM1);
    rVelLatchM2 := ABS(rVelFbM2);
    rAccLatch := rAccUse;
    rDecLatch := rDecUse;
ELSIF xExecHold AND xVelInVelM1 AND xVelInVelM2
        AND (ABS(rVelAppl) > 0.001)
        AND (ABS(rVelActM1) >= 0.9 * ABS(rVelAppl))
        AND (ABS(rVelActM2) >= 0.9 * ABS(rVelAppl)) THEN
    IF ABS(ABS(rVelFbM1) - rVelLatchM1) >= 0.004 THEN
        rVelLatchM1 := ABS(rVelFbM1);
    END_IF;
    IF ABS(ABS(rVelFbM2) - rVelLatchM2) >= 0.004 THEN
        rVelLatchM2 := ABS(rVelFbM2);
    END_IF;
ELSIF NOT xExecHold THEN
    rVelLatchM1 := 0.0;
    rVelLatchM2 := 0.0;
END_IF;
fbVelM1(Axis := AxisM1, Execute := xExecM1,
        Velocity := rVelLatchM1, Direction := eDirM1,
        Acceleration := rAccLatch, Deceleration := rDecLatch);
fbVelM2(Axis := AxisM2, Execute := xExecHold AND xExecBoth,
        Velocity := rVelLatchM2, Direction := eDirM2,
        Acceleration := rAccLatch, Deceleration := rDecLatch);

xExecPrev := xExecM1;
xVelRunPrevM1 := xReqVelM1;
xVelRunPrevM2 := xReqVelM2;
rVelInPrevM1 := rVelFbM1;
rVelInPrevM2 := rVelFbM2;

(* ------------------- 8. 停车 ------------------- *)
fbStopM1(Axis := AxisM1, Execute := xStop OR xStopFallback, Deceleration := rDecUse);
fbStopM2(Axis := AxisM2, Execute := xStop OR xStopFallback, Deceleration := rDecUse);
fbHaltM1(Axis := AxisM1, Execute := xNeedHaltM1, Deceleration := rDecUse);
fbHaltM2(Axis := AxisM2, Execute := xNeedHaltM2, Deceleration := rDecUse);
xHaltPrev := xHaltTrig;

(* ------------------- 9. 诊断与走距 ------------------- *)
xVelReqM1 := xReqVelM1;
xVelReqM2 := xReqVelM2;
xVelExecM1 := xExecM1;
xVelExecM2 := xExecHold AND xExecBoth;
xVelBusyM1 := fbVelM1.Busy;
xVelBusyM2 := fbVelM2.Busy;
xVelInVelM1 := fbVelM1.InVelocity;
xVelInVelM2 := fbVelM2.InVelocity;
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
IF NOT xEnable THEN
    iVelExecRise := 0;
END_IF;
xMovePrev := xMoveRel;
eModePrev := eMode;
xRegOnPrev := xRegOn;