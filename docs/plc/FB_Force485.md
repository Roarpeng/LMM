# FB_Force485 — LE 拉压传感器 Modbus-RTU 主站

> 说明书：`LE系列拉压传感器说明书P150000122-1.0.1.pdf`  
> RS485 · 115200 8N1 · FC03/06 · CRC16/Modbus 低字节在前

## 外部接口

| 针脚 | 方向 | 含义 |
|------|------|------|
| `i_xEnable` | IN | 使能通讯 |
| `i_bySlave` | IN | 站号 1–250（默认 1） |
| `i_rScale` | IN | 原始值→工程量倍率（默认 0.01＝百分位） |
| `i_xTare` | IN | 上升沿去皮（写 `0x11=1`） |
| `i_tTimeout` | IN | 单次应答超时（默认 `T#200MS`） |
| `i_tPoll` | IN | 轮询间隔（默认 `T#20MS`） |
| `i_abyRx` / `i_uiRxLen` / `i_xRxNew` | IN | 串口收缓冲（由 PRG 串口层填入） |
| `o_abyTx` / `o_uiTxLen` / `o_xTxReq` | OUT | 待发帧；`o_xTxReq` 脉冲=1 周期 |
| `o_rForce` | OUT | 力值（N，已×scale） |
| `o_iRaw` | OUT | INT16 原始寄存器 |
| `o_xOk` | OUT | 近期通讯成功 |
| `o_xTimeout` | OUT | 连续失败超限 |
| `o_iState` | OUT | 状态机步号（诊断） |

## 状态机

| 步 | 动作 |
|----|------|
| 0 | 空闲 / 未使能 |
| 1 | 发 FC06 写单位寄存器 `0x02=5`（N） |
| 2 | 等写应答或超时 |
| 3 | 发 FC03 读 `0x0000` qty=1 |
| 4 | 等读应答；成功→解析 INT16→`o_rForce`；再等 `i_tPoll` 回步 3 |
| 5 | 去皮写 `0x11=1`（插入，完成后回轮询） |

连续超时 ≥3 次 → `o_xTimeout:=TRUE`；成功一次清超时。

## 示例帧（站号=1）

| 用途 | 报文 |
|------|------|
| 读力 | `01 03 00 00 00 01 84 0A` |
| 写单位 N | `01 06 00 02 00 05 E8 09` |
| 去皮 | `01 06 00 11 00 01 18 0F` |

读应答：`01 03 02 Hi Lo CRClo CRChi` → `o_iRaw := INT(SHL(Hi,8) OR Lo)`（有符号）。

## 编译适配（汇川 / CoDeSys ST）

| 错误写法 | 正确写法 | 说明 |
|----------|----------|------|
| `XOR(a, b)` | `a XOR b` | XOR 是 **中缀运算符**，不是函数 |
| `WORD_TO_BYTE(w)` | `INT_TO_BYTE(WORD_TO_INT(w AND 16#FF))` | 用标准转换链 |
| `BYTE_TO_DINT(b)` | `DWORD_TO_DINT(BYTE_TO_DWORD(b))` | 用标准 DWORD 链 |
| 声明 `POINTER TO BYTE` | 本 FB **不用指针** | 缓冲走 ARRAY 针脚 |

CRC 核心：

```iecst
wCrc := wCrc XOR BYTE_TO_WORD(o_abyTx[i]);
IF (wCrc AND 16#0001) <> 0 THEN
    wCrc := SHR(wCrc, 1) XOR WORD#16#A001;
ELSE
    wCrc := SHR(wCrc, 1);
END_IF;
```

## 不做

- 持续推送指令 `qty=0`（易粘包）
- 改站号 / 采样率（现场用上位机改一次即可）
