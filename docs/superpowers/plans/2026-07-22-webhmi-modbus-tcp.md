# WebHMI Modbus TCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 保持WebSocket/JSON页面契约，将PLC与Gateway之间的自定义TCP/JSON替换为“PLC Modbus TCP Master → Gateway Modbus TCP Server”的64 WORD双快照通讯。

**Architecture:** Gateway在 `192.168.1.1:502` 提供Holding Register；命令区1000由Gateway维护、PLC以FC03读入，状态区1100由PLC以FC16写回。PLC的 `PRG_TcpHmi` 只负责过程映像编解码、心跳和 `Tcp_*` 仲裁，不直接控制轴。

**Tech Stack:** InoProShop PLCopen XML、IEC 61131-3 ST、Node.js CommonJS、`modbus-serial`、Node内置 `node:test`、Python XML生成/验证。

## Global Constraints

- 保留用户当前所有未提交改动，不执行reset/checkout，不创建提交。
- 保留3-POU边界：`PRG_Axis_Control`独立任务；`PRG_TcpHmi`与`PRG_Logic`在MainTask。
- PLC是Modbus TCP Master，Gateway是Server；复用更新后XML的 `MODBUS_TCP/modbusTcp` 节点和GUID。
- 命令区Holding Register `1000..1063`，PLC FC03输入映像 `%IW103..%IW166`。
- 状态区Holding Register `1100..1163`，PLC FC16输出映像 `%QW44..%QW107`。
- 两区均为64 WORD；首尾序号必须相等；主版本不兼容时拒绝命令。
- BOOL打包为WORD位域；连续量使用高字在前的有符号缩放DINT。
- 位置、速度、距离、增益、航向误差缩放1000；力缩放100。
- 超过1秒心跳不变化：清动作命令、远程停止/中止并释放远程控制源。
- 生产模式断线不自动切换Mock；只有显式 `MOCK_PLC=1` 才运行Mock。
- 物理急停是唯一安全急停，Web停止不宣称安全等级。

---

### Task 1: 协议映射与编解码

**Files:**
- Create: `config/modbus-map.json`
- Create: `gateway/lib/modbus-codec.js`
- Create: `gateway/test/modbus-codec.test.js`
- Create: `tools/generate_modbus_map.py`
- Create: `docs/plc/MODBUS_MAP.md`

**Interfaces:**
- Produces: `createCommandImage(values, sequence, heartbeat) -> Uint16Array(64)`
- Produces: `decodeStatusImage(words) -> { valid, values, diagnostics }`
- Produces: `encodeStatusImage(values, sequence, ack, heartbeat) -> Uint16Array(64)`
- Produces: `decodeCommandImage(words, previousSequence) -> { valid, isNew, values, diagnostics }`

- [ ] **Step 1: 写失败测试**

测试必须覆盖：64 WORD长度、魔数/版本、双序号、BOOL位域、缩放DINT正负数、错误版本、错误尾序号和心跳回绕。

```js
test('command image round-trips signed scaled values', () => {
  const words = createCommandImage(
    { HMI_xJogXPos: true, HMI_rJogVelX: -1.25, HMI_rForceSet: 123.45 },
    7,
    65535
  );
  const decoded = decodeCommandImage(words, 6);
  assert.equal(words.length, 64);
  assert.equal(decoded.valid, true);
  assert.equal(decoded.values.HMI_rJogVelX, -1.25);
  assert.equal(decoded.values.HMI_rForceSet, 123.45);
});
```

- [ ] **Step 2: 运行测试并确认因模块不存在而失败**

Run: `node --test gateway/test/modbus-codec.test.js`

- [ ] **Step 3: 实现最小编解码和单一映射文件**

命令布局固定为：0魔数、1版本、2首序号、3心跳、4/5位域、6回零轴、7自动次数、8起连续缩放DINT、63尾序号。状态布局固定为：0魔数、1版本、2首序号、3命令确认、4心跳回显、5通讯状态、6设备状态、7模式、8报警、9自动步骤、10/11状态位域、12起连续缩放DINT、63尾序号。

- [ ] **Step 4: 生成地址文档并运行测试**

Run: `python3 tools/generate_modbus_map.py && node --test gateway/test/modbus-codec.test.js`

Expected: 生成 `docs/plc/MODBUS_MAP.md`，测试全部通过。

### Task 2: Gateway Modbus TCP Server与WebSocket兼容

**Files:**
- Modify: `gateway/package.json`
- Modify: `gateway/package-lock.json`
- Create: `gateway/lib/modbus-store.js`
- Create: `gateway/lib/mock-plc.js`
- Create: `gateway/test/modbus-store.test.js`
- Create: `gateway/test/gateway-mode.test.js`
- Modify: `gateway/server.js`
- Modify: `gateway/README.md`

**Interfaces:**
- Consumes: Task 1 codec。
- Produces: `createModbusStore()`，支持FC03读取1000命令区、FC16写1100状态区。
- Produces: Gateway状态JSON，保持现有 `t:"s"` 和 `t:"w"` 契约。

- [ ] **Step 1: 安装当前最新版依赖**

Run: `cd gateway && npm install modbus-serial`

- [ ] **Step 2: 写失败测试**

测试要求：未知地址拒绝；1000区可读；1100区完整写入后才发布状态；Web写只更新白名单；非Mock模式断线不调用Mock。

```js
test('production mode never falls back to mock', () => {
  assert.equal(resolveGatewayMode({ MOCK_PLC: '0' }), 'modbus-server');
});
```

- [ ] **Step 3: 运行测试确认失败**

Run: `node --test gateway/test/modbus-store.test.js gateway/test/gateway-mode.test.js`

- [ ] **Step 4: 拆分Mock和寄存器存储并改写Server入口**

Gateway启动HTTP/WS和 `ModbusRTU.ServerTCP`。`t:"w"` 更新命令镜像及心跳；PLC写入完整状态区时解码并广播；`ping`只回复浏览器 `pong`。

- [ ] **Step 5: 运行Gateway测试和语法检查**

Run: `cd gateway && npm test && node --check server.js`

Expected: 全部通过，生产代码不再使用 `net.connect` 或端口9100。

### Task 3: PLC XML设备树与PRG_TcpHmi

**Files:**
- Create: `tools/refactor_modbus_hmi.py`
- Create: `tools/test_refactor_modbus_hmi.py`
- Modify: `LMM.xml`
- Modify: `docs/plc/GVL.md`
- Modify: `docs/plc/TCP_HMI.md`
- Modify: `docs/plc/HMI.md`

**Interfaces:**
- Consumes: Task 1布局。
- Produces: `MB_CmdIn AT %IW103 : ARRAY[0..63] OF WORD`
- Produces: `MB_StatusOut AT %QW44 : ARRAY[0..63] OF WORD`
- Produces: 重写后的 `PRG_TcpHmi`，继续写 `Tcp_*`，继续由 `PLC_PRG`先于Logic调用。

- [ ] **Step 1: 写失败的XML静态测试**

测试必须验证：两个设备树通道长度64；FC03偏移1000；FC16偏移1100；输入/输出数组上界63；新过程映像变量存在；旧 `FB_TCPServer` 类型、实例和对象树引用不存在；XML良构。

- [ ] **Step 2: 运行测试确认当前XML失败**

Run: `python3 -m unittest tools/test_refactor_modbus_hmi.py -v`

- [ ] **Step 3: 实现可重跑的XML重构脚本**

脚本只修改样例中的 `modbusTcp` 现有节点；重写 `PRG_TcpHmi`；添加GVL映像和诊断变量；删除 `FB_TCPServer`；不得重建用户设备树GUID。

PLC解码规则：

```iecst
dwValue := SHL(WORD_TO_DWORD(MB_CmdIn[i]), 16)
           OR WORD_TO_DWORD(MB_CmdIn[i + 1]);
rValue := DINT_TO_REAL(DWORD_TO_DINT(dwValue)) / rScale;
```

失联时将 `Tcp_xConnected`置FALSE、`Tcp_xTimeout`置TRUE，清点动/启动/回零并置停止和自动中止。

- [ ] **Step 4: 执行脚本并验证**

Run: `python3 tools/refactor_modbus_hmi.py && python3 -m unittest tools/test_refactor_modbus_hmi.py -v`

Expected: XML测试全部通过且脚本第二次运行不改变结果。

### Task 4: 集成验证与工作流同步

**Files:**
- Modify: `docs/plc/README.md`
- Modify: `docs/plc/WEB_PLC_ALIGN.md`
- Modify: `.equipment-workflow/state.md`

**Interfaces:**
- Consumes: Tasks 1–3全部产物。
- Produces: 可执行的InoProShop导入与现场联调清单。

- [ ] **Step 1: 更新通讯文档和Gate D检查项**

明确PLC Master、Gateway Server、IP `192.168.1.1`、端口502、Unit ID 1、过程映像起点核对和失联测试。

- [ ] **Step 2: 执行完整验证**

Run:

```bash
python3 tools/generate_modbus_map.py
python3 -m unittest tools/test_refactor_modbus_hmi.py -v
cd gateway && npm test && node --check server.js
cd .. && python3 -c "import xml.etree.ElementTree as ET; ET.parse('LMM.xml')"
```

- [ ] **Step 3: 检查需求覆盖和未提交差异**

Run: `git status --short && git diff --check`

Expected: 无空白错误；不包含用户已有文件的意外回退；不创建Git提交。
