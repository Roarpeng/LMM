# Gateway 主站 → PLC 从站（Modbus TCP 角色对调）

日期：2026-07-25  
状态：设计已确认（方案 1：角色对调，地址表不动）

## 动机

现场 PLC 主站通道**无法配置主动连外部网络**；只能由外部设备连入 PLC。  
原架构（PLC Master 连 Gateway Server `:502`）与现场能力冲突，联调不可用。

## 目标

- Gateway 作为 Modbus TCP **主站**，主动连接 PLC **从站**
- PLC 监听并应答；不主动连 Gateway
- 保持 `config/modbus-map.json` 地址与缩放、浏览器 WS/JSON 契约不变
- WebHMI 仍可通过 Gateway 调试

## 非目标

- 不改轴运动 / 力控 / LineTrack 逻辑
- 不更换寄存器地址表（仍 Holding `1000..1063` / `1100..1163`，各 64 WORD）
- 不引入第二套 HMI 协议

## 架构

```
浏览器 ──WS/JSON──▶ Gateway（主站）──TCP──▶ PLC（从站）192.168.1.88:502 unit=1
                         │
                         ├─ FC16 写 Holding 1000..1063 = 命令（Web→PLC）
                         └─ FC03 读 Holding 1100..1163 = 状态（PLC→Web）
```

相对旧架构仅**对调谁发起请求**；命令/状态区语义不变。

| 项 | 旧 | 新 |
|----|----|----|
| PLC | Master，连 Gateway | **Slave**，监听 |
| Gateway | Server，听 `:502` | **Master**，连 PLC |
| 命令区 1000 | PLC FC03 读 Gateway | Gateway **FC16 写** PLC |
| 状态区 1100 | PLC FC16 写 Gateway | Gateway **FC03 读** PLC |

## 连接参数

| 变量 | 默认 | 说明 |
|------|------|------|
| `PLC_HOST` | `192.168.1.88` | PLC 从站 IP |
| `PLC_PORT` | `502` | Modbus TCP 端口 |
| `PLC_UNIT_ID` | `1` | Unit ID |
| `MOCK_PLC` | 未设/`0` | `1` 时本机 Mock，不连真机 |
| `HTTP_PORT` / `WS_PORT` | `8080` | WebHMI |

废弃/不再使用：Gateway 侧 `MODBUS_HOST`/`MODBUS_PORT` 作为**本机监听**（改为 PLC 目标；迁移期可兼容别名指向 `PLC_*`）。

## 组件职责

### Gateway

- 周期：组装命令镜像 → FC16@1000；FC03@1100 → 解码状态 → 推送 `t:s`
- 连接失败 / 读写超时 → 发布 offline 状态（对齐现有 `STATUS_TIMEOUT_MS` 语义）
- `tools/start-webhmi.ps1`：默认真机连 `192.168.1.88:502`；`-Mock` 本地冒烟
- **不再**在本机监听 Modbus TCP 502

### PLC

- 设备树：Modbus TCP **从站**；Holding `1000..1063` / `1100..1163` 映射到原过程映像（`MB_CmdIn` / `MB_StatusOut` 或等价）
- `PRG_TcpHmi`：保留编解码与面板/触摸屏/Web 仲裁；在线/心跳改为「被主站访问」语义
- 不改 `PRG_Axis_Control` / `PRG_Logic` 运动与力控

### Web

- `web/live` 不变（仍只对 Gateway WS）

## 错误与离线

- Gateway 连不上 PLC → Web 显示离线；命令写租约策略保持（安全侧停）
- 读写异常 / 超时 → 同现网超时路径，不自动切 Mock（仅 `MOCK_PLC=1` 才 Mock）

## 验收

- Gateway 能连 `192.168.1.88:502` 并周期 FC16/FC03
- Web 点动 → 命令出现在 PLC@1000；状态从 PLC@1100 刷回
- `MOCK_PLC=1` 与 `gateway` 相关单测通过
- 文档 `TCP_HMI.md` / `WEB_PLC_ALIGN.md` / `gateway/README.md` 改为「Gateway 主站 → PLC 从站」表述（禁用易混的「Gateway Server = 主站」说法；中文统一写主站/从站）

## 风险

- Inovance 从站通道与 `%IW/%QW` 映射需在设备树重配；若映射脚标变化，以 `modbus-map` 为准对齐
- 旧 PLC 工程若仍保留 Master 通道，需删除或禁用，避免双角色冲突
