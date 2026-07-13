# PRG_Logic.md — 许可、联锁、命令裁定

> 运行于 Logic/主任务。通过 GVL 与 Axis 交互，**禁止 CALL** `PRG_Axis_Control` / `FB_Servo` / `FB_XDiff`。

## 职责

1. 急停锁存（按钮极性：FALSE=触发）、点按停止、长按停止 3s 复位（清锁存 + 各轴错误）  
2. 使能允许、Fault 汇总  
3. 限位联锁 → 屏蔽对应 JOG  
4. X 命令源互斥（Indep / Sync / Diff）  
5. 写 `GVL_AxisCmd`、写 HMI 灯与 AlarmID  

## 按钮约定

| 信号 | 未动作 | 动作 | 行为 |
|------|--------|------|------|
| `HMI_xEStop` | **TRUE** | **FALSE**=按下 | 可按可松；按下→锁存急停；松开信号回 TRUE，**不清**锁存 |
| `HMI_xStop` | FALSE | TRUE=按下 | **点按/短按**：停止运动；**长按 3s**：复位脉冲 |
| 长按复位 | — | `HMI_xStopHold3s` 或 Logic `TON` | 清 `xEStopLatched` + `AxisCmd_xResetFault` 复位各轴错误 |

## 纲要

```iecst
PROGRAM PRG_Logic
VAR
    tonHold         : TON;
    xResetPulse     : BOOL;
    xResetPrev      : BOOL;
END_VAR

(* === 急停锁存：信号 FALSE = 触发 === *)
IF NOT HMI_xEStop THEN
    xEStopLatched := TRUE;
END_IF;

(* 长按停止 3s：要求急停按钮已松开（HMI_xEStop=TRUE） *)
tonHold(IN := HMI_xStop AND HMI_xEStop, PT := T#3S);
xResetPulse := (HMI_xStopHold3s OR tonHold.Q) AND NOT xResetPrev;
xResetPrev := HMI_xStopHold3s OR tonHold.Q;

IF xResetPulse THEN
    xEStopLatched := FALSE;
    AxisCmd_xResetFault := TRUE;  (* 一拍脉冲；下周期清 FALSE *)
ELSE
    AxisCmd_xResetFault := FALSE;
END_IF;

(* === Fault / 许可 === *)
xFaultAggregate := AxisFb_xFaultM1 OR AxisFb_xFaultM2 OR AxisFb_xFaultY OR AxisFb_xFaultZ
                   OR (xM5Ready AND AxisFb_xFaultR);

(* 急停按钮仍按下(FALSE)时也不允许使能 *)
xEnablePermit := HMI_xEStop AND NOT xEStopLatched AND NOT xFaultAggregate;
eOpMode := 0; (* Manual only *)

(* === 限位联锁 === *)
xIlk_BlockYPlus := I_xLimYPos;
xIlk_BlockYNeg  := I_xLimYNeg;
xIlk_BlockZPlus := I_xLimZPos;
xIlk_BlockZNeg  := I_xLimZNeg;
xIlk_BlockYWhenZ := AxisFb_xMovingZ;

(* === 急停/停止 → Axis ===
   点按 HMI_xStop：停运动；急停锁存或按钮仍按下：停+禁使能 *)
AxisCmd_xStopAll := xEStopLatched OR NOT HMI_xEStop OR HMI_xStop OR xFaultAggregate;
AxisCmd_xPower   := xEnablePermit AND NOT AxisCmd_xStopAll;

(* === X 模式互斥 === *)
AxisCmd_eXMode := LIMIT(0, HMI_eXMode, 2);
AxisCmd_eDiffFunc := LIMIT(0, HMI_eDiffFunc, 2);
AxisCmd_rDiffDelta := HMI_rDiffDelta;
AxisCmd_rTurnOmega := HMI_rTurnOmega;
AxisCmd_rWheelBase := LIMIT(4.0, HMI_rWheelBase, 6.0);
AxisCmd_rJogVelX := HMI_rJogVelX;
AxisCmd_rJogVelY := HMI_rJogVelY;
AxisCmd_rJogVelZ := HMI_rJogVelZ;

AxisCmd_xJogM1Pos := FALSE; AxisCmd_xJogM1Neg := FALSE;
AxisCmd_xJogM2Pos := FALSE; AxisCmd_xJogM2Neg := FALSE;
AxisCmd_xJogXSyncPos := FALSE; AxisCmd_xJogXSyncNeg := FALSE;
AxisCmd_xJogXDiffPos := FALSE; AxisCmd_xJogXDiffNeg := FALSE;

IF xEnablePermit AND NOT AxisCmd_xStopAll THEN
    CASE AxisCmd_eXMode OF
        0:
            AxisCmd_xJogM1Pos := HMI_xJogM1Pos;
            AxisCmd_xJogM1Neg := HMI_xJogM1Neg;
            AxisCmd_xJogM2Pos := HMI_xJogM2Pos;
            AxisCmd_xJogM2Neg := HMI_xJogM2Neg;
        1:
            AxisCmd_xJogXSyncPos := HMI_xJogXSyncPos;
            AxisCmd_xJogXSyncNeg := HMI_xJogXSyncNeg;
        2:
            AxisCmd_xJogXDiffPos := HMI_xJogXDiffPos;
            AxisCmd_xJogXDiffNeg := HMI_xJogXDiffNeg;
    END_CASE;
END_IF;

AxisCmd_xJogYPos := xEnablePermit AND HMI_xJogYPos AND NOT xIlk_BlockYPlus
                    AND NOT xIlk_BlockYWhenZ;
AxisCmd_xJogYNeg := xEnablePermit AND HMI_xJogYNeg AND NOT xIlk_BlockYNeg
                    AND NOT xIlk_BlockYWhenZ;
AxisCmd_xJogZPos := xEnablePermit AND HMI_xJogZPos AND NOT xIlk_BlockZPlus;
AxisCmd_xJogZNeg := xEnablePermit AND HMI_xJogZNeg AND NOT xIlk_BlockZNeg;

IF xM5Ready THEN
    AxisCmd_xJogRPos := xEnablePermit AND HMI_xJogRPos;
    AxisCmd_xJogRNeg := xEnablePermit AND HMI_xJogRNeg;
ELSE
    AxisCmd_xJogRPos := FALSE;
    AxisCmd_xJogRNeg := FALSE;
    IF HMI_xJogRPos OR HMI_xJogRNeg OR HMI_xHomeReqR THEN
        iAlarmID := 1099;
    END_IF;
END_IF;

AxisCmd_xHomeY := xEnablePermit AND HMI_xHomeReqY;
AxisCmd_xHomeZ := xEnablePermit AND HMI_xHomeReqZ;
AxisCmd_xHomeR := xEnablePermit AND xM5Ready AND HMI_xHomeReqR;

(* === Alarm === *)
IF xEStopLatched OR NOT HMI_xEStop THEN
    iAlarmID := 1001;
ELSIF xFaultAggregate THEN
    iAlarmID := 1002;
ELSIF (HMI_xJogYPos AND xIlk_BlockYPlus) OR (HMI_xJogZNeg AND xIlk_BlockZNeg) THEN
    iAlarmID := 1003;
ELSIF iAlarmID <> 1099 THEN
    iAlarmID := 0;
END_IF;

HMI_xLampEStop    := xEStopLatched OR NOT HMI_xEStop;
HMI_xLampEnableOk := xEnablePermit;
HMI_xLampFault    := xFaultAggregate;
HMI_iAlarmShow    := iAlarmID;
```

## 自动

本期 **不做自动**。`eOpMode` 固定 Manual。

## Must not

- `PRG_Axis_Control(...)` / SoftMotion FB 直接实例  
- 写 `AxisFb_*`  
