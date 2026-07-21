# TCP_HMI — WebHMI ↔ PLC 通讯契约

> 权威符号：`LMM.xml` GVL 中的 `HMI_*`。  
> 架构：浏览器 WebSocket ↔ `gateway/` ↔ TCP JSON Lines ↔ PLC Server `:9100`。  
> Socket 实现：手册 **场景 1**（`SktTCPServer` 状态机）→ [FB_TCPServer.md](FB_TCPServer.md)

## 连接

| 项 | 值 |
|----|-----|
| PLC 角色 | TCP Server（手册场景 1） |
| 端口 | `9100`（合法 2000~65536） |
| 绑定 IP | `0.0.0.0`（双网口均可连） |
| 帧 | 一行一个 JSON，`\n` 结尾（UTF-8） |
| Recv | `uiDataSize:=0` 标准模式；`abyData:=DataBuffer[1]` |
| 已连接 | `SktTCPGetStatus.eStatus = TCP_ESTABLISHED`（≠ Server.xBusy） |
| 写节流 | ≥50ms 或变位 |
| 状态周期 | ~100ms |
| 超时 | 500ms 无 `w`/`ping` → 清 Tcp 侧 BOOL；`Tcp_xEStop:=TRUE` |

## 写白名单 `t:"w"`（→ `Tcp_*` 影子，再由 Logic 合成到 `HMI_*`）

安全：`HMI_xEStop` `HMI_xStop` `HMI_xStopHold3s` `HMI_xStart` `HMI_xEnable`  
模式：`HMI_xAutoMode`  
手动：`HMI_xJogXPos/Neg` `HMI_xSpinLeft/Right` `HMI_xJogY/Z/R Pos/Neg`  
速度：`HMI_rJogVelX` `HMI_rSpinVel` `HMI_rJogVelY/Z/R`  
自动：`HMI_xAutoStart/Abort` `HMI_rAutoDistX` `HMI_rAutoVelX/Y/Z` `HMI_rWheelBase` `HMI_rForceSet` `HMI_xForceSimEnable` `HMI_rForceSim` `HMI_xForceTare` `HMI_xForceUntare`

禁止写：`AxisCmd_*` / `eDevState` / `iAutoStep` / 已删旧符号。

## 读白名单 `t:"s"`（PLC → 网关）

`HMI_eDevState` `HMI_xDevStop/Run/Error` `HMI_eOpMode`  
`HMI_xLampEStop/EnableOk/Fault` `HMI_iAlarmShow`  
`HMI_iAutoStepShow` `HMI_xAutoBusy/Done` `HMI_rForceShow`  
可选：`Force_xCommOk` `Force_xTareBusy` `Force_xTareDone`  
可选：`AxisFb_rPosY/Z/R` `AxisFb_xReady` `AxisFb_xFault*` `AxisFb_xMoveDoneX/Y`  
链路：`Tcp_xConnected` `Tcp_xTimeout`

## 面板 ∨ TCP 合成（PRG_Logic）

| 规则 | 公式 |
|------|------|
| 急停 | `HMI_xEStop := EStop AND Tcp_xEStop` |
| 其它 BOOL request | `HMI_* := Panel_* OR Tcp_*` |
| REAL | `Tcp_xOnline` 时用 `Tcp_r*`；离线时面板 `JogVel` → `HMI_rJogVelX/Y/Z` |

`Tcp_xEStop` 上电默认 TRUE。

## 心跳

```json
{"t":"ping"}
{"t":"pong"}
{"t":"err","code":1,"msg":"parse"}
```

## 程序

| POU | 职责 |
|-----|------|
| `FB_TCPServer` | 手册场景 1：`SktTCPServer`→`GetStatus`→`Recv/Send`→`SktClose` |
| `PRG_TcpHmi` | 收 `w`→Tcp_*、发 `s`、超时清 JOG |
| `PRG_Logic` | 面板∨Tcp → HMI_* |
| `PLC_PRG` | `PRG_TcpHmi(); PRG_Logic();` |

## 现场联调（对照手册）

1. 下载工程，`i_xEnable` 保持 TRUE → status 1→2，等待客户端。  
2. 网关或网络调试助手连 `PLC_IP:9100`。  
3. Server.`xDone` 后 GetStatus=`TCP_ESTABLISHED`，再收发 JSON。  
4. 客户端断开 → status 4→255→1，自动再听。  
5. 库类型以 F2 为准；枚举路径可能是 `CmpHCTCPIP.TCP_STATUS.TCP_ESTABLISHED`。
