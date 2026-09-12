# X 轴视觉直控（M1/M2 速度透传）— 0.60

> 目的：直线行走不由 PLC 内部按航向误差做差速，而由视觉工控机**直接给 M1/M2 两个速度**，闭环走直线。
> **硬约束：AM600 Modbus TCP 从站只允许 1 个主站**，故视觉不直连 PLC，而是
> **视觉 → 网关（唯一主站）→ PLC**。PLC 侧代码与"视觉直连"方案完全一致，无需改动。
> 权威符号：`LMM_g_0.60.xml` GVL 的 `Vis_*` / `HMI_*Direct*` / `Direct_*` / `AxisCmd_*Direct*`。

## 拓扑

```
视觉工控机 ──HTTP POST /vision──> gateway (唯一 Modbus TCP 主站) ──> PLC 从站 192.168.1.88:502
浏览器 WebHMI ──WS───────> gateway
```

- 网关把视觉值写进命令镜像 `word56..59`；视觉静默 >`VISION_TIMEOUT_MS`（默认 200ms）→ 网关清零。
- PLC 侧另有独立 200ms 看门狗（`Vis_wSeq` 不翻则离线），双保险；任一环节断 → 停机。

## 视觉侧接口

```
POST http://<gateway>:8080/vision
Content-Type: application/json

{"enable": true, "velM1": -0.400, "velM2": -0.385}
```

- 每 20~50ms 发一次（`velM1`/`velM2` 单位 m/s，正负=方向）。
- `enable:false` 或停止发送（>200ms）→ 直控退出 → X 双轴减速停。
- 环境变量 `VISION_TIMEOUT_MS`（默认 200）可调。

## 0.63 通用透传（与直控解耦）

- 新增状态 `word32..38`：`AxisFb_rVelActM1/M2`（实际速度）、`AxisFb_xMovingM1/M2`、`AxisFb_xPoweredM1/M2`、`AxisFb_xSyncWarn/Fault`、`AxisFb_rSyncErr`。
- 原 `Direct_rVelM1Act/M2Act`（word29/30）保留兼容；两者同源（`fbX.rVelActM1Out/M2Out`）。
- 由 `tools/patch_g063.py` 在 `LMM_g_0.62.xml` 基础上**纯插入**生成 `LMM_g_0.63.xml`，不改设备树/任务/GVL addData。
- WebHMI v2「X 双驱」页直接显示实际速度，无需视觉直控在役。

## Python 示例

```python
import requests, time
GW = "http://192.168.1.x:8080/vision"
while running:
    requests.post(GW, json={"enable": True, "velM1": v1, "velM2": v2}, timeout=0.1)
    time.sleep(0.02)
```

## 寄存器（PLC 视角；由网关写）

| Holding | word | 变量 | 类型 | 说明 |
|---|---|---|---|---|
| 4150 | 54 | `HMI_rVelM1Set` | INT×1000 | Web 手测 M1 速度 |
| 4151 | 55 | `HMI_rVelM2Set` | INT×1000 | Web 手测 M2 速度 |
| 4152 | 56 | `Vis_xEnable` | WORD bit0 | 视觉直控请求（网关中继） |
| 4153 | 57 | `Vis_wSeq` | WORD | 心跳序号（网关每次中继 +1） |
| 4154 | 58 | `Vis_rVelM1Set` | INT×1000 | 视觉 M1 速度 |
| 4155 | 59 | `Vis_rVelM2Set` | INT×1000 | 视觉 M2 速度 |

Web 使能位：`word5 bit10 = HMI_xDirectEnable`。

### 状态区（Holding 4352+ = 0x1100，PLC 写，网关/浏览器读）

| Holding | word | 变量 | 说明 |
|---|---|---|---|
| 4380 | 28 | `Direct_xActive` bit0 / `Direct_xOnline` bit1 / `Direct_xEnable` bit2 | 在役 / 视觉在线 / 仲裁后使能 |
| 4381 | 29 | `Direct_rVelM1Act` (INT×1000) | M1 实际速度 |
| 4382 | 30 | `Direct_rVelM2Act` (INT×1000) | M2 实际速度 |
| 4383 | 31 | `Direct_wSeqEcho` | 视觉序号回显 |

## 使能逻辑（`PRG_Logic`）

- `Direct_xEnable := (视觉请求 ∨ Web请求) AND 安全(急停/未停止/无故障/手动模式)`
- 视觉请求 = `Vis_xEnable AND 视觉在线(200ms 内有心跳)`；视觉在线时速度取视觉值，否则退 Web 值。
- **失联即停**：视觉/网关任一断 → 请求失效 → `FB_XDual` 回 `eMode=0` 走 Halt。

## 运动侧（`FB_XDual` eMode=4）

- 直控时绕过 trim/sync/爬坡，两个速度分别经 `MC_MoveVelocity` 直下 M1/M2。
- 目标变化走**限频重触发**（默认 40ms，输入 `tDirectRetrig`），无变化不触发。
- 任一侧目标为 0 且在动 → 双轴 Halt；停/急停/换向逻辑仍生效。
- 直控期间屏蔽 X 手动点动/旋转。

## 现场核对

1. 视觉工控机能访问网关 `http://<gateway-ip>:8080/vision`。
2. 手动模式 → Web 调试页 `/debug.html` 勾选 `HMI_xDirectEnable`、填两速度，先手测 X 双驱；再接视觉 POST。
3. 停发视觉（或拔视觉网线）≤200ms，`Direct_xOnline` 落、X 双轴减速停。
