# PLC_PRG.md — 主任务入口

> 主/Logic 任务调用本程序。 **不** 调用 `PRG_Axis_Control`。

```iecst
PROGRAM PLC_PRG
VAR
END_VAR

PRG_TcpHmi();
PRG_Logic();
(* 可选：PRG_HMI(); 若触摸屏逻辑放 PLC 侧 *)
```

## 任务一览

| 任务 | 程序 | 周期 | 说明 |
|------|------|------|------|
| Main / Logic | `PLC_PRG` → `PRG_TcpHmi` + `PRG_Logic` | TBD | TCP HMI + 联锁与命令裁定 |
| Axis（独立） | `PRG_Axis_Control` | TBD（与 EC 同步） | 仅 GVL I/O，无外部 CALL |
| Force（独立） | `PRG_Force485` | 10–20 ms | LE 力传感 RS485；无外部 CALL |
| EtherCAT | 系统 | — | 已有工程配置 |

## 导入顺序建议

1. 建 GVL（按 `GVL.md`）  
2. 建 `FB_Servo` / `FB_XDiff`  
3. 建 `PRG_Axis_Control` 并挂 **独立任务**  
4. 建 `PRG_Logic`，由 `PLC_PRG` 调用  
5. HMI 绑定  
6. 补 IO 地址与轴参（同向极性、轮距、JOG 速度）  

## 范围

- 本期：4 轴手动 + 急停/长按复位 + 联锁 + X 差速  
- 不做：自动循环、视觉直线、M5 实轴  
