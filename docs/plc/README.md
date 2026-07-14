# docs/plc — S6 索引

| # | File | Stage role |
|---|------|------------|
| 1 | [GVL.md](GVL.md) | 契约与 Axis I/O |
| 2 | [FB_Servo.md](FB_Servo.md) | 单轴原子（Axis 任务内） |
| 3 | [FB_XDiff.md](FB_XDiff.md) | X 同步/差速（Axis 任务内） |
| 4 | [Axis_Control.md](Axis_Control.md) | **独立任务**，无外部 CALL |
| 5 | [PRG_Logic.md](PRG_Logic.md) | 设备态 / 手动 / 自动恒力步序 |
| 6 | [HMI.md](HMI.md) | 触摸屏：手动键 + 自动参数 |

手动：X±、左/右旋转、Y±、Z±、R±。自动：X→Z压到力→Y恒力。力默认模拟 N。  

| 7 | [PLC_PRG.md](PLC_PRG.md) | 主入口 |
| 8 | [WEB_PLC_ALIGN.md](WEB_PLC_ALIGN.md) | Web v2 ↔ PLC 对齐（Gate D） |

S5 AlarmID：1001 E-Stop · 1002 Fault · 1003 Limit · 1004 Reject · 1099 M5 N/A  
