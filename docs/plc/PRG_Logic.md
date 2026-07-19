# PRG_Logic.md — 设备态、手动裁定、自动步序、恒力

> Logic 任务。禁止 CALL Axis / FB_Servo / FB_XDiff。

## 设备态

| eDevState | 灯 | 含义 |
|-----------|-----|------|
| 0 | Stop | 停止/待机 |
| 1 | Run | 正在运行（手动或自动） |
| 2 | Error | 错误 |

复位当拍强制 0；急停：`HMI_xEStop := EStop AND Tcp_xEStop`（正常 TRUE / 按下 FALSE）。

## 自动步序 iAutoStep

| 步 | 名 | 行为 |
|----|-----|------|
| 0 | Idle | 等待 AutoStart |
| 1 | MoveX | 相对走 DistX；HoldR=当前角 |
| 2 | PressZ | Z 下行 VelZ；力≥F_set 停 |
| 3 | MoveY | 相对走 **WheelBase(=Y行程)**；Z 恒力闭环 |
| 4 | RWobble | **占位跳过** |
| 5 | Done | 置 Done，回 Idle |

恒力：`Vz := LIMIT(-VelZ, Kp*(F_set-rForceAct), VelZ)`。

## 纲要 ST

```iecst
PROGRAM PRG_Logic
VAR
    tonHold, tonResetHold : TON;
    xResetPulse, xResetPrev, xStartEdge, xStartPrev, xStopEdge, xStopPrev : BOOL;
    xPostResetHold, xAutoStartPrev, xAutoStartEdge : BOOL;
    rX0, rY0, rRHold : REAL;
    xMoveXSent, xMoveYSent : BOOL;
END_VAR

(* —— 面板 ∨ TCP 影子 → HMI（见 TCP_HMI.md）—— *)
Tcp_xOnline := Tcp_xConnected AND NOT Tcp_xTimeout;
HMI_xEStop := EStop AND Tcp_xEStop;
HMI_xStop := StopBtn OR Tcp_xStop;
HMI_xStart := StartBtn OR Tcp_xStart;
HMI_xEnable := StartBtn OR Tcp_xEnable OR Tcp_xStart;
HMI_xStopHold3s := ResetBtn OR Tcp_xStopHold3s;
IF Tcp_xOnline THEN
    HMI_xAutoMode := Tcp_xAutoMode;
    HMI_xForceSimEnable := Tcp_xForceSimEnable;
END_IF;
HMI_xJogXPos := JogFwd OR Tcp_xJogXPos;
HMI_xJogXNeg := JogBwd OR Tcp_xJogXNeg;
HMI_xSpinLeft := Tcp_xSpinLeft;
HMI_xSpinRight := Tcp_xSpinRight;
HMI_xJogYPos := JogRight OR Tcp_xJogYPos;
HMI_xJogYNeg := JogLeft OR Tcp_xJogYNeg;
HMI_xJogZPos := JogUp OR Tcp_xJogZPos;
HMI_xJogZNeg := JogDown OR Tcp_xJogZNeg;
HMI_xJogRPos := Tcp_xJogRPos;
HMI_xJogRNeg := Tcp_xJogRNeg;
HMI_xAutoStart := Tcp_xAutoStart;
HMI_xAutoAbort := Tcp_xAutoAbort;
IF Tcp_xOnline THEN
    HMI_rJogVelX := Tcp_rJogVelX;
    HMI_rSpinVel := Tcp_rSpinVel;
    HMI_rJogVelY := Tcp_rJogVelY;
    HMI_rJogVelZ := Tcp_rJogVelZ;
    HMI_rJogVelR := Tcp_rJogVelR;
    HMI_rAutoDistX := Tcp_rAutoDistX;
    HMI_rAutoVelX := Tcp_rAutoVelX;
    HMI_rAutoVelY := Tcp_rAutoVelY;
    HMI_rAutoVelZ := Tcp_rAutoVelZ;
    HMI_rWheelBase := Tcp_rWheelBase;
    HMI_rForceSet := Tcp_rForceSet;
    HMI_rForceSim := Tcp_rForceSim;
ELSE
    HMI_rJogVelX := JogVel;
    HMI_rJogVelY := JogVel;
    HMI_rJogVelZ := JogVel;
END_IF;

(* —— 急停 / 复位 —— *)
IF NOT HMI_xEStop THEN xEStopLatched := TRUE; END_IF;
tonHold(IN := HMI_xStop AND HMI_xEStop, PT := T#3S);
xResetPulse := (HMI_xStopHold3s OR tonHold.Q) AND NOT xResetPrev;
xResetPrev := HMI_xStopHold3s OR tonHold.Q;
IF xResetPulse THEN
    xEStopLatched := FALSE;
    AxisCmd_xResetFault := TRUE;
    eDevState := 0;
    xPostResetHold := TRUE;
    iAutoStep := 0;
ELSE
    AxisCmd_xResetFault := FALSE;
END_IF;

xFaultAggregate := AxisFb_xFaultM1 OR AxisFb_xFaultM2 OR AxisFb_xFaultY OR AxisFb_xFaultZ
                   OR (xM5Ready AND AxisFb_xFaultR)
                   OR (NOT HMI_xForceSimEnable AND Force_xTimeout);
xEnablePermit := HMI_xEStop AND NOT xEStopLatched AND NOT xFaultAggregate;
eOpMode := SEL(HMI_xAutoMode, 0, 1);
HMI_eOpMode := eOpMode;

tonResetHold(IN := xPostResetHold, PT := T#2S);
IF NOT xFaultAggregate AND HMI_xEStop AND NOT xEStopLatched THEN
    xPostResetHold := FALSE;
ELSIF tonResetHold.Q OR NOT HMI_xEStop OR xEStopLatched THEN
    xPostResetHold := FALSE;
END_IF;

xStartEdge := (HMI_xStart OR HMI_xEnable) AND NOT xStartPrev;
xStartPrev := HMI_xStart OR HMI_xEnable;
xStopEdge := HMI_xStop AND NOT xStopPrev;
xStopPrev := HMI_xStop;

IF xResetPulse THEN
    eDevState := 0;
ELSIF NOT HMI_xEStop OR xEStopLatched THEN
    eDevState := 2;
ELSIF xFaultAggregate AND NOT xPostResetHold THEN
    eDevState := 2;
ELSIF eDevState = 2 THEN
    ;
ELSIF xStopEdge AND NOT tonHold.Q THEN
    eDevState := 0;
    iAutoStep := 0;
ELSIF xStartEdge AND eDevState = 0 AND xEnablePermit THEN
    eDevState := 1;
ELSIF xStartEdge AND eDevState = 0 AND NOT xEnablePermit THEN
    iAlarmID := 1004;
END_IF;

Dev_xStop := (eDevState = 0);
Dev_xRun := (eDevState = 1);
Dev_xError := (eDevState = 2);
HMI_eDevState := eDevState;
HMI_xDevStop := Dev_xStop;
HMI_xDevRun := Dev_xRun;
HMI_xDevError := Dev_xError;

(* —— 力：模拟或 485 任务 —— *)
IF HMI_xForceSimEnable THEN
    rForceAct := HMI_rForceSim;
(* ELSE：rForceAct 由 PRG_Force485 写入 *)
END_IF;
HMI_rForceShow := rForceAct;
IF rForceKp < 1.0E-6 THEN rForceKp := 1.0; END_IF;

xIlk_BlockYPlus := I_xLimYPos; xIlk_BlockYNeg := I_xLimYNeg;
xIlk_BlockZPlus := I_xLimZPos; xIlk_BlockZNeg := I_xLimZNeg;
xIlk_BlockYWhenZ := FALSE; (* 自动跟力时允许 Y+Z 同动 *)

AxisCmd_xStopAll := (eDevState <> 1) OR HMI_xStop OR HMI_xAutoAbort;
AxisCmd_xPower := (eDevState = 1);
AxisCmd_rJogVelX := HMI_rJogVelX;
AxisCmd_rSpinVel := HMI_rSpinVel;
AxisCmd_rJogVelY := HMI_rJogVelY;
AxisCmd_rJogVelZ := HMI_rJogVelZ;
AxisCmd_rJogVelR := HMI_rJogVelR;
AxisCmd_rWheelBase := LIMIT(4.0, HMI_rWheelBase, 6.0);

(* 清手动/自动命令 *)
AxisCmd_xJogXPos := FALSE; AxisCmd_xJogXNeg := FALSE;
AxisCmd_xSpinLeft := FALSE; AxisCmd_xSpinRight := FALSE;
AxisCmd_xJogYPos := FALSE; AxisCmd_xJogYNeg := FALSE;
AxisCmd_xJogZPos := FALSE; AxisCmd_xJogZNeg := FALSE;
AxisCmd_xJogRPos := FALSE; AxisCmd_xJogRNeg := FALSE;
AxisCmd_xUseZVelCmd := FALSE; AxisCmd_rZVelCmd := 0.0;
AxisCmd_xMoveRelX := FALSE; AxisCmd_xMoveRelY := FALSE;
AxisCmd_xHoldR := FALSE;

xAutoStartEdge := HMI_xAutoStart AND NOT xAutoStartPrev;
xAutoStartPrev := HMI_xAutoStart;

IF Dev_xError OR HMI_xAutoAbort OR (eDevState <> 1) THEN
    iAutoStep := 0;
    HMI_xAutoBusy := FALSE;
END_IF;

(* ===== 手动：仅 RUN + 手动模式 ===== *)
IF Dev_xRun AND (eOpMode = 0) AND NOT HMI_xStop THEN
    IF HMI_xSpinLeft XOR HMI_xSpinRight THEN
        AxisCmd_xSpinLeft := HMI_xSpinLeft;
        AxisCmd_xSpinRight := HMI_xSpinRight;
    ELSIF HMI_xJogXPos XOR HMI_xJogXNeg THEN
        AxisCmd_xJogXPos := HMI_xJogXPos;
        AxisCmd_xJogXNeg := HMI_xJogXNeg;
    END_IF;
    AxisCmd_xJogYPos := HMI_xJogYPos AND NOT xIlk_BlockYPlus;
    AxisCmd_xJogYNeg := HMI_xJogYNeg AND NOT xIlk_BlockYNeg;
    AxisCmd_xJogZPos := HMI_xJogZPos AND NOT xIlk_BlockZPlus;
    AxisCmd_xJogZNeg := HMI_xJogZNeg AND NOT xIlk_BlockZNeg;
    IF xM5Ready THEN
        AxisCmd_xJogRPos := HMI_xJogRPos;
        AxisCmd_xJogRNeg := HMI_xJogRNeg;
    END_IF;
END_IF;

(* ===== 自动 ===== *)
IF Dev_xRun AND (eOpMode = 1) AND NOT HMI_xStop THEN
    IF iAutoStep = 0 AND xAutoStartEdge THEN
        iAutoStep := 1;
        rRHold := AxisFb_rPosR;
        xMoveXSent := FALSE; xMoveYSent := FALSE;
        HMI_xAutoDone := FALSE;
        HMI_xAutoBusy := TRUE;
    END_IF;

    CASE iAutoStep OF
        1: (* MoveX *)
            AxisCmd_xHoldR := TRUE;
            AxisCmd_rRHoldPos := rRHold;
            AxisCmd_rMoveDistX := HMI_rAutoDistX;
            AxisCmd_rMoveVelX := HMI_rAutoVelX;
            AxisCmd_xMoveRelX := TRUE;
            IF AxisFb_xMoveDoneX THEN
                AxisCmd_xMoveRelX := FALSE;
                iAutoStep := 2;
            END_IF;
        2: (* PressZ *)
            AxisCmd_xHoldR := TRUE;
            AxisCmd_rRHoldPos := rRHold;
            AxisCmd_xUseZVelCmd := TRUE;
            IF rForceAct >= HMI_rForceSet THEN
                AxisCmd_rZVelCmd := 0.0;
                iAutoStep := 3;
                xMoveYSent := FALSE;
            ELSE
                AxisCmd_rZVelCmd := -ABS(HMI_rAutoVelZ); (* 下压方向：现场可反 *)
            END_IF;
        3: (* MoveY + 恒力 *)
            AxisCmd_xHoldR := TRUE;
            AxisCmd_rRHoldPos := rRHold;
            AxisCmd_rMoveDistY := AxisCmd_rWheelBase; (* 跨距=Y行程 *)
            AxisCmd_rMoveVelY := HMI_rAutoVelY;
            AxisCmd_xMoveRelY := TRUE;
            AxisCmd_xUseZVelCmd := TRUE;
            AxisCmd_rZVelCmd := LIMIT(-ABS(HMI_rAutoVelZ),
                rForceKp * (HMI_rForceSet - rForceAct), ABS(HMI_rAutoVelZ));
            IF AxisFb_xMoveDoneY THEN
                AxisCmd_xMoveRelY := FALSE;
                AxisCmd_rZVelCmd := 0.0;
                iAutoStep := 4;
            END_IF;
        4: (* RWobble 占位 *)
            iAutoStep := 5;
        5: (* Done *)
            HMI_xAutoBusy := FALSE;
            HMI_xAutoDone := TRUE;
            iAutoStep := 0;
    END_CASE;
END_IF;

(* Alarm 简化 *)
IF Dev_xError THEN
    IF xEStopLatched OR NOT HMI_xEStop THEN
        iAlarmID := 1001;
    ELSIF NOT HMI_xForceSimEnable AND Force_xTimeout THEN
        iAlarmID := 1005;
    ELSE
        iAlarmID := 1002;
    END_IF;
ELSIF iAlarmID <> 1004 THEN
    iAlarmID := 0;
END_IF;

HMI_iAutoStepShow := iAutoStep;
HMI_xLampEStop := xEStopLatched OR NOT HMI_xEStop;
HMI_xLampEnableOk := Dev_xRun;
HMI_xLampFault := xFaultAggregate;
HMI_iAlarmShow := iAlarmID;

StopLamp := Dev_xStop;
StartLamp := Dev_xRun;
```

## Must not

- CALL Axis；写 AxisFb  
- 自动中透传手动 JOG  
