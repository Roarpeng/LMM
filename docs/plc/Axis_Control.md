# Axis_Control.md — 运动独立任务

## 架构（强制）

- **单独任务**运行（任务名 TBD，建议周期与 EtherCAT/SoftMotion 一致）。
- **不接受** Logic / HMI / 其他程序的外部 `CALL`。
- 与外界 **仅** 通过 `GVL_AxisCmd`（入）/ `GVL_AxisFb`（出）交换。
- `FB_Servo` / `FB_XDiff` **只在本任务内**实例化。

## 轴绑定（对照 LMM.xml）

| 逻辑轴 | SoftMotion 对象 | 驱动 |
|--------|-----------------|------|
| M1 | Axis (#1) | MDX_EC Alias1 | 龙门 X 侧 A；相对编码器；上电 0；**运动⊥Y** |
| M2 | Axis_1 (#2) | MDX_EC_1 Alias2 | 龙门 X 侧 B；相对编码器；上电 0；**运动⊥Y** |
| Y | Axis_2 (#3) | MDX_EC_2 Alias3 |
| Z | Axis_3 (#4) | MDX_EC_3 Alias4 |
| R | （未配置） | M5 到货后追加 |

## 程序体纲要 `PRG_Axis_Control`

```iecst
PROGRAM PRG_Axis_Control
VAR
    fbM1, fbM2, fbY, fbZ, fbR : FB_Servo;
    fbXDiff                   : FB_XDiff;
    xPair                     : BOOL;
END_VAR

(* —— 读命令区，不写 AxisCmd —— *)
fbXDiff(
    eMode       := AxisCmd_eXMode,
    eDiffFunc   := AxisCmd_eDiffFunc,
    xJogSyncPos := AxisCmd_xJogXSyncPos,
    xJogSyncNeg := AxisCmd_xJogXSyncNeg,
    xJogDiffPos := AxisCmd_xJogXDiffPos,
    xJogDiffNeg := AxisCmd_xJogXDiffNeg,
    xStop       := AxisCmd_xStopAll,
    xEnable     := AxisCmd_xPower,
    rJogVel     := AxisCmd_rJogVelX,
    rDiffDelta  := AxisCmd_rDiffDelta,
    rTurnOmega  := AxisCmd_rTurnOmega,
    rWheelBase  := AxisCmd_rWheelBase
);
xPair := fbXDiff.xUsePairVel;

(* M1/M2：成对速度 或 独立 JOG *)
IF xPair THEN
    (* 将 rVelCmdM1/M2 写入两侧 MoveVelocity；JOG 位强制 FALSE *)
    fbM1(Axis := Axis,   xEnable := AxisCmd_xPower, xJogPos := FALSE, xJogNeg := FALSE,
         xStop := AxisCmd_xStopAll, xResetFault := AxisCmd_xResetFault, xHome := FALSE, rJogVel := fbXDiff.rVelCmdM1);
    fbM2(Axis := Axis_1, xEnable := AxisCmd_xPower, xJogPos := FALSE, xJogNeg := FALSE,
         xStop := AxisCmd_xStopAll, xResetFault := AxisCmd_xResetFault, xHome := FALSE, rJogVel := fbXDiff.rVelCmdM2);
    (* 实现时：用 Execute+Velocity= rVelCmd* 覆盖 JOG；见 FB_Servo 扩展或专用路径 *)
ELSE
    fbM1(Axis := Axis,   xEnable := AxisCmd_xPower,
         xJogPos := AxisCmd_xJogM1Pos, xJogNeg := AxisCmd_xJogM1Neg,
         xStop := AxisCmd_xStopAll, xResetFault := AxisCmd_xResetFault, rJogVel := AxisCmd_rJogVelX);
    fbM2(Axis := Axis_1, xEnable := AxisCmd_xPower,
         xJogPos := AxisCmd_xJogM2Pos, xJogNeg := AxisCmd_xJogM2Neg,
         xStop := AxisCmd_xStopAll, xResetFault := AxisCmd_xResetFault, rJogVel := AxisCmd_rJogVelX);
END_IF;

fbY(Axis := Axis_2, xEnable := AxisCmd_xPower,
    xJogPos := AxisCmd_xJogYPos, xJogNeg := AxisCmd_xJogYNeg,
    xStop := AxisCmd_xStopAll, xResetFault := AxisCmd_xResetFault,
    xHome := AxisCmd_xHomeY, rJogVel := AxisCmd_rJogVelY);

fbZ(Axis := Axis_3, xEnable := AxisCmd_xPower,
    xJogPos := AxisCmd_xJogZPos, xJogNeg := AxisCmd_xJogZNeg,
    xStop := AxisCmd_xStopAll, xResetFault := AxisCmd_xResetFault,
    xHome := AxisCmd_xHomeZ, rJogVel := AxisCmd_rJogVelZ);

fbR(Axis := (*TBD*), xEnable := AxisCmd_xPower AND xM5Ready,
    xJogPos := AxisCmd_xJogRPos, xJogNeg := AxisCmd_xJogRNeg,
    xStop := AxisCmd_xStopAll, xResetFault := AxisCmd_xResetFault,
    xHome := AxisCmd_xHomeR, rJogVel := AxisCmd_rJogVelR);

(* —— 只写反馈区 —— *)
IF xPair THEN
    AxisFb_rVelCmdM1 := fbXDiff.rVelCmdM1;
    AxisFb_rVelCmdM2 := fbXDiff.rVelCmdM2;
ELSE
    AxisFb_rVelCmdM1 := SEL(AxisCmd_xJogM1Pos, -AxisCmd_rJogVelX, SEL(AxisCmd_xJogM1Neg, AxisCmd_rJogVelX, 0.0));
    (* 简化：实际以 FB 内速度为准；Indep 时用 JOG 方向 *)
    AxisFb_rVelCmdM2 := SEL(AxisCmd_xJogM2Pos, -AxisCmd_rJogVelX, SEL(AxisCmd_xJogM2Neg, AxisCmd_rJogVelX, 0.0));
END_IF;
AxisFb_rPosM1 := fbM1.rActPos;  AxisFb_xMovingM1 := fbM1.xMoving;
AxisFb_xPoweredM1 := fbM1.xPowered; AxisFb_xFaultM1 := fbM1.xFault;
AxisFb_xStandstill1 := fbM1.xStandstill;
(* 同理 M2/Y/Z/R … *)
AxisFb_xHomedY := fbY.xHomed;
AxisFb_xHomedZ := fbZ.xHomed;
AxisFb_xReady := NOT (fbM1.xFault OR fbM2.xFault OR fbY.xFault OR fbZ.xFault);
```

## 任务配置（导入时）

| 项 | 值 |
|----|-----|
| 程序 | `PRG_Axis_Control` |
| 调用方 | **无**（仅任务配置挂接） |
| 输入 | `GVL_AxisCmd` + `xM5Ready` |
| 输出 | `GVL_AxisFb` |

## Must not

- 写 `xEStopLatched` / `iAlarmID` / HMI 灯  
- 被 `PRG_Logic` CALL  
- 发明第 5 轴硬件未就绪时的强制运动  
