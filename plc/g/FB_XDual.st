FUNCTION_BLOCK FB_XDual
(* ==============================================================================
 * FB_XDual — X 轴双驱（g 线 0.59）：单沿起步 + SM3 斜坡 + Halt 对称减速
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
 *   0.57：现场仍每次起步沿 X 往复冲 3 次（约 3s）。根因：起步=速度阶跃（Acc=25）
 *         打进 CSV 速度环，激起双驱耦合龙门 ~1Hz 纵向共振。0.53 阶梯爬速本可消过冲，
 *         但本机 Execute 保持时 Velocity 不刷新，首拍 ~0 锁死（"不过冲也不走"）。
 *   0.58：恢复 rVelSlew 阶梯爬速；爬坡期 Execute 每步重触发（OFF/ON 交替一拍，
 *         上升沿重采样）；斜率取用户 Acc/Dec 钳 [0.05, rRampAccMax]，SM3 Acc 只跟梯；
 *         松手/到位先阶梯降到 ~0 再 Halt；MoveRel 剩余≤slew²/2Dec 提前减速；
 *         到位锁 xDecelDone 禁停稳后重爬目标。
 *   0.59：0.58 每步重触发 = 250Hz 沿风暴，现场 acc=0.8 起步仍快速冲 2 次（~1s）、
 *         第三次慢、停死；M2 明显慢于 M1（两侧接受沿时刻不一致，M2 漏沿爬速落后）。
 *         改单沿起步：一个上升沿写最终目标 + 钳制用户 Acc/Dec（0.05~1.0），
 *         SM3 自带斜坡 0→目标（0.8 → 0.5s）；稳态 trim/sync 更新走限频重触发
 *         （≥200ms 一次、差值≥0.004）；减速统一 Halt（用户 Dec 对称）。
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
    rRatioM1 : REAL := 1.0;
    rRatioM2 : REAL := 1.0;
    rHeadingDeadband : REAL := 0.003;
    rTrimFilterTc : REAL := 0.05;
    rCycleSec : REAL := 0.004;
    (* 0.60 外部直控（视觉直写 M1/M2 速度）：xDirectMode=TRUE 时绕过 trim/sync *)
    xDirectMode : BOOL;
    rVelM1Direct : REAL;
    rVelM2Direct : REAL;
    tDirectRetrig : TIME := T#40MS;
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
    xVelExecM1 : BOOL;
    xVelExecM2 : BOOL;
    xVelInVelM1 : BOOL;
    xVelInVelM2 : BOOL;
    iVelExecRise : INT;
    rVelActM1Out : REAL;
    rVelActM2Out : REAL;
    xDirectActive : BOOL;
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
    rTrimRaw : REAL;
    rTrimFiltered : REAL;
    rAlphaFilter : REAL;
    rUseRatioM1 : REAL;
    rUseRatioM2 : REAL;
    rSyncExpect : REAL;
    rSyncResid : REAL;
    rCorrPos : REAL;
    rCorrV1 : REAL;
    rCorrV2 : REAL;
    rVelFF1 : REAL;
    rVelFF2 : REAL;
    rKpSync : REAL := 0.05;
    rKvSync : REAL := 0.0;
    rSyncDeadband : REAL := 0.02;
    rCorrPosMax : REAL := 0.08;
    rCorrVelMax : REAL := 0.06;
    xStraightEdge : BOOL;
    xJogRaw : BOOL;
    xJogHeld : BOOL;
    tonJogOff : TON;
    tonStillM1 : TON;
    tonStillM2 : TON;
    tonHoldFallback : TON;
    tonJogGrace : TON;
    rHoldVelMax : REAL := 0.5;
    xSoftHold : BOOL;
    xSoftHoldPrev : BOOL;
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
    xDirFlipM1 : BOOL;
    xDirFlipM2 : BOOL;
    xVelRunPrevM1 : BOOL;
    xVelRunPrevM2 : BOOL;
    rVelInPrevM1 : REAL;
    rVelInPrevM2 : REAL;
    rVelAppl : REAL;
    rAccUse : REAL;
    rDecUse : REAL;
    rAccLatch : REAL;
    rDecLatch : REAL;
    rVelLatchM1 : REAL;
    rVelLatchM2 : REAL;
    xExecPrev : BOOL;
    rAccSoftMin : REAL := 0.05;
    rAccSoft : REAL;
    rDecSoft : REAL;
    rRampAccMax : REAL := 1.0;
    xDecelActive : BOOL;
    xDecelDone : BOOL;
    rDecelDist : REAL;
    xM1Decel : BOOL;
    xM2Decel : BOOL;
    xBothPowered : BOOL;
    xPowerGate : BOOL;
    xReqVelM1 : BOOL;
    xReqVelM2 : BOOL;
    xNeedHaltM1 : BOOL;
    xNeedHaltM2 : BOOL;
    xRegOn : BOOL;
    xRegOnPrev : BOOL;
    xStopping : BOOL;
    xWasStopping : BOOL;
    xHaltTrig : BOOL;
    xHaltPrev : BOOL;
    xPowerSettled : BOOL;
    xStartReady : BOOL;
    xStopFallback : BOOL;
    tonHaltWin : TON;
    tonPowerOk : TON;
    tonVelHold : TON;
    tonRampLock : TON;
    tonTrimRetrig : TON;
    xTrimWant : BOOL;
    xTrimPulse : BOOL;
    xTrimPulsePrev : BOOL;
    xMoveRelDecelTrig : BOOL;
    xExecM1 : BOOL;
    xExecHold : BOOL;
    xHaltBusy : BOOL;
    xExecBoth : BOOL;
    xDirFlipAny : BOOL;
    xVelHoldOff : BOOL;
    xErrVelPrev : BOOL;
    xRampLock : BOOL;
    rVelFbM1 : REAL;
    rVelFbM2 : REAL;
    rVelFbHoldM1 : REAL;
    rVelFbHoldM2 : REAL;
    rCorrLim : REAL;
    xMovePrev : BOOL;
    xArmed : BOOL;
    rStart : REAL;
    rAvg : REAL;
    rSyncWarnLevel : REAL := 0.05;
    rSyncFaultLevel : REAL := 0.15;
    tonSyncFault : TON;
    tonDirectRetrig : TON;
    xDirectWant : BOOL;
    xDirectPulse : BOOL;
    xDirectPulsePrev : BOOL;
    xHaltDemand : BOOL;
END_VAR

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
ELSIF xDirectMode THEN
    (* 0.60 外部直控优先于点动：视觉接管期间忽略点动/走距输入 *)
    eMode := 4;
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
xStopFallback := xStopping AND tonHaltWin.Q AND NOT (xStandstillM1 AND xStandstillM2) AND NOT xDecelActive;
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

(* 0.59：SM3 斜坡用钳制 Acc/Dec（0.05~rRampAccMax）。HMI 25/100 兜底不再变阶跃；
   rDecUse 保留软下限继续供 Stop 急停。 *)
rAccSoft := ABS(rAcc);
IF rAccSoft < rAccSoftMin THEN
    rAccSoft := rAccSoftMin;
END_IF;
IF rAccSoft > rRampAccMax THEN
    rAccSoft := rRampAccMax;
END_IF;
rDecSoft := ABS(rDec);
IF rDecSoft < rAccSoftMin THEN
    rDecSoft := rAccSoftMin;
END_IF;
IF rDecSoft > rRampAccMax THEN
    rDecSoft := rRampAccMax;
END_IF;

(* 0.36：禁止 PLC 再爬 rVelAppl。按下即目标速度，松开即 0，停靠 Halt。 *)
(* 0.59 注：rVelAppl 是最终目标；起步斜坡由 SM3 按 rAccSoft 生成（单沿锁存）。 *)
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
ELSIF eMode = 4 THEN
    (* 0.60 外部直控：两个速度直接来自视觉，不做 trim/sync/斜坡 *)
    rTrimFiltered := 0.0;
    rVelCmdM1 := rVelM1Direct * rUseRatioM1;
    rVelCmdM2 := rVelM2Direct * rUseRatioM2;
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
(* 0.54：上升沿锁目标。0.58 每步重触发被 0.59 废除：250Hz 沿风暴反复踢起龙门
   1Hz 共振（现场 acc=0.8：起步快速冲 2 次 ~1s、第三次慢、停死）；两侧 FB/驱动
   接受沿时刻不一致 → M2 漏沿爬速落后（M2 明显慢）。0.59：起步只发一个上升沿，
   一次写入最终目标 + 钳制 Acc/Dec，SM3 自带斜坡 0→目标（0.8 → 0.5s）；
   稳态 trim/sync 更新走限频重触发；减速由 Halt 接管（见第 8 节）。 *)
xHaltBusy := fbHaltM1.Busy OR fbHaltM2.Busy OR fbStopM1.Busy OR fbStopM2.Busy;
IF (eMode = 1) AND xPowerGate AND xPowerSettled AND (ABS(rVelAppl) > 0.001)
        AND NOT xHaltBusy AND NOT xDecelActive AND NOT xDecelDone THEN
    xReqVelM1 := TRUE;
    xReqVelM2 := TRUE;
ELSIF ((eMode = 2) OR (eMode = 3) OR (eMode = 4)) AND xPowerGate AND xPowerSettled AND NOT xHaltBusy
        AND NOT xDecelActive AND NOT xDecelDone THEN
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

(* 方向/换向看 FB 速度（0.54 语义）；减速期由 Halt 接管，无符号穿零 *)
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

(* 0.59 提前减速：剩余 ≤ v²/(2·Dec)，v 取双轴实际速度较大者（越保守越早触发）。
   MoveRel 未武装/静止（moved≈0）不触发，短走距不得起步即停。 *)
rDecelDist := 0.0;
IF ABS(rVelActM1) >= ABS(rVelActM2) THEN
    rDecelDist := (ABS(rVelActM1) * ABS(rVelActM1)) / (2.0 * rDecSoft);
ELSE
    rDecelDist := (ABS(rVelActM2) * ABS(rVelActM2)) / (2.0 * rDecSoft);
END_IF;
xMoveRelDecelTrig := xMoveRel AND xArmed AND (NOT xDecelDone)
                     AND (ABS(rMoveDist) > 0.001)
                     AND (ABS(rAvg - rStart) > 0.001)
                     AND (ABS(rAvg - rStart) >= ABS(rMoveDist) - rDecelDist);

(* 松手短窗 Halt 脉冲 + MoveRel 提前减速 Halt 脉冲；减速期禁重复发 *)
xHaltTrig := (xStopping AND (eMode = 0) AND NOT xStop AND NOT xStopFallback
              AND (xMovingM1 OR xMovingM2) AND NOT xDecelActive)
             OR (xMoveRelDecelTrig AND NOT xDecelActive);
(* 0.60 外部直控：任一侧目标为 0 且在动 → 双轴 Halt（停止/失联兜底由 eMode→0 处理） *)
xHaltDemand := xHaltTrig OR ((eMode = 4)
               AND (((NOT xReqVelM1) AND xMovingM1) OR ((NOT xReqVelM2) AND xMovingM2)));
xNeedHaltM1 := xHaltDemand AND NOT xHaltPrev;
xNeedHaltM2 := xNeedHaltM1;
(* 0.56 点动闭锁 + 0.59 减速期撤 Execute（Halt 接管，禁止速度指令抢轴） *)
IF xStop OR NOT xEnable THEN
    xExecHold := FALSE;
ELSIF xDecelActive THEN
    xExecHold := FALSE;
ELSIF xReqVelM1 THEN
    xExecHold := TRUE;
ELSIF (eMode = 0) OR ((eMode = 4) AND (NOT xReqVelM1 OR NOT xReqVelM2)) THEN
    xExecHold := FALSE;
END_IF;
(* 0.59 稳态 trim/sync 更新：限频重触发（≥200ms 一次）。仅非爬坡期（xRampLock 已放）、
   两侧到速、目标与锁存差 ≥0.004。脉冲期撤 Execute 一拍，下一拍上升沿重采样；
   无视觉/同步漂移时永不触发——起步到停车全程一个沿。 *)
xTrimWant := xExecHold AND (NOT xRampLock) AND xVelInVelM1 AND xVelInVelM2
             AND (NOT xDecelActive) AND (NOT xStop)
             AND ((ABS(ABS(rVelFbM1) - rVelLatchM1) >= 0.004)
                  OR (ABS(ABS(rVelFbM2) - rVelLatchM2) >= 0.004));
tonTrimRetrig(IN := xTrimWant, PT := T#200MS);
xTrimPulse := xTrimWant AND tonTrimRetrig.Q AND NOT xTrimPulsePrev;
xTrimPulsePrev := xTrimWant;
(* 0.60 外部直控：目标变化时限频重触发，跟随视觉（无变化不触发，不起沿风暴） *)
xDirectWant := (eMode = 4) AND xExecHold AND (NOT xDecelActive) AND (NOT xStop)
               AND ((ABS(ABS(rVelFbM1) - rVelLatchM1) >= 0.004)
                    OR (ABS(ABS(rVelFbM2) - rVelLatchM2) >= 0.004));
tonDirectRetrig(IN := xDirectWant, PT := tDirectRetrig);
xDirectPulse := xDirectWant AND tonDirectRetrig.Q AND NOT xDirectPulsePrev;
xDirectPulsePrev := xDirectWant;
xExecBoth := NOT xDirFlipAny AND NOT xNeedHaltM1 AND NOT xVelHoldOff AND NOT xTrimPulse
             AND NOT xDirectPulse;
xExecM1 := xExecHold AND xExecBoth;
IF xExecM1 AND NOT xExecPrev THEN
    iVelExecRise := iVelExecRise + 1;
    rVelLatchM1 := ABS(rVelFbM1);
    rVelLatchM2 := ABS(rVelFbM2);
    rAccLatch := rAccSoft;
    rDecLatch := rDecSoft;
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
fbHaltM1(Axis := AxisM1, Execute := xNeedHaltM1, Deceleration := rDecSoft);
fbHaltM2(Axis := AxisM2, Execute := xNeedHaltM2, Deceleration := rDecSoft);
xHaltPrev := xHaltDemand;

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
(* 0.60 直控调试输出：实际速度 + 直控在役标志 *)
rVelActM1Out := rVelActM1;
rVelActM2Out := rVelActM2;
xDirectActive := (eMode = 4);

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

(* 0.59 减速状态：松手有速或 MoveRel 提前触发 → Halt 脉冲接管减速；
   双轴静止退出并置到位锁；新点动/旋转/新走距清锁。 *)
IF xMoveRel AND NOT xMovePrev THEN
    xDecelDone := FALSE;
END_IF;
IF xStop OR NOT xEnable THEN
    xDecelActive := FALSE;
    xDecelDone := FALSE;
ELSIF (eMode <> 0) AND (NOT xMoveRel) THEN
    xDecelActive := FALSE;
    xDecelDone := FALSE;
ELSIF xDecelActive THEN
    IF (NOT xMovingM1) AND (NOT xMovingM2) THEN
        xDecelActive := FALSE;
        xDecelDone := TRUE;
    END_IF;
ELSIF (eMode = 0) AND (xMovingM1 OR xMovingM2) THEN
    xDecelActive := TRUE;
ELSIF xMoveRelDecelTrig THEN
    xDecelActive := TRUE;
END_IF;
xMovePrev := xMoveRel;
eModePrev := eMode;
xRegOnPrev := xRegOn;
