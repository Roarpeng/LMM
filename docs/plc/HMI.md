# HMI.md — 设备操作触摸屏绑定

> 只写 `GVL_HMI`；读 `GVL_HMI_Status` / `GVL_AxisFb`。契约：[GVL.md](GVL.md)

## 设备三态灯

| 灯 | 变量 | 含义 |
|----|------|------|
| Stop | `HMI_xDevStop` | 停止 / 待机 |
| Run | `HMI_xDevRun` | 正在运行（手动或自动，看 `HMI_eOpMode`） |
| Error | `HMI_xDevError` | 错误 |

复位长按当拍 → Error 灭、Stop 亮。

## 画面分区

1. **安全**：急停、启动、停止（长按复位）、三态灯  
2. **模式**：手动 / 自动（`HMI_xAutoMode`）  
3. **手动**：X+/X−、**左旋转 / 右旋转**、Y+/Y−、Z+/Z−、R+/R−；速度 VelX/Y/Z/R  
4. **自动**：X距/速、Y距/速、Z速、F_set；启动/中止；步号、力实际  

## 手动键（电平 TRUE=动 FALSE=停）

| 控件 | 变量 |
|------|------|
| X+ / X− | `HMI_xJogXPos` / `HMI_xJogXNeg` |
| 左旋转 / 右旋转 | `HMI_xSpinLeft` / `HMI_xSpinRight` |
| Y± Z± R± | `HMI_xJogY/Z/R*` |
| 速度 | `HMI_rJogVelX/Y/Z/R`（旋转用 VelX） |

前提：设备 **RUN** 且 **手动**（`HMI_xAutoMode=FALSE`）。左右旋互斥；X± 与旋转互斥。

## 自动

| 控件 | 变量 |
|------|------|
| 自动模式 | `HMI_xAutoMode=TRUE` |
| 启动 / 中止 | `HMI_xAutoStart` / `HMI_xAutoAbort` |
| X距/速 Y距/速 Z速 | `HMI_rAutoDistX/VelX` … `HMI_rAutoVelZ` |
| 力设定 | `HMI_rForceSet`（N） |
| 力模拟 | `HMI_xForceSimEnable` + `HMI_rForceSim` |
| 步号/忙/完成/力 | `HMI_iAutoStepShow` / `HMI_xAutoBusy` / `HMI_xAutoDone` / `HMI_rForceShow` |

### 自动主序（显示用）

0 Idle → 1 X走距 → 2 Z下压到力 → 3 Y走距+恒力 → 4 R摇摆(占位) → 5 Done  

## 流程

手动：松急停 → 复位清错 → 启动→RUN → 点动。  
自动：切自动 → 填参数 → RUN 下按自动启动。

## Must not

- 写 `AxisCmd_*` / `eDevState` / `iAutoStep`  
- 自动进行中开放手动 JOG（Logic 禁透传）  
