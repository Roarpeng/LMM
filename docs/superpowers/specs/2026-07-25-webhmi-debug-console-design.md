# WebHMI 真机调试台增强

日期：2026-07-25  
状态：设计已确认（方案 1：补齐缺口 + Mock 冒烟验收）

## 目标

用 `web/live` + Gateway 真机模式做现场调试：一键启动、宽松可读布局、Modbus 已映射的调试 I/O 全量露出。X 抖动问题后续用本页采集数据再分析。

## 范围

- 一键启动：`tools/start-webhmi.ps1`（默认真机 `MOCK_PLC=0`；`-Mock` 本地冒烟）→ 打开 `http://127.0.0.1:8080/`
- 命令可写：点动/回零/自动参数、Acc/Dec、KpTrack、HeadingErr、KpForce、ForceGuide、力模拟与去皮
- 状态可读：Pos/VelCmd M1·M2、ΔPos 曲线与快照、Fault、MoveDone、力诊断、Tcp 状态
- **增量（相对现状缺口）：** 状态区显式显示 `HMI_xDevStop` / `HMI_xDevRun` / `HMI_xDevError`（不得仅靠 `eDevState` 推断而不露出字段名）
- 布局：宽屏三栏、字号与间距加大，专设「X 双驱监视」大字区 + 快照日志
- 不改 PLC 运动逻辑；不扩展 `Cfg_rLim*`（映射未含）

## 非目标

- 不新增 CSV 导出、键盘点动、限位配置等扩展能力（本迭代不做）
- 不以本页替代触摸屏正式 HMI

## 架构

不变：浏览器 WS/JSON → Gateway Modbus TCP Server `:502` ← PLC Master（FC03@1000 / FC16@1100 / len=64）。

## 验收

- `.\tools\start-webhmi.ps1`（或 `-Mock`）启动后可打开页面并连上 Gateway（WS pill 正常）
- Mock 或真机下手动点动时可见 VelCmdM1/M2、PosM1/M2、ΔPos 实时刷新
- `config/modbus-map.json` 全部 command/status 字段在页面有写或读入口（协议头 magic/version/sequence/heartbeat/tailSequence 除外）
- `cd gateway && npm test` 通过

## 实施策略

1. 对照 map 扫覆盖缺口并补 UI/绑定  
2. Mock 冒烟（点动 → 监视区刷新）  
3. 现有 gateway 单测回归  
4. 真机联调按现场清单（PLC Master 指向本机 :502）
