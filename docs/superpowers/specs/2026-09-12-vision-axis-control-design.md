# 全轴直控（视觉 / WebHMI 同一接口）设计

日期：2026-09-12
状态：设计（待评审，**未实现**）
入口：change-request
基线：LMM_g_0.67.xml、Gateway（唯一 Modbus 主站）、WebHMI v3

## 0. 结论

- 视觉工控机**也运行 WebHMI**，与操作员**共用同一套接口**（Gateway WebSocket/JSON + 页面 + 写租约）。
- **不新增 /vision/* 协议**；把「每轴直控」纳入现有命令/状态映射与 WS 契约（t:"w" / t:"s"）。
- 覆盖：**5 个电机 写速度 / 读速度 / 读位置；Y/Z/R + 整机 X 写位置；力当前值（读）/ 力设定目标（写）**。
- PLC：命令/状态镜像 **64W → 96W**（同一 FC16/FC03，单请求在上限内）。
- **电机使能、报警、限位、急停仍 PLC 独占**。

## 0.1 M1/M2 不单独写位置（重要决策）

理由：

1. **M1/M2 走速度环**：FB_XDual 只接受速度指令（xUseVelCmd/rVelCmd），位置不是驱动原生输入；写位置必须由上层转成速度曲线。
2. **X 位置是整机层约束**：目标位置 → 速度斜坡 → 分给 M1/M2（含同步），属于上层职责，下放到单电机无物理意义。
3. **机械耦合**：M1/M2 同梁，两个不同的绝对位置 = 扭梁/卡死；只允许小幅调平修正，不允许独立定位。
4. **风险**：独立定位需在 FB_XDual 新增「独立位置」模式，是本次改动中风险最高、收益最低的一项。

因此：

- **M1/M2**：只写速度（HMI_rVelM1Set/M2Set）；读位置/速度/同步差。
- **X 写位置**：单一整机目标 HMI_rDirectPosX（上层速度斜坡实现）；或视觉自己用「写速度 + 读位置」做外环，此时不必用该字段。
- **Y/Z/R**：走 FB_Servo，写速度 + 写位置（绝对/相对）天然支持。
- 可选调平：如需微小偏正，用现有同步补偿（HMI_rKpTrack / HMI_rHeadingErr）或后续加小幅 trim（带硬限），不做双电机绝对定位。

## 1. 为什么扩展到 96 字

- 现有命令镜像（Holding 4096..4159）64 字仅剩 offset 60..62。
- 直控需要：4 模式 + 3 轴速度 + 4 轴位置(各 2 字，含整机 X) + 心跳 ≈ 16 字（X 速度沿用已有 54/55）。
- Modbus 单次读 ≤125、写 ≤123 → **96W 可一次读写**（现有 60+1 分块改为 95+1）。
- 现有字段 offset **全部不变**，仅镜像长度与尾部序号（63→95）变化。

## 2. 命令区新增（offset 60..75，尾部序号 63→95）

| offset | 字段 | 类型 | 说明 |
|---:|---|---|---|
| 60 | HMI_iDirectModeX | UINT | 0 idle / 1 vel（X 无 pos 模式） |
| 61-62 | HMI_rDirectPosX | SCALED_DINT ×1000 | （可选）整机 X 目标位置 m，上层速度斜坡实现 |
| 63 | HMI_iDirectModeY | UINT | 0 idle / 1 vel / 2 posAbs / 3 posRel |
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

已在映射内、无需新增：

| 字段 | offset | 说明 |
|---|---:|---|
| HMI_xDirectEnable | word5 bit10 | 直控总请求 |
| HMI_rVelM1Set / HMI_rVelM2Set | 54 / 55 | X 两电机速度（SCALED_INT ×1000） |
| HMI_rForceSet | 28 | **力设定目标**（SCALED_DINT ×100） |

## 3. 状态区新增（offset 39..45，尾部序号 63→95）

| offset | 字段 | 类型 | 说明 |
|---:|---|---|---|
| 39 | AxisFb_rVelActY | SCALED_INT ×1000 | Y 实际速度 m/s |
| 40 | AxisFb_rVelActZ | SCALED_INT ×1000 | Z 实际速度 |
| 41 | AxisFb_rVelActR | SCALED_INT ×1000 | R 实际速度 |
| 42 | Direct2_xActiveX/Y/Z/R | BOOL bit0..3 | 各轴直控在役 |
| 42 | Direct2_xOnline / Direct2_xSafe | BOOL bit4/5 | 心跳在线 / 安全允许 |
| 43 | Direct2_wSeqEcho | UINT | 心跳回显 |
| 44-45 | HMI_rForceSetEcho | SCALED_DINT ×100 | 力设定回显（可选） |
| 95 | tailSequence | WORD | 尾部序号（原 63） |

已有（直接用）：X/Y/Z/R 位置 AxisFb_rPosM1/M2/Y/Z/R（14/16/18/20/22）、
M1/M2 实际与指令速度（32/34、24/26）、X 同步误差（37）、力当前值 HMI_rForceShow（12）。

## 4. 写者矩阵（Gate C）

| 变量 | 类型 | 唯一写者 | 读者 |
|------|------|----------|------|
| MB_CmdIn / MB_StatusOut | ARRAY[0..95] OF WORD | 设备 I/O（Gateway 主站） | PRG_TcpHmi |
| HMI_iDirectMode*/HMI_rDirect*/HMI_wDirectSeq | — | PRG_TcpHmi（解码） | PRG_Logic |
| HMI_rForceSet | — | PRG_TcpHmi（解码） | PRG_Logic |
| AxisCmd_* | — | PRG_Logic | PRG_Axis_Control |
| AxisFb_* | — | PRG_Axis_Control | PRG_TcpHmi |
| Direct2_flags / Direct2_seqEcho | — | PRG_TcpHmi | 设备 I/O |

## 5. PLC 修改清单

1. GVL：MB_CmdIn / MB_StatusOut 由 ARRAY[0..63] → **ARRAY[0..95]**；新增第 2/3 节变量与 Cfg_rDirectVelMaxX/Y/Z/R、Cfg_tDirectTimeout := T#300MS。
2. PRG_TcpHmi：解码/编码新增字段；**尾部序号 63 → 95**；状态清零循环 FOR i := 5 TO 62 → **5 TO 94**。
3. PRG_Logic：直控路由（每轴 mode → AxisCmd_*）；限幅与软限位；HMI_wDirectSeq 300ms 不变 → 退出直控 + Halt；力设定交由现有力控制逻辑。
4. PRG_Axis_Control / FB_XDual：**不需要新增独立位置模式**。若 X 目标位置由 PLC 实现，只需在 Logic 增加一个 X 位置环/速度斜坡（远小于双电机独立定位的风险）；M1/M2 仍按速度下发。
5. 设备树（InoProShop 40502 从站）：两条通道 ARRAY[0..63] → **ARRAY[0..95]**；Holding 0x1000..105F（命令）/ 0x1100..115F（状态）；%IW103 / %QW44 起始不变。
6. Gateway：config/modbus-map.json imageWords 64→96、tailSequence 63→95、新增字段；modbus-master 分块 60+1 → 95+1；generate_modbus_map.py 与测试同步；WebHMI v3 新增「直控」页。

## 6. 仲裁 / 看门狗 / 限幅 / 安全

- 操作员与视觉**共用 WS**：由 Gateway **单写者租约**决定谁在写；PLC 不必区分来源（eCtrlSrc 仍 0/1）。
- 优先级：**安全（急停/锁存/轴故障） > 停止/复位 > 直控 > 点动/自动**。
- 直控进入条件：HMI_xDirectEnable 且手动模式 且 xSafe 且无轴故障。
- 看门狗：HMI_wDirectSeq 300ms 不变 → 退出直控并减速停。
- 限幅：速度上限 Cfg_rDirectVelMax*；位置钳位到软限位（Y/Z/R）；X 位置目标限幅在行程内。
- 使能/报警 PLC 独占：直控**不能** enable/disable 伺服、不能清报警。

## 7. 兼容 / 迁移

- 不启用直控时，行为与 LMM_g_0.67.xml 完全一致（新字段为 0）。
- 现有 offset 全部不变；仅镜像长度与尾部序号变化。
- 分阶段：① 只读 5 电机速度/位置 + 力 → ② M1/M2 速度直控 → ③ Y/Z/R 速度 → ④ Y/Z/R 定位 → ⑤（可选）X 整机位置 → ⑥ 力设定 → ⑦ 联调。

## 8. 验收

- [ ] 未启用直控：与 0.67 行为一致。
- [ ] 读：M1/M2/Y/Z/R 实际速度与位置、力当前值 与 HMI 一致。
- [ ] 写：M1/M2 速度、Y/Z/R 速度与位置生效。
- [ ] 写：HMI_rForceSet 生效并可回显。
- [ ] 看门狗：停止发送 300ms 内减速停，在线位清零。
- [ ] 急停/故障：命令被拒、Halt、报警上报。
- [ ] WebHMI 与视觉同一页面/协议均可操作；写租约互斥正确。

## 9. 影响文件

plc/GVL.st、plc/g/PRG_TcpHmi.st、plc/g/PRG_Logic.st、设备树（InoProShop）、config/modbus-map.json、gateway/lib/modbus-master.js、tools/generate_modbus_map.py、gateway/test/modbus-codec.test.js、web/live/*（直控页）、docs/plc/*。
