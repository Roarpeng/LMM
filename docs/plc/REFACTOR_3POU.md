# LMM 重构契约 — 3 POU + 4 底层 FB（S 定稿）

> 目标：解决"手动不动/无报警/devstatus 互耦"；把底层拆成 4 个纯功能 FB；程序只保留 3 个 POU（+PLC_PRG 入口）。
> 权威符号仍以 `GVL` 为准。任务间**只经 GVL 交换，禁止跨任务 CALL**。

## 1. 顶层 / 任务

| 任务 | 周期 | POU |
|------|------|-----|
| ETHERCAT (prio 0) | 4ms | `PRG_Axis_Control`（轴控制） |
| MainTask (prio 1) | 4ms | `PLC_PRG` → `PRG_TcpHmi()` → `PRG_Logic()` |

数据流单向环：`HMI_* →(Logic) AxisCmd_* →(Axis) AxisFb_* →(回读) HMI_*`。
状态显示量（`Dev_x*`/`HMI_eDevState`）**只读派生，绝不参与运动互锁**。

## 2. 三个程序 POU

| POU | 角色 | 只写 | 读 |
|-----|------|------|----|
| `PRG_TcpHmi` | HMI 交互：面板IO + 触摸屏Req + Web(`FB_TCPServer`) 三源仲裁 | `HMI_*` | 面板IO/`Tcp_*`/触摸屏Req |
| `PRG_Logic` | 安全去耦 + 手动 + 自动多道循环 + 回零编排 | `AxisCmd_*` + 报警/灯 | `HMI_*`/`AxisFb_*` |
| `PRG_Axis_Control` | 组装 `FB_XDual`+3×`FB_Servo`(Y/Z/R)+`FB_Force`+`FB_ForceFollow` | `AxisFb_*`/`rForceAct`/`Force_*` | `AxisCmd_*` |

## 3. 底层 FB

- **FB_Servo**（电机控制，单轴原子）：`MC_Power/Reset/Stop/Home/SetPosition/MoveVelocity/MoveRelative/MoveAbsolute`。
  仲裁优先级：`停止/故障 > 回零 > 绝对定位 > 相对定位 > 速度模式 > 点动 > 空闲`。
  输出 `xReady`（功率级就绪且非 Errorstop）——用于诊断"为何不动"。Y/Z/R 使用。
- **FB_XDual**（X 双驱）：`FB_XLineTrack` 差速 + 双 `FB_Servo`（M1/M2 独立速度）；走距用平均相对位移判完成；无 Virtual/Gear/同步跳闸。详见 `docs/superpowers/specs/2026-07-25-x-dual-linetrack-design.md`。
- **FB_Force**（力转换）：`wRaw(%IW102) → rForceN`；软件去皮（上升沿记偏移）；`wRaw` 长时间不变→`xTimeout`（只报警）。
- **FB_ForceFollow**（恒力律）：`rZVelCmd := -rKp*(rForceSet-rForceAct)`（**向下=负**增压）；死区置 0；回零后夹紧 `[-0.7,0]`；`xInvert` 现场翻转符号。
- **FB_XLineTrack**（差速合成）：由 `FB_XDual` 调用；直行/自动走距与 Spin 均走 LineTrack 速度合成。

## 4. 安全 / 使能（去耦）

```
xSafe := HMI_xEStop AND NOT xEStopLatched;
AxisCmd_xPower   := xSafe;
AxisCmd_xStopAll := HMI_xStop OR NOT xSafe OR xFaultAggregate OR HMI_xAutoAbort;
```
`xFaultAggregate` 仅来自 `AxisFb_xFault*`（=各轴 `MC_ReadStatus.Errorstop`）。
使能就绪缺失（命令 Power 但 `AxisFb_xReady*` 全 FALSE 超时）→ 报警 **1007**（不阻断，仅提示）。

## 5. HMI 三源仲裁（PRG_TcpHmi）

- 命令组（jog/mode/params/auto/home/forceguide）：**Web 在线且有操作 → 整组 `HMI_*:=Tcp_*`（web 优先）**；否则触摸屏直写 `HMI_*` 生效。
- 安全/起停（单写者，防自锁）：
```
HMI_xEStop      := EStop AND Tcp_xEStop AND HMI_xEStopReq;   (* 正常 TRUE *)
HMI_xStart      := StartBtn OR HMI_xStartReq OR (Tcp_xOnline AND Tcp_xStart);
HMI_xStop       := StopBtn  OR HMI_xStopReq  OR (Tcp_xOnline AND Tcp_xStop);
HMI_xStopHold3s := ResetBtn OR HMI_xResetReq OR (Tcp_xOnline AND Tcp_xStopHold3s);
```
> **触摸屏软键**绑定新增 `HMI_xStartReq/StopReq/ResetReq/EStopReq(默认TRUE)/AutoStartReq/AutoAbortReq`，不再直写 `HMI_xStart/Stop/EStop`（消除双写者自锁，即问题1"模式卡死/无法动"的根因之一）。

## 6. 自动多道循环（PRG_Logic）

参数：`HMI_rAutoDistX`(每道X步距) · `HMI_iAutoPasses`(总道数) · `HMI_rWheelBase`(Y行程=跨距) · `HMI_rAutoVelX/Y/Z` · `HMI_rForceSet` · `HMI_rKpForce`。

```
0 待机 : AutoStart↑ → 记 R 保持角、去皮、iPass:=1 → 1
1 X前进: MoveRel X=rAutoDistX（velocity 模式 + 视觉纠偏，Axis 内按里程判完成）→ 2
2 Y归位: MoveAbs Y=0（起始侧）→ 3
3 Z下压: 力跟随，rForceAct≥rForceSet → 4
4 Y横移: MoveRel Y=rWheelBase 全程恒力 + R 保持角 → 5
5 判定 : iPass<nPasses ? (Z抬起→iPass++→1) : 6
6 收尾 : Z抬起 → Y/Z/R 回零位 → AutoDone
```
任一拍 `急停/停止/中止/本轴Fault` → 回 0。

## 7. 手动

- X±：`SpinLeft/Right`(原地转) 与 `JogXPos/Neg`(直行) 互斥；直行速 `rJogVelX`、旋转速 `rSpinVel` 分开。
- Y/Z/R±：`Jog*` + 各轴 Vel；Y/Z 受硬限位 + Z 回零后软限位 `[-0.7,0]`。
- 力引导：`HMI_xForceGuide` 电平 → `AxisCmd_xForceFollow`（Z 恒力），覆盖 Z 点动。

## 8. 回零

Y/Z 硬件限位回零；R 编码器回零。`HMI_xHomeY/Z/R` 或 `HMI_iHomeAxis(1Y2Z3R)+HMI_xHomeExec`，上升沿，同时只回一轴。
`FB_Servo`：`MC_Home(Position:=0)`→Done→`MC_SetPosition(0)`→`xHomed`→清命令。

## 9. GVL 增量

新增：`HMI_iAutoPasses` `Tcp_iAutoPasses` `HMI_rHeadingErr` `Tcp_rHeadingErr` `HMI_rKpTrack` `HMI_rKpForce`
`HMI_xStartReq/StopReq/ResetReq/EStopReq/AutoStartReq/AutoAbortReq`
`AxisCmd_rHeadingErr/rTrackKp/rForceSet/rForceKp/rForceVelMax/rMoveAbsPosY` `AxisCmd_xForceFollow/xMoveAbsY`
`AxisFb_xReadyM1/M2/Y/Z/R`
报警新增：**1007 使能未就绪**。
删除的 POU：`PRG_Force485`（下沉为 `FB_Force`）、`FB_XDiff`（改 `FB_XLineTrack`）。

## 10. 报警表

1001 急停 · 1002 电机故障 · 1003 限位 · 1005 力超时 · 1006 从站失败 · **1007 使能未就绪**。
（**1008 已废除** — 原 X 同步跳闸，LineTrack 方案不做编码器互差联锁。）
