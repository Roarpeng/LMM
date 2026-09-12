# 全轴直控（视觉 / WebHMI 同一接口）设计

日期：2026-09-12
状态：设计（待评审，**未实现**）
入口：change-request
基线：LMM_g_0.67.xml、Gateway（唯一 Modbus 主站）、WebHMI v3

## 0. 结论（对上一版设计的修订）

- 视觉工控机**也运行 WebHMI**，与操作员**共用同一套接口**：Gateway WebSocket/JSON + WebHMI 页面。
- 因此**不新增 /vision/* 协议**；把「每轴直控」纳入**现有命令/状态映射与 WS 契约**（t:"w" / t:"s"）。
- 接口侧：新增字段进同一 WS 消息；WebHMI 新增「直控」页；视觉可直接开该页，或按同一协议脚本化。
- PLC 侧：把命令/状态镜像 **64W → 96W**（同一 FC16/FC03，单请求在上限内），新增每轴 方式/速度/位置 与反馈。
- **电机使能、报警、限位、急停仍 PLC 独占**。

## 1. 为什么扩展到 96 字

- 现有命令镜像（Holding 4096..4159）64 字仅剩 offset 60..62 三个自由字。
- 每轴直控需 方式1 + 速度1 + 位置2；4 轴约 15 字。
- Modbus：单次读 ≤125 字、写 ≤123 字 → **96W 可一次读写**（现有 60+1 分块改为 95+1）。
- 保持「一套镜像、一套 WS 消息」，且**不动已验证字段的 offset**。

## 2. 命令区新增（offset 60..94，尾部序号 63→95）

| offset | 字段 | 类型 | 说明 |
|---:|---|---|---|
| 60 | HMI_iDirectModeX | UINT | 0 idle / 1 vel / 2 posAbs / 3 posRel |
| 61-62 | HMI_rDirectPosX | SCALED_DINT ×1000 | X 目标位置 m |
| 63 | HMI_iDirectModeY | UINT | |
| 64 | HMI_rDirectVelY | SCALED_INT ×1000 | m/s |
| 65-66 | HMI_rDirectPosY | SCALED_DINT ×1000 | m |
| 67 | HMI_iDirectModeZ | UINT | |
| 68 | HMI_rDirectVelZ | SCALED_INT ×1000 | m/s |
| 69-70 | HMI_rDirectPosZ | SCALED_DINT ×1000 | m |
| 71 | HMI_iDirectModeR | UINT | |
| 72 | HMI_rDirectVelR | SCALED_INT ×1000 | 工程单位/s |
| 73-74 | HMI_rDirectPosR | SCALED_DINT ×1000 | 工程单位 |
| 75 | HMI_wDirectSeq | UINT | 客户端直控心跳（每周期 +1，看门狗） |
| 76-94 | 预留 | | |
| 95 | tailSequence | WORD | 尾部序号（原 63） |

- X 速度沿用现有 HMI_rVelM1Set / HMI_rVelM2Set（offset 54/55）。
- 直控总开关沿用 HMI_xDirectEnable（布尔，见 word5 bit10）。

## 3. 状态区新增（offset 39..44，尾部序号 63→95）

| offset | 字段 | 类型 | 说明 |
|---:|---|---|---|
| 39 | AxisFb_rVelActY | SCALED_INT ×1000 | Y 实际速度 m/s |
| 40 | AxisFb_rVelActZ | SCALED_INT ×1000 | Z 实际速度 |
| 41 | AxisFb_rVelActR | SCALED_INT ×1000 | R 实际速度 |
| 42 | Direct2_flags | WORD | bit0 X在役 / bit1 Y / bit2 Z / bit3 R / bit4 在线 / bit5 安全 |
| 43 | Direct2_seqEcho | UINT | 直控心跳回显 |
| 95 | tailSequence | WORD | 尾部序号（原 63） |

- X M1/M2 实际速度已在 32/34；力在 12；X/Y/Z/R 位置在 14..22（均不变）。

## 4. 写者矩阵（Gate C）

| 变量 | 类型 | 唯一写者 | 读者 |
|------|------|----------|------|
| MB_CmdIn / MB_StatusOut | ARRAY[0..95] OF WORD | 设备 I/O（Gateway 主站） | PRG_TcpHmi |
| Tcp_* 直控影子 | — | PRG_TcpHmi | PRG_Logic |
| AxisCmd_* | — | PRG_Logic | PRG_Axis_Control |
| AxisFb_* | — | PRG_Axis_Control | PRG_TcpHmi |
| HMI_iDirectMode*/HMI_rDirect* | — | PRG_TcpHmi（解码） | PRG_Logic |

## 5. PLC 修改清单

1. GVL：MB_CmdIn / MB_StatusOut 由 ARRAY[0..63] → **ARRAY[0..95]**；新增第 2/3 节变量与
   Cfg_rDirectVelMaxX/Y/Z/R、Cfg_tDirectTimeout := T#300MS。
2. PRG_TcpHmi：解码/编码新增字段；**尾部序号 63 → 95**；状态清零循环 FOR i := 5 TO 62 → **5 TO 94**；
   新增每轴实际速度编码（39/40/41）与直控状态字（42）。
3. PRG_Logic：新增「直控路由」——HMI_xDirectEnable 且安全且手动时，用 HMI_iDirectMode*/HMI_rDirect*/HMI_rVelM1Set/M2Set 生成 AxisCmd_*；
   每轴限幅与软限位；HMI_wDirectSeq 300ms 不变 → 退出直控 + Halt。
4. PRG_Axis_Control：**不变**（仍只消费 AxisCmd_*；Y/Z/R 用 FB_Servo 速度/定位，X 用 FB_XDual 直控）。
5. 设备树（InoProShop 40502 从站）：两条通道 ARRAY[0..63] → **ARRAY[0..95]**；
   Holding 0x1000..105F（命令）/ 0x1100..115F（状态）；%IW103/%QW44 起始不变。
6. Gateway：config/modbus-map.json imageWords 64→96、tailSequence 63→95、新增字段；
   modbus-master 分块 60+1 → 95+1；generate_modbus_map.py 与测试同步；WebHMI v3 新增「直控」页。

## 6. 仲裁 / 看门狗 / 限幅 / 安全

- 操作员与视觉**共用 WS**：由 Gateway **单写者租约**决定谁在写；PLC 不必区分来源（eCtrlSrc 仍 0/1）。
- 优先级：**安全（急停/锁存/轴故障） > 停止/复位 > 直控 > 普通点动/自动**。
- 直控进入条件：HMI_xDirectEnable 且手动模式 且 xSafe 且无轴故障。
- 看门狗：HMI_wDirectSeq 300ms 不变 → 退出直控并减速停。
- 限幅：速度上限 Cfg_rDirectVelMax*；位置钳位到软限位（Y/Z/R）。
- 使能/报警 PLC 独占：直控**不能** enable/disable 伺服、不能清报警；急停/故障时命令被忽略并 Halt。

## 7. 兼容 / 迁移

- 不启用直控时，行为与 LMM_g_0.67.xml 完全一致（新字段为 0）。
- 现有字段 offset 全部不变；仅镜像长度与尾部序号变化。
- 分阶段：① 只读每轴速度/位置/力 → ② 单轴速度 → ③ 单轴定位 → ④ X 双驱/全轴 → ⑤ 联调。

## 8. 验收

- [ ] 未启用直控：与 0.67 行为一致。
- [ ] 读：X/Y/Z/R 实际速度、位置、力 与 HMI 一致。
- [ ] 写：单轴速度、单轴绝对/相对位置生效；X 双驱 M1/M2 差速。
- [ ] 看门狗：停止发送 300ms 内减速停，在线位清零。
- [ ] 急停/故障：命令被拒、Halt、报警上报。
- [ ] WebHMI 与视觉同一页面/协议均可操作；写租约互斥正确。

## 9. 影响文件

plc/GVL.st、plc/g/PRG_TcpHmi.st、plc/g/PRG_Logic.st、设备树（InoProShop）、
config/modbus-map.json、gateway/lib/modbus-master.js、tools/generate_modbus_map.py、
gateway/test/modbus-codec.test.js、web/live/*（新增直控页）、docs/plc/*。
