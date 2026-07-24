# HMI.md — 触摸屏 / WebHMI 变量中文说明

> 触摸屏与 WebHMI **共用同一套 `HMI_*` 语义**。  
> - **触摸屏**：直接写 `HMI_*` 或 `HMI_*Req`（请求类），读状态组。  
> - **WebHMI**：浏览器仍写/读 `HMI_*` 名字；Gateway→Modbus→`Tcp_*` 影子→`PRG_TcpHmi` 仲裁到 `HMI_*`。  
> 禁止写：`AxisCmd_*`、`iAutoStep`、过程映像 `MB_*`。  
> 契约：`GVL.md` · 通讯：`TCP_HMI.md` · 地址表：`MODBUS_MAP.md` · 实控：`web/live/`

## 绑定总则

| 规则 | 说明 |
|------|------|
| 写方向 | 操作控件 → `HMI_*`（或触摸屏 `*Req`）；Web 经网关进 `Tcp_*` 再仲裁 |
| 读方向 | 灯、报警、步号、力、位置 → `HMI_*` 状态 / `AxisFb_*` / `Force_x*` |
| 点动 | **电平**：按住 TRUE，松开必须 FALSE。面板 Jog 键在 `eCtrlSrc=0` 时与 `HMI_xJog*` 等效（Fwd/Bwd→X±，Right/Left→Y±，Up/Down→Z±，Clock→R±） |
| 启动/回零/去皮 | **上升沿**有效 |
| 急停极性 | TRUE=正常；FALSE=按下（更严：物理 AND 触摸屏 AND Web） |
| 互斥 | 面板与远程不同时混控；掉线回面板 |

---

## 1. 安全与起停（写）

| 变量 | 中文 | 用法 |
|------|------|------|
| `HMI_xEStop` | 急停请求 | TRUE 正常 / FALSE 按下。Web「急停」非安全认证功能 |
| `HMI_xEStopReq` | 触摸屏急停 | 仅触摸屏；与物理急停、Web 相与 |
| `HMI_xStop` | 停止 | 任一源为真即停机 |
| `HMI_xStopReq` | 触摸屏停止 | |
| `HMI_xStopHold3s` | 复位 | 对应长按停止；清急停锁存与轴故障 |
| `HMI_xResetReq` | 触摸屏复位 | |
| `HMI_xStart` / `HMI_xEnable` | 启动 | 上升沿；Enable 为别名。手动点动不强制先启动 |
| `HMI_xStartReq` | 触摸屏启动 | |

## 2. 模式与状态灯（模式可写；灯只读）

| 变量 | 中文 | 用法 |
|------|------|------|
| `HMI_xAutoMode` | 模式 | FALSE 手动 / TRUE 自动 |
| `HMI_eOpMode` | 方式显示 | 0 手动 1 自动 |
| `HMI_eDevState` | 状态码 | 0 停 1 运行 2 错误（仅显示） |
| `HMI_xDevStop` / `Run` / `Error` | 三态灯 | 停 / 运行 / 故障 |
| `HMI_xLampEStop` / `EnableOk` / `Fault` | 指示灯 | 急停 / 就绪 / 故障 |
| `HMI_iAlarmShow` | 报警号 | 1001…1007 等 |

## 3. 手动点动（写，电平）

| 变量 | 中文 | 用法 |
|------|------|------|
| `HMI_xJogXPos` / `Neg` | X± | M1=M2 同速；与旋转互斥 |
| `HMI_xSpinLeft` / `Right` | 左/右旋 | 差速原地转；与 X± 互斥 |
| `HMI_xJogYPos` / `Neg` | Y± | 受限位与 Z 互锁 |
| `HMI_xJogZPos` / `Neg` | Z± | 硬限位 `Cfg_rLimZ*`（默认 [−0.7, 0]） |
| `HMI_xJogRPos` / `Neg` | R± | 需 M5 就绪 |
| `HMI_rJogVelX` | X 直行速度 | **不等于** 旋转速度 |
| `HMI_rSpinVel` | 左右旋速度 | 与 VelX 分开设 |
| `HMI_rJogVelY/Z/R` | Y/Z/R 速度 | |

前提：急停正常、未停止、手动模式。

## 4. 回零（写触发 / 读状态）

| 变量 | 中文 | 用法 |
|------|------|------|
| `HMI_iHomeAxis` | 轴选择 | 0 无 / 1Y / 2Z / 3R |
| `HMI_xHomeExec` | 执行回零 | 上升沿 |
| `HMI_xHomeY/Z/R` | 独立回零 | 上升沿，可替代选择+执行 |
| `HMI_xHomedY/Z/R` | 已回零 | 只读 |
| `HMI_xHomeBusyY/Z/R` | 回零中 | 只读 |

同时只回一轴；停止/急停中止。完成后当前位置为 0。

## 5. 自动与力控（写参数 / 读进度）

| 变量 | 中文 | 用法 |
|------|------|------|
| `HMI_xAutoStart` / `Abort` | 启动 / 中止 | 启动上升沿；中止立即结束 |
| `HMI_xAutoStartReq` / `AbortReq` | 触摸屏启动/中止 | |
| `HMI_rAutoDistX` | X 走距 | |
| `HMI_rAutoVelX/Y/Z` | 自动速度 | |
| `HMI_rWheelBase` | 跨距=Y行程 | 4~6 m |
| `HMI_iAutoPasses` | 总道数 | ≥1 |
| `HMI_rForceSet` | 恒力设定 | N |
| `HMI_rKpForce` | 力跟随 Kp | |
| `HMI_rKpTrack` | 直线纠偏 Kp | |
| `HMI_rHeadingErr` | 航向误差 | 视觉/外部输入 |
| `HMI_xForceGuide` | 力引导 | 电平：TRUE 持续跟随 |
| `HMI_xForceTare` / `Untare` | 去皮 / 取消 | 上升沿 |
| `HMI_xForceSimEnable` + `HMI_rForceSim` | 力模拟 | 台架调试 |
| `HMI_iAutoStepShow` | 步号 | 只读 |
| `HMI_xAutoBusy` / `Done` | 忙 / 完成 | 只读 |
| `HMI_rForceShow` | 显示力 | 只读，单位 N |

自动主序概要：Idle → X走距 → Z下压到力 → Y走跨距+恒力 →（R）→ Done；可多道循环。

## 5b. 硬限位配置（写，所有模式强制）

| 变量 | 中文 | 默认 |
|------|------|------|
| `Cfg_rLimYPos` / `Neg` | Y 正/负限位 (m) | 6.0 / 0.0 |
| `Cfg_rLimZPos` / `Neg` | Z 正/负限位 (m) | 0.0 / −0.7 |
| `Cfg_rLimRPos` / `Neg` | R 正/负限位 (度) | 180 / −180 |

X 轴无限位。限位在 `FB_Servo` 内强制执行（点动/速度挡方向、定位夹目标、
撞到即 MC_Halt）；**可手动改**——触摸屏直绑 GVL；Web 端暂不提供。
改小到当前位置之内时，仍允许向回运动。

## 6. 力传感与轴反馈（只读，建议监控页）

| 变量 | 中文 |
|------|------|
| `Force_xCommOk` / `Timeout` / `SlaveFail` | 力通讯正常 / 超时(1005) / 从站失败(1006) |
| `Force_xTareBusy` / `Done` | 去皮中 / 完成 |
| `rForceAct` | 实际力（内部）；界面优先 `HMI_rForceShow` |
| `AxisFb_rPosY/Z/R`（及 M1/M2） | 实际位置 |
| `AxisFb_xReady` / `xReady*` | 轴就绪 |
| `AxisFb_xFault*` | 轴故障 |
| `AxisFb_xHomed*` / `xMoveDoneX/Y` | 回零与运动完成 |
| `AxisFb_rVelCmdM1/M2` | 纠偏后速度指令 |

## 7. Web 专用链路与影子（触摸屏不要绑命令到 Tcp_*）

| 变量 | 中文 | 用法 |
|------|------|------|
| `Tcp_xConnected` / `Timeout` / `Online` | 远程连接状态 | Web 状态栏 |
| `Tcp_iCommStatus` | 通讯诊断码 | 0~4 |
| `Tcp_*`（与 HMI 同后缀） | Web 命令影子 | 仅 PLC 通讯程序写；触摸屏写 `HMI_*` |
| `MB_CmdIn` / `MB_StatusOut` | Modbus 过程映像 | 禁止操作控件绑定 |

## 8. 画面分区建议

1. **安全**：急停、启动、停止/复位、三态灯、报警号  
2. **模式**：手动/自动  
3. **手动**：X±、旋、Y/Z/R±；VelX / SpinVel / VelY/Z/R  
4. **回零**：轴选择+执行或独立键；Homed/Busy  
5. **自动**：距/速/跨距/道数/F_set/Kp；启动中止；步号与力  
6. **监控**：位置、就绪、力通讯、远程在线  

## Must not

- 写 `AxisCmd_*` / `MB_*` / 内部 `Tcp_w*`  
- 绑已删除符号：`JogXSync*`、`eXMode`、`AutoDistY` 等  
- 自动进行中开放手动 JOG  
- 把 Web 急停宣传为安全认证急停  
