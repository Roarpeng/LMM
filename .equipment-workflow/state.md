# equipment-plc-workflow state

## Meta
- Project: LMM XYZR + 力传感
- Entry: change-request（HMI 精简：SpinVel / 跨距=Y）
- Updated: 2026-07-16

## Current
- Stage: S6/S7 — 契约与 LMM.xml / Web 已精简
- Next: 触摸屏按 HMI.md 重绑；导入 LMM.xml；确认「Web v2 通过」

## Locked decisions
- X 直行 `HMI_rJogVelX` ≠ 左右旋 `HMI_rSpinVel`
- 龙门跨距 = Y 行程 = `HMI_rWheelBase`（4~6）；删除 `HMI_rAutoDistY`
- 删除旧 Indep/Sync/Diff/Home/Δ/ω HMI 与 AxisCmd 符号
- 手动：X±、左右旋、Y±Z±R±
- 自动：X距速 → Z压到力 → Y走跨距+恒力 → R占位
- 面板 IO 固定；EStop 正常 TRUE

## Paths
- docs/plc/GVL.md, HMI.md, PRG_Logic.md, Axis_Control.md
- LMM.xml, web/v2
