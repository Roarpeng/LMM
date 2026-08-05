# X 双驱双速度（g 0.26）设计

日期：2026-08-05  
状态：**已实施 g 0.26**  
基线：0.25（CSP+CSV 混架构；换向/松手仍不理想）  
交付：`LMM_g_0.26.xml`

## 动机

- 现场视觉航向纠偏是速度域外环；M1 CSP + M2 CSV 带宽不对称，换向/松手行为不一致。
- 0.25 已消报警，但仍有「一方向走完立刻反方向不动」「松手仍溜」。
- 决策：不再纠结混架构，改为 **双速度指令**。

## 目标

1. M1/M2 均用 `MC_MoveVelocity`（同构），废除 M1 `MC_Jog`。
2. 换向：任一侧符号变化 → 撤 `Execute` 一拍再重触发（对齐 `FB_Servo`）。
3. 松手：`eMode=0` → 立刻撤双轴 `Execute` → `MC_Halt` 减速（禁止零速保持 Execute）。
4. 视觉：保留 `rHeadingErr * rKpTrack` 差速；同步 trim 轻量（P，I/D=0，同号钳位）。
5. SoftHold：保持调节器；仅表示空闲（无速度 FB），退出沿 Reset。

## 非目标

- 本轮不改设备树 `0x6060`（若现场已是线轴 finite，SoftMotion 速度 FB 可用；真 CSV 驱动模式可后补）。
- 不恢复 Virtual / GearIn。
- 不改 Y/Z/R、HMI 命令字。

## 速度合成

| 模式 | rVelCmdM1 | rVelCmdM2 |
|------|-----------|-----------|
| Jog/MoveRel | ±V | V1 − 2·trim_vis + trim_sync（同号钳位） |
| SpinL/R | ±Vspin | −V1 |
| 停止 | 0 | 0 → Halt |

## 验收

1. JOG+ → 松手停 → JOG− 立刻反走；反之亦然。
2. 松手后双轴减速停，不继续溜。
3. 视觉纠偏时差速响应对称。
4. 无位置误差超限报警。
