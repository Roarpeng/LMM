# GVL.md — LMM 全局变量契约

> Writer 以 S5 为准。Axis 与 Logic **仅 GVL 交换**，禁止跨任务 CALL。  
> 轴：X=M1+M2，Y=M3，Z=M4，R=M5。X⊥Y。  
> HMI 面向设备操作（手动简洁键 + 自动参数）；力单位默认 **N**，本期可模拟。  
> 面板物理 IO 地址**固定**（见 GVL_Panel）。EStop：**正常 TRUE / 按下 FALSE**。

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
    HMI_xStopHold3s     : BOOL;   (* 【复位脉冲】 *)
    HMI_xStart          : BOOL;   (* 【启动】上升沿 STOP→RUN *)
    HMI_xEnable         : BOOL;   (* 【启动别名】与 Start 等效 *)
    HMI_xAutoMode       : BOOL;   (* 【自动模式】TRUE=自动；FALSE=手动 *)

    (* —— 手动点动（电平）；仅 RUN+手动 —— *)
    HMI_xJogXPos        : BOOL;   (* 【X+】M1=M2 同速同向 *)
    HMI_xJogXNeg        : BOOL;   (* 【X-】 *)
    HMI_xSpinLeft       : BOOL;   (* 【左旋转】M1/M2 一正一反 *)
    HMI_xSpinRight      : BOOL;   (* 【右旋转】与左旋反向互斥 *)
    HMI_xJogYPos        : BOOL;
    HMI_xJogYNeg        : BOOL;
    HMI_xJogZPos        : BOOL;
    HMI_xJogZNeg        : BOOL;
    HMI_xJogRPos        : BOOL;
    HMI_xJogRNeg        : BOOL;
    HMI_rJogVelX        : REAL;   (* X直行与左/右旋共用 *)
    HMI_rJogVelY        : REAL;
    HMI_rJogVelZ        : REAL;
    HMI_rJogVelR        : REAL;

    (* —— 自动 —— *)
    HMI_xAutoStart      : BOOL;   (* 上升沿启动；须 RUN+自动 *)
    HMI_xAutoAbort      : BOOL;
    HMI_rAutoDistX      : REAL;
    HMI_rAutoVelX       : REAL;
    HMI_rAutoDistY      : REAL;
    HMI_rAutoVelY       : REAL;
    HMI_rAutoVelZ       : REAL;
    HMI_rForceSet       : REAL;   (* F_set 单位N *)
    HMI_xForceSimEnable : BOOL;
    HMI_rForceSim       : REAL;
END_VAR
```

### GVL_HMI_Status（Logic 写 · HMI 读）

```iecst
VAR_GLOBAL
    HMI_eDevState       : INT;    (* 0停止/待机 1运行中 2错误 *)
    HMI_xDevStop        : BOOL;
    HMI_xDevRun         : BOOL;
    HMI_xDevError       : BOOL;
    HMI_eOpMode         : INT;    (* 0手动 1自动 *)
    HMI_xLampEStop      : BOOL;
    HMI_xLampEnableOk   : BOOL;
    HMI_xLampFault      : BOOL;
    HMI_iAlarmShow      : INT;
    HMI_iAutoStepShow   : INT;
    HMI_xAutoBusy       : BOOL;
    HMI_xAutoDone       : BOOL;
    HMI_rForceShow      : REAL;
END_VAR
```

### GVL_Logic

```iecst
VAR_GLOBAL
    eDevState           : INT;
    Dev_xStop           : BOOL;
    Dev_xRun            : BOOL;
    Dev_xError          : BOOL;
    xEStopLatched       : BOOL;
    xEnablePermit       : BOOL;
    xFaultAggregate     : BOOL;
    eOpMode             : INT;
    iAlarmID            : INT;
    iAutoStep           : INT;    (* 0Idle 1MoveX 2PressZ 3MoveY 4RWobble 5Done *)
    rForceAct           : REAL;
    rForceKp            : REAL;
    xIlk_BlockYPlus     : BOOL;
    xIlk_BlockYNeg      : BOOL;
    xIlk_BlockZPlus     : BOOL;
    xIlk_BlockZNeg      : BOOL;
    xIlk_BlockYWhenZ    : BOOL;
    xM5Ready            : BOOL;
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
    AxisCmd_rJogVelX, AxisCmd_rJogVelY, AxisCmd_rJogVelZ, AxisCmd_rJogVelR : REAL;
    AxisCmd_xMoveRelX : BOOL;
    AxisCmd_rMoveDistX, AxisCmd_rMoveVelX : REAL;
    AxisCmd_xMoveRelY : BOOL;
    AxisCmd_rMoveDistY, AxisCmd_rMoveVelY : REAL;
    AxisCmd_rZVelCmd : REAL;
    AxisCmd_xUseZVelCmd : BOOL;
    AxisCmd_xHoldR : BOOL;
    AxisCmd_rRHoldPos : REAL;
    AxisCmd_rAcc, AxisCmd_rDec, AxisCmd_rWheelBase : REAL;
END_VAR
```

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
