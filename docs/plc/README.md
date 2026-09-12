# docs/plc — 文档索引

> **权威源码**：`plc/src/*.st` + `plc/GVL.st`（维护工作流见 `plc/README.md`）。
> 本目录是说明文档；代码与文档冲突时以 `plc/` 源码为准。
> **当前在役**：`LMM_g_0.67.xml`（设备树 Modbus TCP 从站通道 `0x1000/0x1100`；POU 逻辑 = 0.63 速度透传 + 0.64 力通讯单一写者 + 0.66 就绪判据）。

| # | 文档 | 内容 |
|---|------|------|
| 1 | [GVL.md](GVL.md) | 全局变量契约（分组、写者、面板/限位/控制源） |
| 2 | [FB_Servo.md](FB_Servo.md) | 单轴原子 FB：点动/速度/定位/回零/硬限位 |
| 3 | [Axis_Control.md](Axis_Control.md) | 运动独立任务（ETHERCAT）：5 轴组装 + 力/纠偏 |
| 4 | [PRG_Logic.md](PRG_Logic.md) | 安全去耦 / 手动 / 自动多道循环 / 回零编排 |
| 5 | [HMI.md](HMI.md) | 触摸屏 / WebHMI 变量中文用法总表 |
| 6 | [TCP_HMI.md](TCP_HMI.md) | WebHMI ↔ Gateway ↔ Modbus TCP 通讯契约 |
| 6b | [MODBUS_MAP.md](MODBUS_MAP.md) | Holding 1000/1100 地址表（生成，勿手改） |
| 6c | [VISION_MODBUS_TCP.md](VISION_MODBUS_TCP.md) | 视觉纠偏 Modbus TCP（IP / 寄存器 / 字节） |
| 6d | [VISION_DIRECT.md](VISION_DIRECT.md) | X 轴视觉直控（0.60）+ 双电机速度通用透传（0.63） |
| 7 | [PLC_PRG.md](PLC_PRG.md) | 主入口与任务一览 |
| 8 | [IMPORT_LMM_XML.md](IMPORT_LMM_XML.md) | 导入 InoProShop / 联调检查单 |
| 9 | [WEB_PLC_ALIGN.md](WEB_PLC_ALIGN.md) | Web live ↔ PLC 对齐速查 |

WebHMI v2 + 0.63 速度透传设计/计划：
[`../superpowers/specs/2026-09-12-x-speed-webhmi-v2-design.md`](../superpowers/specs/2026-09-12-x-speed-webhmi-v2-design.md) /
[`../superpowers/plans/2026-09-12-x-speed-webhmi-v2.md`](../superpowers/plans/2026-09-12-x-speed-webhmi-v2.md)。

历史（勿再用）：`REFACTOR_3POU.md`（重构契约，已落地）；
`FB_TCPServer` / `FB_Force485` / `PRG_Force485` / `FB_XDiff` 文档在 `attic/docs/`。

## 报警表

1001 急停 · 1002 电机故障 · 1003 限位 · 1005 力超时 · 1006 从站使能失败 · 1007 使能未就绪

## 现场验证清单

- [ ] InoProShop 导入 `LMM.xml` 编译 0 错
- [ ] 面板 JogFwd/Bwd → X±；Left/Right → Y±；Up/Down → Z±；Clock → R±
- [ ] Web/触摸屏点动：按住动、松开即停
- [ ] Y/Z/R 点动到硬限位被挡（Cfg_rLim* 可改）；X 无限制
- [ ] 力引导电平：TRUE 跟力、FALSE 停；Z 到限位停
- [ ] Y/Z/R 回零各自完成、位置置 0
- [ ] 自动循环：X 走距 → Y 归位 → Z 压到力 → Y 走跨距恒力 → 多道 → 收尾
- [ ] 拔网线 ≤1s 远程动作清零；恢复后不自行运动；面板可接管
