# Web v2 ↔ PLC 对齐（精简）

> 权威：`docs/plc/HMI.md` + `GVL.md` + `TCP_HMI.md`  
> 实控页：`web/live/`（经 `gateway/` TCP:9100）

## 轴

X=M1+M2 · Y=M3 · Z=M4 · R=M5

## 手动

| 操作 | HMI |
|------|-----|
| X± | `JogXPos/Neg` + `rJogVelX` |
| 左/右旋 | `SpinLeft/Right` + `rSpinVel` |
| Y/Z/R± | `Jog*` + 各轴 Vel |

## 自动

| 参数 | HMI |
|------|-----|
| X 距/速 | `rAutoDistX` / `rAutoVelX` |
| **跨距=Y行程** | `rWheelBase`（4~6） |
| Y/Z 速 | `rAutoVelY` / `rAutoVelZ` |
| 力 | `rForceSet` |

步序：1 MoveX → 2 PressZ → 3 MoveY(=WheelBase)+恒力 → 4 R占位 → 5 Done

## 设备态

0 Stop · 1 Run · 2 Error

## 面板 IO

Start %IX1.6 · Stop %IX1.4 · EStop %IX0.4（TRUE正常）· StopLamp %QX0.6 · StartLamp %QX0.7

## TCP WebHMI

| 项 | 值 |
|----|-----|
| 契约 | [TCP_HMI.md](TCP_HMI.md) |
| PLC | Server `:9100`，`PRG_TcpHmi` → `Tcp_*` |
| 合成 | 面板 ∨ Tcp → `HMI_*`（急停 AND） |
| 网关 | `gateway/` → `web/live` |
