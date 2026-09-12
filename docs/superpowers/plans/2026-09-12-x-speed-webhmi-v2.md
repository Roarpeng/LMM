# X 速度透传 + WebHMI v2 实施计划

> 依据：`docs/superpowers/specs/2026-09-12-x-speed-webhmi-v2-design.md`
> 入口模式：change-request。MD 为源，Web 为验收视图。

## 任务

### T1 Gateway / 契约
- [ ] `config/modbus-map.json` status 增加 `AxisFb_rVelActM1/M2`、`AxisFb_xMoving*`、`AxisFb_xPowered*`、`AxisFb_xSyncWarn/Fault`、`AxisFb_rSyncErr`
- [ ] `gateway/lib/mock-plc.js` 状态补 `Direct_rVelM1Act/M2Act` 与新字段
- [ ] `gateway/lib/modbus-master.js` 暴露 `getDiagnostics()`
- [ ] `gateway/server.js` 增加 `GET /health`、`t:"lease"`、离线合并、`PLC_POLL_MS` 默认 50
- [ ] 更新/新增 `gateway/test/*`（health、字段覆盖）

### T2 WebHMI v2
- [ ] 重写 `web/live/index.html`：顶部状态栏 + 页签（自动/手动/X 双驱/调试/日志）
- [ ] 保留 `web-client.test.js` 约束结构（flush/patch/bindParam/onopen/onclose、force-sim、字段名）
- [ ] 键盘点动；触屏 hold-to-run；X 直控滑条；原始寄存器表 + 命令控制台；趋势 + 快照 + CSV
- [ ] rAF 合帧 + 变更 diff + 本地外推（响应速度）

### T3 PLC 0.63
- [ ] `plc/g/PRG_Axis_Control.st` 增 `AxisFb_rVelActM1/M2 := fbX.rVelActM1Out/M2Out`
- [ ] `tools/patch_g063.py`：0.62 → 0.63，插入 GVL 变量 + TcpHmi 状态编码（word32..38），幂等、CRLF/LF 安全
- [ ] 生成 `LMM_g_0.63.xml`；`inject_g.py --check` / ST 语法自查

### T4 文档 / 状态
- [ ] 更新 `docs/plc/MODBUS_MAP.md`（生成）、`VISION_DIRECT.md`、`TCP_HMI.md`、`WEB_PLC_ALIGN.md`、`gateway/README.md`
- [ ] 更新 `.equipment-workflow/state.md`

## 门禁

- Gate D：PLC 0.63 烧录后按 Web v2 检查单联调；自动循环在本迭代**不放行**（HMI 改版不涉及步序逻辑）。
- 安全：Web 急停仍为请求；物理急停 AND 仲裁不变。
