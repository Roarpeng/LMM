# X 双驱独立差速（LineTrack）设计

日期：2026-07-25  
状态：**已实现**（2026-07-25）  
取代：[`2026-07-25-virtual-gantry-x-design.md`](./2026-07-25-virtual-gantry-x-design.md)（Virtual + 电子齿轮方案作废）

## 动机

现场 `FB_GantryX`（`Axis_Virtual` + `MC_GearIn`）导致 X 轴无法运动。编码器反馈位置不等于真轨几何位置，基于 `|PosM1−PosM2|` 的同步偏差联锁无意义。改为 **M1/M2 独立速度控制 + `FB_XLineTrack` 差速合成**。

## 目标

- 去掉虚拟轴与电子齿轮（`MC_GearIn` / `GearOut` / `Phasing`）
- 手动：X± 同速直行（可带航向纠偏）；左右旋一正一反
- 自动：同样走 LineTrack；走距用 **平均相对位移** 判完成
- 保持 `AxisCmd_*` / `HMI_*` / Modbus 命令契约不变
- **不做** 位置反馈偏差联锁（无 SyncWarn/Fault、无报警 1008）

## 非目标

- 不恢复硬同步 / 电子齿轮
- 不以编码器互差防拧架（机械与操作负责）
- 不改 Y/Z/R 与力控路径

## 架构

```
AxisCmd (Jog / Spin / MoveRel / Stop / Power)
        │
        ▼
   FB_XLineTrack          ← 速度合成
        │ rVelM1, rVelM2
        ▼
  FB_Servo(M1)  FB_Servo(M2)   ← 仅速度模式；xLimEn:=FALSE
        │
        ▼
  平均相对位移 → MoveDoneX
```

建议在 `PRG_Axis_Control` 内用薄封装 `FB_XDual`（内部 = LineTrack + 双 Servo + 走距），对外仍消费现有 `AxisCmd_*`。

## 运动语义

### LineTrack 模式映射

| 条件 | `eMode` | 速度输入 |
|------|---------|----------|
| JogX+ / JogX−（互斥） | 1 直行 | `rBaseVel = ±AxisCmd_rJogVelX`；手动纠偏可用 `rKpTrack`（常为 0） |
| SpinL / SpinR | 2 / 3 | `rSpinVel = AxisCmd_rSpinVel` |
| 自动 `AxisCmd_xMoveRelX` | 1 | `rBaseVel = sign(dist)·rMoveVelX`，叠 `rTrackKp·rHeadingErr`，trim 限幅用 `Cfg_rPhaseMax` |
| Stop / 无命令 | 0 | 两轴速度 0 → `MC_Halt` |

优先级：Stop/Fault > Spin > Jog/MoveRel（与 `PRG_Logic` 中 X 与旋转互斥一致）。

### 走距完成（相对位移，方案 A）

1. `xMoveRel` **上升沿**锁存 `rStart := (PosM1 + PosM2) / 2`
2. 运行中 `rAvg := (PosM1 + PosM2) / 2`
3. 当 `|rAvg − rStart| ≥ |rMoveDist|` → `AxisFb_xMoveDoneX := TRUE`
4. 停止或撤销走距时清完成标志并解除锁存

说明：用的是**相对增量**，不是绝对坐标几何，也不是两轴互差。

### 明确取消的联锁

- `|PosM1 − PosM2|` 预警 / 跳闸
- `AxisFb_xSyncWarn` / `AxisFb_xSyncFault`（恒 FALSE）
- Logic 报警 **1008**
- `Cfg_rSyncWarn` / `Cfg_rSyncFault` 不再参与停机（可保留变量以免破坏 RETAIN 布局，但文档标明废弃）

## 接口与 GVL

### `PRG_Axis_Control` 组装

| 实例 | 轴 | 说明 |
|------|----|------|
| `fbTrack` 或内嵌于 `FB_XDual` | — | `FB_XLineTrack` |
| `fbM1 : FB_Servo` | `Axis`（M1） | `xUseVelCmd`，`xLimEn:=FALSE` |
| `fbM2 : FB_Servo` | `Axis_1`（M2） | 同上 |
| `fbY/Z/R` | 不变 | 现有 `FB_Servo` |

删除：`fbGantry : FB_GantryX` 及对 `Axis_Virtual` 的引用。

### 反馈兼容

| 符号 | 行为 |
|------|------|
| `AxisFb_rPosM1/M2`、`rVelCmdM1/M2` | 继续写（显示/调试） |
| `AxisFb_rPosX` | `(PosM1+PosM2)/2` |
| `AxisFb_xMoveDoneX` | 相对平均位移判据 |
| `AxisFb_xPowered/Ready/Fault/Moving/Standstill*`（M1/M2） | 来自双 `FB_Servo` |
| `AxisFb_rSyncErr` | 恒 0 |
| `AxisFb_xSyncWarn` / `xSyncFault` | 恒 FALSE |
| `AxisFb_xGantryCoupled` / `xInGear*` / `xPoweredV` | 恒 FALSE |
| `AxisFb_iGantryState` / `rVelFactorX` | 恒 0 |

HMI / Modbus 命令与状态字布局尽量不动；1008 相关状态位可恒 0。

## 删除清单

- POU：`FB_GantryX`（`LMM.xml`；仓库无独立 `.st` 时以 XML 为准删除）
- 设备树：`Axis_Virtual`（导入工程后禁用或删除，并核对轴映射）
- SM3 调用：`MC_GearIn` / `MC_GearOut` / `MC_Phasing`（X 路径）
- `PRG_Logic`：`iAlarmID := 1008` 分支
- 文档：标记 virtual-gantry 设计为 **作废**；更新 `Axis_Control.md` / 报警表 / `plc/README.md`

## 测试验收

1. 手动 X±：M1/M2 同向运动，松手减速停
2. 左/右旋：一正一反，松手停
3. 自动 X 步：LineTrack 运行，平均相对位移到达 → `MoveDoneX`，步进继续
4. 无 Virtual、无 Gear 时双轴可 Power/Ready；不会因 ΔPos 报 1008
5. Y/Z/R 点动与回零回归通过

## 风险

- 开环软同步：两侧速度指令相同（或带 trim），无编码器互锁防拧架
- 自动走距是编码器相对里程，与真轨几何仍可能偏差
- 删除 `Axis_Virtual` 后需完整重新下载与轴号核对

## 实现顺序（概要）

- [x] 新增 `FB_XDual`（`LMM.xml`）并接 `PRG_Axis_Control`（`fbX : FB_XDual`）
- [x] 从 XML 移除 `FB_GantryX`；Logic 去掉 1008
- [x] 更新文档与 gateway/mock 对 1008 / coupled 的假设
- [ ] 现场：删/禁 `Axis_Virtual`，验证手动与自动 X（见 [Axis_Control.md](../../plc/Axis_Control.md) 验收清单）

## 现场 InoProShop 清单

1. 导入注入后的 `LMM.xml`
2. 编译：确认无 `FB_GantryX` / `Axis_Virtual` 未解析引用
3. 设备树：**禁用或删除** `Axis_Virtual`
4. 核对 `Axis` / `Axis_1` 仍为 M1 / M2
5. 下载后验收：手动 X±、SpinL/R、自动一步走距；确认无报警 1008
