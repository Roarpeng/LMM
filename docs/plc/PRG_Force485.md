# PRG_Force485 — 力传感独立任务

> **独立任务 `ForceTask`**（建议 20ms）运行本程序。  
> **禁止** Main / Logic / Axis `CALL` 本程序；仅经 GVL 交换。

## 职责

1. 调用 `FB_Force485`（协议状态机）
2. 串口收发适配：把 `o_abyTx` 发出，把收到的字节填入 `i_abyRx`
3. 当 `NOT HMI_xForceSimEnable` 时写 `rForceAct := o_rForce`
4. 写 `Force_xCommOk` / `Force_xTimeout` / `Force_iRaw` / `Force_iState`

## GVL 绑定

| 符号 | 写者 | 说明 |
|------|------|------|
| `Force_bySlave` | 常量/HMI | 默认 1 |
| `Force_rScale` | 常量 | 默认 0.01 |
| `Force_xEnable` | 常量/Logic | 默认 TRUE |
| `HMI_xForceTare` | HMI/TCP | 脉冲去皮（可选） |
| `Force_xCommOk` | 本程序 | 通讯 OK |
| `Force_xTimeout` | 本程序 | 超时 |
| `Force_iRaw` / `Force_iState` | 本程序 | 诊断 |
| `rForceAct` | 本程序（非模拟时） | 实际力 N |

## 串口适配（二选一）

### A（推荐联调）SoftComm / 设备树串口

InoProShop：串口 115200 8N1，无校验。  
用小段 ST 或 SoftComm「自由协议」：

- `Force_xTxReq` 上升沿 → 发送 `Force_abyTx[0 .. Force_uiTxLen-1]`
- 收到完整应答 → 写入 `Force_abyRx`、`Force_uiRxLen`、置 `Force_xRxNew` 一拍

本程序已把 FB 的 Tx/Rx 与上述 GVL 数组对接。

示例（串口层伪代码，按本机 COM FB 改）：

```iecst
(* 在 ForceTask 同任务、PRG_Force485 之后，或独立 COM 程序 *)
IF Force_xTxReq AND NOT xTxPrev THEN
    (* COM_SEND(Force_abyTx, Force_uiTxLen) *)
END_IF;
xTxPrev := Force_xTxReq;
(* 当 COM 收满一帧 *)
(* Force_abyRx := ...; Force_uiRxLen := n; Force_xRxNew := TRUE; *)
```

### B SysCom（CAA SerialCom）

若工程已加 SysCom 库，可在本程序「串口区」按 F2 改 `SysComOpen/Write/Read` 成员名（见 [IMPORT_LMM_XML.md](IMPORT_LMM_XML.md)）。默认交付用 **A：GVL 缓冲**，保证无 SysCom 也能编译协议层。

## 任务配置（InoProShop）

| 任务 | 程序 | 周期 |
|------|------|------|
| ForceTask | `PRG_Force485` | 10–20 ms |

与 `AxisTask` 同级独立；不要放进 `PLC_PRG`。
