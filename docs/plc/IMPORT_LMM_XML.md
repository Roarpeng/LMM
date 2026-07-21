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
| `PRG_Force485` | 组态通道换算 + `SM1001` 重试3次 + 去皮 |
| `FB_Force485` | 停用 |
| `PLC_PRG` | `PRG_Force485` → `PRG_TcpHmi` → `PRG_Logic` |
| `AxisTask` | 4ms，运行 `PRG_Axis_Control` |
| `ForceTask` | 建议 10–20ms 跑 `PRG_Force485`（当前可挂 MainTask） |

## 导入步骤

1. InoProShop 打开/导入本 `LMM.xml`（或覆盖工程后重新加载）
2. 编译：若 `AXIS_REF_SM3` / `MC_*` 类型名与库版本不符，在库管理器确认 **SM3_Basic** 已加入，按本机类型名微调 `FB_Servo`
3. 确认任务：`MainTask`→PLC_PRG；`AxisTask`→PRG_Axis_Control；`ForceTask`→PRG_Force485；**不要**在 Main 里 CALL Axis/Force
4. 映射限位 `I_xLim*`（地址 TBD）
5. 极性：面板 `EStop AT %IX0.4` **正常=TRUE / 按下=FALSE**，桥接 `HMI_xEStop:=EStop`（不取反）；灯：`StopLamp %QX0.6←Dev_xStop`，`StartLamp %QX0.7←Dev_xRun`  
6. 面板键：`StartBtn %IX1.6`、`StopBtn %IX1.4`、`ResetBtn`（→StopHold3s）— **地址固定勿改**
8. **ST 方言**：XOR 用中缀 `a XOR b`；TCP 按手册：`abyData:=DataBuffer[1]`（`ARRAY[1..8192] OF BYTE`），`uiDataSize:=0`；连接判定用 `TCP_ESTABLISHED`
9. **力传感 RS485（LE）** — 见下节

## LE 拉压传感器 RS485（网络组态 Modbus 主站）

`PRG_Force485` 读组态映射变量；**`SM1001` 自动使能从站**（失败重试 3 次 → 报警 **1006**）。

| 项 | 值 |
|----|-----|
| 电气 | DC12V；485+绿 / 485-白 |
| 串口 | COM0，**115200 8N1** |
| 站号 | 1；使能 `SM1001` |
| 读力 | 通道 FC03 `0x0000` → `Force_wInRaw` |
| 去皮 | `HMI_xForceTare` / 自动步内部 → `Force_wOutTare` |
| 力引导 | `HMI_xForceGuide` 电平；`HMI_rForceSet`；Z=`Axis_4` |

详见 [PRG_Force485.md](PRG_Force485.md)。

### 联调检查单

- [ ] 组态通道已映射 `Force_wInRaw` / `Force_wOutTare` / `Force_wOutUnit`
- [ ] 12V、A/B、COM0；`SM1001` 自动为 TRUE
- [ ] `Force_xCommOk=TRUE`；`Force_iState=4`
- [ ] 关模拟后 `HMI_rForceShow` 随压力变化
- [ ] `HMI_xForceTare` 去皮；自动进 step2 也会去皮
- [ ] `HMI_xForceGuide=TRUE` 时 Z 跟力；FALSE 停止
- [ ] 从站 3 次失败 → Alarm **1006**

## 与 Web / TCP

对照 `docs/plc/WEB_PLC_ALIGN.md`、`docs/plc/TCP_HMI.md`。  
实控：`gateway/` + `web/live/`（默认 `MOCK_PLC=1` 可无 PLC 试画面）。  
导入后确认：`PLC_PRG` 调用 `PRG_TcpHmi` 再 `PRG_Logic`；`FB_TCPServer` 使用本机 `SktTCP*` 库。
