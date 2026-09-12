# X 双电机速度透传 + WebHMI v2 设计

日期：2026-09-12
状态：设计已确认（change-request；Web 先行，PLC 0.63 随后）
基线：`LMM_g_0.62.xml`（在役；InoProShop 重存，设备树已配好 Modbus TCP 从站，外部 client 连 `192.168.1.88:502` 已验证可连）

## 背景 / 现场确认

- 通讯方向**保持仓库现状**：Gateway = Modbus TCP **主站**，PLC = **从站**（`192.168.1.88:502`）。现场用 Modbus 调试工具设为 **client** 连 `:502` 成功，说明该端口是**从站**，与仓库一致，无需对调角色。
- X 两电机实际速度**早已在 PLC 内计算**：`plc/g/FB_XDual.st` 中 `rVelActM1/A2 := AxisM1/M2.fActVelocity`，经 `PRG_Axis_Control` 写入 `Direct_rVelM1Act/M2Act`，再编码到状态 **word29/30**（每周期无条件写，手动/自动/直控模式都有效）。Gateway 也已随状态镜像广播。**缺口只在 Web 没显示、字段名偏「视觉直控」。**

## 目标

1. **WebHMI v2**：把 `web/live/index.html` 升级为多页签操作台（自动 / 手动 / X 双驱 / 调试 / 日志），排版与响应速度优化，尽量接近实时。
2. **X 速度透传（Web 先行）**：Web 大字显示 M1/M2 **实际速度**、速度指令、ΔVel、同步差与趋势，**无需重烧 PLC**。
3. **X 速度透传（PLC 0.63）**：新增通用状态字 `AxisFb_rVelActM1/M2` + 运动/使能/同步位 + `AxisFb_rSyncErr`，语义脱离「视觉直控」。
4. 调试能力：键盘点动、X 直控 M1/M2 滑条、原始寄存器表 + 白名单命令控制台、快照/趋势。

## 非目标

- 不改通讯方向，不引入第二套 HMI 协议，不改轴运动/力控/自动步序逻辑。
- 不把 HMI 做成安全等级急停（Web 急停仍是请求，物理急停 AND 仲裁不变）。

## 寄存器增量（0.63 新增，仅状态区）

| Holding | word | 变量 | 类型 | 说明 |
|---|---|---|---|---|
| 1132 | 32 | `AxisFb_rVelActM1` | SCALED_DINT ×1000 | M1 实际速度 m/s（2 word） |
| 1134 | 34 | `AxisFb_rVelActM2` | SCALED_DINT ×1000 | M2 实际速度 m/s（2 word） |
| 1136 | 36 | `AxisFb_xMovingM1/M2` `xPoweredM1/M2` `xSyncWarn` `xSyncFault` | BOOL 位 | bit0..5 |
| 1137 | 37 | `AxisFb_rSyncErr` | SCALED_DINT ×1000 | M1−M2 同步误差 m（2 word） |

- 命令区**不变**（1000..1063）。原有 `Direct_rVelM1Act/M2Act`（word29/30）**保留**，做兼容。
- word13/15/17/19/21/23/25/27 及 32..62 为空闲，插入后仍无重叠（`tools/generate_modbus_map.py` 校验）。

## 架构（不变）

```
浏览器 --WS/JSON--> Gateway（Modbus TCP 主站）--TCP--> PLC（从站）192.168.1.88:502
                      ├─ FC16 写 Holding 1000..1063（命令）
                      └─ FC03 读 Holding 1100..1163（状态，64 WORD）
视觉工控机 --HTTP POST /vision--> Gateway（唯一主站，中继到 word56..59）
```

## 实时性（"能做到实时吗"）

- 链路是**事件驱动推送**：Gateway 每个轮询周期把整帧状态 `t:"s"` 推给所有浏览器；不是浏览器轮询。
- 默认轮询 `PLC_POLL_MS` 从 100ms 下调为 **50ms**（可用环境变量覆盖），端到端典型 **50–120ms**。
- Web 端：`requestAnimationFrame` 合帧、仅更新变化的 DOM、速度显示本地线性外推，避免整页重绘。
- 这是遥测/操作 HMI，**不需要 WebRTC**；WS 二进制/数据通道与普通 WS 延迟同量级，收益不足以抵消复杂度。
- 提供 ping/pong 往返延迟指示，现场可量化。

## 组件职责

- `config/modbus-map.json`：状态区新增字段（单一契约来源）。
- `gateway/lib/modbus-store.js` / `modbus-codec.js`：无需改；按 map 自动解码。
- `gateway/lib/mock-plc.js`：补 `Direct_*` 与新字段，离页 Mock 也能看到速度。
- `gateway/lib/modbus-master.js`：增加 `getDiagnostics()`（connected / 最近成功 / 错误计数）。
- `gateway/server.js`：`GET /health`；写租约变化广播 `t:"lease"`；离线状态合并新字段；`PLC_POLL_MS` 默认 50。
- `web/live/index.html`：v2 操作台（本迭代主体）。
- `plc/g/PRG_Axis_Control.st` + `tools/patch_g063.py` → `LMM_g_0.63.xml`（G/VL + TcpHmi 状态编码行插入，字节安全、幂等）。

## 验收

- [ ] `cd gateway && npm test` 全绿（含「live page mentions every map field」）。
- [ ] `python3 tools/generate_modbus_map.py` 通过且 `MODBUS_MAP.md` 更新。
- [ ] Mock 启动 `tools/start-webhmi.ps1 -Mock`：四个页签可切；点动按住动、松开停；X 双驱页显示 M1/M2 实际速度；调试页可写白名单；趋势/快照可用。
- [ ] 真机：Web 点动/自动/急停与面板一致；X 双驱页实际速度跟随。
- [ ] PLC 0.63：InoProShop 导入编译 0 错；word32/34/36/37 与 Web 对应；烧录后 Gate D 联调。
