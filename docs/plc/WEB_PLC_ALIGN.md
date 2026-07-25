# Web live ↔ PLC 对齐速查

> 权威：[HMI.md](HMI.md) + [GVL.md](GVL.md) + [TCP_HMI.md](TCP_HMI.md)。
> 实控页：`web/live/`（浏览器 ↔ `gateway/` WebSocket ↔ Modbus TCP ↔ PLC）。

## 通讯

| 项 | 值 |
|----|-----|
| PLC 角色 | Modbus TCP **Master** |
| Gateway | Modbus TCP **Server** `0.0.0.0:502`，`web/live` HTTP `:8080` |
| 一键启动 | 仓库根：`.\tools\start-webhmi.ps1`（真机 `MOCK_PLC=0`） |
| 调试冒烟 | `.\tools\start-webhmi.ps1 -Mock` |
| 命令区 | Holding `1000..1063`（PLC FC03 读） |
| 状态区 | Holding `1100..1163`（PLC FC16 写） |
| 地址表 | `config/modbus-map.json` → [MODBUS_MAP.md](MODBUS_MAP.md) |

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
