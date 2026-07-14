# Axis_Control.md — 运动独立任务

## 架构

- 独立任务；**无外部 CALL**；仅读写 `GVL_AxisCmd` / `GVL_AxisFb`。  
- 实例：`FB_Servo`×轴 + `FB_XDiff`（仅 Sync / 原地左右旋）。

## 轴

| 逻辑 | 电机 | SoftMotion |
|------|------|------------|
| X | M1+M2 | Axis, Axis_1 |
| Y | M3 | Axis_2 |
| Z | M4 | Axis_3 |
| R | M5 | 预留/追加 |

## 纲要

```iecst
PROGRAM PRG_Axis_Control
VAR
    fbM1, fbM2, fbY, fbZ, fbR : FB_Servo;
    fbXDiff : FB_XDiff;
    fbMoveX1, fbMoveX2, fbMoveY : MC_MoveRelative; (* 或工程等价 *)
    xPair : BOOL;
    eMode : INT;
    xDiffPos, xDiffNeg : BOOL;
END_VAR

(* X：同步直行 / 左旋 / 右旋 *)
eMode := 0;
xDiffPos := FALSE; xDiffNeg := FALSE;
IF AxisCmd_xSpinLeft XOR AxisCmd_xSpinRight THEN
    eMode := 2; (* Diff + 原地转 *)
    xDiffPos := AxisCmd_xSpinLeft;   (* 现场可对调 *)
    xDiffNeg := AxisCmd_xSpinRight;
ELSIF AxisCmd_xJogXPos XOR AxisCmd_xJogXNeg THEN
    eMode := 1;
END_IF;

fbXDiff(
    eMode := eMode,
    eDiffFunc := 1, (* 固定原地旋转子功能 *)
    xJogSyncPos := AxisCmd_xJogXPos,
    xJogSyncNeg := AxisCmd_xJogXNeg,
    xJogDiffPos := xDiffPos,
    xJogDiffNeg := xDiffNeg,
    xStop := AxisCmd_xStopAll,
    xEnable := AxisCmd_xPower,
    rJogVel := AxisCmd_rJogVelX,
    rDiffDelta := 0.0,
    rTurnOmega := 0.0,
    rWheelBase := AxisCmd_rWheelBase
);
xPair := fbXDiff.xUsePairVel;

IF AxisCmd_xMoveRelX AND AxisCmd_xPower AND NOT AxisCmd_xStopAll THEN
    (* 双驱同距：MC_MoveRelative Distance:=AxisCmd_rMoveDistX Velocity:=AxisCmd_rMoveVelX *)
    fbMoveX1(Axis := Axis, Execute := TRUE, Distance := AxisCmd_rMoveDistX,
             Velocity := AxisCmd_rMoveVelX, Acceleration := AxisCmd_rAcc, Deceleration := AxisCmd_rDec);
    fbMoveX2(Axis := Axis_1, Execute := TRUE, Distance := AxisCmd_rMoveDistX,
             Velocity := AxisCmd_rMoveVelX, Acceleration := AxisCmd_rAcc, Deceleration := AxisCmd_rDec);
    AxisFb_xMoveDoneX := fbMoveX1.Done AND fbMoveX2.Done;
ELSIF xPair THEN
    fbM1(Axis := Axis, xEnable := AxisCmd_xPower, xUseVelCmd := TRUE, rVelCmd := fbXDiff.rVelCmdM1,
         xStop := AxisCmd_xStopAll, xResetFault := AxisCmd_xResetFault, rAcc := AxisCmd_rAcc, rDec := AxisCmd_rDec);
    fbM2(Axis := Axis_1, xEnable := AxisCmd_xPower, xUseVelCmd := TRUE, rVelCmd := fbXDiff.rVelCmdM2,
         xStop := AxisCmd_xStopAll, xResetFault := AxisCmd_xResetFault, rAcc := AxisCmd_rAcc, rDec := AxisCmd_rDec);
    AxisFb_xMoveDoneX := FALSE;
ELSE
    fbMoveX1(Execute := FALSE); fbMoveX2(Execute := FALSE);
    AxisFb_xMoveDoneX := FALSE;
    fbM1(Axis := Axis, xEnable := AxisCmd_xPower, xJogPos := FALSE, xJogNeg := FALSE,
         xStop := AxisCmd_xStopAll, xResetFault := AxisCmd_xResetFault);
    fbM2(Axis := Axis_1, xEnable := AxisCmd_xPower, xJogPos := FALSE, xJogNeg := FALSE,
         xStop := AxisCmd_xStopAll, xResetFault := AxisCmd_xResetFault);
END_IF;

(* Y 相对 / JOG *)
IF AxisCmd_xMoveRelY AND AxisCmd_xPower AND NOT AxisCmd_xStopAll THEN
    fbMoveY(Axis := Axis_2, Execute := TRUE, Distance := AxisCmd_rMoveDistY,
            Velocity := AxisCmd_rMoveVelY, Acceleration := AxisCmd_rAcc, Deceleration := AxisCmd_rDec);
    AxisFb_xMoveDoneY := fbMoveY.Done;
    fbY(Axis := Axis_2, xEnable := AxisCmd_xPower, xJogPos := FALSE, xJogNeg := FALSE,
        xStop := AxisCmd_xStopAll, xResetFault := AxisCmd_xResetFault);
ELSE
    fbMoveY(Execute := FALSE);
    AxisFb_xMoveDoneY := FALSE;
    fbY(Axis := Axis_2, xEnable := AxisCmd_xPower,
        xJogPos := AxisCmd_xJogYPos, xJogNeg := AxisCmd_xJogYNeg,
        xStop := AxisCmd_xStopAll, xResetFault := AxisCmd_xResetFault, rJogVel := AxisCmd_rJogVelY,
        rAcc := AxisCmd_rAcc, rDec := AxisCmd_rDec);
END_IF;

(* Z：自动速度指令优先 *)
IF AxisCmd_xUseZVelCmd THEN
    fbZ(Axis := Axis_3, xEnable := AxisCmd_xPower, xUseVelCmd := TRUE, rVelCmd := AxisCmd_rZVelCmd,
        xStop := AxisCmd_xStopAll, xResetFault := AxisCmd_xResetFault, rAcc := AxisCmd_rAcc, rDec := AxisCmd_rDec);
ELSE
    fbZ(Axis := Axis_3, xEnable := AxisCmd_xPower,
        xJogPos := AxisCmd_xJogZPos, xJogNeg := AxisCmd_xJogZNeg,
        xStop := AxisCmd_xStopAll, xResetFault := AxisCmd_xResetFault, rJogVel := AxisCmd_rJogVelZ,
        rAcc := AxisCmd_rAcc, rDec := AxisCmd_rDec);
END_IF;

(* R：保持角 / JOG；无硬件时 xM5Ready=FALSE 不实例实轴 *)
(* Hold：MC_MoveAbsolute 到 AxisCmd_rRHoldPos 或速度跟踪；本期文档预留 *)
fbR(... 按 AxisCmd_xHoldR / JOG / xM5Ready ...);

AxisFb_rVelCmdM1 := fbXDiff.rVelCmdM1;
AxisFb_rVelCmdM2 := fbXDiff.rVelCmdM2;
AxisFb_rPosM1 := fbM1.rActPos; AxisFb_rPosM2 := fbM2.rActPos;
AxisFb_rPosY := fbY.rActPos; AxisFb_rPosZ := fbZ.rActPos;
AxisFb_xPoweredM1 := fbM1.xPowered; (* … 同理 *)
AxisFb_xFaultM1 := fbM1.xFault; (* … *)
AxisFb_xReady := NOT (fbM1.xFault OR fbM2.xFault OR fbY.xFault OR fbZ.xFault);
```

## Must not

- 写 HMI / Alarm / eDevState  
- 被 Logic CALL  
