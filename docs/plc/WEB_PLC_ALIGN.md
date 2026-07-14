# Web v2 ↔ PLC 对齐（简化版）

> 权威：`docs/plc/HMI.md` + `GVL.md`。手动无 Indep/Diff 菜单。

## 轴

X=M1+M2 · Y=M3 · Z=M4 · R=M5

## 手动

| 操作 | HMI | Axis |
|------|-----|------|
| X± | JogXPos/Neg | Sync 同速 |
| 左/右旋转 | SpinLeft/Right | Diff 原地一正一反 |
| Y/Z/R± | Jog* | FB_Servo |
| 速度 | rJogVel* | （旋转用 VelX） |

## 自动步序

1 MoveX → 2 PressZ(力≥F_set) → 3 MoveY+恒力 → 4 RWobble占位 → 5 Done

## 设备态

0 Stop停止/待机 · 1 Run运行中 · 2 Error错误

## 面板 IO（固定）

Start %IX1.6 · Stop %IX1.4 · EStop %IX0.4（TRUE正常）· StopLamp %QX0.6 · StartLamp %QX0.7
