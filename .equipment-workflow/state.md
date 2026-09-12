# equipment-plc-workflow state

## Meta
- Project: LMM XYZR + 力传感
- Entry: change-request（X 双电机速度透传 + WebHMI v2）
- Updated: 2026-09-12

## Current
- Stage: S6/S7 — WebHMI v2 与 PLC 0.63 增量已落地（Web 为验收视图，MD 为源）
- Spec: `docs/superpowers/specs/2026-09-12-x-speed-webhmi-v2-design.md`
- Plan: `docs/superpowers/plans/2026-09-12-x-speed-webhmi-v2.md`
- 在役基线：`LMM_g_0.67.xml`（PLC 导出；Modbus TCP 从站 Type 40502 通道 `16#1000/16#1100` ↔ `%IW103/%QW44`；POU 逻辑=0.66+0.64+0.63；**WebHMI 实控验证 OK**）
- 通讯方向：Gateway（Modbus TCP 主站）→ PLC（从站）`192.168.1.88:502`；命令 Holding `4096..4159`（0x1000）、状态 `4352..4415`（0x1100）
- 速度透传（两层）：
  - Web 先行：状态 word29/30 `Direct_rVelM1Act/M2Act`（实际速度，各模式有效）已在 WebHMI v2「X 双驱」显示，**无需重烧**
  - PLC 0.63：新增状态 word32..38（`AxisFb_rVelActM1/M2`、Moving/Powered/SyncWarn/Fault、`AxisFb_rSyncErr`）
- 交付物：
  - `web/live/index.html` v2（自动/手动/X 双驱/调试/日志；键盘点动、X 直控滑条、寄存器表、趋势/快照、CSV）
  - `gateway/server.js`（`GET /health`、`t:"hello"/"lease"`、离线合并、`PLC_POLL_MS` 默认 50）
  - `gateway/lib/mock-plc.js`（实际速度/新字段）、`gateway/lib/modbus-master.js`（`getDiagnostics()`）
  - `tools/patch_g063.py` → `LMM_g_0.63.xml`；`gateway/scripts/smoke-webhmi.js`
- 验证：
  - `cd gateway && npm test` → **43 PASS**
  - `python3 tools/patch_g063.py` 幂等；`LMM_g_0.63.xml` XML 解析 OK；`inject_g.py --check` OK
  - Mock 冒烟 `node gateway/scripts/smoke-webhmi.js` → PASS（页面/health/map/WS hello·status·lease·新字段）
- Next: 真机联调 WebHMI v2（自动/手动/急停与面板一致；X 双驱页 M1/M2 实际速度跟随；点动按住动/松开停）

## Field findings（2026-09-12）
- **已解决（2026-09-12）**：Gateway 连 `192.168.1.88:502` 成功；PLC 程序侧正常（`MB_StatusOut[0]=19533`、`[2]` 每周期跳）。
- 根因：InoProShop 从站映射「起始地址」字段是**十六进制**，填 `1000`/`1100` 实际为 `0x1000`=**4096** / `0x1100`=**4352**；
  网关原按十进制 1000/1100 读写，落到空白区 → `MAGIC_MISMATCH,VERSION_MISMATCH`。
- 实测：Holding `4096..4159` = 命令镜像（PLC 状态 `word3` 回显命令序号），`4352..4415` = `0x4C4D 0x0100` + 序号递增。
- 处理：`config/modbus-map.json` 基址改为 4096/4352（**无需再改/下载 PLC**）；`generate_modbus_map.py` 与全部文档同步；
  Gateway 另有 `PLC_CMD_BASE`/`PLC_STATUS_BASE` 覆盖、协议错不再断开重连、`/health`、只读探针 `probe-plc.js`。
- 验证：真机 `/health` → `statusIsOffline=false`、`lastError=null`；启动日志 `cmd@4096 status@4352`；`npm test` 43 PASS。
- 踩坑备忘：从站 I/O 映射变量名不能与 GVL 同名（`MB_CmdIn`/`MB_StatusOut`），否则编译 `C0136/C0018`。
- **急停锁存 / 心跳（2026-09-12）**：真机状态 `HMI_iAlarmShow=1001`、`HMI_xLampEStop=TRUE`、`HMI_eDevState=2`、
  `AxisFb_xReady=FALSE` → PLC `xEStopLatched` 锁存，所有轴被 `xSafe` 锁住。
  - 操作：**松开物理急停 → 网页按一次「复位」**（`HMI_xStopHold3s` 上升沿）清锁存 + 轴故障复位。
  - Gateway fail-safe 由 `HMI_xEStop=FALSE` 改为 `HMI_xStop=TRUE + HMI_xEStop=TRUE`（停止不锁存）；
    新增 `store.advanceHeartbeat()` 每周期推进心跳，避免停顿 >1s 被判远程超时。
  - `npm test` → **44 PASS**。
- **1005 误报修复（2026-09-12）**：`Force_xTimeout`/`Force_xCommOk` 原有两个写者——`PRG_Force485`（真实回文判定）
  与 `PRG_Axis_Control`（`FB_Force` 的“原始值 2s 不变”看门狗）。力稳定时后者误置 TRUE → 偶尔报警 1005。
  - 修：删除 `PRG_Axis_Control` 里 `Force_xCommOk := fbForce.xCommOk;` / `Force_xTimeout := fbForce.xTimeout;`，
    使 `PRG_Force485` 成为唯一写者；`tools/patch_g064.py` 由 0.63 生成 **`LMM_g_0.64.xml`**（幂等、XML 解析 OK）。
  - 代价：启动时 3 次读失败 → 1006（`Force_xSlaveFail`）；运行中失联的持续检测另行用 RTU 从站诊断位（待现场确认）。
- **1007 静默误报修复（2026-09-12）**：`FB_XDual` 的 M1/M2 就绪判据误含 `NOT xStop`：
  `xReadyM1 := xEnable AND NOT xStop AND NOT xFaultM1`。`xStop` 来自 `AxisCmd_xStopAll`（`HMI_xStop` 等），
  设备停止/静默时 `xStop=TRUE` → Ready 立即 FALSE，而 `AxisCmd_xPower` 仍真且无故障 → `tonReady` 2s 后报 1007。
  - 0.65 曾误改为 `xPoweredM1/M2 AND NOT xFault`：`xRegOn` 在静态（eMode=0 且非停止）为 FALSE → `xPowered=FALSE` → 静态持续报 1007（回归）。
  - **正确修（0.66）**：`xReadyM1/M2 := xEnable AND NOT xFaultM1/M2`（不含 `xStop`、也不要求 `xPowered`）；
    `tools/patch_g066.py` 由 0.65 生成 **`LMM_g_0.66.xml`**。
  - `xPowerGate` 仍含 `NOT xStop`，运动互锁不变；仅「就绪」/1007 判据修正。
- **WebHMI v3（2026-09-12）**：前端重构为 `web/live/{index.html, styles.css, app.js}`（无构建）；信息架构 = 总览/自动/手动/X双驱/力传感/趋势/报警/调试/系统，左导航 + 设备视图 + 急停覆盖层；通讯层与 WS 契约不变。
  - Spec：`docs/superpowers/specs/2026-09-12-webhmi-v3-ui-design.md`。
  - `gateway/test/web-client.test.js` 改为读取三文件拼接校验；`npm test` 44 PASS、运行时自检 + Mock 冒烟 PASS。
- **视觉直控全轴（2026-09-12，change-request；实现完成，待烧录 0.68）**：视觉工控机**也运行 WebHMI**，与操作员共用同一 WS/JSON 接口与页面 → **不新增 /vision/* 协议**；把「每轴直控」纳入现有命令/状态映射。
  镜像 **64W → 96W**（尾部序号 63→95，单次 FC16/FC03 内）；新增每轴 方式/速度/位置 与 Y/Z/R 实际速度/直控状态反馈；
  **M1/M2 不单独写位置**（速度环 + 机械耦合；X 位置为整机目标 `HMI_rDirectPosX` 或视觉自闭环）；
  使能/报警/限位/急停仍 **PLC 独占**；`PRG_TcpHmi` 解码、`PRG_Logic` 直控路由 + `HMI_wDirectSeq` 300ms 看门狗；`PRG_Axis_Control` 基本不变。
  - 实现：契约 `config/modbus-map.json`（96W，命令 60..75 / 状态 39..45）；PLC **`LMM_g_0.68.xml`**（`tools/patch_g068.py` 幂等，sha `54cebbe4…`；新建 `plc/g/PRG_TcpHmi.st`，GVL +58 变量）；Gateway 分块 95+1 + mock；WebHMI 新增「直控」页。
  - 验收：`ET.parse(0.68)` OK、`inject_g --check` OK、`generate_modbus_map.py` 与 `MODBUS_MAP.md` 同步、`npm test` 44 PASS、`smoke-webhmi` PASS、无 `ARRAY[0..63]`/`MB_CmdIn[63]` 残留。
  - 现场待办：InoProShop 导入 0.68 → 编译 0 error → 下载（设备树两条通道已补齐 64..95 的 Value）。
- **0.68 上线事故与修复（2026-09-12）**：0.68 把镜像扩到 96W，但 Modbus TCP 从站参数 `MODBUSCHANNELSET` 的 `ReadRegLeg/WriteRegLeg` 仍是 **64**（0.67 遗留，agent 漏改）→ 状态输出区只发布 64 字，`MB_StatusOut[95]` 读回 0 → 网关 `seq==tail` 校验失败 → 判离线，webHMI 连不上。
  - 立即修复（无需重烧）：`modbus-codec.validateImage` 在尾序号字为 0（未映射）时跳过 `SEQUENCE_MISMATCH`；**更新网关并重启**即恢复。
  - 根治：`tools/patch_g069.py` 由 0.68 生成 **`LMM_g_0.69.xml`**（两条通道 Leg 64→96，sha `6201f685…`，幂等），导入后状态尾部恢复发布。
  - 验证：真机 `/health` → `connected:true, statusIsOffline:false, lastValidStatusAgeMs:28, errorCount:0`；`npm test` 44 PASS。
  - 设计：`docs/superpowers/specs/2026-09-12-vision-axis-control-design.md`（含 Gate C 写者矩阵）；接口：`docs/plc/VISION_AXIS_API.md`。
- **现场定稿 0.67（2026-09-12）**：`LMM_g_0.67.xml` 由 PLC 导出，POU 与 0.66 完全一致；
  设备树 TCP 从站为 `Type 40502 ModbusTcpSlave`（Port 502, UnitID 255），Channel 01 input `16#1000..103F`→`%IW103`(MB_CmdIn)、
  Channel 02 output `16#1100..113F`→`%QW44`(MB_StatusOut)。**WebHMI 自动/手动实控验证通过**，报警 1007/1005 不再出现。

## Locked decisions
- Modbus 角色维持 **Gateway 主站 / PLC 从站**（现场 Modbus client 连 `:502` 验证）
- Web 急停仍为**请求**；物理急停 AND 仲裁不变（非安全等级）
- 速度透传先 Web、后 PLC 0.63；命令区与浏览器 WS/JSON 契约不变
- `Axis_Control` 独立任务、仅 GVL 交换，未改动

## Paths
- `web/live/index.html`, `gateway/`, `config/modbus-map.json`, `docs/plc/MODBUS_MAP.md`, `LMM_g_0.63.xml`, `tools/patch_g063.py`
