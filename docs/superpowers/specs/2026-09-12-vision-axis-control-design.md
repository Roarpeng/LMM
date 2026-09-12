# 视觉直控全轴（Vision Direct Motion）设计

日期：2026-09-12
状态：设计（待评审，**未实现**）
入口：change-request
基线：`LMM_g_0.67.xml`（在役）、Gateway（主站 4096/4352）、WebHMI v3

## 1. 需求

- 视觉工控机**直接控制每个轴的电机**：写速度、写位置；读取位置 / 速度 / 力矩。
- 电机**使能、报警、限位、急停仍由 PLC 全权负责**。
- 视觉工控机**走 WebHMI（Gateway）接口**，不直连 PLC（PLC 从站只允许 1 个主站）。

## 2. 约束 / 非目标

- **不动**现有 HMI 命令/状态 64W 镜像（Holding `4096`/`4352`）与 WebHMI 浏览器契约。
- **不动**现有 X 视觉直控（`Vis_*` word56..59）行为；新功能独立并存。
- 视觉**不参与**使能/报警；不做安全等级、不做认证安全。
- 仍是 **Gateway 唯一 Modbus TCP 主站**；视觉只连 Gateway。

## 3. 方案：独立「视觉直控镜像」

新增**一对并列 64W 通道**，与 HMI 镜像互不干扰（比扩到 128W 更安全、可回退）：

| 通道 | 方向 | Holding（十六进制） | 十进制 | 映射 PLC | 变量 |
|------|------|--------------------|--------|----------|------|
| Channel 03 | input（视觉→PLC） | `16#1200..123F` | 4608..4671 | `%IW...` | `VIS_CmdIn` |
| Channel 04 | output（PLC→视觉） | `16#1300..133F` | 4864..4927 | `%QW...` | `VIS_StatusOut` |

> 设备树：40502 `ModbusTcpSlave` 增加 Channel 03（ARRAY[0..63] input）/ Channel 04（ARRAY[0..63] output）。

### 3.1 VIS_CMD（Gateway 写 → PLC 读）

| word | 变量 | 类型 | 说明 |
|---:|---|---|---|
| 0 | magic | WORD | `16#5649`（'VI'） |
| 1 | version | WORD | `16#0100` |
| 2 | seqHead | WORD | 命令序号（首） |
| 3 | heartbeat | WORD | 每次写入递增（看门狗） |
| 4 | flags | WORD | bit0 enable；bit1 stop；bit2 resetReq |
| 5 | X_mode | UINT | 0 idle / 1 vel / 2 posAbs / 3 posRel |
| 6 | X_velM1 | INT×1000 | m/s |
| 7 | X_velM2 | INT×1000 | m/s（可差速） |
| 8-9 | X_pos | DINT×1000 | m（高字在前） |
| 10 | Y_mode | UINT | 同上 |
| 11 | Y_vel | INT×1000 | m/s |
| 12-13 | Y_pos | DINT×1000 | m |
| 14 | Z_mode | UINT | |
| 15 | Z_vel | INT×1000 | m/s |
| 16-17 | Z_pos | DINT×1000 | m |
| 18 | R_mode | UINT | |
| 19 | R_vel | INT×1000 | 工程单位/s |
| 20-21 | R_pos | DINT×1000 | 工程单位（画面按 °） |
| 22-62 | reserved | | |
| 63 | seqTail | WORD | 尾部序号，须 = word2 |

### 3.2 VIS_STATUS（PLC 写 → Gateway 读）

| word | 变量 | 类型 | 说明 |
|---:|---|---|---|
| 0/1 | magic/version | WORD | 同上 |
| 2/3/4 | seq / ackSeq / hbEcho | WORD | 序号、已接受命令序号回显、心跳回显 |
| 5 | status | WORD | bit0 online；bit1 safe；bit2 visionActive；bit3 sourceIsVision |
| 6 | X_flags | WORD | movingM1/M2、poweredM1/M2、syncWarn、syncFault、homed? |
| 7-8 | X_posM1 | DINT×1000 | m |
| 9-10 | X_posM2 | DINT×1000 | m |
| 11/12 | X_velActM1/M2 | INT×1000 | m/s |
| 13-14 | X_syncErr | DINT×1000 | m |
| 15 | Y_flags | WORD | moving/ready/fault/homed/limit |
| 16-17 | Y_pos | DINT×1000 | m |
| 18 | Y_velAct | INT×1000 | m/s |
| 19/20-21/22 | Z_flags / Z_pos / Z_velAct | | |
| 23/24-25/26 | R_flags / R_pos / R_velAct | | |
| 27-28 | forceN | DINT×100 | N |
| 29 | forceRaw | INT | 原始计数 |
| 30 | forceFlags | WORD | commOk/timeout/slaveFail/tareBusy/tareDone |
| 31 | alarm | UINT | 0/1001/1002/1005/1006/1007 |
| 32 | source | UINT | 0 面板 / 1 Web / 2 视觉 |
| 33-62 | reserved | | |
| 63 | seqTail | WORD | = word2 |

## 4. GVL 与写者矩阵（Gate C）

| 变量 | 类型 | 唯一写者 | 读者 |
|------|------|----------|------|
| `VIS_CmdIn` | ARRAY[0..63] OF WORD | 设备 I/O（视觉经网关） | `PRG_Vision` |
| `VisCmd_*` | 结构/标量 | `PRG_Vision` | `PRG_Logic` |
| `Vis_xEnable`/`Vis_xOnline` | BOOL | `PRG_Vision` | `PRG_TcpHmi`/`PRG_Logic` |
| `eCtrlSrc` | UINT | `PRG_TcpHmi` | `PRG_Logic` |
| `AxisCmd_*` | — | `PRG_Logic` | `PRG_Axis_Control` |
| `AxisFb_*` | — | `PRG_Axis_Control` | `PRG_Logic`/`PRG_Vision` |
| `VIS_StatusOut` | ARRAY[0..63] OF WORD | `PRG_Vision` | 设备 I/O |

## 5. PLC 修改清单

1. **新增 POU `PRG_Vision`（MainTask）**：解码 `VIS_CmdIn`→`VisCmd_*`；编码 `VIS_StatusOut`；心跳看门狗；产 `Vis_xEnable/Vis_xOnline`。
2. **`PRG_TcpHmi`**：`eCtrlSrc` 增加来源 **2=视觉**（条件：`Vis_xEnable AND Vis_xOnline AND xSafe AND NOT HMI_xAutoMode`）；视觉活跃时忽略 Web/面板**运动**命令（停止/复位仍生效）。
3. **`PRG_Logic`**：`eCtrlSrc=2` 且安全时，用 `VisCmd_*` 生成 `AxisCmd_*`（速度/定位/相对）；限幅、软限位；丢失看门狗 → `AxisCmd_xStopAll`。
4. **`PRG_Axis_Control`**：不变（仍只消费 `AxisCmd_*`）。X 双驱沿用 `FB_XDual` 直控；Y/Z/R 用 `FB_Servo` 的 `xUseVelCmd`/`xMoveAbs`。
5. **GVL**：新增上表变量 + `Cfg_rVisVelMaxX/Y/Z/R`、`Cfg_tVisTimeout := T#300MS`。
6. **设备树**：40502 增加 Channel 03/04。
7. **Gateway**：`modbus-master` 增写 `VIS_CMD`、读 `VIS_STATUS`；新增 `/vision/*` HTTP API（见 `docs/plc/VISION_AXIS_API.md`）。

## 6. 仲裁与安全

- 优先级：**安全（急停/锁存/轴故障） > 停止/复位 > 视觉直控 > WebHMI > 面板**。
- 视觉直控进入条件（全部满足）：`Vis_xEnable`、`Vis_xOnline`、`xSafe`、手动模式、无轴故障。
- **看门狗**：`Vis_wSeq`（或 heartbeat）300ms 不变 → 退出直控并减速停（`Halt`），状态 `online=false`。
- **限幅**：速度上限 `Cfg_rVisVelMax*`；位置钳位到软限位（Y/Z/R）；X 视现场决定是否加 `Cfg_rLimX*`。
- **使能/报警 PLC 独占**：视觉不可 enable/disable 驱动器、不可清报警（`resetReq` 仅等价于「复位请求」，仍受 PLC 仲裁）。
- 急停/故障时：视觉命令被忽略，`safe=false` + `alarm` 上报，视觉应自行停止发送。

## 7. 迁移 / 兼容

- 视觉未启用时，PLC 行为与 `LMM_g_0.67.xml` **完全一致**（新块不被使用）。
- 视觉与 WebHMI 可同时在线，但**运动源互斥**（视觉活跃时 Web 运动被忽略，Web 仍可停止/复位）。
- 分阶段：① 设备树加通道 + GVL + `PRG_Vision` 只读（先打通读位置/力）→ ② 单轴速度 → ③ 单轴定位 → ④ X 双驱/全轴 → ⑤ 联调验收。

## 8. 验收

- [ ] 视觉未连接：与 0.67 行为一致。
- [ ] 读：X/Y/Z/R 位置、速度、力 与 HMI 一致。
- [ ] 写：单轴速度、单轴绝对/相对位置生效；X 双驱 M1/M2 差速。
- [ ] 看门狗：停止发送 300ms 内轴减速停，`online=false`。
- [ ] 急停/故障：命令被拒、`safe=false`、不上报假动作。
- [ ] 与 WebHMI 互斥：视觉运动时 Web 点动无效，Web/面板「停止」「复位」始终有效。

## 9. 影响文件（预估）

`plc/GVL.st`、`plc/g/PRG_Vision.st`（新）、`plc/g/PRG_TcpHmi.st`、`plc/g/PRG_Logic.st`、设备树（InoProShop）、`config/modbus-map.json`、`gateway/lib/modbus-master.js`、`gateway/server.js`、`docs/plc/*`。
