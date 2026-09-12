# TCP_HMI — WebHMI ↔ PLC 通讯契约（Modbus TCP）

> 权威符号：`LMM.xml` GVL 中的 `HMI_*` / `Tcp_*` / `MB_*`。  
> 架构：浏览器 WebSocket/JSON ↔ `gateway/`（Modbus TCP **主站**）↔ PLC Modbus TCP **从站** `192.168.1.88:502`。  
> 单一映射源：`config/modbus-map.json` → `docs/plc/MODBUS_MAP.md`

## 连接

| 项 | 值 |
|----|-----|
| PLC 角色 | Modbus TCP **从站**（设备树监听，不主动连外） |
| Gateway 角色 | Modbus TCP **主站**（主动连 PLC） |
| PLC 从站地址 | 默认 `192.168.1.88:502`（`PLC_HOST` / `PLC_PORT`） |
| Unit ID | `1`（`PLC_UNIT_ID`） |
| 命令区 | Holding `4096..4159`（`0x1000`；Gateway **FC16 写** → PLC `MB_CmdIn`） |
| 状态区 | Holding `4352..4415`（`0x1100`；Gateway **FC03 读** ← PLC `MB_StatusOut`） |
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

外部视觉纠偏（航向误差）走独立从站协议，见 [VISION_MODBUS_TCP.md](VISION_MODBUS_TCP.md)。

**0.60 X 轴视觉直控**：AM600 Modbus TCP 从站只允许 **1 个主站**，视觉经网关中继：`POST /vision {enable,velM1,velM2}` → 网关写命令镜像 `word56..59`（Holding `4152..4155`），静默 >200ms 自动清零。状态 `word28..31` 回读直控在役/在线/实际速度。详见 [VISION_DIRECT.md](VISION_DIRECT.md)。控制源为手动模式，直控与手动点动/自动互斥。

**0.63 X 双电机速度通用透传**：状态 `word32/33`=M1 实际速度、`word34/35`=M2 实际速度（SCALED_DINT ×1000），`word36` 位=Moving/Powered/SyncWarn/SyncFault，`word37/38`=同步误差；命令区不变。由 `PRG_TcpHmi` 编码、`tools/patch_g063.py` 生成 `LMM_g_0.63.xml`。详见 [VISION_DIRECT.md](VISION_DIRECT.md)。

实控页：`http://127.0.0.1:8080/`（**WebHMI v2**：顶部状态栏 + 自动/手动/X 双驱/调试/日志 页签；键盘点动、X 直控滑条、白名单命令台、寄存器表、趋势/快照；`GET /health` 诊断）。通用调试页：`http://127.0.0.1:8080/debug.html`（`GET /map` 驱动，读全部状态 + 写白名单命令）。

## 现场联调

1. **InoProShop**：把原 Modbus TCP **主站**通道改为 **从站**（或新建从站），Holding 起始地址 **`0x1000`** / **`0x1100`**（该字段为十六进制），各 64 WORD 映射到 `MB_CmdIn`(`%IW103`) / `MB_StatusOut`(`%QW44`)。禁用「主动连 Gateway」的主站通道。  
2. 确认 PLC 网口 IP = `192.168.1.88`（或改 Gateway `PLC_HOST`）。  
3. Gateway：`.\tools\start-webhmi.ps1`（主站连 PLC；`-Mock` 本地冒烟）。  
4. 点动松开即停；拔网线 ≤1s 远程动作清零；恢复网络不自行运动。  
5. 面板在远程掉线后可接管。

## 现场问题与结论：地址字段是十六进制（2026-09-12 已解决）

现象：Gateway 能连上 `192.168.1.88:502`，但 HMI 一直离线、按键/参数「没反应」。
`GET /health` 显示 `connected=true` 且 `lastError="Invalid status image: MAGIC_MISMATCH,VERSION_MISMATCH"`。

排查（只读探针 `node gateway/scripts/probe-plc.js 192.168.1.88 502 1`）：
- PLC 程序侧正常：在线监视 `MB_StatusOut[0]=19533`、`MB_StatusOut[1]=256`、`MB_StatusOut[2]` 每周期递增 → `PRG_TcpHmi` 在跑。
- GVL 有 `MB_CmdIn AT %IW103` / `MB_StatusOut AT %QW44`；从站 Internal I/O 映射也建了 `%IW103`/`%QW44`，但 **InoProShop 该「起始地址」字段是十六进制**：填 `1000`=`0x1000`=**4096**，填 `1100`=`0x1100`=**4352**。网关原按十进制 1000/1100 读写，落到空白区。

实测（修复后）：

| 地址 | 内容 | 结论 |
|------|------|------|
| Holding `4096..4159` | Gateway 命令镜像；PLC 状态 `word3` 回显命令序号 | 命令区 OK |
| Holding `4352..4415` | `0x4C4D 0x0100` + 序号递增 | 状态区 OK |

结论：Gateway 契约基址改为 **4096 / 4352**（`config/modbus-map.json`），**无需再改或下载 PLC**。
启动日志应打印 `[gateway] cmd@4096 status@4352 (len 64)`，`/health` 的 `statusIsOffline=false`。

> 备选：若要在 PLC 侧保持十进制 1000/1100，在 InoProShop 该字段填十六进制 `3E8`（=1000）/ `44C`（=1100）
> 再下载，然后把 `config/modbus-map.json` 基址改回 1000/1100。

**踩坑备忘**：从站 Internal I/O 映射变量名不能与 GVL 同名（`MB_CmdIn`/`MB_StatusOut`），否则编译
`C0136 使用不明确` + `C0018 无效赋值目标`；映射变量用唯一名，GVL `AT %IW103`/`AT %QW44` 保留。

## 急停锁存与远程心跳（2026-09-12）

现场「状态在线，但按任何轴都不动」的第二个原因：PLC 侧 `xEStopLatched` 已锁存 → 报警 1001，
安全逻辑 `xSafe := HMI_xEStop AND NOT xEStopLatched` 为假 → `AxisCmd_xPower := FALSE`，所有轴被锁。

- `HMI_xEStop := EStop(物理) AND Tcp_xEStop(远程) AND HMI_xEStopReq(触摸屏，初值 TRUE)`。
- 只要 `HMI_xEStop` 变 FALSE 一次，`xEStopLatched := TRUE`；只有 `HMI_xStopHold3s` 上升沿（网页「复位」）或
  停止键按住 3s 才清锁存：**松开物理急停 → 网页按一次「复位」**。
- Gateway fail-safe 原先置 `HMI_xEStop=FALSE`，每次启动/断线都会锁存急停；已改为
  `HMI_xStop=TRUE + HMI_xEStop=TRUE`（**停止但不锁存**），恢复后无需再手动复位。
- Gateway 现**每轮询周期推进心跳**（`store.advanceHeartbeat()`）维持 PLC `tonHb` 看门狗；
  否则网页停顿 >1s 会被判远程超时、`Tcp_*` 动作清零（表现：点一下动一下即停）。
- 真机读 4352 状态帧：`HMI_iAlarmShow=1001`、`HMI_xLampEStop=TRUE`、`HMI_eDevState=2`、`AxisFb_xReady=FALSE`
