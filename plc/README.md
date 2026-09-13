# plc/ — PLC 源码（权威）

`LMM.xml`（2MB PLCopen TC6，InoProShop 工程）**不再直接手改**。
权威源码在本目录，改完注入 XML 再导入 InoProShop。

## 工作流

```bash
# 1. 编辑 plc/src/*.st 或 plc/GVL.st
# 2. 注入 LMM.xml（自动备份到 LMM.xml.bak.inject）
python3 tools/inject_st.py
# 3. 静态校验（必须 0 error）
python3 tools/check_lmm.py
# 4. InoProShop 导入 LMM.xml → 编译 → 下载
```

## 文件

| 文件 | POU | 职责 |
|------|-----|------|
| `GVL.st` | 全局变量 | 唯一 GVL，13 个分组；变量中文说明见 `docs/plc/GVL.md` / `HMI.md` |
| `src/PLC_PRG.st` | 程序 | MainTask 入口：`PRG_TcpHmi()` → `PRG_Logic()` |
| `src/PRG_TcpHmi.st` | 程序 | Modbus 编解码 + 面板/触摸屏/Web 三源仲裁 → `HMI_*` |
| `src/PRG_Logic.st` | 程序 | 安全去耦 + 手动点动 + 自动多道循环 + 回零编排 → `AxisCmd_*` |
| `src/PRG_Axis_Control.st` | 程序 | ETHERCAT 任务；`FB_XDual` + Y/Z/R `FB_Servo` + 力 FB → `AxisFb_*` |
| `src/FB_Servo.st` | 功能块 | 单轴原子：MC_Power/Jog/MoveVelocity/MoveRelative/Absolute/Home/Halt；硬限位闸门 |
| `src/FB_XDual.st` | 功能块 | X 双驱封装：`FB_XLineTrack` + 双 `FB_Servo` + 平均相对位移走距；无 Virtual/Gear |
| `src/FB_XLineTrack.st` | 功能块 | 差速速度合成（由 `FB_XDual` 调用） |
| `src/FB_Force.st` | 功能块 | 力原始值换算 + 软件去皮 + 看门狗 |
| `src/FB_ForceFollow.st` | 功能块 | Z 恒力 P 律 |

## g 线（当前在役 `LMM_g_*.xml`）

**当前版本 `LMM_g_0.79.xml`**（仓库只保留最新 3 个 XML：0.77/0.78/0.79；历史版本在 git 历史中）。

`plc/g/*.st` 是 g 线 POU 源：`FB_Servo` / `FB_XDual` / `PRG_Axis_Control` / `PRG_Logic`。
改完用 `python3 tools/inject_g.py <in>.xml <out>.xml` 注入（只替换同名 POU，不动设备树）。
GVL 与 `PRG_TcpHmi` 的增量（0.60 视觉直控、0.63 通用速度透传）用幂等补丁脚本
`tools/patch_g060.py` / `tools/patch_g063.py` 按行插入。基线 `LMM_g_0.62.xml`（InoProShop 重存）
→ 生成 `LMM_g_0.63.xml`。

> 已删除 `FB_GantryX` / Virtual 龙门路径；`PRG_Axis_Control` 实例 `fbX : FB_XDual`。

数据流单向环：`HMI_* →(Logic) AxisCmd_* →(Axis) AxisFb_* →(回读)`。
任务间只经 GVL 交换，禁止跨任务 CALL。

## 规则

- 设备树 / EtherCAT / 轴参数 / IO 地址在 InoProShop 里改，不在本目录
- Modbus 地址表（Holding 1000/1100）改动必须同步 `config/modbus-map.json` + gateway + web
- 死代码不许回魂：`FB_TCPServer` / `PRG_Force485` / `FB_XDiff` / **`FB_GantryX`** 已删（历史在 `attic/`）
