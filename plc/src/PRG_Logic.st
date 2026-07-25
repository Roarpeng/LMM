PROGRAM PRG_Logic
(* PRG_Logic — 消费已仲裁 HMI_* + 面板键；写 AxisCmd_*；状态只读派生（无状态机耦合）。
   禁止 CALL Axis / FB_Servo。 *)
VAR
    tonHold : TON;
    tonReady : TON;
    xResetPulse : BOOL;
    xResetPrev : BOOL;
    xSafe : BOOL;
    xAutoStartPrev : BOOL;
    xAutoStartEdge : BOOL;
    rRHold : REAL;
    iPass : INT;
    xAutoTareSent : BOOL;
    xHomeTrigY : BOOL;
    xHomeTrigZ : BOOL;
    xHomeTrigR : BOOL;
    xHomeTrigYPrev : BOOL;
    xHomeTrigZPrev : BOOL;
    xHomeTrigRPrev : BOOL;
    xAnyHomeBusy : BOOL;
    xReadyAll : BOOL;
    xPanelSrc : BOOL;       (* eCtrlSrc=0：面板/触摸屏源 *)
    xJogXPosM : BOOL;       (* 合并后点动（HMI/Web OR 面板键） *)
    xJogXNegM : BOOL;
    xJogYPosM : BOOL;
    xJogYNegM : BOOL;
    xJogZPosM : BOOL;
    xJogZNegM : BOOL;
    xJogRPosM : BOOL;
    xJogRNegM : BOOL;
END_VAR

(* ===== 急停锁存 / 长按复位 ===== *)
IF NOT HMI_xEStop THEN
    xEStopLatched := TRUE;
END_IF;
tonHold(IN := HMI_xStop AND HMI_xEStop, PT := T#3S);
xResetPulse := (HMI_xStopHold3s OR tonHold.Q) AND NOT xResetPrev;
xResetPrev := HMI_xStopHold3s OR tonHold.Q;
IF xResetPulse THEN
    xEStopLatched := FALSE;
    AxisCmd_xResetFault := TRUE;
    iAutoStep := 0;
    iPass := 0;
    Force_xSlaveFail := FALSE;
ELSE
    AxisCmd_xResetFault := FALSE;
END_IF;

(* 故障汇总：各轴 Errorstop（同步跳闸已废，不再 OR AxisFb_xSyncFault） *)
xFaultAggregate := AxisFb_xFaultM1 OR AxisFb_xFaultM2 OR AxisFb_xFaultY OR AxisFb_xFaultZ
    OR (xM5Ready AND AxisFb_xFaultR);

IF HMI_xAutoMode THEN eOpMode := 1; ELSE eOpMode := 0; END_IF;
HMI_eOpMode := eOpMode;

(* 安全 / 使能 —— 去耦：只看急停 + 故障 *)
xSafe := HMI_xEStop AND NOT xEStopLatched;
AxisCmd_xPower := xSafe;
AxisCmd_xStopAll := HMI_xStop OR NOT xSafe OR xFaultAggregate OR HMI_xAutoAbort;

(* 力/纠偏参数下发 *)
rForceKp := HMI_rKpForce;
IF rForceKp < 1.0E-6 THEN rForceKp := 1.0; END_IF;
AxisCmd_rForceSet := HMI_rForceSet;
AxisCmd_rForceKp := rForceKp;
AxisCmd_rForceVelMax := ABS(HMI_rAutoVelZ);
IF AxisCmd_rForceVelMax < 1.0E-6 THEN AxisCmd_rForceVelMax := ABS(HMI_rJogVelZ); END_IF;
AxisCmd_rHeadingErr := HMI_rHeadingErr;

IF HMI_xForceSimEnable THEN
    rForceAct := HMI_rForceSim;
END_IF;
HMI_rForceShow := rForceAct;

AxisCmd_rJogVelX := HMI_rJogVelX;
AxisCmd_rSpinVel := HMI_rSpinVel;
AxisCmd_rJogVelY := HMI_rJogVelY;
AxisCmd_rJogVelZ := HMI_rJogVelZ;
AxisCmd_rJogVelR := HMI_rJogVelR;
AxisCmd_rWheelBase := LIMIT(4.0, HMI_rWheelBase, 6.0);
(* 每轴加减速（RETAIN 参数；<1 时兜底 100） *)
AxisCmd_rAccX := HMI_rAccX; IF AxisCmd_rAccX < 1.0 THEN AxisCmd_rAccX := 100.0; END_IF;
AxisCmd_rDecX := HMI_rDecX; IF AxisCmd_rDecX < 1.0 THEN AxisCmd_rDecX := 100.0; END_IF;
AxisCmd_rAccY := HMI_rAccY; IF AxisCmd_rAccY < 1.0 THEN AxisCmd_rAccY := 100.0; END_IF;
AxisCmd_rDecY := HMI_rDecY; IF AxisCmd_rDecY < 1.0 THEN AxisCmd_rDecY := 100.0; END_IF;
AxisCmd_rAccZ := HMI_rAccZ; IF AxisCmd_rAccZ < 1.0 THEN AxisCmd_rAccZ := 100.0; END_IF;
AxisCmd_rDecZ := HMI_rDecZ; IF AxisCmd_rDecZ < 1.0 THEN AxisCmd_rDecZ := 100.0; END_IF;
AxisCmd_rAccR := HMI_rAccR; IF AxisCmd_rAccR < 1.0 THEN AxisCmd_rAccR := 100.0; END_IF;
AxisCmd_rDecR := HMI_rDecR; IF AxisCmd_rDecR < 1.0 THEN AxisCmd_rDecR := 100.0; END_IF;

(* 限位联锁：物理限位输入 ∨ 可配置硬限位（Cfg_rLim*，FB_Servo 内另有最终闸门） *)
xIlk_BlockYPlus := I_xLimYPos OR (AxisFb_rPosY >= Cfg_rLimYPos);
xIlk_BlockYNeg := I_xLimYNeg OR (AxisFb_rPosY <= Cfg_rLimYNeg);
xIlk_BlockZPlus := I_xLimZPos OR (AxisFb_rPosZ >= Cfg_rLimZPos);
xIlk_BlockZNeg := I_xLimZNeg OR (AxisFb_rPosZ <= Cfg_rLimZNeg);

(* 每拍清命令 *)
AxisCmd_xJogXPos := FALSE; AxisCmd_xJogXNeg := FALSE;
AxisCmd_xSpinLeft := FALSE; AxisCmd_xSpinRight := FALSE;
AxisCmd_xJogYPos := FALSE; AxisCmd_xJogYNeg := FALSE;
AxisCmd_xJogZPos := FALSE; AxisCmd_xJogZNeg := FALSE;
AxisCmd_xJogRPos := FALSE; AxisCmd_xJogRNeg := FALSE;
AxisCmd_xForceFollow := FALSE;
AxisCmd_xMoveRelX := FALSE;
AxisCmd_xMoveRelY := FALSE;
AxisCmd_xMoveAbsY := FALSE;
AxisCmd_xHoldR := FALSE;
AxisCmd_rTrackKp := 0.0;
Logic_xForceTare := FALSE;

xAutoStartEdge := HMI_xAutoStart AND NOT xAutoStartPrev;
xAutoStartPrev := HMI_xAutoStart;

IF HMI_xAutoAbort OR NOT xSafe OR xFaultAggregate THEN
    iAutoStep := 0;
    iPass := 0;
    HMI_xAutoBusy := FALSE;
END_IF;

(* ===== 点动源合并：面板键（仅面板/触摸屏源时）OR 触摸屏/Web ===== *)
xPanelSrc := (eCtrlSrc = 0);
xJogXPosM := HMI_xJogXPos OR (xPanelSrc AND JogFwd);
xJogXNegM := HMI_xJogXNeg OR (xPanelSrc AND JogBwd);
xJogYPosM := HMI_xJogYPos OR (xPanelSrc AND JogRight);
xJogYNegM := HMI_xJogYNeg OR (xPanelSrc AND JogLeft);
xJogZPosM := HMI_xJogZPos OR (xPanelSrc AND JogUp);
xJogZNegM := HMI_xJogZNeg OR (xPanelSrc AND JogDown);
xJogRPosM := HMI_xJogRPos OR (xPanelSrc AND JogClockAdd);
xJogRNegM := HMI_xJogRNeg OR (xPanelSrc AND JogClockMis);

(* ===== 手动 ===== *)
IF xSafe AND (eOpMode = 0) AND NOT HMI_xStop AND NOT xFaultAggregate THEN
    IF HMI_xSpinLeft XOR HMI_xSpinRight THEN
        AxisCmd_xSpinLeft := HMI_xSpinLeft;
        AxisCmd_xSpinRight := HMI_xSpinRight;
    ELSIF xJogXPosM XOR xJogXNegM THEN
        AxisCmd_xJogXPos := xJogXPosM;
        AxisCmd_xJogXNeg := xJogXNegM;
    END_IF;
    AxisCmd_xJogYPos := xJogYPosM AND NOT xIlk_BlockYPlus;
    AxisCmd_xJogYNeg := xJogYNegM AND NOT xIlk_BlockYNeg;
    IF HMI_xForceGuide THEN
        AxisCmd_xForceFollow := TRUE;
    ELSE
        AxisCmd_xJogZPos := xJogZPosM AND NOT xIlk_BlockZPlus;
        AxisCmd_xJogZNeg := xJogZNegM AND NOT xIlk_BlockZNeg;
    END_IF;
    IF xM5Ready THEN
        AxisCmd_xJogRPos := xJogRPosM;
        AxisCmd_xJogRNeg := xJogRNegM;
    END_IF;
END_IF;

(* ===== 自动多道循环 ===== *)
IF xSafe AND (eOpMode = 1) AND NOT HMI_xStop AND NOT xFaultAggregate THEN
    IF iAutoStep = 0 AND xAutoStartEdge THEN
        rRHold := AxisFb_rPosR;
        xAutoTareSent := FALSE;
        HMI_xAutoDone := FALSE;
        HMI_xAutoBusy := TRUE;
        iPass := 1;
        iAutoStep := 1;
    END_IF;

    CASE iAutoStep OF
        1:
            AxisCmd_xHoldR := TRUE;
            AxisCmd_rRHoldPos := rRHold;
            AxisCmd_rTrackKp := HMI_rKpTrack;
            AxisCmd_rMoveDistX := HMI_rAutoDistX;
            AxisCmd_rMoveVelX := HMI_rAutoVelX;
            AxisCmd_xMoveRelX := TRUE;
            IF AxisFb_xMoveDoneX THEN
                AxisCmd_xMoveRelX := FALSE;
                iAutoStep := 2;
            END_IF;
        2:
            AxisCmd_xHoldR := TRUE;
            AxisCmd_rRHoldPos := rRHold;
            AxisCmd_rMoveAbsPosY := 0.0;
            AxisCmd_rMoveVelY := HMI_rAutoVelY;
            AxisCmd_xMoveAbsY := TRUE;
            IF AxisFb_xStandstillY AND (ABS(AxisFb_rPosY) < 0.005) THEN
                AxisCmd_xMoveAbsY := FALSE;
                xAutoTareSent := FALSE;
                iAutoStep := 3;
            END_IF;
        3:
            AxisCmd_xHoldR := TRUE;
            AxisCmd_rRHoldPos := rRHold;
            IF NOT xAutoTareSent THEN
                Logic_xForceTare := TRUE;
                xAutoTareSent := TRUE;
            END_IF;
            AxisCmd_xForceFollow := TRUE;
            IF rForceAct >= HMI_rForceSet THEN
                iAutoStep := 4;
            END_IF;
        4:
            AxisCmd_xHoldR := TRUE;
            AxisCmd_rRHoldPos := rRHold;
            AxisCmd_xForceFollow := TRUE;
            AxisCmd_rMoveDistY := AxisCmd_rWheelBase;
            AxisCmd_rMoveVelY := HMI_rAutoVelY;
            AxisCmd_xMoveRelY := TRUE;
            IF AxisFb_xMoveDoneY THEN
                AxisCmd_xMoveRelY := FALSE;
                iAutoStep := 5;
            END_IF;
        5:
            IF iPass < HMI_iAutoPasses THEN
                iPass := iPass + 1;
                iAutoStep := 1;
            ELSE
                iAutoStep := 6;
            END_IF;
        6:
            HMI_xAutoBusy := FALSE;
            HMI_xAutoDone := TRUE;
            iAutoStep := 0;
            iPass := 0;
    END_CASE;
END_IF;

(* ===== 回零：Y/Z/R；同时只回一轴 ===== *)
xHomeTrigY := HMI_xHomeY OR ((HMI_iHomeAxis = 1) AND HMI_xHomeExec);
xHomeTrigZ := HMI_xHomeZ OR ((HMI_iHomeAxis = 2) AND HMI_xHomeExec);
xHomeTrigR := HMI_xHomeR OR ((HMI_iHomeAxis = 3) AND HMI_xHomeExec);
xAnyHomeBusy := AxisCmd_xHomeY OR AxisCmd_xHomeZ OR AxisCmd_xHomeR;

IF AxisCmd_xStopAll OR NOT xSafe OR xFaultAggregate THEN
    AxisCmd_xHomeY := FALSE;
    AxisCmd_xHomeZ := FALSE;
    AxisCmd_xHomeR := FALSE;
ELSE
    IF AxisCmd_xHomeY AND AxisFb_xHomedY THEN AxisCmd_xHomeY := FALSE; END_IF;
    IF AxisCmd_xHomeZ AND AxisFb_xHomedZ THEN AxisCmd_xHomeZ := FALSE; END_IF;
    IF AxisCmd_xHomeR AND AxisFb_xHomedR THEN AxisCmd_xHomeR := FALSE; END_IF;
    IF (eOpMode = 0) AND NOT HMI_xStop THEN
        IF xHomeTrigY AND NOT xHomeTrigYPrev AND NOT xAnyHomeBusy THEN
            AxisCmd_xHomeY := TRUE;
        ELSIF xHomeTrigZ AND NOT xHomeTrigZPrev AND NOT xAnyHomeBusy THEN
            AxisCmd_xHomeZ := TRUE;
        ELSIF xHomeTrigR AND NOT xHomeTrigRPrev AND NOT xAnyHomeBusy AND xM5Ready THEN
            AxisCmd_xHomeR := TRUE;
        END_IF;
    END_IF;
END_IF;
xHomeTrigYPrev := xHomeTrigY;
xHomeTrigZPrev := xHomeTrigZ;
xHomeTrigRPrev := xHomeTrigR;

IF AxisCmd_xHomeY THEN AxisCmd_xJogYPos := FALSE; AxisCmd_xJogYNeg := FALSE; END_IF;
IF AxisCmd_xHomeZ THEN AxisCmd_xJogZPos := FALSE; AxisCmd_xJogZNeg := FALSE; AxisCmd_xForceFollow := FALSE; END_IF;
IF AxisCmd_xHomeR THEN AxisCmd_xJogRPos := FALSE; AxisCmd_xJogRNeg := FALSE; END_IF;

HMI_xHomedY := AxisFb_xHomedY;
HMI_xHomedZ := AxisFb_xHomedZ;
HMI_xHomedR := AxisFb_xHomedR;
HMI_xHomeBusyY := AxisCmd_xHomeY;
HMI_xHomeBusyZ := AxisCmd_xHomeZ;
HMI_xHomeBusyR := AxisCmd_xHomeR;

(* 使能就绪诊断 → 1007 *)
xReadyAll := AxisFb_xReadyM1 AND AxisFb_xReadyM2 AND AxisFb_xReadyY AND AxisFb_xReadyZ
    AND (NOT xM5Ready OR AxisFb_xReadyR);
tonReady(IN := AxisCmd_xPower AND NOT xReadyAll AND NOT xFaultAggregate, PT := T#2S);

(* 报警 *)
IF xEStopLatched OR NOT HMI_xEStop THEN
    iAlarmID := 1001;
ELSIF AxisFb_xFaultM1 OR AxisFb_xFaultM2 OR AxisFb_xFaultY OR AxisFb_xFaultZ
        OR (xM5Ready AND AxisFb_xFaultR) THEN
    iAlarmID := 1002;
ELSIF tonReady.Q THEN
    iAlarmID := 1007;
ELSIF NOT HMI_xForceSimEnable AND Force_xSlaveFail THEN
    iAlarmID := 1006;
ELSIF NOT HMI_xForceSimEnable AND Force_xTimeout THEN
    iAlarmID := 1005;
ELSE
    iAlarmID := 0;
END_IF;

(* 状态灯（只读派生，不互锁） *)
Dev_xError := xFaultAggregate;
Dev_xRun := xSafe AND NOT HMI_xStop AND NOT xFaultAggregate;
Dev_xStop := NOT Dev_xRun AND NOT Dev_xError;
HMI_xDevError := Dev_xError;
HMI_xDevRun := Dev_xRun;
HMI_xDevStop := Dev_xStop;
IF Dev_xError THEN HMI_eDevState := 2;
ELSIF Dev_xRun THEN HMI_eDevState := 1;
ELSE HMI_eDevState := 0; END_IF;

HMI_iAutoStepShow := iAutoStep;
HMI_xLampEStop := xEStopLatched OR NOT HMI_xEStop;
HMI_xLampEnableOk := Dev_xRun;
HMI_xLampFault := xFaultAggregate;
HMI_iAlarmShow := iAlarmID;

StopLamp := Dev_xStop;
StartLamp := Dev_xRun;
