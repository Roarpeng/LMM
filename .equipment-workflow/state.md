# equipment-plc-workflow state

## Meta
- Project: LMM XYZR + 力传感
- Entry: change-request（LE 拉压 RS485）
- Updated: 2026-07-18

## Current
- Stage: S6/S8 — TCP 已按手册场景1（SktTCP* 状态机）改写 FB_TCPServer
- Next: 重新导入 LMM.xml；gateway 连真机 `:9100` 联调

## Locked decisions
- X 直行 `HMI_rJogVelX` ≠ 左右旋 `HMI_rSpinVel`
- 龙门跨距 = Y 行程 = `HMI_rWheelBase`（4~6）
- TCP：手册场景1 Server；`uiDataSize=0`；连接判定=`TCP_ESTABLISHED`；ID=`stConnectInfo.diConnectID`
- 面板 ∨ Tcp 影子合成；急停 AND（更严）
- web/v2 保留验收模拟；web/live 实控
- 力传感：RS485 Modbus-RTU；独立 ForceTask；Alarm 1005

## Paths
- docs/plc/FB_TCPServer.md, TCP_HMI.md, GVL.md, LMM.xml, gateway/
