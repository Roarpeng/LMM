# equipment-plc-workflow state

## Meta
- Project: LMM XYZR + 力传感
- Entry: change-request（WebHMI Modbus TCP）
- Updated: 2026-07-22

## Current
- Stage: S6/S7 — WebHMI Modbus TCP 改造已落地（Gateway Server + PLC Master 过程映像）
- Spec: `docs/superpowers/specs/2026-07-22-webhmi-modbus-tcp-design.md`
- Plan: `docs/superpowers/plans/2026-07-22-webhmi-modbus-tcp.md`
- 映射：`config/modbus-map.json` → `docs/plc/MODBUS_MAP.md`
- 脚本：`tools/refactor_modbus_hmi.py`（备份 `LMM.xml.bak.modbus_hmi`）
- 架构（以设备树为准）：浏览器 WS/JSON → Gateway Modbus TCP **Server :502** ← PLC Modbus TCP **Master**
- 地址：命令 Holding `1000..1063` → `MB_CmdIn %IW103`；状态 Holding `1100..1163` ← `MB_StatusOut %QW44`
- 删除：`FB_TCPServer`；`PRG_TcpHmi` 改为过程映像编解码 + 仲裁
- 验证：`python3 -m unittest tools.test_refactor_modbus_hmi` PASS；`cd gateway && npm test` 37 PASS
- Next: InoProShop 导入/合并 `LMM.xml` → 核对 `modbusTcp` 通道长度64、读1000/写1100 → 编译 → Gate D 联调

## Locked decisions
- X 直行 `HMI_rJogVelX` ≠ 左右旋 `HMI_rSpinVel`
- 龙门跨距 = Y 行程 = `HMI_rWheelBase`（4~6）
- 面板 ‖ 远程互斥；急停 AND（更严）；Web急停非安全等级
- web/v2 保留验收模拟；web/live 实控
- 力传感：RS485 Modbus-RTU；Alarm 1005/1006
- 生产断线禁止自动 Mock；仅 `MOCK_PLC=1`
- Gateway 绑定目标 IP `192.168.1.1:502`（与设备树一致）

## Paths
- docs/plc/TCP_HMI.md, MODBUS_MAP.md, GVL.md, LMM.xml, gateway/, config/modbus-map.json
