# WebHMI 真机调试台收尾 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 `docs/superpowers/specs/2026-07-25-webhmi-debug-console-design.md` 收尾：补齐 `HMI_xDevStop/Run/Error` 露出、保证 modbus-map 全字段覆盖，并用 Mock + 单测验收一键调试台可用。

**Architecture:** 不改 Gateway/PLC 通讯栈。仅改 `web/live/index.html` 状态绑定，并在 `gateway/test/web-client.test.js` 加覆盖率回归。冒烟用 `tools/start-webhmi.ps1 -Mock`（或 `npm start`）。

**Tech Stack:** 静态 HTML/JS、Node.js `node:test`、Gateway Mock PLC、PowerShell 启动脚本。

## Global Constraints

- Spec：`docs/superpowers/specs/2026-07-25-webhmi-debug-console-design.md`
- 不改 PLC 运动逻辑；不扩展 `Cfg_rLim*`
- 协议头字段不要求页面露出：`magic` / `version` / `sequence` / `heartbeat` / `tailSequence`
- 保留现有未提交改动；不 `reset`/`checkout`；**除非用户明确要求，否则不 git commit**
- 真机验收依赖现场 PLC Master 指向本机 `:502`；本计划以 Mock 冒烟为主

## File map

| File | Responsibility |
|------|----------------|
| `web/live/index.html` | 调试台 UI + WS 写命令/读状态；本计划补 DevStop/Run/Error 绑定 |
| `gateway/test/web-client.test.js` | 页面契约静态测试；本计划加 map 覆盖 + Dev* 字段断言 |
| `tools/start-webhmi.ps1` | 一键启动（已有，仅验收） |
| `config/modbus-map.json` | 覆盖率真源（只读对照，不改） |
| `gateway/lib/mock-plc.js` | 已输出 `HMI_xDev*` 与 VelCmd（只读对照，不改除非冒烟失败） |

---

### Task 1: 失败测试 — Dev* 字段与 map 全覆盖

**Files:**
- Modify: `gateway/test/web-client.test.js`
- Test: `gateway/test/web-client.test.js`

**Interfaces:**
- Consumes: `config/modbus-map.json` → `command.fields[].name`, `status.fields[].name`
- Consumes: `web/live/index.html` 全文
- Produces: 两个新 `test(...)` 用例（静态字符串断言）

- [ ] **Step 1: 在 `web-client.test.js` 末尾追加失败测试**

```js
test('status pills bind HMI_xDevStop / HMI_xDevRun / HMI_xDevError by name', () => {
  assert.match(html, /HMI_xDevStop/);
  assert.match(html, /HMI_xDevRun/);
  assert.match(html, /HMI_xDevError/);
  assert.match(html, /msg\.HMI_xDevStop/);
  assert.match(html, /msg\.HMI_xDevRun/);
  assert.match(html, /msg\.HMI_xDevError/);
});

test('live page mentions every modbus-map command and status field name', () => {
  const map = JSON.parse(
    fs.readFileSync(path.join(__dirname, '..', '..', 'config', 'modbus-map.json'), 'utf8'),
  );
  const missing = [];
  for (const f of map.command.fields) {
    if (!html.includes(f.name)) missing.push('cmd:' + f.name);
  }
  for (const f of map.status.fields) {
    if (!html.includes(f.name)) missing.push('st:' + f.name);
  }
  assert.deepEqual(missing, [], 'missing map fields in web/live/index.html:\n' + missing.join('\n'));
});
```

- [ ] **Step 2: 跑测试确认失败**

Run:

```powershell
cd z:\Share\LMM\gateway
npm test
```

Expected: FAIL — `status pills bind HMI_xDevStop...` 和/或 map 覆盖测试报 `st:HMI_xDevStop` 等。

- [ ] **Step 3: 不提交**（除非用户要求）

---

### Task 2: 实现 Dev* 绑定并让测试通过

**Files:**
- Modify: `web/live/index.html`（`S` 初始、`ingestStatus`、`render`/`lamp-*` 更新处）
- Test: `gateway/test/web-client.test.js`

**Interfaces:**
- Consumes: status JSON 字段 `HMI_xDevStop:boolean`, `HMI_xDevRun:boolean`, `HMI_xDevError:boolean`（Mock 已发）
- Produces: pills `#lamp-stop` / `#lamp-run` / `#lamp-err` 由上述 BOOL 驱动；`#fb-dev` 行同时显示三字段名

- [ ] **Step 1: 在 `S` 初始对象中增加三项**

在 `eDevState: 0, eOpMode: 0, ...` 附近加入：

```js
devStop: true, devRun: false, devError: false,
```

- [ ] **Step 2: 在 `ingestStatus` 中写入**

紧接 `S.eDevState = msg.HMI_eDevState ?? S.eDevState;` 之后：

```js
S.devStop = !!msg.HMI_xDevStop;
S.devRun = !!msg.HMI_xDevRun;
S.devError = !!msg.HMI_xDevError;
```

（字段名字符串必须字面出现，供覆盖率测试匹配。）

- [ ] **Step 3: 改 lamp 渲染，优先用 Dev* BOOL**

将：

```js
const stop = S.eDevState === 0, run = S.eDevState === 1, err = S.eDevState === 2;
$('lamp-stop').className = 'pill' + (stop ? ' on ok' : '');
$('lamp-run').className = 'pill' + (run ? ' on ok' : '');
$('lamp-err').className = 'pill' + (err ? ' on bad' : '');
```

替换为：

```js
const stop = S.devStop, run = S.devRun, err = S.devError;
$('lamp-stop').textContent = 'HMI_xDevStop=' + (stop ? 'T' : 'F');
$('lamp-stop').className = 'pill' + (stop ? ' on ok' : '');
$('lamp-run').textContent = 'HMI_xDevRun=' + (run ? 'T' : 'F');
$('lamp-run').className = 'pill' + (run ? ' on ok' : '');
$('lamp-err').textContent = 'HMI_xDevError=' + (err ? 'T' : 'F');
$('lamp-err').className = 'pill' + (err ? ' on bad' : '');
```

- [ ] **Step 4: `#fb-dev` 行带上字段名（双保险，便于肉眼验收）**

将 `$('fb-dev').textContent = ...` 改为：

```js
$('fb-dev').textContent =
  'eDev=' + S.eDevState +
  ' Stop=' + (S.devStop ? 'T' : 'F') +
  ' Run=' + (S.devRun ? 'T' : 'F') +
  ' Err=' + (S.devError ? 'T' : 'F') +
  ' / ' + (S.eOpMode ? 'AUTO' : 'MAN');
```

（`HMI_xDev*` 已在 lamp `textContent` 与 `msg.HMI_xDev*` 中出现即可满足 map 测试；若 map 测试仍缺，确认 Step 2 的 `msg.HMI_xDev*` 字面量在文件中。）

- [ ] **Step 5: 跑测试确认通过**

Run:

```powershell
cd z:\Share\LMM\gateway
npm test
```

Expected: 全部 PASS（含两个新用例）。

- [ ] **Step 6: 不提交**（除非用户要求）

---

### Task 3: Mock 冒烟验收 + 文档对齐

**Files:**
- Verify: `tools/start-webhmi.ps1`
- Verify: `gateway/README.md`、`docs/plc/WEB_PLC_ALIGN.md`（已有一键启动说明则只核对，无过时内容则不改）
- Optional Modify: `docs/plc/WEB_PLC_ALIGN.md` — 仅当缺少「调试台 / `-Mock`」一句时补一行

**Interfaces:**
- Consumes: Mock 模式下点动写 `HMI_xJogXPos` → `AxisFb_rVelCmdM1/M2`、`AxisFb_rPosM1/M2` 变化
- Produces: 书面验收记录（本任务结束时在回复中列出勾选结果）

- [ ] **Step 1: Mock 启动（后台）**

```powershell
cd z:\Share\LMM
.\tools\start-webhmi.ps1 -Mock -NoBrowser
```

Expected 控制台含：`mode=MOCK`、`open http://127.0.0.1:8080/`。

- [ ] **Step 2: HTTP/WS 可达性检查**

```powershell
Invoke-WebRequest -Uri http://127.0.0.1:8080/ -UseBasicParsing | Select-Object StatusCode, @{n='HasDevStop';e={$_.Content -match 'HMI_xDevStop'}}
```

Expected: `StatusCode=200`，`HasDevStop=True`。

- [ ] **Step 3: 可选 — 用短 Node 脚本确认 Mock 点动改 VelCmd**

若环境不便开浏览器，在仓库根执行：

```powershell
cd z:\Share\LMM\gateway
node -e "const {createMockPlc}=require('./lib/mock-plc'); const m=createMockPlc(); m.onCommand({HMI_xEStop:true,HMI_xJogXPos:true,HMI_rJogVelX:0.4,HMI_rKpTrack:0,HMI_rHeadingErr:0}); const s=m.tick(0.1); console.log(s.AxisFb_rVelCmdM1,s.AxisFb_rVelCmdM2,s.HMI_xDevRun);"
```

（若 `createMockPlc` / `onCommand` / `tick` 导出名不同，先 `Read` `gateway/lib/mock-plc.js` 顶部 exports，再改调用；目标：VelCmd 非 0 且 `HMI_xDevRun===true`。）

- [ ] **Step 4: 停掉 Mock Gateway（Ctrl+C 或结束对应 node 进程）**

- [ ] **Step 5: 文档核对**

确认以下任一处写明一键启动（已有则不动）：

- `gateway/README.md`：`.\tools\start-webhmi.ps1`
- `docs/plc/WEB_PLC_ALIGN.md`：同上

若缺失，在 `WEB_PLC_ALIGN.md`「通讯」表追加一行：`调试冒烟 | .\tools\start-webhmi.ps1 -Mock`。

- [ ] **Step 6: Spec 验收清单自检（回复用户时勾选）**

- [ ] 脚本可启动并打开/服务页面  
- [ ] map command/status 字段全露出（测试绿）  
- [ ] Mock 下 VelCmd/Pos/Dev* 有更新路径  
- [ ] `npm test` 绿  

- [ ] **Step 7: 不提交**（除非用户要求）

---

## Spec coverage (self-review)

| Spec 项 | Task |
|---------|------|
| 一键启动 | Task 3 |
| Acc/Dec、Kp*、ForceGuide、X 双驱监视 | 已在现有 `index.html`；Task 1 map 覆盖锁定不回退 |
| `HMI_xDevStop/Run/Error` 显式露出 | Task 1–2 |
| 不改 PLC / 不扩限位 | Global Constraints |
| Mock 冒烟 + `npm test` | Task 2–3 |

无 TBD。Commit 步骤刻意省略（用户规则优先）。
