# Axis_Control.md — 运动独立任务

> 源码：`plc/src/PRG_Axis_Control.st`。ETHERCAT 任务 4ms；**无外部 CALL**；仅读写 GVL。

## 轴

| 逻辑 | 电机 | SoftMotion | 硬限位 |
|------|------|------------|--------|
| X | M1+M2 | `Axis` / `Axis_1`（独立双驱，无 Virtual） | 无；**不做**编码器互差联锁 |
| Y | M3 | `Axis_2` | `Cfg_rLimY*` |
| Z | M4 | `Axis_3` | `Cfg_rLimZ*` |
| R | M5 | `Axis_4`（`xM5Ready` 门控） | `Cfg_rLimR*` |

## 组装

- `fbForce : FB_Force` — `Force_wInRaw(%IW102) → rForceAct`（模拟时 Logic 直写 `rForceAct`）
  - 力通讯状态 `Force_xCommOk`/`Force_xTimeout` **由 `PRG_Force485` 的收发回文状态机唯一判定**；
    `FB_Force` 的“原始值 2s 不变”看门狗**不再驱动报警**（力稳定时会误报 1005）。
- `fbX : FB_XDual` — X 双驱（`FB_XLineTrack` 差速 + 双 `FB_Servo`；无 Virtual/Gear）
- `fbFF : FB_ForceFollow` — Z 恒力 P 律，限 `[-rVelMax, rVelMax]`，撞 `Cfg_rLimZ*` 归零
- `fbY/fbZ/fbR : FB_Servo` — 见 [FB_Servo.md](FB_Servo.md)

## X 双驱（LineTrack）

`FB_XDual` 内部：`FB_XLineTrack` 合成 `rVelM1/rVelM2` → 双 `FB_Servo`（`xUseVelCmd`，`xLimEn:=FALSE`）。

- **直行（JogX± / 自动 MoveRel）**：`eMode=1`，M1/M2 同向；可选 `rKpTrack·rHeadingErr` 航向纠偏（trim 限 `Cfg_rPhaseMax`）
- **原地转（SpinL/R）**：`eMode=2/3`，一正一反差速
- **走距完成**：`xMoveRel` 上升沿锁存 `(PosM1+PosM2)/2`；运行中平均相对位移 `|Δ| ≥ |rMoveDist|` → `AxisFb_xMoveDoneX`
- **停止**：两轴速度 0 → `MC_Halt`
- **已取消**：Virtual 轴、`MC_GearIn/Out/Phasing`、`|PosM1−PosM2|` 同步预警/跳闸、报警 **1008**

兼容反馈：`AxisFb_rPosX := (PosM1+PosM2)/2`；`rSyncErr`/龙门耦合/Gear 相关位恒 0/FALSE。

详见 [x-dual-linetrack-design](../superpowers/specs/2026-07-25-x-dual-linetrack-design.md)。

## Y / Z / R

- Y：回零 > 绝对（归位 0） > 相对（横移跨距） > 点动；`AxisFb_xMoveDoneY := fbY.xMoveRelDone`
- Z：`AxisCmd_xForceFollow` 时走 `fbFF.rZVelCmd` 速度指令，否则回零/点动
- R：回零 > 保持角（`AxisCmd_xHoldR` 绝对定位到 `rRHoldPos`） > 点动；`xM5Ready=FALSE` 不上使能

## Must not

- 写 `HMI_*` / 报警 / 设备状态
- 被 Logic CALL

## 现场 InoProShop 验收（X 双驱切换后）

1. 导入注入后的 `LMM.xml`，编译 **0 error**（无 `FB_GantryX` / 未解析 `Axis_Virtual` 引用）
2. 设备树：**禁用或删除** `Axis_Virtual`；核对 `Axis`/`Axis_1` 仍为 M1/M2
3. 下载后：手动 X±、SpinL/R、自动一步走距；确认双轴 Power/Ready，**无报警 1008**
