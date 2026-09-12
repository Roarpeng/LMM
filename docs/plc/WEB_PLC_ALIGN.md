# Web live ↔ PLC 对齐速查

> 权威：[HMI.md](HMI.md) + [GVL.md](GVL.md) + [TCP_HMI.md](TCP_HMI.md)。
> 实控页：`web/live/`（浏览器 ↔ `gateway/` WebSocket ↔ Modbus TCP ↔ PLC）。

## 通讯

| 项 | 值 |
|----|-----|
| PLC 角色 | Modbus TCP **从站**（监听，不主动连外） |
| Gateway | Modbus TCP **主站** → 默认 `192.168.1.88:502`；`web/live` HTTP `:8080` |
| 一键启动 | 仓库根：`.\tools\start-webhmi.ps1`（真机主站；`-Mock` 本地） |
| 调试冒烟 | `.\tools\start-webhmi.ps1 -Mock` |
| 命令区 | Holding `4096..4159`（`0x1000`；Gateway **FC16 写**） |
| 状态区 | Holding `4352..4415`（`0x1100`；Gateway **FC03 读**） |
| 地址表 | `config/modbus-map.json` → [MODBUS_MAP.md](MODBUS_MAP.md) |
| 通用调试页 | `http://127.0.0.1:8080/debug.html`（`GET /map` 驱动，写白名单 + X 直控手测） |

> X 轴视觉直控（M1/M2 速度透传，`directx` 段 + 视觉块 `4152..4155`）见 [VISION_DIRECT.md](VISION_DIRECT.md)。

## X 双电机实际速度（0.63）

| word | 字段 | 说明 |
|------|------|------|
| 32/33 | `AxisFb_rVelActM1` | M1 实际速度 m/s（×1000） |
| 34/35 | `AxisFb_rVelActM2` | M2 实际速度 m/s（×1000） |
| 36 | `AxisFb_xMovingM1/M2` `xPoweredM1/M2` `xSyncWarn/Fault` | 位状态 |
| 37/38 | `AxisFb_rSyncErr` | M1−M2 同步误差 |

> WebHMI v2（`web/live/index.html`）：顶部状态栏 + 自动/手动/X 双驱/调试/日志；X 双驱页大字显示实际速度/指令/ΔVel/趋势；调试页有 X 直控滑条、白名单命令台、寄存器表与 `/health`。

## 轴

X=M1+M2 · Y=M3 · Z=M4 · R=M5

## 手动

| 操作 | HMI |
|------|-----|
| X± | `HMI_xJogXPos/Neg` + `HMI_rJogVelX` |
| 左/右旋 | `HMI_xSpinLeft/Right` + `HMI_rSpinVel` |
| Y/Z/R± | `HMI_xJog*` + `HMI_rJogVel*` |
| Z 力引导 | `HMI_xForceGuide`（电平） |
| 回零 Y/Z/R | `HMI_xHome*` 或 `HMI_iHomeAxis`+`HMI_xHomeExec` |

## 自动

`HMI_rAutoDistX/rAutoVelX` · `HMI_rWheelBase`(跨距=Y行程 4~6) · `HMI_rAutoVelY/Z` ·
`HMI_rForceSet` · `HMI_iAutoPasses` · `HMI_rKpForce/KpTrack/HeadingErr`

步序：1 X走距 → 2 Y归位 → 3 Z压到力 → 4 Y走跨距恒力 → 5 多道判定 → 6 Done

## 硬限位

`Cfg_rLimY*/Z*/R*`（X 无）；所有模式强制；手动可改（触摸屏直绑 GVL；Web 暂不提供）。

## 设备态 / 报警

`HMI_eDevState`：0 停 · 1 运行 · 2 错误。报警 1001/1002/1005/1006/1007。

## 控制源

面板 ‖ 触摸屏 ‖ Web **互斥**（`eCtrlSrc`：谁操作谁独占，掉线回面板）；
急停 AND（取更严）；停止/中止任一侧可介入。
