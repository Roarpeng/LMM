# HMI.md — 设备操作触摸屏绑定

> 只写 `GVL_HMI`；读 `GVL_HMI_Status` / `GVL_AxisFb`。契约：[GVL.md](GVL.md)

## 设备三态灯

| 灯 | 变量 | 含义 |
|----|------|------|
| Stop | `HMI_xDevStop` | 停止 / 待机 |
| Run | `HMI_xDevRun` | 正在运行（看 `HMI_eOpMode`） |
| Error | `HMI_xDevError` | 错误 |

## 画面分区

1. **安全**：急停、启动、停止（长按复位）、三态灯  
2. **模式**：手动 / 自动（`HMI_xAutoMode`）  
3. **手动**：X±、左右旋、Y±、Z±、R±；**VelX / SpinVel / VelY/Z/R**  
4. **自动**：X距/速、**跨距(=Y行程)**、Y速、Z速、F_set；启动/中止；步号、力  

## 手动键（电平 TRUE=动 FALSE=停）

| 控件 | 变量 |
|------|------|
| X+ / X− | `HMI_xJogXPos` / `HMI_xJogXNeg` |
| 左旋转 / 右旋转 | `HMI_xSpinLeft` / `HMI_xSpinRight` |
| Y± Z± R± | `HMI_xJogY/Z/R*` |
| X 直行速度 | `HMI_rJogVelX` |
| 左右旋速度 | `HMI_rSpinVel` |
| Y/Z/R 速度 | `HMI_rJogVelY/Z/R` |

前提：设备 **RUN** 且 **手动**。左右旋互斥；X± 与旋转互斥。

## 自动

| 控件 | 变量 |
|------|------|
| 自动模式 | `HMI_xAutoMode=TRUE` |
| 启动 / 中止 | `HMI_xAutoStart` / `HMI_xAutoAbort` |
| X 距 / 速 | `HMI_rAutoDistX` / `HMI_rAutoVelX` |
| 跨距(=Y行程) | `HMI_rWheelBase`（4~6 m） |
| Y 速 / Z 速 | `HMI_rAutoVelY` / `HMI_rAutoVelZ` |
| 力设定 | `HMI_rForceSet`（N） |
| 力模拟 | `HMI_xForceSimEnable` + `HMI_rForceSim` |
| 步号/忙/完成/力 | `HMI_iAutoStepShow` / `HMI_xAutoBusy` / `HMI_xAutoDone` / `HMI_rForceShow` |

### 自动主序

0 Idle → 1 X走距 → 2 Z下压到力 → 3 **Y 走跨距**+恒力 → 4 R摇摆(占位) → 5 Done  

## Must not

- 写 `AxisCmd_*` / `eDevState` / `iAutoStep`  
- 绑已删除旧符号：`JogXSync*` / `eXMode` / `AutoDistY` 等  
- 自动进行中开放手动 JOG  
