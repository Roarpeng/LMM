# Gateway 主站 → PLC 从站 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 把 Gateway 从本机 Modbus TCP Server 改为 Modbus TCP **主站**，主动连接 PLC 从站 `192.168.1.88:502`；地址表与 Web 契约不变。

**Architecture:** `modbus-serial` Client：周期 FC16@1000 写命令、FC03@1100 读状态；`createModbusStore` 增加主站用的 `getCommandWords`/`ingestStatusWords`；生产 mode 名改为 `modbus-master`。

**Tech Stack:** Node.js、`modbus-serial`、`ws`、`node:test`

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-25-gateway-modbus-master-plc-slave-design.md`
- PLC 从站默认 `192.168.1.88:502` unit=`1`
- Holding `1000..1063` / `1100..1163` 各 64 WORD 不变
- 浏览器 WS 契约不变；仅 `MOCK_PLC=1` 用 Mock
- 不改轴运动/力控；中文文档写「主站/从站」，避免 Gateway=Server 易混说法
- 除非用户要求，不 git commit

## File map

| File | Role |
|------|------|
| `gateway/lib/modbus-store.js` | 命令/状态镜像；加主站读写 API，保留 vector 供单测假从站 |
| `gateway/lib/modbus-master.js` | **新建** 主站轮询（connect/write/read/reconnect） |
| `gateway/server.js` | 生产模式改挂主站；env=`PLC_HOST/PORT/UNIT_ID` |
| `gateway/test/gateway-mode.test.js` | mode 字符串断言 |
| `gateway/test/gateway-behavior.test.js` | 生产测：本地假从站 + Gateway 主站 |
| `tools/start-webhmi.ps1` | 默认连 PLC；去掉本机听 502 |
| `docs/plc/TCP_HMI.md` `WEB_PLC_ALIGN.md` `gateway/README.md` | 角色对调文档 |
| `plc/src/PRG_TcpHmi.st` | 注释改为从站语义 |

---

### Task 1: Store 主站 API + mode 名

**Files:** Modify `gateway/lib/modbus-store.js`, `gateway/server.js` (`resolveGatewayMode`), `gateway/test/gateway-mode.test.js`

- [ ] **Step 1:** 失败测试 — `resolveGatewayMode({})` 期望 `modbus-master`（改 `gateway-mode.test.js`）
- [ ] **Step 2:** 实现 `resolveGatewayMode` 返回 `modbus-master`；store 增加：

```js
getCommandWords() { return Uint16Array.from(commandWords); }
ingestStatusWords(values) {
  // 与 vector.setRegisterArray 相同校验/解码，成功则 onStatus
}
```

- [ ] **Step 3:** `npm test` 中 mode 相关通过；全量尽量绿

---

### Task 2: Modbus 主站轮询模块 + server 接入

**Files:** Create `gateway/lib/modbus-master.js`; Modify `gateway/server.js`

- [ ] **Step 1:** 实现 `createModbusMaster({ host, port, unitID, store, pollMs, onError })`：
  - `connectTCP` → `setID` → 循环：`writeRegisters(1000, words)` → `readHoldingRegisters(1100, 64)` → `store.ingestStatusWords`
  - 失败不抛崩进程；记录错误；由现有 `STATUS_TIMEOUT_MS` 变 offline
  - `close()` 停定时器并关连接
- [ ] **Step 2:** `startGateway` 生产分支：不再 `ServerTCP`；启动 master，默认 `PLC_HOST=192.168.1.88` `PLC_PORT=502` `PLC_UNIT_ID=1`；兼容旧 `MODBUS_HOST/PORT` 若设则作为 PLC 目标别名
- [ ] **Step 3:** 行为测试：起本地 `ServerTCP` 假从站（vector 存 cmd/status），Gateway `MOCK_PLC=0` 连它；Web 写后假从站 cmd 区变化；假从站 status FC03 数据被 ingest

---

### Task 3: 启动脚本 + 文档 + ST 注释

**Files:** `tools/start-webhmi.ps1`, docs, `plc/src/PRG_TcpHmi.st` 头注释；必要时 `inject` 说明

- [ ] **Step 1:** 脚本：`-PlcHost` 默认 `192.168.1.88`；设 `PLC_*`；日志写「主站→从站」；本机不听 502
- [ ] **Step 2:** 更新 TCP_HMI / WEB_PLC_ALIGN / gateway README
- [ ] **Step 3:** `PRG_TcpHmi.st` 注释改为 PLC=从站；设备树改从站的操作步骤写入 TCP_HMI「现场联调」（InoProShop 手工项列出清单）

---

## Spec coverage

| Spec | Task |
|------|------|
| Gateway 主站连 192.168.1.88:502 | 2–3 |
| FC16@1000 / FC03@1100 | 2 |
| map/WS 不变 | 1–2 |
| Mock / 文档主站从站表述 | 2–3 |
| PLC 设备树从站 | Task 3 文档清单（XML 全自动改组态若风险高则手工步骤） |
