# Axis_Control.md — 运动独立任务

> 源码：`plc/src/PRG_Axis_Control.st`。ETHERCAT 任务 4ms；**无外部 CALL**；仅读写 GVL。

## 轴

| 逻辑 | 电机 | SoftMotion | 硬限位 |
|------|------|------------|--------|
| X | M1+M2 | `Axis`, `Axis_1` | 无（`xLimEn:=FALSE`） |
| Y | M3 | `Axis_2` | `Cfg_rLimY*` |
| Z | M4 | `Axis_3` | `Cfg_rLimZ*` |
| R | M5 | `Axis_4`（`xM5Ready` 门控） | `Cfg_rLimR*` |

## 组装

- `fbForce : FB_Force` — `Force_wInRaw(%IW102) → rForceAct`（模拟时 Logic 直写 `rForceAct`）
- `fbTrack : FB_XLineTrack` — X 直行（基础速度带符号 + 视觉纠偏 trim）/ 原地左右旋
- `fbFF : FB_ForceFollow` — Z 恒力 P 律，限 `[-rVelMax, rVelMax]`，撞 `Cfg_rLimZ*` 归零
- `fbM1/fbM2/fbY/fbZ/fbR : FB_Servo` — 见 [FB_Servo.md](FB_Servo.md)

## X 特别处理

- X 相对走距（自动步 1）不用定位 FB：**速度模式 + 里程判完成**
  （`rXStart` 记起点，`ABS(rActPos-rXStart) >= ABS(rMoveDistX)` → `AxisFb_xMoveDoneX`）
- 方向由 `AxisCmd_rMoveDistX` 符号决定；点动 X± 同理由 `AxisCmd_rJogVelX` 给绝对值
- 完成后撤速度（`xXVelActive:=FALSE`）→ FB_Servo 内部 MC_Halt 停车

## Y / Z / R

- Y：回零 > 绝对（归位 0） > 相对（横移跨距） > 点动；`AxisFb_xMoveDoneY := fbY.xMoveRelDone`
- Z：`AxisCmd_xForceFollow` 时走 `fbFF.rZVelCmd` 速度指令，否则回零/点动
- R：回零 > 保持角（`AxisCmd_xHoldR` 绝对定位到 `rRHoldPos`） > 点动；`xM5Ready=FALSE` 不上使能

## Must not

- 写 `HMI_*` / 报警 / 设备状态
- 被 Logic CALL
