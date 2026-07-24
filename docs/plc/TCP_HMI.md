# TCP_HMI — WebHMI ↔ PLC 通讯契约（Modbus TCP）

> 权威符号：`LMM.xml` GVL 中的 `HMI_*` / `Tcp_*` / `MB_*`。  
> 架构：浏览器 WebSocket/JSON ↔ `gateway/`（Modbus TCP **Server** `:502`）↔ PLC Modbus TCP **Master**。  
> 单一映射源：`config/modbus-map.json` → `docs/plc/MODBUS_MAP.md`

## 连接

| 项 | 值 |
|----|-----|
| PLC 角色 | Modbus TCP **Master**（设备树 `MODBUS_TCP` / `modbusTcp`） |
| Gateway 角色 | Modbus TCP **Server** |
| Gateway 绑定 | `0.0.0.0:502`（现场目标 IP `192.168.1.1`，与设备树 `IpAddr` 一致） |
| Unit ID | `1` |
| 命令区 | Holding `1000..1063`（PLC **FC03 读** → `MB_CmdIn AT %IW103`） |
| 状态区 | Holding `1100..1163`（PLC **FC16 写** → `MB_StatusOut AT %QW44`） |
| 快照长度 | 64 WORD；首尾序号必须相等 |
| REAL/连续量 | 有符号缩放 DINT，高字在前；位置/速度 scale=1000，力 scale=100 |
| 心跳 | Gateway 每次命令刷新递增；PLC 1s 无变化 → 超时 |
| 生产断线 | **禁止**自动切 Mock；仅 `MOCK_PLC=1` 启用 Mock |

## 写白名单（浏览器 `t:"w"` → Gateway 命令镜像）

与 `config/modbus-map.json` `command.fields` 一致。禁止写 `AxisCmd_*` / 设备派生状态。

## 读白名单（PLC 状态镜像 → Gateway → 浏览器 `t:"s"`）

与 `status.fields` 一致，含 `Tcp_xConnected` / `Tcp_xTimeout` / `Tcp_iCommStatus` / 轴位置与报警。

## 面板 ‖ 远程并行互斥（`PRG_TcpHmi`）

| 规则 | 行为 |
|------|------|
| 源选择 `eCtrlSrc` | GVL 变量；`0=面板/触摸屏` / `1=远程(Modbus)`；仅 PRG_TcpHmi 写 |
| 面板 Jog 键 | `eCtrlSrc=0` 时直接点动（Fwd/Bwd→X± Right/Left→Y± Up/Down→Z± Clock→R±） |
| TCP/Modbus 掉线 | 强制 `eCtrlSrc:=0`；清点动/启动/回零；置停止与自动中止 |
| `eCtrlSrc=1` | 整组 `HMI_* := Tcp_*` |
| 急停 | `HMI_xEStop := EStop AND Tcp_xEStop AND HMI_xEStopReq`（更严） |
| Web“急停” | **非安全等级**停止请求；物理急停才是安全急停 |

## 程序

| POU | 职责 |
|-----|------|
| `PRG_TcpHmi` | 解码 `MB_CmdIn`→`Tcp_*`；编码状态→`MB_StatusOut`；心跳；控制源仲裁 |
| `PRG_Logic` | 工艺/安全/自动（不解析通讯） |
| `PLC_PRG` | `PRG_TcpHmi(); PRG_Logic();` |
| ~~`FB_TCPServer`~~ | **已删除** |

## 现场联调

1. InoProShop：确认 `modbusTcp` 通道长度为 64，读 1000 / 写 1100。  
2. Gateway：`MOCK_PLC=0 MODBUS_HOST=0.0.0.0 MODBUS_PORT=502 npm run start:plc`  
3. 确认 PLC 主站目标 IP = Gateway 工业网口。  
4. 点动松开即停；拔网线 ≤1s 远程动作清零；恢复网络不自行运动。  
5. 面板在远程掉线后可接管。
