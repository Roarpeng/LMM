# FB_TCPServer — 按手册场景 1 改写

> 权威：`19011700-SC_A08《中型PLC指令手册》`  
> **6.1 自由 TCP** · 样例「AC702 做 TCP 服务器，将接收到数据按原路回传」  
> 库：`cmphctcpip` / `SktTCP*`（**不要**用带指针的旧 `TCP_Server`）

本 FB 对外仍提供 HMI 桥接口（`i_xEnable` / `i_uiPort` / 收发 STRING）；**内部状态机与手册样例一致**，收发改为业务 JSON，而非 echo。

## 状态机（与手册 `status` 一致）

| status | 含义 | 动作 |
|--------|------|------|
| 1 | 参数初始化 | `strIPAddr:='0.0.0.0'`，`uiPort:=i_uiPort`，`diConnectID:=1` → 2 |
| 2 | 创建 Server | `SktTCPServer(xExecute:=TRUE)`；`xDone`→3；`xError`→255 |
| 3 | 收发 + 状态检测 | `SktTCPGetStatus` 须 `eStatus=TCP_ESTABLISHED`；`SktTCPRecv`；按需 `SktTCPSend` |
| 4 | 关闭 | `SktClose`；`xDone`→255 |
| 255 | 复位 | 全部 FB 失能；若仍使能则回到 1 等待下一客户端 |

使能：`i_xEnable` 上升沿 → `status:=1`；下降沿且在 3 → `status:=4`（手册 R_TRIG / F_TRIG）。

## 样例关键钉（必须遵守）

```iecst
(* 已连接后：Recv/Send/GetStatus/Close 一律用 stConnectInfo.diConnectID *)
SktTCPGetStatus(xEnable:=TRUE, diConnectID:=stConnectInfo.diConnectID, ...);
IF eStatus <> TCP_STATUS.TCP_ESTABLISHED THEN (* → 关连接 *) END_IF;

SktTCPRecv(
    xEnable := TRUE,
    diConnectID := stConnectInfo.diConnectID,
    abyData := DataBuffer[1],   (* ARRAY[1..8192] OF BYTE *)
    uiDataSize := 0);           (* 0=标准模式，非定长 *)

SktTCPSend(
    xExecute := ...,
    diConnectID := stConnectInfo.diConnectID,
    abyData := DataBuffer[1],
    uiDataSize := uiCount,
    uiTimeOut := 500);
IF SktTCPSend.xDone THEN
    SktTCPSend(xExecute := FALSE);
END_IF;
```

- **已连接** ≠ `SktTCPServer.xBusy`（Busy=仍在等客户端）。  
- `TCP_ESTABLISHED` 枚举值手册为 **INT=1**。  
- 端口合法范围 **2000~65536**（本机默认 `9100`）。

## 对外销（给 PRG_TcpHmi）

| 方向 | 符号 | 说明 |
|------|------|------|
| IN | `i_xEnable` | 对应样例 `start_tcp_communication` |
| IN | `i_uiPort` | 写入 `ADDRESS.uiPort` |
| IN | `i_xSendTrig` / `i_strSend` | 触发发送 JSON 行（写入 `DataBuffer`） |
| OUT | `o_xConnected` | `GetStatus.eStatus = TCP_ESTABLISHED` |
| OUT | `o_xRecvNew` / `o_strRecv` / `o_uiRecvLen` | Recv.`xReady` 当拍；BYTE→STRING（至 LF） |
| OUT | `o_xSendDone` / `o_xError` / `o_wErrorID` | 发送完成 / 错 |

## 与手册 echo 样例的差异（有意）

手册 status=3 在 `xReady` 时 **原路 Send**；本机改为：

- `xReady` → 拼 `o_strRecv`（给 JSON 解析）  
- `i_xSendTrig` → 把 `i_strSend` 写入缓冲再 Send  

状态机、引脚、`uiDataSize:=0`、`stConnectInfo.diConnectID`、Close/复位流程与手册相同。

## 编译注意

- 类型 F2：`ADDRESS` / `CONNECT_ID` / `CONNECT_INFO` / `TCP_STATUS` 以本机库为准；样例写 `CmpHCTCPIP.*`。  
- `abyData:=DataBuffer[1]` 为手册写法；若报 AnyType，再对 F2 核对，勿改回定长 512。  
- `JMP RUN_RND` 样例用于跳过同扫描后续；本实现用 `IF/ELSIF` 等价，无 JMP。
