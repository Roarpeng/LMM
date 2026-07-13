# HMI.md — 请求边沿与显示

> 只写 `GVL_HMI` 请求；读 `GVL_HMI_Status` / `GVL_AxisFb`。不写 Enable/Alarm 源。

## 画面分区（本期手动）

1. **安全**：急停、停止（点按停 / 长按 3s 复位）  
2. **X**：模式三选一 + 同步/差速/独立按钮  
3. **Y/Z**：JOG ±、回零请求  
4. **R**：灰显（`xM5Ready=FALSE`）  
5. **状态灯**：急停锁存、使能允许、Fault、AlarmID、各轴 Moving/Pos  

## 急停按钮极性

| 状态 | `HMI_xEStop` | 说明 |
|------|--------------|------|
| 未按下 | **TRUE** | 正常 |
| 按下触发 | **FALSE** | 可按可松；松后回到 TRUE，锁存由 Logic 保持 |

HMI/接线按常闭或“健康为 1”映射到本变量；**禁止**再按“按下=TRUE”理解。

## 停止按钮

| 操作 | 效果 |
|------|------|
| 点按 / 短按 | `HMI_xStop=TRUE` 期间 → Logic 置 `AxisCmd_xStopAll`（停运动） |
| 长按 ≥3s | `HMI_xStopHold3s` 脉冲 → 清急停锁存 + `AxisCmd_xResetFault` **复位各轴错误** |

```iecst
tonStop(IN := HMI_xStop AND HMI_xEStop, PT := T#3S);  (* 急停须已松开 *)
(* 上升沿脉冲 *)
HMI_xStopHold3s := tonStop.Q AND NOT tonStop.Q 的上一周期; 
```

若 HMI 无法计时，仅写 `HMI_xStop`，由 `PRG_Logic` 的 `TON` 完成长按检测（两套只保留一套）。

## 绑定原则（与 Web v2 一一对应）

| 控件 | 变量 | 方向 |
|------|------|------|
| 急停 | HMI_xEStop（TRUE=未触发） | HMI→ |
| 停止 | HMI_xStop / HMI_xStopHold3s | HMI→ |
| X 模式 | HMI_eXMode | HMI→ |
| Diff 子功能 | HMI_eDiffFunc（0纠偏/1原地旋转一正一反/2差速拐弯） | HMI→ |
| Sync/Diff/Indep JOG | HMI_xJogXSync* / XDiff* / M1* / M2* | HMI→ |
| Y/Z JOG·Home | HMI_xJogY/Z* · HomeReqY/Z | HMI→ |
| 参数 | HMI_rJogVelX/Y/Z · rDiffDelta · rTurnOmega · rWheelBase | HMI→ |
| 灯/位/速 | HMI_xLamp* · AxisFb_rPos* · AxisFb_rVelCmdM1/M2 | ←Logic/Axis |

完整对照：[WEB_PLC_ALIGN.md](WEB_PLC_ALIGN.md)

## Must not

- 直接写 `AxisCmd_*` / `xEnablePermit` / `iAlarmID`  
- 调用 Axis 任务程序  
