# GVL.md — LMM 全局变量契约

> Writer 以 S5 为准。地址 `%I/%Q` 可 TBD，导入前补齐。  
> Axis 与 Logic **仅通过本文件分组交换**，禁止跨任务 CALL。
> X=龙门双驱（运动方向**与 Y 垂直**）；M1/M2 相对编码器，上电相对 0；跨距 4~6m 可变。
> 功能对齐见 [WEB_PLC_ALIGN.md](WEB_PLC_ALIGN.md)（以 Web v2 为准）。

## 分组

### GVL_HMI（HMI 写 request）

```iecst
VAR_GLOBAL
    (* 急停按钮极性：未按下=TRUE，按下触发=FALSE；可按可松，松后信号回到 TRUE。
       Logic 在信号为 FALSE 时置急停锁存；松开按钮不会自动清锁存。 *)
    HMI_xEStop          : BOOL;   (* TRUE=未触发 OK；FALSE=急停按下 *)
    HMI_xStop           : BOOL;   (* 点按/按住：停止请求 *)
    HMI_xStopHold3s     : BOOL;   (* 长按满 3s 脉冲：复位锁存 + 各轴错误复位请求 *)

    HMI_eXMode          : INT;    (* 0=Indep 1=Sync 2=Diff *)
    HMI_eDiffFunc       : INT;    (* Diff：0纠偏 1原地旋转(一正一反) 2差速拐弯 *)
    HMI_xJogM1Pos       : BOOL;
    HMI_xJogM1Neg       : BOOL;
    HMI_xJogM2Pos       : BOOL;
    HMI_xJogM2Neg       : BOOL;
    HMI_xJogXSyncPos    : BOOL;   (* 同步直行 + *)
    HMI_xJogXSyncNeg    : BOOL;
    HMI_xJogXDiffPos    : BOOL;   (* Diff 方向 + *)
    HMI_xJogXDiffNeg    : BOOL;
    HMI_xJogYPos        : BOOL;
    HMI_xJogYNeg        : BOOL;
    HMI_xJogZPos        : BOOL;
    HMI_xJogZNeg        : BOOL;
    HMI_xJogRPos        : BOOL;   (* 预留 *)
    HMI_xJogRNeg        : BOOL;
    HMI_xHomeReqY       : BOOL;
    HMI_xHomeReqZ       : BOOL;
    HMI_xHomeReqR       : BOOL;   (* 预留 *)
    HMI_rJogVelX        : REAL;   (* X 基速，对齐 Web JogVel *)
    HMI_rJogVelY        : REAL;
    HMI_rJogVelZ        : REAL;
    HMI_rDiffDelta      : REAL;   (* 差速 Δ，单位与轴速度一致 *)
    HMI_rTurnOmega      : REAL;   (* Diff 拐弯角速度 *)
    HMI_rWheelBase      : REAL;   (* 龙门跨距 m，4..6 *)
END_VAR
```

### GVL_Logic（Logic 写）

```iecst
VAR_GLOBAL
    xEStopLatched       : BOOL;
    xEnablePermit       : BOOL;
    xFaultAggregate     : BOOL;
    eOpMode             : INT;    (* 0=Manual 本期固定 *)
    iAlarmID            : INT;    (* 0=无；1001..1099 见 S5 *)
    xIlk_BlockYPlus     : BOOL;
    xIlk_BlockYNeg      : BOOL;
    xIlk_BlockZPlus     : BOOL;
    xIlk_BlockZNeg      : BOOL;
    xIlk_BlockYWhenZ    : BOOL;   (* Z 运动中禁 Y，可参数化 *)
    xM5Ready            : BOOL;   (* FALSE：忽略 R *)
END_VAR
```

### GVL_IO（映射层写 / 物理输入）

```iecst
VAR_GLOBAL
    I_xLimYPos          : BOOL;   (* AT %I* TBD *)
    I_xLimYNeg          : BOOL;
    I_xHomeY            : BOOL;
    I_xLimZPos          : BOOL;
    I_xLimZNeg          : BOOL;
    I_xHomeZ            : BOOL;
    I_xLimRPos          : BOOL;   (* 预留 *)
    I_xLimRNeg          : BOOL;
    I_xHomeR            : BOOL;
END_VAR
```

### GVL_AxisCmd（Logic → Axis 任务，唯一命令入口）

```iecst
VAR_GLOBAL
    AxisCmd_xPower      : BOOL;   (* 使能请求，受 xEnablePermit 门控后写入 *)
    AxisCmd_eXMode      : INT;    (* 透传/裁定后的 X 模式 *)
    AxisCmd_eDiffFunc   : INT;    (* 0纠偏 1原地旋转 2差速拐弯 *)
    AxisCmd_xJogM1Pos   : BOOL;
    AxisCmd_xJogM1Neg   : BOOL;
    AxisCmd_xJogM2Pos   : BOOL;
    AxisCmd_xJogM2Neg   : BOOL;
    AxisCmd_xJogXSyncPos: BOOL;
    AxisCmd_xJogXSyncNeg: BOOL;
    AxisCmd_xJogXDiffPos: BOOL;
    AxisCmd_xJogXDiffNeg: BOOL;
    AxisCmd_xJogYPos    : BOOL;
    AxisCmd_xJogYNeg    : BOOL;
    AxisCmd_xJogZPos    : BOOL;
    AxisCmd_xJogZNeg    : BOOL;
    AxisCmd_xJogRPos    : BOOL;
    AxisCmd_xJogRNeg    : BOOL;
    AxisCmd_xStopAll    : BOOL;   (* 立即停所有轴运动 *)
    AxisCmd_xResetFault : BOOL;   (* 脉冲：各轴错误复位 MC_Reset *)
    AxisCmd_xHomeY      : BOOL;
    AxisCmd_xHomeZ      : BOOL;
    AxisCmd_xHomeR      : BOOL;
    AxisCmd_rDiffDelta  : REAL;
    AxisCmd_rTurnOmega  : REAL;
    AxisCmd_rWheelBase  : REAL;   (* 龙门当前跨距 m，4..6 *)
    AxisCmd_rJogVelX    : REAL;
    AxisCmd_rJogVelY    : REAL;
    AxisCmd_rJogVelZ    : REAL;
    AxisCmd_rJogVelR    : REAL;
END_VAR
```

### GVL_AxisFb（Axis 任务 → Logic/HMI，禁止 Logic 写）

```iecst
VAR_GLOBAL
    AxisFb_rVelCmdM1    : REAL;   (* FB_XDiff/独立 JOG 当前速度指令，供 HMI *)
    AxisFb_rVelCmdM2    : REAL;
    AxisFb_rPosM1       : REAL;
    AxisFb_rPosM2       : REAL;
    AxisFb_rPosY        : REAL;
    AxisFb_rPosZ        : REAL;
    AxisFb_rPosR        : REAL;
    AxisFb_xStandstill1 : BOOL;
    AxisFb_xStandstill2 : BOOL;
    AxisFb_xStandstillY : BOOL;
    AxisFb_xStandstillZ : BOOL;
    AxisFb_xStandstillR : BOOL;
    AxisFb_xMovingM1    : BOOL;
    AxisFb_xMovingM2    : BOOL;
    AxisFb_xMovingY     : BOOL;
    AxisFb_xMovingZ     : BOOL;
    AxisFb_xMovingR     : BOOL;
    AxisFb_xPoweredM1   : BOOL;
    AxisFb_xPoweredM2   : BOOL;
    AxisFb_xPoweredY    : BOOL;
    AxisFb_xPoweredZ    : BOOL;
    AxisFb_xPoweredR    : BOOL;
    AxisFb_xHomedY      : BOOL;
    AxisFb_xHomedZ      : BOOL;
    AxisFb_xHomedR      : BOOL;
    AxisFb_xFaultM1     : BOOL;
    AxisFb_xFaultM2     : BOOL;
    AxisFb_xFaultY      : BOOL;
    AxisFb_xFaultZ      : BOOL;
    AxisFb_xFaultR      : BOOL;
    AxisFb_xReady       : BOOL;   (* 四轴通讯/状态可动 *)
END_VAR
```

### GVL_HMI_Status（Logic 写，HMI 读灯）

```iecst
VAR_GLOBAL
    HMI_xLampEStop      : BOOL;
    HMI_xLampEnableOk   : BOOL;
    HMI_xLampFault      : BOOL;
    HMI_iAlarmShow      : INT;
END_VAR
```

## 写者矩阵摘要

| 组 | Writer |
|----|--------|
| GVL_HMI | HMI |
| GVL_Logic / HMI_Status / AxisCmd | Logic |
| GVL_IO | IO 映射 |
| GVL_AxisFb | **Axis_Control 任务 only** |
