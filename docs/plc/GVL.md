# GVL.md — 全局变量契约

> 权威定义：`plc/GVL.st`（13 个分组，变量逐个带中文注释）。本文讲规则，不复制全表。
> 触摸屏 / WebHMI 变量中文用法总表：[HMI.md](HMI.md)。
> 轴：X=M1+M2，Y=M3，Z=M4，R=M5。X⊥Y。**跨距 = Y 行程**（`HMI_rWheelBase`，4~6 m）。

## 铁律

- 任务间**只经 GVL 交换，禁止跨任务 CALL**
- 写者唯一：`HMI_*` 只由 `PRG_TcpHmi` 写（触摸屏直写 `HMI_*`/`HMI_*Req` 除外）；
  `AxisCmd_*` 只由 `PRG_Logic` 写；`AxisFb_*`/`rForceAct`/`Force_x*` 只由 `PRG_Axis_Control` 写
- 状态显示量（`Dev_x*`/`HMI_eDevState`）**只读派生，绝不参与运动互锁**
- EStop：**正常 TRUE / 按下 FALSE**

## 分组速览（对应 plc/GVL.st 编号）

| # | 组 | 关键变量 | 写者 |
|---|----|---------|------|
| 1 | 面板物理 IO | `StartBtn %IX1.6` `StopBtn %IX1.4` `EStop %IX0.4` `StopLamp %QX0.6` `StartLamp %QX0.7`（地址固定勿改）+ 8 个 Jog 键 | 物理 |
| 2 | 安全/起停 | `HMI_xEStop/xStop/xStopHold3s/xStart`、`xEStopLatched`、`xFaultAggregate`、`eCtrlSrc` | TcpHmi |
| 3 | 状态显示 | `HMI_eDevState/HMI_eOpMode/HMI_iAlarmShow/HMI_xDev*/HMI_xLamp*` | Logic |
| 4 | 手动点动 | `HMI_xJog*/xSpin*` + `HMI_rJogVel*/rSpinVel`（X 直行与旋转速度**分开**） | TcpHmi |
| 5 | 回零 | `HMI_xHomeY/Z/R`、`HMI_iHomeAxis+xHomeExec`、`HMI_xHomed*/xHomeBusy*` | TcpHmi/Logic |
| 6 | 自动 | `HMI_rAutoDistX/rAutoVel*/rWheelBase/iAutoPasses/rForceSet/rKp*/rHeadingErr`、`iAutoStep` | TcpHmi |
| 7 | 力控 | `Force_*`（组态 Modbus RTU COM0）、`HMI_xForce*`、`rForceAct`、`HMI_rForceShow` | Axis/Logic |
| 8 | **硬限位配置** | `Cfg_rLimY*/Z*/R*`（Y[0,6] Z[-0.7,0] R[-180,180] 默认） | **触摸屏/调试手动改** |
| 9 | 联锁/限位输入 | `I_xLimY*/Z*`（地址 TBD）、`xIlk_Block*`、`xM5Ready` | 物理/Logic |
| 10 | 轴命令 | `AxisCmd_*` | Logic |
| 11 | 轴反馈 | `AxisFb_*` | Axis |
| 12 | Modbus+Web 影子 | `MB_CmdIn %IW103`、`MB_StatusOut %QW44`、`Tcp_*` | TcpHmi |
| 13 | 触摸屏请求 | `HMI_x*Req`（防双写自锁） | 触摸屏 |

## 面板 Jog 键（直接点动）

面板键在 `eCtrlSrc=0`（面板/触摸屏源）时与 `HMI_xJog*` 以 OR 合并进 Logic 手动段，
受完全相同的限位/安全门控：

| 键 | 轴 | 键 | 轴 |
|----|----|----|----|
| JogFwd / JogBwd | X+ / X- | JogUp / JogDown | Z+ / Z- |
| JogRight / JogLeft | Y+ / Y- | JogClockAdd / JogClockMis | R+ / R- |

（映射现场可对调，改 `PRG_Logic.st` 点动源合并段。）

## 硬限位（除 X 外所有轴、所有模式强制）

- 配置：`Cfg_rLim{Y,Z,R}{Pos,Neg}`，默认 Y[0,6]、Z[-0.7,0]、R[-180,180]，**可手动改**
- 执行：`FB_Servo` 内最终闸门（点动/速度挡方向、定位夹目标、撞限位 MC_Halt）；
  `FB_ForceFollow` 对 Z 另有同值夹紧；Logic 的 `xIlk_Block*` 只是点动前的提前挡
- `I_xLim*` 物理限位开关（若接线）与 Cfg 限位**或**关系进 `xIlk_Block*`

## 控制源仲裁（eCtrlSrc，GVL，仅 PRG_TcpHmi 写）

- `0=面板/触摸屏`：触摸屏直写 `HMI_*` 生效；面板 Jog 键并入点动
- `1=远程Web`：整组 `HMI_* := Tcp_*`
- 谁有操作谁独占；掉线强制回 0 并清点动/置停止+中止
- 急停取更严：`HMI_xEStop := EStop AND Tcp_xEStop AND HMI_xEStopReq`

## 已删除（勿再使用/绑屏）

`JogVel` `HomeReq` `CaliForReq` `ClearBruch` `yLength` `eDevState` `xEnablePermit`
`xIlk_BlockYWhenZ` `I_xLimR*` `I_xHomeY/Z/R` `Tcp_uiPort` `AxisCmd_rZVelCmd` `AxisCmd_xUseZVelCmd`
以及更早的 `HMI_eXMode` `JogM1/M2` `JogXSync*` `DiffDelta` `TurnOmega` `AutoDistY`。
