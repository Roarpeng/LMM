# gateway — LMM WebHMI

浏览器继续使用现有 **WebSocket/JSON** 契约。Gateway 在生产模式作为
**Modbus TCP 主站**，主动连接 PLC **从站**，周期：

- **FC16** 写命令镜像 Holding `4096..4159`（`0x1000`，现场从站映射字段为十六进制）
- **FC03** 读状态镜像 Holding `4352..4415`（`0x1100`）

## 启动

**真机联调（推荐一键）：**

```powershell
# 仓库根目录 — Gateway 主站 → PLC 从站 192.168.1.88:502
.\tools\start-webhmi.ps1
.\tools\start-webhmi.ps1 -PlcHost 192.168.1.88 -PlcPort 502
```

```bash
cd gateway
npm install
npm run start:plc   # 真机：主站连 PLC（默认 192.168.1.88:502）
npm start           # 仅本地 Mock（无 PLC）
```

打开：http://127.0.0.1:8080/

## 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `HTTP_PORT` / `WS_PORT` | 8080 | HTTP+WS |
| `PLC_HOST` | 192.168.1.88 | PLC 从站 IP |
| `PLC_PORT` | 502 | PLC Modbus TCP 端口 |
| `PLC_UNIT_ID` | 1 | Unit ID |
| `PLC_POLL_MS` | 50 | 主站轮询周期（越小越实时；现场可调） |
| `WRITER_LEASE_MS` | 1000 | 浏览器单写者租约超时 |
| `STATUS_TIMEOUT_MS` | 1000 | 最后有效状态后的离线判定 |
| `PLC_CMD_BASE` | 4096 | 现场对齐：命令区基址（=0x1000） |
| `PLC_STATUS_BASE` | 4352 | 现场对齐：状态区基址（=0x1100） |
| `MOCK_PLC` | 未设置 | 仅值为 `1` 时启用进程内模拟 PLC |

兼容：若未设 `PLC_HOST`/`PLC_PORT`，可读旧名 `MODBUS_HOST`/`MODBUS_PORT` 作为 **PLC 目标**（不再表示本机监听）。

浏览器消息仍为 `t:"w"` 写命令、`t:"s"` 收状态、`t:"ping"` /
`t:"pong"` 保活。寄存器映射见
[`config/modbus-map.json`](../config/modbus-map.json)。

首个有效 `t:"w"` 发送者获得独占写租约；其他浏览器写入会收到
`t:"err"`。所有者断线或租约超时会原子切换到安全命令。生产模式启动
时状态为离线；超过 `STATUS_TIMEOUT_MS` 无有效状态帧则重新发布离线。

## 诊断与实时性

- `GET /health`：模式、客户端数、写租约归属、在线判定、Modbus 主站诊断（连接/轮询/错误计数/最近成功）。
- WS 连接立即收到首帧 `t:"s"`，随后 `t:"hello"`（clientId/mode）；写租约变化广播 `t:"lease"`。
- 遥测为**每轮询周期整帧推送**（非浏览器轮询）；默认 50ms，端到端典型 50–120ms。WebHMI v2 用 rAF 合帧 + 变更 diff 渲染。
- Mock 冒烟：`cd gateway && node scripts/smoke-webhmi.js`（校验页面/health/map/WS 新字段）。

0.63 状态区新增（由 PLC `PRG_TcpHmi` 编码）：`AxisFb_rVelActM1/M2`（word32/34）、
`AxisFb_xMovingM1/M2` `AxisFb_xPoweredM1/M2` `AxisFb_xSyncWarn/Fault`（word36 位）、
`AxisFb_rSyncErr`（word37）。

## 安全 / 心跳（重要）

- 主站**每轮询周期单独推进命令镜像心跳**（`store.advanceHeartbeat()`），维持 PLC 侧 `tonHb` 看门狗在线；
  否则网页暂停写入 >1s 会被 PLC 判「远程超时」，`Tcp_*` 动作被清零（表现：点一下动一下就停）。
- 通信失效（页面断开/写入租约丢失）时 `safeguardCommands()` 置 `HMI_xStop=TRUE`、`HMI_xEStop=TRUE`：
  **停止但不锁存急停**，恢复后无需手动复位。
- PLC 侧 `xEStopLatched` 一旦锁存（历史/上电/物理急停）→ 报警 1001，所有轴被安全逻辑锁住：
  **松开物理急停 → 网页按一次「复位」**（`HMI_xStopHold3s` 上升沿）才能清锁存并使能。
- Web 急停仍是**请求**（非安全等级）；物理急停 AND 仲裁不变。
