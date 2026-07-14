# equipment-plc-workflow state

## Meta
- Project: LMM XYZR + 力传感
- Entry: change-request（HMI 简化 + 自动恒力）
- Updated: 2026-07-14

## Current
- Stage: S7 Web v2 已按现行 MD 重做（待「Web v2 通过」）
- Next: 用户确认 Gate D；导入 LMM.xml；触摸屏按 HMI.md

## Locked decisions
- 手动：X±、左/右旋转、Y±、Z±、R± + 各轴速度
- 自动：X距速 → Z下压到 F_set → Y距+恒力闭环 → R摇摆占位
- 力：N；模拟优先；485 后补
- R/M5：接口满，xM5Ready 门控
- 面板 IO 地址固定；EStop 正常 TRUE

## Paths
- docs/plc/GVL.md, HMI.md, PRG_Logic.md, Axis_Control.md
- LMM.xml, web/v2
