# 视觉工控机直控 —— WebHMI 接口开放文档（v1 草案）

> 视觉工控机与操作员**共用同一套 WebHMI**：同一 Gateway WebSocket/JSON 契约、同一页面、同一写租约。
> 覆盖：**5 个电机（M1、M2、Y、Z、R）写速度 / 读速度 / 读位置；Y/Z/R 写位置；X 整机写位置；力当前值（读）/ 力设定目标（写）**。
> 职责边界：**电机使能、报警、限位、急停由 PLC 全权负责**。
> 对应设计：docs/superpowers/specs/2026-09-12-vision-axis-control-design.md（尚未实现）。

## 0. 关键约定：M1/M2 是速度环，不单独写位置

- M1/M2 走**速度环**（FB_XDual 只收速度指令）；位置不是驱动原生输入。
- X 的**位置**是整机层约束：目标位置 → 速度斜坡 → 分给 M1/M2（含同步）。
- M1/M2 同梁机械耦合，两个不同绝对位置会扭梁；只允许小幅调平，不允许独立定位。
- 因此：**M1/M2 只写速度、读位置/速度**；X 写位置用**单一整机目标** HMI_rDirectPosX；
  或者视觉自己做外环（写 M1/M2 速度 + 读位置，到目标即减速），此时不使用 HMI_rDirectPosX。

## 1. 能力覆盖清单

| 需求 | 字段 | 说明 |
|------|------|------|
| M1 写速度 | HMI_rVelM1Set | 已有 |
| M2 写速度 | HMI_rVelM2Set | 已有 |
| Y 写速度 | HMI_rDirectVelY | 新增 |
| Z 写速度 | HMI_rDirectVelZ | 新增 |
| R 写速度 | HMI_rDirectVelR | 新增 |
| M1/M2 写位置 | （不提供单独位置） | 速度环 + 机械耦合，见第 0 节 |
| X 写位置 | HMI_rDirectPosX | 整机目标（可选；上层速度斜坡） |
| Y/Z/R 写位置 | HMI_rDirectPosY / Z / R | 新增（FB_Servo 原生定位） |
| M1/M2 读速度 | AxisFb_rVelActM1 / M2 | 0.63 已有 |
| Y/Z/R 读速度 | AxisFb_rVelActY / Z / R | 新增 |
| 5 电机读位置 | AxisFb_rPosM1 / M2 / Y / Z / R | 已有 |
| 力当前值（读） | HMI_rForceShow | 已有 |
| 力设定目标（写） | HMI_rForceSet | 已有（offset 28） |
| 力设定回显（读） | HMI_rForceSetEcho | 新增（可选） |
| 直控总开关 | HMI_xDirectEnable | 已有 |
| 直控心跳 | HMI_wDirectSeq | 新增（300ms 看门狗） |

## 2. 连接

| 项 | 值 |
|----|-----|
| 地址 | ws://<gateway-host>:8080 |
| 发送 | {"t":"w", 字段...} 写命令（可只带要写的字段，网关按字段合并） |
| 接收 | {"t":"s", 字段...} 状态广播 |
| 保活 | 发 {"t":"ping"}，收 {"t":"pong"} |
| 写租约 | 收 {"t":"lease","owner":...}；操作员与视觉由租约互斥 |

> **直控写入必须同时带 HMI_xEStop:true 与 HMI_xStop:false**（网关 fail-safe 缺省会请求急停）。

## 3. 写：直控命令（t:"w"）

### 3.1 总开关与心跳

| 字段 | 类型 | 说明 |
|------|------|------|
| HMI_xDirectEnable | bool | 直控总请求；false = 释放直控 |
| HMI_wDirectSeq | int | 直控心跳，每周期 +1（PLC 300ms 看门狗，必须递增） |

### 3.2 X 双驱（速度环）

| 字段 | 类型 | 单位 | 说明 |
|------|------|------|------|
| HMI_iDirectModeX | int | — | 0 idle / 1 vel（X 无 pos 模式） |
| HMI_rVelM1Set | number | m/s | X 电机 M1 速度 |
| HMI_rVelM2Set | number | m/s | X 电机 M2 速度（可差速，用于纠偏） |
| HMI_rDirectPosX | number | m | （可选）整机 X 目标位置；由上层速度斜坡实现 |

### 3.3 Y / Z / R（支持定位）

| 字段 | 类型 | 单位 | 说明 |
|------|------|------|------|
| HMI_iDirectModeY | int | — | 0 idle / 1 vel / 2 posAbs / 3 posRel |
| HMI_rDirectVelY | number | m/s | Y 速度 |
| HMI_rDirectPosY | number | m | Y 目标位置 |
| HMI_iDirectModeZ | int | — | 同上 |
| HMI_rDirectVelZ | number | m/s | Z 速度 |
| HMI_rDirectPosZ | number | m | Z 目标位置 |
| HMI_iDirectModeR | int | — | 同上 |
| HMI_rDirectVelR | number | 工程单位/s | R 速度 |
| HMI_rDirectPosR | number | 工程单位 | R 目标位置 |

### 3.4 力设定

| 字段 | 类型 | 单位 | 说明 |
|------|------|------|------|
| HMI_rForceSet | number | N | 拉压力目标值（恒力 / 力保持） |
| HMI_xForceGuide | bool | — | 力引导（可选） |
| HMI_xForceTare / HMI_xForceUntare | bool | — | 去皮 / 取消去皮（脉冲，可选） |

语义：vel=按速度持续运动；posAbs=绝对定位；posRel=相对移动；idle=该轴减速停。未出现的轴按 idle。

## 4. 读：状态（t:"s"）

### 4.1 5 电机 位置 / 速度

| 字段 | 单位 | 说明 |
|------|------|------|
| AxisFb_rPosM1 / rPosM2 | m | X 电机 M1 / M2 实际位置 |
| AxisFb_rPosY / rPosZ / rPosR | m / 工程单位 | Y / Z / R 实际位置 |
| AxisFb_rVelActM1 / rVelActM2 | m/s | X 电机 M1 / M2 实际速度（以此为准） |
| AxisFb_rVelCmdM1 / rVelCmdM2 | m/s | X 电机 M1 / M2 指令速度 |
| AxisFb_rVelActY / rVelActZ / rVelActR | m/s | Y / Z / R 实际速度（新增） |
| AxisFb_rSyncErr | m | X 同步误差（M1−M2） |

### 4.2 力

| 字段 | 单位 | 说明 |
|------|------|------|
| HMI_rForceShow | N | 力传感器当前值 |
| HMI_rForceSetEcho | N | 当前设定目标回显（新增，可选） |
| Force_xCommOk / Force_xTimeout / Force_xSlaveFail | bool | 力传感器通讯状态 |

### 4.3 设备 / 安全 / 直控状态

| 字段 | 说明 |
|------|------|
| HMI_iAlarmShow | 0 / 1001 急停 / 1002 轴故障 / 1003 限位 / 1005 力超时 / 1006 力从站失败 / 1007 使能未就绪 |
| HMI_xLampEStop / HMI_xDevRun / HMI_xDevError | 急停灯 / 运行 / 故障 |
| AxisFb_xReady | 全轴就绪 |
| AxisFb_xFaultM1 / M2 / Y / Z / R | 各轴故障位 |
| Direct2_flags | bit0 X 在役 / bit1 Y / bit2 Z / bit3 R / bit4 在线 / bit5 安全（新增） |
| Direct2_seqEcho | 直控心跳回显（新增） |

## 5. 控制流程

1. 收 {"t":"s"} 确认 AxisFb_xReady=true、HMI_iAlarmShow=0、HMI_xLampEStop=false。
2. 每 **20–50ms** 发一条 {"t":"w"}：HMI_xDirectEnable:true、HMI_wDirectSeq 递增、目标轴字段，以及 HMI_xEStop:true、HMI_xStop:false。
3. 结束：发 HMI_xDirectEnable:false；必要时 HMI_xStop:true。

## 6. 单位与符号

| 量 | 单位 | 说明 |
|----|------|------|
| X/Y/Z 位置 | 米 (m) | 与 HMI 一致 |
| X/Y/Z 速度 | 米/秒 (m/s) | 带符号，正=标定正方向 |
| R 位置/速度 | 驱动器工程单位（HMI 按 ° 显示） | 顺时针为正 |
| 力 | 牛顿 (N) | 方向见标定 |

## 7. 时序与看门狗

- 命令周期 20–50ms。
- 超过 **300ms** 未收到带 HMI_wDirectSeq 变化的写入 → PLC 退出直控并**减速停**。
- 视觉进程异常/网络断开时机器会自己停下。

## 8. 安全规则与约束（必读）

1. 视觉不是安全回路；PLC 的急停、限位、报警永远优先。
2. HMI_iAlarmShow != 0 或 HMI_xLampEStop=true 时不要发运动命令，并退出直控。
3. PLC 可能随时因急停/停止/故障覆盖；以 t:"s" 状态为准。
4. 速度/位置会被 PLC 限幅与软限位钳位。
5. 视觉不能 enable/disable 伺服、不能清报警；HMI_xDirectEnable 只是请求直控。
6. X 不提供 M1/M2 单独位置；需要纠偏请用 HMI_rVelM1Set/HMI_rVelM2Set 差速或同步补偿参数。
7. 操作员与视觉共用写接口，由网关写租约互斥；被他人持有时应等待。
8. 力设定 HMI_rForceSet 仅在力控制/力保持生效时有意义；写入不改变使能/报警。

## 9. Python 示例

    import json, time, websocket

    GW = "ws://192.168.1.50:8080"
    ws = websocket.create_connection(GW, timeout=1)
    seq = 0

    def send(**fields):
        base = {"t": "w", "HMI_xEStop": True, "HMI_xStop": False}
        base.update(fields)
        ws.send(json.dumps(base))

    # 1) 等安全
    while True:
        st = json.loads(ws.recv())
        if st.get("t") == "s":
            assert st.get("HMI_iAlarmShow", 0) == 0
            break

    # 2) X 双驱 0.3 m/s + Y 绝对定位 1.2 m + 力设定 80 N
    while True:
        seq += 1
        send(HMI_xDirectEnable=True, HMI_wDirectSeq=seq,
             HMI_iDirectModeX=1, HMI_rVelM1Set=0.30, HMI_rVelM2Set=0.30,
             HMI_iDirectModeY=2, HMI_rDirectPosY=1.200, HMI_rDirectVelY=0.30,
             HMI_iDirectModeZ=0, HMI_iDirectModeR=0,
             HMI_rForceSet=80.0)
        time.sleep(0.03)
        st = json.loads(ws.recv())
        if st.get("t") == "s" and abs(st.get("AxisFb_rPosY", 0) - 1.2) < 0.001:
            break

    # 3) 退出直控
    send(HMI_xDirectEnable=False)

    # 备注：若想让 X 停在某位置，视觉可用「写 M1/M2 速度 + 读 AxisFb_rPosM1/M2」自行闭环，
    # 或使用 HMI_rDirectPosX 让上层做速度斜坡。

注：真实使用建议后台线程收 t:"s"，主循环发 t:"w"，保证 20–50ms 周期。

## 10. 页面

WebHMI v3 将新增「直控」页：5 电机速度、Y/Z/R 位置、X 整机位置、力设定与实时回读。视觉可直接打开同一页面操作，也可按第 3–5 节脚本化。

## 11. 被拒 / 边界

- 急停/故障/未就绪：命令被忽略，轴不动。
- 自动模式：直控需手动模式（HMI_xAutoMode=false）。
- 越界：速度/位置被限幅或钳位。
- 心跳丢失：300ms 内自动退出直控。

## 12. 版本

| 版本 | 日期 | 说明 |
|------|------|------|
| v1 草案 | 2026-09-12 | 与现有 WebHMI 同一 WS 契约；M1/M2 速度环（不单独写位置） |

> 变更只追加字段，不删除既有字段。
