# WebHMI 真机调试台增强

## 目标

用 `web/live` + Gateway 真机模式做现场调试：一键启动、宽松可读布局、Modbus 已映射的调试 I/O 全量露出。X 抖动问题后续用本页采集数据再分析。

## 范围

- 一键启动：`tools/start-webhmi.ps1` → `npm run start:plc` → 打开浏览器
- 补齐命令：Acc/Dec、KpTrack、HeadingErr、KpForce、ForceGuide
- 补齐状态显示：Pos/VelCmd M1·M2、ΔPos、Fault、MoveDone、力诊断、Tcp 状态
- 布局：宽屏多栏、字号与间距加大，专设「X 双驱监视」大字区 + 快照日志
- 不改 PLC 运动逻辑；不扩展 `Cfg_rLim*`（映射未含）

## 架构

不变：浏览器 WS/JSON → Gateway Server:502 ← PLC Master。

## 验收

- 脚本启动后可打开页面并连上 Gateway
- 手动点动时可见 VelCmdM1/M2、PosM1/M2、ΔPos 实时刷新
- 所有 modbus-map command/status 字段在页面有写或读入口（协议头除外）
