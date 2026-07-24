# PRG_Logic.md — 设备逻辑

> 源码：`plc/src/PRG_Logic.st`。禁止 CALL Axis / FB_Servo。
> 消费已仲裁的 `HMI_*` + 面板 Jog 键；写 `AxisCmd_*`；状态只读派生（无状态机耦合）。

## 安全 / 使能（去耦）

```iecst
xSafe := HMI_xEStop AND NOT xEStopLatched;
AxisCmd_xPower := xSafe;
AxisCmd_xStopAll := HMI_xStop OR NOT xSafe OR xFaultAggregate OR HMI_xAutoAbort;
```

- 急停按下 → `xEStopLatched` 锁存；仅 `HMI_xStopHold3s`（或停+急停正常长按 3s）复位
- `xFaultAggregate` 仅来自 `AxisFb_xFault*`（各轴 `MC_ReadStatus.ErrorStop`）
- 力 1005/1006 只报警不进故障；灯/状态码只读派生不互锁

## 点动源合并（面板直动）

```iecst
xPanelSrc := (eCtrlSrc = 0);
xJogXPosM := HMI_xJogXPos OR (xPanelSrc AND JogFwd);   (* 其余轴同理 *)
```
映射：Fwd/Bwd→X±，Right/Left→Y±，Up/Down→Z±，ClockAdd/Mis→R±。

## 手动（xSafe + 手动 + 未停止 + 无故障）

- X± 与左右旋互斥（XOR）；直行 `HMI_rJogVelX`、旋转 `HMI_rSpinVel` 分开
- Y/Z 点动受 `xIlk_Block*` 挡（物理限位开关 ∨ `Cfg_rLim*`）
- `HMI_xForceGuide` 电平 → `AxisCmd_xForceFollow`，覆盖 Z 点动
- R 需 `xM5Ready`

## 自动多道循环

参数：`HMI_rAutoDistX`（每道 X 步距）·`HMI_iAutoPasses`（总道数）·`HMI_rWheelBase`（Y 行程=跨距）
·`HMI_rAutoVelX/Y/Z`·`HMI_rForceSet`·`HMI_rKpForce`·`HMI_rKpTrack`+`HMI_rHeadingErr`（视觉纠偏）。

```
0 待机 : AutoStart↑ → 记 R 保持角、iPass:=1 → 1
1 X前进: MoveRel X=rAutoDistX（速度模式+里程判完成，可纠偏）→ 2
2 Y归位: MoveAbs Y=0 → 3
3 Z下压: 去皮 + 力跟随，rForceAct≥rForceSet → 4
4 Y横移: MoveRel Y=rWheelBase 全程恒力 + R 保持角 → 5
5 判定 : iPass<nPasses ? (iPass++ → 1) : 6
6 收尾 : AutoDone，回 0
```
任一拍 `急停/停止/中止/轴Fault` → 步序清零。

## 回零（Y/Z/R，上升沿，同时只回一轴）

`HMI_xHomeY/Z/R` 或 `HMI_iHomeAxis(1Y2Z3R)+HMI_xHomeExec` → `AxisCmd_xHome*` →
`FB_Servo`：`MC_Home(0)` → `MC_SetPosition(0)` → `xHomed` → Logic 清命令。
反馈 `HMI_xHomed*` / `HMI_xHomeBusy*`；回零中屏蔽该轴点动与力引导。

## 限位联锁

```iecst
xIlk_BlockYPlus := I_xLimYPos OR (AxisFb_rPosY >= Cfg_rLimYPos);   (* 其余同理 *)
```
最终闸门在 FB_Servo（所有模式）；这里只提前挡点动。

## 报警

1001 急停（锁存或按下）→ 1002 轴故障 → 1007 使能未就绪（Power 2s 无 Ready）→
1006 力从站失败 → 1005 力超时；否则 0。
