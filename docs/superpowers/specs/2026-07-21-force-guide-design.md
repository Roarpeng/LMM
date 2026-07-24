# 力传感从站使能 / 去皮 / Z 轴力引导

## 确认结论

- 报警码：**1006**（从站使能 3 次失败）
- 去皮：沿用 `HMI_xForceTare`；外部上升沿或自动步内部触发
- 力引导：`HMI_xForceGuide` 电平 TRUE 持续跟随，FALSE 停止；手动/自动均可

## 架构

| 模块 | 职责 |
|------|------|
| `PRG_Force485` | `SM1001` 使能重试；`Force_wInRaw`→力；去皮写 `Force_wOutTare` |
| `PRG_Logic` | `HMI_xForceGuide` 时写 Z 速度；自动进入压下步时内部去皮；报警 1006 |
| 组态 | Modbus 通道映射（无 `MB_Connect`） |

## 力引导公式

`AxisCmd_rZVelCmd := LIMIT(±HMI_rAutoVelZ, rForceKp*(HMI_rForceSet - rForceAct))`

回零后 Z 软限位 **`[−0.7, 0]`**：越上界禁止正速、越下界禁止负速；力跟随同样受此限制。
