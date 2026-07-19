# docs/plc — S6 索引

| # | File | Stage role |
|---|------|------------|
| 1 | [GVL.md](GVL.md) | 契约与 Axis I/O |
| 2 | [FB_Servo.md](FB_Servo.md) | 单轴原子（Axis 任务内） |
| 3 | [FB_XDiff.md](FB_XDiff.md) | X 同步/差速（Axis 任务内） |
| 4 | [Axis_Control.md](Axis_Control.md) | **独立任务**，无外部 CALL |
| 5 | [PRG_Logic.md](PRG_Logic.md) | 设备态 / 手动 / 自动恒力步序 |
| 6 | [HMI.md](HMI.md) | 触摸屏：手动键 + 自动参数 |
| 6b | [TCP_HMI.md](TCP_HMI.md) | TCP JSON + WebHMI 网关契约 |
| 6c | [FB_TCPServer.md](FB_TCPServer.md) | 手册场景1：SktTCP* 状态机 |
| 6d | [FB_Force485.md](FB_Force485.md) | LE 拉压传感器 Modbus-RTU |
| 6e | [PRG_Force485.md](PRG_Force485.md) | **独立 ForceTask**，写 rForceAct |
| 7 | [PLC_PRG.md](PLC_PRG.md) | 主入口（TcpHmi + Logic） |
| 8 | [WEB_PLC_ALIGN.md](WEB_PLC_ALIGN.md) | Web v2 / live ↔ PLC 对齐 |

S5 AlarmID：1001 E-Stop · 1002 Fault · 1003 Limit · 1004 Reject · **1005 Force485 超时** · 1099 M5 N/A  
