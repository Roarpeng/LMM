# 视觉工控机直控轴 —— 开放接口文档（v1 草案）

> 面向：视觉工控机开发人员
> 目标：通过 WebHMI 网关（Gateway）接口直接控制每个轴（写速度 / 写位置），并读取位置、速度、力矩。
> 职责边界：**电机使能、报警、限位、急停由 PLC 全权负责**；视觉只发运动请求、读反馈。
> 状态：接口草案，对应设计 docs/superpowers/specs/2026-09-12-vision-axis-control-design.md（尚未实现）。实现后本文档即现场契约。

## 1. 架构

    视觉工控机 ──HTTP JSON /vision/*──▶ Gateway（唯一 Modbus TCP 主站） ──Modbus TCP──▶ PLC（从站 192.168.1.88:502）
    浏览器 WebHMI ──WebSocket──────────▶ Gateway

- 视觉**不要直连 PLC**：PLC 从站只允许 1 个主站，主站就是 Gateway。
- 视觉使用独立的 /vision/* HTTP 接口，**不占用浏览器 WebSocket 写租约**，互不干扰。

## 2. 连接

| 项 | 值 |
|----|-----|
| Base URL | http://<gateway-host>:8080 |
| 方法 / 编码 | HTTP + JSON，Content-Type: application/json; charset=utf-8 |
| 鉴权 | 局域网内暂无（如需可后续加 token 头） |
| 连接数 | 建议单连接，不要高并发 |

## 3. 单位与符号约定

| 量 | 单位 | 说明 |
|----|------|------|
| X / Y / Z 位置 | 米 (m) | 与 HMI 显示一致 |
| X / Y / Z 速度 | 米/秒 (m/s) | 带符号，正 = 标定正方向 |
| R 位置 / 速度 | 驱动器工程单位（HMI 按 ° 显示） | 顺时针为正 |
| 力 | 牛顿 (N) | 拉/压方向见标定 |
| 精度 | 位置/速度 0.001，力 0.01 | 协议内部 ×1000 / ×100 |

## 4. 读取状态

**GET /vision/state**

返回 200：

    {
      "t": "vision-state",
      "ts": 1789190000123,
      "link": { "gateway": true, "plc": true, "online": true, "ageMs": 12 },
      "safe": true,
      "estop": false,
      "source": "vision",
      "alarm": 0,
      "axes": {
        "x": { "posM1": 1.2340, "posM2": 1.2300, "velM1": 0.300, "velM2": 0.300,
               "syncErr": 0.0040, "moving": true, "ready": true, "fault": false },
        "y": { "pos": 0.5200, "vel": 0.000, "moving": false, "ready": true, "fault": false, "homed": false },
        "z": { "pos": -0.0420, "vel": 0.000, "moving": false, "ready": true, "fault": false, "homed": true },
        "r": { "pos": 0.0000, "vel": 0.000, "moving": false, "ready": true, "fault": false, "homed": true }
      },
      "force": { "n": 12.30, "raw": 1230, "commOk": true, "timeout": false, "slaveFail": false }
    }

| 字段 | 说明 |
|------|------|
| link.plc | Gateway 与 PLC 是否在线 |
| safe | PLC 判断当前可运行（无急停锁存、无故障）。**false 时不要发运动命令** |
| source | 当前运动源：panel / web / vision / none |
| alarm | 1001 急停 · 1002 轴故障 · 1003 限位 · 1005 力超时 · 1006 力从站失败 · 1007 使能未就绪 · 0 正常 |
| axes.x.posM1 / posM2 | X 双驱两电机实际位置 |
| axes.x.velM1 / velM2 | X 双驱两电机实际速度 |
| axes.x.syncErr | X 双驱同步误差（M1 − M2） |
| axes.y/z/r.pos / vel | 各轴实际位置 / 速度 |
| axes.*.ready / fault / homed / moving | 轴状态位 |
| force.n / raw / commOk | 实际力 / 原始计数 / 力传感器通讯 |

## 5. 发送运动命令

**POST /vision/cmd**

请求体：

    {
      "enable": true,
      "seq": 1024,
      "axes": {
        "x": { "mode": "velocity", "v1": 0.300, "v2": 0.300 },
        "y": { "mode": "position", "pos": 1.2000, "vel": 0.300 },
        "z": { "mode": "velocity", "v": -0.050 },
        "r": { "mode": "hold" }
      }
    }

| 字段 | 类型 | 说明 |
|------|------|------|
| enable | bool | true = 请求直控；false = 释放直控。**不是伺服使能**（使能仍由 PLC 负责） |
| seq | int | 客户端自增序号，用于回显 / 对账（建议每次 +1） |
| axes | object | 只写需要动的轴；未出现的轴按 idle 处理 |
| mode | string | idle / velocity / position / relative / hold |
| v | number | 速度 m/s（Y / Z / R） |
| v1 / v2 | number | X 双驱 M1 / M2 速度 m/s（可差速） |
| pos | number | 目标位置（position 绝对 / relative 相对） |
| vel | number | 定位速度上限（可选） |

语义：

- velocity：按给定速度持续运动，直到收到新命令或 stop。
- position：绝对定位到 pos（X 用两电机同步到同一位置）。
- relative：相对当前位置移动 pos。
- hold：保持当前位（Z 力保持沿用 PLC 现有逻辑，视觉不发力指令）。
- idle：该轴不动（减速停）。

响应 200：

    { "ok": true, "seq": 1024, "source": "vision", "safe": true }

失败：

    { "ok": false, "code": "NOT_SAFE", "msg": "PLC not safe (alarm 1001)" }

## 6. 停止 / 释放

**POST /vision/stop**

立即释放直控：所有轴减速停（PLC 仍保持使能），source 归还给面板 / Web。

## 7. 时序与看门狗（重要）

- 命令周期：每 **20–50 ms** 发一次 POST /vision/cmd（与视觉帧率一致）。
- 看门狗：超过 **300 ms** 未收到命令 → Gateway / PLC 自动退出直控并**减速停**，source 归还。
- 视觉进程异常或网络断开时机器会自己停下，不会失控。
- 建议：主循环内发送；若图像处理耗时，发送线程应独立。

## 8. 安全规则（必读）

1. 视觉**不是安全回路**；PLC 的急停、限位、报警永远优先。
2. safe=false 或 alarm != 0 时**不要发运动命令**，并主动 POST /vision/stop。
3. PLC 可能在任何时刻因急停 / 停止 / 故障覆盖视觉命令；以 GET /vision/state 为准。
4. 速度 / 位置会被 PLC **限幅与软限位钳位**；越界可能被拒绝或钳位。
5. 不要依赖「命令下达即到位」；按 axes.*.pos / vel 反馈做闭环。
6. 视觉不能用本接口 enable / disable 伺服，也不能清报警；enable 只是「请求直控」。

## 9. 错误码

| code | 场景 | HTTP |
|------|------|------|
| NOT_SAFE | 急停 / 锁存 / 轴故障，PLC 拒绝运动 | 200（看 ok=false） |
| NOT_ONLINE | Gateway 或 PLC 离线 | 503 |
| AUTO_MODE | 当前自动模式，直控需手动模式 | 409 |
| BAD_AXIS / BAD_MODE | 轴名 / 模式非法 | 400 |
| RANGE | 数值越界 | 400 |

## 10. Python 示例

    import requests, time

    GW = "http://192.168.1.50:8080"   # Gateway 地址
    seq = 0

    def cmd(payload):
        global seq
        seq += 1
        payload["seq"] = seq
        r = requests.post(GW + "/vision/cmd", json=payload, timeout=0.1)
        return r.json()

    # 1) 读状态
    st = requests.get(GW + "/vision/state", timeout=0.2).json()
    assert st["safe"], ("not safe", st["alarm"])

    # 2) X 双驱 0.3 m/s 前进 + Y 绝对定位到 1.2 m
    while True:
        res = cmd({
            "enable": True,
            "axes": {
                "x": {"mode": "velocity", "v1": 0.30, "v2": 0.30},
                "y": {"mode": "position", "pos": 1.200, "vel": 0.30},
                "z": {"mode": "idle"},
                "r": {"mode": "idle"},
            },
        })
        if not res.get("ok"):
            print("cmd rejected:", res); break
        st = requests.get(GW + "/vision/state", timeout=0.1).json()
        if st["axes"]["y"]["pos"] >= 1.199 and not st["axes"]["y"]["moving"]:
            break
        time.sleep(0.02)

    # 3) 停止
    requests.post(GW + "/vision/stop", timeout=0.2)

## 11. 版本与变更

| 版本 | 日期 | 说明 |
|------|------|------|
| v1 草案 | 2026-09-12 | 首版；对应设计 spec 2026-09-12-vision-axis-control-design.md |

> 实现顺序建议：① 只读状态 → ② 单轴速度 → ③ 单轴定位 → ④ X 双驱 / 全轴 → ⑤ 联调。
> 变更只追加字段，不删除既有字段。
