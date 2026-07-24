# gateway — LMM WebHMI

浏览器继续使用现有 **WebSocket/JSON** 契约。Gateway 在生产模式作为
**Modbus TCP Server**，由 PLC Master 通过 FC03 读取 `1000..1063`
命令镜像、通过 FC16 写入 `1100..1163` 状态镜像。

## 启动

```bash
cd gateway
npm install
npm start          # 显式 MOCK_PLC=1，无 PLC 可测 web/live

# 生产模式（不会自动回退 Mock）：
MODBUS_HOST=0.0.0.0 MODBUS_PORT=502 npm run start:plc
```

打开：http://127.0.0.1:8080/

## 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `HTTP_PORT` / `WS_PORT` | 8080 | HTTP+WS |
| `MODBUS_HOST` | 0.0.0.0 | Modbus TCP监听地址 |
| `MODBUS_PORT` | 502 | Modbus TCP监听端口 |
| `MODBUS_UNIT_ID` | 1 | Modbus Unit ID |
| `WRITER_LEASE_MS` | 1000 | 浏览器单写者租约超时 |
| `STATUS_TIMEOUT_MS` | 1000 | 最后有效FC16后的离线判定时间 |
| `MOCK_PLC` | 未设置 | 仅值为 `1` 时启用进程内模拟 PLC |

浏览器消息仍为 `t:"w"` 写命令、`t:"s"` 收状态、`t:"ping"` /
`t:"pong"` 保活。寄存器映射见
[`config/modbus-map.json`](../config/modbus-map.json)。

首个有效 `t:"w"` 发送者获得独占写租约；其他浏览器写入会收到
`t:"err"`。所有者断线或租约超时会原子切换到安全命令。生产模式启动
时状态为离线，且最后一次有效完整 FC16（`1100` 起始、64 WORD）超过
1 秒后重新发布离线状态。FC06 和部分/偏移 FC16 均被拒绝。
