# Web v2 ↔ PLC 功能对齐表

> 权威：`web/v2/index.html` 行为 = `docs/plc/*.md` 导入实现。  
> Gate D：用户确认「web2 理解是正确的了」(2026-07-13)。

## 运动学（示意 = 现场约定）

| 轴 | Web 示意 | PLC |
|----|----------|-----|
| X = M1/M2 | 沿导轨，**与 Y 垂直** | 龙门双驱相对轴，上电 0 |
| Y | 沿横梁，⊥X | Axis_2 |
| Z | 装在 Y 上 | Axis_3 |
| R | 禁用 | M5 未就绪，`xM5Ready=FALSE` |

## 控件 → GVL → 模块

| Web 操作 | HMI 变量 | Logic 写出 | Axis 消费 |
|----------|----------|------------|-----------|
| 急停按住/松开 | `HMI_xEStop` F/T | `xEStopLatched`；`AxisCmd_xStopAll`；清使能闩 | 停+松使能 |
| **使能（瞬时）** | `HMI_xEnable` 上升沿 | 切换 `xPowerLatched` → `AxisCmd_xPower` | `MC_Power` / `FB_Servo.xEnable` |
| 停止点按 | `HMI_xStop` | `AxisCmd_xStopAll`（**不清**使能闩） | MC_Stop |
| 停止长按3s | `HMI_xStopHold3s` | 清锁存 + `AxisCmd_xResetFault` + **下使能** | `MC_Reset` 各轴 |
| Indep/Sync/Diff | `HMI_eXMode` 0/1/2 | `AxisCmd_eXMode` | `FB_XDiff` / 单侧 |
| 纠偏/原地旋/差速弯 | `HMI_eDiffFunc` 0/1/2 | `AxisCmd_eDiffFunc` | `FB_XDiff` CASE |
| Sync± 按住 | `HMI_xJogXSyncPos/Neg` | 透传（仅 mode=1，须已使能） | 同速 V；松=暂停 |
| Diff± 按住 | `HMI_xJogXDiffPos/Neg` | 透传（仅 mode=2） | 见 FB_XDiff；松=暂停 |
| M1/M2± | `HMI_xJogM1/M2*` | 仅 mode=0 | 单侧 JOG；松=暂停 |
| Y/Z± | `HMI_xJogY/Z*` | 限位门控 | `FB_Servo`；松=暂停 |
| Home Y/Z | `HMI_xHomeReqY/Z` | `AxisCmd_xHome*` | `MC_Home` |
| JogVel/Δ/ω/L | `HMI_rJogVel*` / `rDiffDelta` / `rTurnOmega` / `rWheelBase` | → AxisCmd | FB 参数 |
| 限位勾选 | `I_xLim*` | `xIlk_Block*` | 禁对应方向 |
| Z忙禁Y | （Logic 用 `AxisFb_xMovingZ`） | `xIlk_BlockYWhenZ` | 禁 Y |
| Fault 模拟 | （联调时驱动 Fault） | `xFaultAggregate` / 1002 | 停+下使能 |

## Diff 速度公式（Web = FB_XDiff）

| eDiffFunc | V1 / V2 |
|-----------|---------|
| 0 纠偏 | `(V±Δ)*dir` 同向 |
| 1 原地旋转 | `+mag, -mag`（一正一反）；mag=`ω·L/2` 或 `V` |
| 2 差速拐弯 | `(V±ω·L/2)*dir`；无 ω 则用 Δ |

`L` 限制 **[4, 6] m**；非法则拐弯/旋转拒动。

## AlarmID

| ID | Web | PLC |
|----|-----|-----|
| 1001 | 急停 | `xEStopLatched OR NOT HMI_xEStop` |
| 1002 | Fault | `xFaultAggregate` |
| 1003 | 限位拒动 | JOG 撞限位 |
| 1004 | 无许可拒动 | 可选 |
| 1099 | R 操作 | M5 未就绪 |

## 任务边界（不可破）

```
HMI / PRG_Logic  --GVL_AxisCmd-->  PRG_Axis_Control(独立任务)  --GVL_AxisFb-->  HMI
                         禁止 CALL
```

## 本期不做

自动循环、视觉直线、M5 实轴。  
