# GVL.md — LMM 全局变量契约

> Writer 以 S5 为准。Axis 与 Logic **仅 GVL 交换**，禁止跨任务 CALL。  
> 轴：X=M1+M2，Y=M3，Z=M4，R=M5。X⊥Y。  
> **跨距 = Y 行程**（同一机械量 `HMI_rWheelBase`，4~6 m）。  
> X 直行速度与左右旋速度 **分开**。  
> 面板物理 IO 地址**固定**。EStop：**正常 TRUE / 按下 FALSE**。

## 分组

### GVL_Panel（面板物理 IO — 勿改地址）

```iecst
VAR_GLOBAL
    StartBtn            : BOOL;   (* AT %IX1.6 【启动】→ HMI_xStart / HMI_xEnable *)
    StopBtn             : BOOL;   (* AT %IX1.4 【停止】→ HMI_xStop *)
    ResetBtn            : BOOL;   (* 【复位】→ HMI_xStopHold3s *)
    EStop               : BOOL;   (* AT %IX0.4 【急停】正常TRUE 按下FALSE → 直通 HMI_xEStop *)
    StopLamp            : BOOL;   (* AT %QX0.6 【停止灯】← Dev_xStop *)
    StartLamp           : BOOL;   (* AT %QX0.7 【运行灯】← Dev_xRun *)
END_VAR
```

### GVL_HMI（HMI / 面板桥接写 request）

```iecst
VAR_GLOBAL
    (* —— 安全 / 设备 —— *)
    HMI_xEStop          : BOOL;   (* 【急停】TRUE正常 FALSE按下 *)
    HMI_xStop           : BOOL;   (* 【停止】短按停机；长按3s复位 *)
    HMI_xStopHold3s     : BOOL;   (* 【复位】 *)
    HMI_xStart          : BOOL;   (* 【启动】上升沿 STOP→RUN *)
    HMI_xEnable         : BOOL;   (* 【启动别名】与 Start 等效 *)
    HMI_xAutoMode       : BOOL;   (* TRUE=自动；FALSE=手动 *)

    (* —— 手动点动（电平）；仅 RUN+手动 —— *)
    HMI_xJogXPos        : BOOL;   (* 【X+】M1=M2 同速同向 *)
    HMI_xJogXNeg        : BOOL;   (* 【X-】 *)
    HMI_xSpinLeft       : BOOL;   (* 【左旋转】一正一反 *)
    HMI_xSpinRight      : BOOL;   (* 【右旋转】 *)
    HMI_xJogYPos, HMI_xJogYNeg : BOOL;
    HMI_xJogZPos, HMI_xJogZNeg : BOOL;
    HMI_xJogRPos, HMI_xJogRNeg : BOOL;
    HMI_rJogVelX        : REAL;   (* 【X直行速度】 *)
    HMI_rSpinVel        : REAL;   (* 【左右旋速度】与 JogVelX 分开 *)
    HMI_rJogVelY        : REAL;
    HMI_rJogVelZ        : REAL;
    HMI_rJogVelR        : REAL;

    (* —— 自动 —— *)
    HMI_xAutoStart      : BOOL;
    HMI_xAutoAbort      : BOOL;
    HMI_rAutoDistX      : REAL;   (* X 走距 *)
    HMI_rAutoVelX       : REAL;
    HMI_rWheelBase      : REAL;   (* 【龙门跨距=Y行程】4~6 m；自动 Y 走距用此值 *)
    HMI_rAutoVelY       : REAL;
    HMI_rAutoVelZ       : REAL;
    HMI_rForceSet       : REAL;   (* F_set 单位N *)
    HMI_xForceSimEnable : BOOL;
    HMI_rForceSim       : REAL;
END_VAR
```

**已删除（勿再绑屏）**：`HMI_eXMode` / `eDiffFunc` / `JogM1/M2` / `JogXSync*` / `JogXDiff*` / `HomeReq*` / `DiffDelta` / `TurnOmega` / `AutoDistY`。

### GVL_HMI_Status（Logic 写 · HMI 读）

```iecst
VAR_GLOBAL
    HMI_eDevState       : INT;    (* 0停止/待机 1运行中 2错误 *)
    HMI_xDevStop, HMI_xDevRun, HMI_xDevError : BOOL;
    HMI_eOpMode         : INT;    (* 0手动 1自动 *)
    HMI_xLampEStop, HMI_xLampEnableOk, HMI_xLampFault : BOOL;
    HMI_iAlarmShow      : INT;
    HMI_iAutoStepShow   : INT;
    HMI_xAutoBusy, HMI_xAutoDone : BOOL;
    HMI_rForceShow      : REAL;
END_VAR
```

### GVL_Logic

```iecst
VAR_GLOBAL
    eDevState           : INT;
    Dev_xStop, Dev_xRun, Dev_xError : BOOL;
    xEStopLatched, xEnablePermit, xFaultAggregate : BOOL;
    eOpMode, iAlarmID, iAutoStep : INT;
    rForceAct, rForceKp : REAL;
    xIlk_BlockYPlus, xIlk_BlockYNeg : BOOL;
    xIlk_BlockZPlus, xIlk_BlockZNeg : BOOL;
    xIlk_BlockYWhenZ, xM5Ready : BOOL;
END_VAR
```

### GVL_Force（PRG_Force485 写状态 · Logic 读故障）

> 详见 [FB_Force485.md](FB_Force485.md) / [PRG_Force485.md](PRG_Force485.md)。  
> `rForceAct`：模拟时 Logic 写；实传感时 **仅** Force 任务写。

| Variable | Writer | Readers | Notes |
|----------|--------|---------|-------|
| Force_xEnable / Force_bySlave / Force_rScale | 常量或 HMI | PRG_Force485 | 默认 Enable=TRUE, Slave=1, Scale=0.01 |
| HMI_xForceTare | HMI/TCP | PRG_Force485 | 脉冲去皮 |
| Force_xCommOk / Force_xTimeout | PRG_Force485 | Logic/HMI | 通讯 |
| Force_iRaw / Force_iState | PRG_Force485 | 诊断 | |
| Force_abyTx/Rx · uiTx/RxLen · xTxReq · xRxNew | PRG_Force485 ↔ 串口层 | SoftComm/SysCom | 自由协议缓冲 |
| rForceAct（非模拟） | PRG_Force485 | Logic | |

```iecst
VAR_GLOBAL
    Force_xEnable       : BOOL := TRUE;
    Force_bySlave       : BYTE := 1;
    Force_rScale        : REAL := 0.01;
    HMI_xForceTare      : BOOL;
    Force_xCommOk       : BOOL;
    Force_xTimeout      : BOOL;
    Force_iRaw          : INT;
    Force_iState        : INT;
    Force_abyTx         : ARRAY[0..63] OF BYTE;
    Force_uiTxLen       : UINT;
    Force_xTxReq        : BOOL;
    Force_abyRx         : ARRAY[0..63] OF BYTE;
    Force_uiRxLen       : UINT;
    Force_xRxNew        : BOOL;
END_VAR
```

### GVL_IO

```iecst
VAR_GLOBAL
    I_xLimYPos, I_xLimYNeg, I_xHomeY : BOOL;
    I_xLimZPos, I_xLimZNeg, I_xHomeZ : BOOL;
    I_xLimRPos, I_xLimRNeg, I_xHomeR : BOOL;
END_VAR
```

### GVL_AxisCmd（Logic → Axis）

```iecst
VAR_GLOBAL
    AxisCmd_xPower, AxisCmd_xStopAll, AxisCmd_xResetFault : BOOL;
    AxisCmd_xJogXPos, AxisCmd_xJogXNeg : BOOL;
    AxisCmd_xSpinLeft, AxisCmd_xSpinRight : BOOL;
    AxisCmd_xJogYPos, AxisCmd_xJogYNeg : BOOL;
    AxisCmd_xJogZPos, AxisCmd_xJogZNeg : BOOL;
    AxisCmd_xJogRPos, AxisCmd_xJogRNeg : BOOL;
    AxisCmd_rJogVelX, AxisCmd_rSpinVel : REAL;
    AxisCmd_rJogVelY, AxisCmd_rJogVelZ, AxisCmd_rJogVelR : REAL;
    AxisCmd_xMoveRelX : BOOL;
    AxisCmd_rMoveDistX, AxisCmd_rMoveVelX : REAL;
    AxisCmd_xMoveRelY : BOOL;
    AxisCmd_rMoveDistY, AxisCmd_rMoveVelY : REAL;  (* DistY := WheelBase *)
    AxisCmd_rZVelCmd : REAL;
    AxisCmd_xUseZVelCmd : BOOL;
    AxisCmd_xHoldR : BOOL;
    AxisCmd_rRHoldPos : REAL;
    AxisCmd_rAcc, AxisCmd_rDec, AxisCmd_rWheelBase : REAL;
END_VAR
```

**已删除**：`AxisCmd_eXMode` / `eDiffFunc` / `JogM*` / `JogXSync*` / `JogXDiff*` / `Home*` / `DiffDelta` / `TurnOmega`。

### GVL_AxisFb（Axis only 写）

```iecst
VAR_GLOBAL
    AxisFb_rVelCmdM1, AxisFb_rVelCmdM2 : REAL;
    AxisFb_rPosM1, AxisFb_rPosM2, AxisFb_rPosY, AxisFb_rPosZ, AxisFb_rPosR : REAL;
    AxisFb_xMovingM1, AxisFb_xMovingM2, AxisFb_xMovingY, AxisFb_xMovingZ, AxisFb_xMovingR : BOOL;
    AxisFb_xPoweredM1, AxisFb_xPoweredM2, AxisFb_xPoweredY, AxisFb_xPoweredZ, AxisFb_xPoweredR : BOOL;
    AxisFb_xFaultM1, AxisFb_xFaultM2, AxisFb_xFaultY, AxisFb_xFaultZ, AxisFb_xFaultR : BOOL;
    AxisFb_xReady : BOOL;
    AxisFb_xMoveDoneX, AxisFb_xMoveDoneY : BOOL;
END_VAR
```

### GVL_Tcp（PRG_TcpHmi 写影子 · Logic 合成到 HMI）

> 详见 [TCP_HMI.md](TCP_HMI.md)。`Tcp_xEStop` 上电默认 TRUE。

| Variable | Writer | Readers | Notes |
|----------|--------|---------|-------|
| Tcp_xConnected / Tcp_xTimeout / Tcp_xOnline | PRG_TcpHmi | HMI/Web | 链路 |
| Tcp_xEStop … Tcp_rForceSim（与 HMI request 同名后缀） | PRG_TcpHmi | PRG_Logic | 影子 |
| HMI_*（合成后） | PRG_Logic | 全机 | 面板∨Tcp |

```iecst
VAR_GLOBAL
    Tcp_xConnected, Tcp_xTimeout, Tcp_xOnline : BOOL;
    Tcp_xEStop : BOOL := TRUE;
    Tcp_xStop, Tcp_xStopHold3s, Tcp_xStart, Tcp_xEnable : BOOL;
    Tcp_xAutoMode : BOOL;
    Tcp_xJogXPos, Tcp_xJogXNeg, Tcp_xSpinLeft, Tcp_xSpinRight : BOOL;
    Tcp_xJogYPos, Tcp_xJogYNeg, Tcp_xJogZPos, Tcp_xJogZNeg : BOOL;
    Tcp_xJogRPos, Tcp_xJogRNeg : BOOL;
    Tcp_rJogVelX, Tcp_rSpinVel, Tcp_rJogVelY, Tcp_rJogVelZ, Tcp_rJogVelR : REAL;
    Tcp_xAutoStart, Tcp_xAutoAbort : BOOL;
    Tcp_rAutoDistX, Tcp_rAutoVelX, Tcp_rAutoVelY, Tcp_rAutoVelZ : REAL;
    Tcp_rWheelBase, Tcp_rForceSet, Tcp_rForceSim : REAL;
    Tcp_xForceSimEnable : BOOL;
END_VAR
```
