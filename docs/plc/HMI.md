# HMI.md — 触摸屏变量绑定（本期手动）

> 只写 `GVL_HMI` 请求；读 `GVL_HMI_Status` / `GVL_AxisFb`。不写 Enable/Alarm 源（使能闩在 Logic）。  
> 完整对照：[WEB_PLC_ALIGN.md](WEB_PLC_ALIGN.md) · 契约源：[GVL.md](GVL.md)

## 画面分区

1. **安全**：急停、停止（点按停 / 长按 3s 复位）、**使能**  
2. **X**：模式三选一 + 同步/差速/独立点动  
3. **Y/Z**：点动 ±、回零  
4. **R**：灰显（`xM5Ready=FALSE`）  
5. **状态灯**：急停锁存、使能、Fault、AlarmID、各轴 Powered/Moving/Pos  

---

## 操作语义（触摸屏必读）

### 1. 使能 `HMI_xEnable`

| 项 | 约定 |
|----|------|
| 控件类型 | **瞬时按钮**（按下=TRUE，松开=FALSE） |
| PLC 行为 | **上升沿切换**：未使能→上使能；已使能→下使能 |
| 复位后 | 长按停止复位 / 急停 / 故障 → 使能闩强制 FALSE → **必须再按一次使能** |
| 灯 | `HMI_xLampEnableOk`=已上使能且许可仍成立；各轴 `AxisFb_xPowered*`=驱动实使能 |

推荐流程：松开急停 → 长按停止复位错误 → 灯 Fault 灭 → **按使能** → Powered 亮 → 再点动。

### 2. 点动 JOG（电平）

| 项 | 约定 |
|----|------|
| 控件类型 | **按住型**（按下 TRUE / 松开 FALSE） |
| TRUE | 按设定速度**移动** |
| FALSE | **暂停**（停速度指令 / `MC_MoveVelocity.Execute:=FALSE`，**不**经 JOG 口下使能） |
| 前提 | `AxisCmd_xPower` 已 TRUE 且未 StopAll / 未撞限位 |

互锁：+/− 不要同时 TRUE；X 三模式互斥由 Logic 裁定。

### 3. 急停 / 停止

| 状态 | `HMI_xEStop` | 说明 |
|------|--------------|------|
| 未按下 | **TRUE** | 正常 |
| 按下触发 | **FALSE** | 可按可松；松后回到 TRUE，锁存由 Logic 保持 |

| 操作 | 效果 |
|------|------|
| 点按 / 短按 `HMI_xStop` | 停运动（`AxisCmd_xStopAll`）；**不清**使能闩 |
| 长按 ≥3s | 清急停锁存 + `AxisCmd_xResetFault` + **下使能** |

```iecst
tonStop(IN := HMI_xStop AND HMI_xEStop, PT := T#3S);
(* 上升沿脉冲 → HMI_xStopHold3s；或仅写 HMI_xStop，由 PRG_Logic TON 完成 *)
```

---

## 触摸屏绑定总表

### 写入（HMI → PLC）

| 画面控件 | 变量 | 类型 | 地址 | 行为 |
|----------|------|------|------|------|
| 急停 | `HMI_xEStop` | BOOL | TBD | 未按=TRUE / 按下=FALSE |
| 停止 | `HMI_xStop` | BOOL | TBD | 按住=TRUE |
| 停止长按脉冲（可选） | `HMI_xStopHold3s` | BOOL | TBD | 满 3s 一拍；也可只靠 PLC TON |
| **使能** | `HMI_xEnable` | BOOL | TBD | 瞬时；上升沿切换使能 |
| X 模式 | `HMI_eXMode` | INT | TBD | 0=Indep 1=Sync 2=Diff |
| Diff 子功能 | `HMI_eDiffFunc` | INT | TBD | 0纠偏 1原地旋 2差速弯 |
| Sync +/− | `HMI_xJogXSyncPos/Neg` | BOOL | TBD | 电平点动 |
| Diff +/− | `HMI_xJogXDiffPos/Neg` | BOOL | TBD | 电平点动 |
| M1 +/− | `HMI_xJogM1Pos/Neg` | BOOL | TBD | 仅 Indep |
| M2 +/− | `HMI_xJogM2Pos/Neg` | BOOL | TBD | 仅 Indep |
| Y +/− | `HMI_xJogYPos/Neg` | BOOL | TBD | 电平点动 |
| Z +/− | `HMI_xJogZPos/Neg` | BOOL | TBD | 电平点动 |
| R +/− | `HMI_xJogRPos/Neg` | BOOL | TBD | 预留灰显 |
| Home Y/Z/R | `HMI_xHomeReqY/Z/R` | BOOL | TBD | 按住/脉冲均可；本期电平透传 |
| JogVel X/Y/Z | `HMI_rJogVelX/Y/Z` | REAL | TBD | 速度设定 |
| Δ / ω / L | `HMI_rDiffDelta` / `rTurnOmega` / `rWheelBase` | REAL | TBD | L∈[4,6] |

### 读取（PLC → HMI）

| 画面灯/数值 | 变量 | 类型 | 含义 |
|-------------|------|------|------|
| 急停灯 | `HMI_xLampEStop` | BOOL | 锁存或按钮仍按下 |
| **使能灯** | `HMI_xLampEnableOk` | BOOL | 已触发使能且许可 OK |
| Fault 灯 | `HMI_xLampFault` | BOOL | 轴故障汇总 |
| 报警号 | `HMI_iAlarmShow` | INT | 0 / 1001..1099 |
| 许可（调试） | `xEnablePermit` | BOOL | 条件满足；≠已使能 |
| M1..Z Powered | `AxisFb_xPoweredM1/M2/Y/Z` | BOOL | 驱动实使能 |
| M1..Z Moving | `AxisFb_xMoving*` | BOOL | 运动中 |
| 位置 | `AxisFb_rPosM1/M2/Y/Z` | REAL | 实际位置 |
| M1/M2 速度指令 | `AxisFb_rVelCmdM1/M2` | REAL | 当前指令速 |
| Homed Y/Z | `AxisFb_xHomedY/Z` | BOOL | 已回零 |
| Ready | `AxisFb_xReady` | BOOL | 四轴可动（无 Fault） |

地址 `%I/%Q` / 触摸屏通讯区：导入前在工程里填；**符号名以上表为准**。

---

## Must not

- 直接写 `AxisCmd_*` / `xEnablePermit` / `iAlarmID` / `xPowerLatched`  
- 调用 Axis 任务程序  
- JOG 用“按下脉冲一次走一步”理解（本期是**按住移动 / 松开暂停**）  
