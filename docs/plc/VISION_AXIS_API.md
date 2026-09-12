# 视觉工控机直控轴 —— WebHMI 接口开放文档（v1 草案）

> 视觉工控机与操作员**共用同一套 WebHMI**：同一 Gateway WebSocket/JSON 契约、同一页面。
> 本文档说明如何用**现有 WS 接口**控制每个轴（写速度 / 位置）并读取位置、速度、力。
> 职责边界：**电机使能、报警、限位、急停由 PLC 全权负责**；视觉只发运动请求、读反馈。
> 状态：草案，对应设计 docs/superpowers/specs/2026-09-12-vision-axis-control-design.md（尚未实现）。

## 1. 架构

    视觉工控机 / 操作员浏览器 ──WebSocket JSON──▶ Gateway（唯一 Modbus TCP 主站） ──Modbus TCP──▶ PLC（192.168.1.88:502）

- 视觉**不直连 PLC**；PLC 从站只允许 1 个主站，即 Gateway。
- 视觉用的就是**现在这套**：同一 WS 地址、同一消息类型、同一 WebHMI 页面。
- 本次新增的只是**每轴直控字段**（原来只有 X 双驱直控）。

## 2. 连接

| 项 | 值 |
|----|-----|
| 地址 | ws://<gateway-host>:8080 |
| 发送 | {"t":"w", 字段...} 写命令（可只带要写的字段，网关按字段合并） |
| 接收 | {"t":"s", 字段...} 状态广播 |
| 保活 | 发 {"t":"ping"}，收 {"t":"pong"} |
| 写租约 | 收 {"t":"lease","owner":...}；owner 为当前写者。操作员与视觉由租约互斥 |

> **直控写入必须同时带上 HMI_xEStop:true 与 HMI_xStop:false**（网关 fail-safe 缺省会请求急停）。

## 3. 每轴直控字段（t:"w"）

| 字段 | 类型 | 单位 | 说明 |
|------|------|------|------|
| HMI_xDirectEnable | bool | — | 直控总请求（沿用现有字段） |
| HMI_wDirectSeq | int | — | 直控心跳，每周期 +1（PLC 300ms 看门狗） |
| HMI_iDirectModeX | int | — | 0 idle / 1 vel / 2 posAbs / 3 posRel |
| HMI_rVelM1Set | number | m/s | X 双驱 M1 速度 |
| HMI_rVelM2Set | number | m/s | X 双驱 M2 速度（可差速） |
| HMI_rDirectPosX | number | m | X 目标位置 |
| HMI_iDirectModeY | int | — | 同 X 的 mode |
| HMI_rDirectVelY | number | m/s | Y 速度 |
| HMI_rDirectPosY | number | m | Y 目标位置 |
| HMI_iDirectModeZ | int | — | |
| HMI_rDirectVelZ | number | m/s | Z 速度 |
| HMI_rDirectPosZ | number | m | Z 目标位置 |
| HMI_iDirectModeR | int | — | |
| HMI_rDirectVelR | number | 工程单位/s | R 速度 |
| HMI_rDirectPosR | number | 工程单位 | R 目标位置 |

语义：

- vel：按给定速度持续运动，直到收到新命令或退出直控。
- posAbs：绝对定位到目标位置（X 由两电机同步）。
- posRel：相对当前位置移动。
- idle：该轴不动（减速停）。
- 未出现的轴按 idle；X 速度用 HMI_rVelM1Set/M2Set，不用 HMI_rDirectVelX。

## 4. 状态字段（t:"s"）

沿用现有状态字段，新增：

| 字段 | 类型 | 说明 |
|------|------|------|
| AxisFb_rPosM1 / rPosM2 | number | X 双驱位置 m |
| AxisFb_rPosY / rPosZ / rPosR | number | 各轴位置 |
| AxisFb_rVelActM1 / rVelActM2 | number | X 双驱实际速度 m/s |
| AxisFb_rVelActY / rVelActZ / rVelActR | number | 各轴实际速度（**本次新增**） |
| AxisFb_rSyncErr | number | X 同步误差 |
| Direct2_flags | int | bit0 X 在役 / bit1 Y / bit2 Z / bit3 R / bit4 在线 / bit5 安全（**本次新增**） |
| Direct2_seqEcho | int | 心跳回显（**本次新增**） |
| HMI_rForceShow | number | 力 N |
| HMI_iAlarmShow | int | 报警号：1001 急停 / 1002 轴故障 / 1003 限位 / 1005 力超时 / 1006 力从站失败 / 1007 使能未就绪 / 0 正常 |
| HMI_xLampEStop / HMI_xDevRun / HMI_xDevError | bool | 急停灯 / 运行 / 故障 |
| AxisFb_xReady | bool | 全轴就绪 |

## 5. 控制流程

1. 收 {"t":"s"} 确认 AxisFb_xReady=true、HMI_iAlarmShow=0、HMI_xLampEStop=false（安全）。
2. 每 **20–50ms** 发一条 {"t":"w"}，带 HMI_xDirectEnable:true、HMI_wDirectSeq 递增、目标轴字段，以及 HMI_xEStop:true、HMI_xStop:false。
3. 结束：发 HMI_xDirectEnable:false（并停止递增）；必要时 HMI_xStop:true。

## 6. 单位与符号

| 量 | 单位 | 说明 |
|----|------|------|
| X/Y/Z 位置 | 米 (m) | 与 HMI 一致 |
| X/Y/Z 速度 | 米/秒 (m/s) | 带符号，正=标定正方向 |
| R 位置/速度 | 驱动器工程单位（HMI 按 ° 显示） | 顺时针为正 |
| 力 | 牛顿 (N) | 方向见标定 |

## 7. 时序与看门狗（重要）

- 命令周期 20–50ms。
- 超过 **300ms** 未收到带 HMI_wDirectSeq 变化的写入 → PLC 退出直控并**减速停**。
- 视觉进程异常/网络断开时机器会自己停下。

## 8. 安全规则（必读）

1. 视觉不是安全回路；PLC 的急停、限位、报警永远优先。
2. HMI_iAlarmShow != 0 或 HMI_xLampEStop=true 时不要发运动命令，并退出直控。
3. PLC 可能随时因急停/停止/故障覆盖；以 t:"s" 状态为准。
4. 速度/位置会被 PLC 限幅与软限位钳位。
5. 视觉不能 enable/disable 伺服、不能清报警；HMI_xDirectEnable 只是「请求直控」。
6. 操作员与视觉共用写接口，由网关写租约互斥；被他人持有时应等待。

## 9. Python 示例

    import json, time, websocket

    GW = "ws://192.168.1.50:8080"
    ws = websocket.create_connection(GW, timeout=1)
    seq = 0

    def send(**fields):
        base = {"t": "w", "HMI_xEStop": True, "HMI_xStop": False}
        base.update(fields)
        ws.send(json.dumps(base))

    # 1) 等状态且安全
    while True:
        st = json.loads(ws.recv())
        if st.get("t") == "s":
            assert st.get("HMI_iAlarmShow", 0) == 0, st.get("HMI_iAlarmShow")
            break

    # 2) X 双驱 0.3 m/s + Y 绝对定位 1.2 m
    while True:
        seq += 1
        send(HMI_xDirectEnable=True, HMI_wDirectSeq=seq,
             HMI_iDirectModeX=1, HMI_rVelM1Set=0.30, HMI_rVelM2Set=0.30,
             HMI_iDirectModeY=2, HMI_rDirectPosY=1.200, HMI_rDirectVelY=0.30,
             HMI_iDirectModeZ=0, HMI_iDirectModeR=0)
        time.sleep(0.03)
        st = json.loads(ws.recv())
        if st.get("t") == "s" and abs(st.get("AxisFb_rPosY", 0) - 1.2) < 0.001:
            break

    # 3) 退出直控
    send(HMI_xDirectEnable=False)

注：真实使用建议用非阻塞收（后台线程收 t:"s"，主循环发 t:"w"），保证 20–50ms 发送周期。

## 10. 页面

WebHMI v3 将新增「直控」页：每轴 模式 / 速度 / 位置 输入与实时回读。视觉工控机可直接打开同一页面手动操作，也可按第 3–5 节脚本化。

## 11. 被拒/边界

- 急停/故障/未就绪：命令被忽略，状态 unsafe，轴不动。
- 自动模式：直控需手动模式（HMI_xAutoMode=false）。
- 越界：速度/位置被限幅或钳位。
- 心率丢失：300ms 内自动退出直控。

## 12. 版本

| 版本 | 日期 | 说明 |
|------|------|------|
| v1 草案 | 2026-09-12 | 首版；与现有 WebHMI 同一 WS 契约，新增每轴直控字段 |

> 变更只追加字段，不删除既有字段。
