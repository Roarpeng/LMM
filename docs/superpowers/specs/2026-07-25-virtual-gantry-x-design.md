# 虚拟轴龙门 X（M1/M2）设计

日期：2026-07-25  
状态：**作废** — 由 [`2026-07-25-x-dual-linetrack-design.md`](./2026-07-25-x-dual-linetrack-design.md) 取代（独立双驱 + LineTrack，无 Virtual/电子齿轮）

## 现场约束

- M1/M2 跨两条平行导轨，横梁刚性连接；导轨长达数百米且非理想直线。
- 「走直线」= 结构不拧架 + 沿双轨前进；常需**连续小相位差速**跟轨。
- 功能保留：同步直行、航向/跟轨纠偏、原地旋转；HMI/`AxisCmd_*` 契约不变。

## 四层架构

| 层 | 机制 | 职责 |
|----|------|------|
| L1 | `Axis_Virtual` + `MC_GearIn` M1/M2 | 硬同步底 |
| L2 | Virtual `MC_MoveVelocity(指令速)` + Acc/Dec | 调速（本机无 `MC_SetOverride`，直接改 Velocity） |
| L3 | 耦合下 `MC_Phasing`（M2） | 连续小跟轨/航向 |
| L4 | `MC_GearOut` + `FB_XLineTrack` | 原地旋转 |

状态机：`0 Idle → 1 Coupling → 2 Coupled（保持 GearIn）→ 3 Decoupling → 4 DiffRun → 5 Aligning`。

**关键时序（与现场电子齿轮一致）：**

1. 三轴 `MC_Power`（含 Virtual）
2. 从轴 Halt 静止后 `MC_GearIn(Master:=Axis_Virtual, Slave:=M1/M2, 1:1)`，`Execute` 保持（`xStartSync`）
3. `InGear` 后才对 Virtual 发 `MC_MoveVelocity`；松手只停虚轴速度，**不解耦**
4. 原地旋转：`MC_GearOut` → 双轴差速 → 停稳再重新 GearIn

## 关键符号

- 配置（RETAIN）：`Cfg_rVelBaseMaxX` / `Cfg_rPhaseMax` / `Cfg_rSyncWarn` / `Cfg_rSyncFault`
- 反馈：`AxisFb_rPosX` / `rSyncErr` / `rVelFactorX` / `xGantryCoupled` / `xSyncWarn` / `xSyncFault` / `iGantryState`
- 报警 **1008**：同步跳闸（锁存，复位且 ΔPos 回到允差内清除）

## 库依赖（InoPro 编译）

需 SM3 提供：`MC_GearIn` / `MC_GearOut` / `MC_Phasing`。  
本机 InoPro 无 `MC_SetOverride`，已降级为虚轴直接 `MoveVelocity`。  
若本机参数名/枚举与源码不一致，仅改 `FB_GantryX.st` 后重新注入。  
方向字面值与现工程一致：`positive` / `negative`。

## 设备树

`Axis_Virtual`：`bVirtual=TRUE`，scaling 1:1（技术单位空间），软件限位关闭，限位窗口放大以支持长轨里程。
