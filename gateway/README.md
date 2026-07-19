# gateway — LMM WebHMI

浏览器不能裸 TCP。本目录把 **WebSocket** 转成 PLC **TCP JSON Lines**（`:9100`）。

## 启动

```bash
cd gateway
npm install
npm start          # MOCK_PLC=1，无 PLC 可测 web/live
# 连真机：
PLC_HOST=192.168.1.10 MOCK_PLC=0 npm run start:plc
```

打开：http://127.0.0.1:8080/

## 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `HTTP_PORT` / `WS_PORT` | 8080 | HTTP+WS |
| `PLC_HOST` | 127.0.0.1 | PLC IP |
| `PLC_PORT` | 9100 | TCP |
| `MOCK_PLC` | start 脚本为 1 | 进程内模拟 PLC 状态机 |

协议见 [docs/plc/TCP_HMI.md](../docs/plc/TCP_HMI.md)。  
PLC Socket 按手册场景 1 实现，见 [docs/plc/FB_TCPServer.md](../docs/plc/FB_TCPServer.md)。
