# LMM 龙门设备控制系统

五轴龙门（X = M1+M2 双驱轮、Y、Z、R）+ 拉压力传感器的整机控制项目。
PLC（汇川 AM600 + InoProShop）+ Modbus TCP 网关 + 浏览器 WebHMI。

## 系统结构

```
浏览器 WebHMI ──WS/JSON──► Gateway(Node.js) ──Modbus TCP 主站──► PLC(从站 :502)
                                                              └─ EtherCAT ── 5×MDX_EC 伺服 + RS485 力传感器
```

- 命令镜像 Holding `4096..4191`（96 字，PLC `%IW103` 起），状态镜像 `4352..4447`（`%QW44` 起）
- 契约文件：`config/modbus-map.json`（字段/缩放/位定义的唯一来源，改动需三方同步）
- 协议细节：[docs/plc/TCP_HMI.md](docs/plc/TCP_HMI.md)、[docs/plc/MODBUS_MAP.md](docs/plc/MODBUS_MAP.md)（由 `tools/generate_modbus_map.py` 生成，勿手改）

## 目录

| 路径 | 说明 |
|------|------|
| `plc/` | PLC 权威 ST 源码（`plc/g/*.st` = 在役 g 线；`GVL.st` 全局变量）+ [工作流](plc/README.md) |
| `LMM_g_0.7x.xml` | InoProShop 工程（PLCopen TC6）。**仓库只保留最新 3 个版本**，历史在 git 记录中 |
| `gateway/` | Node.js 网关：Modbus 主站 ↔ WebSocket；含 mock 与冒烟脚本（[README](gateway/README.md)） |
| `web/live/` | WebHMI v3（纯静态无构建：总览/自动/手动/X双驱/直控/力传感/趋势/报警/调试/系统） |
| `config/modbus-map.json` | 命令/状态镜像契约（冻结，改动需 PLC+网关+Web 同步） |
| `tools/` | `inject_g.py`（源码→XML 注入）、`patch_g0xx.py`（历史幂等补丁）、校验脚本 |
| `docs/plc/` | PLC 文档索引（GVL/FB/接口/报警），[入口](docs/plc/README.md) |

## 当前版本

- **PLC 在役**：`LMM_g_0.78.xml`（现场）；**待烧录**：`LMM_g_0.79.xml`
  （96W 镜像 + 每轴直控 + 力峰值 + X 双驱 CoE 诊断 word49..74；
  注意 M1/M2 的 CSV 速度模式需在 InoProShop 把 MDX_EC/MDX_EC_1 的 RxPDO 从 0x1600 改为 0x1603，详见 `.equipment-workflow/state.md` 0.79 节）
- **烧录**：InoProShop 导入 XML → 编译 0 error → 下载

## 常用命令

```bash
# PLC：改 plc/g/*.st 后注入并校验
python3 tools/inject_g.py LMM_g_0.79.xml LMM_g_0.80.xml
python3 tools/inject_g.py --check
python3 tools/check_plcopen_xml.py LMM_g_0.80.xml

# Modbus 契约改后重生成文档
python3 tools/generate_modbus_map.py

# 网关 + WebHMI
cd gateway && npm test                        # 单元测试
node scripts/probe-plc.js 192.168.1.88 502 1  # 只读探针
node scripts/smoke-webhmi.js                  # mock 冒烟
```

## 现场备忘

- InoProShop 从站映射「起始地址」是**十六进制**：`1000`→4096、`1100`→4352
- 报警：1001 急停锁存（松急停→Web「复位」）、1005 力超时、1006 力从站失败、1007 轴未就绪
- X 双驱诊断：WebHMI「X 双驱 → 驱动诊断」卡（模式 6060 / 状态字 6041 / 错误码 603F / 转矩限值）
- 更多历史与排障记录：`.equipment-workflow/state.md`
