# PLC_PRG.md — 主任务入口

> 源码：`plc/src/PLC_PRG.st`。

```iecst
PROGRAM PLC_PRG
PRG_TcpHmi();
PRG_Logic();
END_PROGRAM
```

## 任务一览

| 任务 | 周期 | 优先级 | 程序 |
|------|------|--------|------|
| ETHERCAT | 4ms | 0 | `EtherCAT_Task` + `PRG_Axis_Control` |
| MainTask | 4ms | 1 | `PLC_PRG`（→ `PRG_TcpHmi` + `PRG_Logic`） |

规则：

- `PRG_Axis_Control` 只在 ETHERCAT 任务；**MainTask 不得 CALL 它**（历史教训：PLC_PRG 曾误挂 ETHERCAT 任务导致逻辑双跑）
- 力传感在 Axis 任务内经 `FB_Force` 读组态映射 `%IW102`，无独立 ForceTask
- 任务间只经 GVL 交换
