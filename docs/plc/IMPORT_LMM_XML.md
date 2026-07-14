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
| `PLC_PRG` | 仅调用 `PRG_Logic()` |
| `AxisTask` | 4ms，运行 `PRG_Axis_Control` |

## 导入步骤

1. InoProShop 打开/导入本 `LMM.xml`（或覆盖工程后重新加载）
2. 编译：若 `AXIS_REF_SM3` / `MC_*` 类型名与库版本不符，在库管理器确认 **SM3_Basic** 已加入，按本机类型名微调 `FB_Servo`
3. 确认任务：`MainTask`→PLC_PRG；`AxisTask`→PRG_Axis_Control；**不要**在 Main 里 CALL Axis 程序
4. 映射限位 `I_xLim*`（地址 TBD）
5. 极性：面板 `EStop AT %IX0.4` **正常=TRUE / 按下=FALSE**，桥接 `HMI_xEStop:=EStop`（不取反）；灯：`StopLamp %QX0.6←Dev_xStop`，`StartLamp %QX0.7←Dev_xRun`  
6. 面板键：`StartBtn %IX1.6`、`StopBtn %IX1.4`、`ResetBtn`（→StopHold3s）— **地址固定勿改**

## 与 Web v2

对照 `docs/plc/WEB_PLC_ALIGN.md`。原面板：前进/后退在 Sync/Diff/Indep 下分别映射到 Sync± / Diff± / M1M2。  
