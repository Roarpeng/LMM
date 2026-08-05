# X 双驱 SoftHold（g 0.15）设计

日期：2026-08-03  
状态：**已实施 g 0.19**  
基线：0.18 不摆且 Jog 可用，但静止频繁使能；交付 `LMM_g_0.19.xml`

## 0.18 频繁使能根因

SoftHold 松调节器后速度微抖 → `tonStill` 反复掉 → SoftHold 进进出出 → `bRegulatorOn` 频繁开关。

## SoftHold 0.19

进入 SoftHold 后 **锁存**，速度噪声不得退出；仅 Jog/急停/失能才退出并恢复调节器。

## 动机

0.14 停稳后双轴 Standstill、速度≈0，但 `rPosM1/rPosM2` **长时间不衰减来回爬**（极限环）。根因判断：M1 CSP 硬保位与横梁残扭互相激励；运动中画龙/跟随误差为同一耦合在速度跟随路径上的放大。

## 目标

1. 松手停稳后进入 **SoftHold**：打断 CSP 硬保位极限环
2. 运动同步保留 0.14 骨架，增加 **`xSyncEnable`** 总开关便于对比
3. **`eSlaveMode`** 预留 CST（本轮恒 0，不实现力矩）

## 非目标

- 不恢复 Virtual / `MC_GearIn`
- 不同步偏差停机联锁
- 不改 Y/Z/R、力控、HMI 命令字布局
- 本轮不改设备树、不切 `0x6060=10`

## SoftHold 状态机

| `iHoldState` | 条件 | 行为 |
|--------------|------|------|
| 0 Run | `eMode≠0` 或急停/未使能/未双上电 | 原 0.14 运动路径 |
| 1 Decel | `eMode=0` 且尚未双轴静止满 200ms | Halt 减速（沿用 0.10 去抖） |
| 2 SoftHold | `eMode=0` 且 `tonStillM1/M2.Q` 且使能双上电且非急停 | M1：`MC_MoveVelocity` Execute 保持、Velocity=0；M2：不跟、不给耦合力 |

急停 `xStop`：只走 `MC_Stop`，不进 SoftHold。  
再点动/走距/旋转：立即退出 SoftHold，恢复 Jog/MoveVel。

说明：M1 设备树为 CSP 时，SoftMotion 的「零速 Velocity FB」仍可能偏硬；若现场 SoftHold 后仍永晃，下一版评估真 CSV/CST（`eSlaveMode=1`）。

## 运动同步

- M2 前馈继续跟 **`rVelCmdM1`（指令速度）**（0.12）
- 位置耦合仅 `eMode=1`（0.14）
- **`xSyncEnable`（默认 TRUE）**：FALSE 时强制 `rTrimPos/rTrimInt=0`
- `eSlaveMode` 输出恒 0（CSV）；CST 另开专项

## 验收

1. 松手 → Decel → SoftHold 后，位置不再长时间来回爬
2. SoftHold 下再按 X± 能立刻起步
3. 急停可靠；`xSyncEnable:=FALSE` 可在线对比拧架

## 交付

- `plc/g/FB_XDual.st` → g **0.15**
- `python tools/inject_g.py LMM_g_0.14.xml LMM_g_0.15.xml`
- 纯逻辑：`tools/x_dual_logic.py` + `tools/test_x_dual_logic.py`
