# LMM.xml 导入说明（InoProShop / PLCopen TC6）

备份：`LMM.xml.bak`（写入前自动生成）

## 已写入内容

| 对象 | 说明 |
|------|------|
| `GVL` | 保留原 HMI 变量 + 对齐后的 HMI_/Logic/IO/AxisCmd/AxisFb |
| `FB_XDiff` | Sync/Diff（纠偏·原地旋转·差速拐弯） |
| `FB_Servo` | SoftMotion 单轴封装 |
| `PRG_Logic` | MainTask：联锁/命令；**桥接**原 StopBtn/EStop/Jog* |
| `PRG_Axis_Control` | **AxisTask 独立任务**：只读写 GVL |
| `FB_Force485` / `PRG_Force485` | **ForceTask 独立任务**：LE 拉压 RS485 → `rForceAct` |
| `PLC_PRG` | 调用 `PRG_TcpHmi` + `PRG_Logic`（**不** CALL Force/Axis） |
| `AxisTask` | 4ms，运行 `PRG_Axis_Control` |
| `ForceTask` | 10–20ms，运行 `PRG_Force485`（需在 InoProShop 新建） |

## 导入步骤

1. InoProShop 打开/导入本 `LMM.xml`（或覆盖工程后重新加载）
2. 编译：若 `AXIS_REF_SM3` / `MC_*` 类型名与库版本不符，在库管理器确认 **SM3_Basic** 已加入，按本机类型名微调 `FB_Servo`
3. 确认任务：`MainTask`→PLC_PRG；`AxisTask`→PRG_Axis_Control；`ForceTask`→PRG_Force485；**不要**在 Main 里 CALL Axis/Force
4. 映射限位 `I_xLim*`（地址 TBD）
5. 极性：面板 `EStop AT %IX0.4` **正常=TRUE / 按下=FALSE**，桥接 `HMI_xEStop:=EStop`（不取反）；灯：`StopLamp %QX0.6←Dev_xStop`，`StartLamp %QX0.7←Dev_xRun`  
6. 面板键：`StartBtn %IX1.6`、`StopBtn %IX1.4`、`ResetBtn`（→StopHold3s）— **地址固定勿改**
8. **ST 方言**：XOR 用中缀 `a XOR b`；TCP 按手册：`abyData:=DataBuffer[1]`（`ARRAY[1..8192] OF BYTE`），`uiDataSize:=0`；连接判定用 `TCP_ESTABLISHED`
9. **力传感 RS485（LE）** — 见下节

## LE 拉压传感器 RS485

| 项 | 值 |
|----|-----|
| 电气 | DC12V；485+绿 / 485-白 |
| 串口 | **115200，8 数据位，1 停止，无校验** |
| 站号 | 默认 `Force_bySlave=1` |
| 协议 | Modbus-RTU；轮询读 `0x0000`；上电写单位 `0x02=5`（N） |
| 换算 | `rForceAct = INT16_raw * Force_rScale`（默认 Scale=0.01） |

### InoProShop 串口绑定

1. 设备树选本体/扩展 **COM**（记下口号）
2. 参数：115200 8N1
3. 自由协议或小 ST：见 [PRG_Force485.md](PRG_Force485.md) — 发 `Force_abyTx`，收填 `Force_abyRx` + `Force_xRxNew`
4. 新建任务 **ForceTask**（建议 20ms）→ `PRG_Force485`
5. 联调：先 `HMI_xForceSimEnable=TRUE`；串口助手确认传感器应答 `01 03 00 00 00 01 84 0A`；再关模拟看 `Force_xCommOk` / `HMI_rForceShow`

### 联调检查单

- [ ] 12V 供电、A/B 极性
- [ ] 串口助手能读到力值
- [ ] `Force_xCommOk=TRUE`，`Force_xTimeout=FALSE`
- [ ] 关模拟后 `HMI_rForceShow` 随手压力变化
- [ ] 超时（拔线）→ Alarm **1005**、设备 Error（非模拟时）

## 与 Web / TCP

对照 `docs/plc/WEB_PLC_ALIGN.md`、`docs/plc/TCP_HMI.md`。  
实控：`gateway/` + `web/live/`（默认 `MOCK_PLC=1` 可无 PLC 试画面）。  
导入后确认：`PLC_PRG` 调用 `PRG_TcpHmi` 再 `PRG_Logic`；`FB_TCPServer` 使用本机 `SktTCP*` 库。
