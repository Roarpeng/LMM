# FB_XDiff.md — 龙门 X 双驱（同步 / 差速）

> **本期 HMI 简化**：仅使用 **Sync（eMode=1）** 与 **原地旋转（eMode=2, eDiffFunc=1）** 对应 X± / 左旋右旋。Indep/纠偏/差速弯不再对触摸屏开放。

## 上层模式 `eMode`

| 值 | 名称 | 作用 |
|----|------|------|
| 0 | Indep | 单侧 JOG |
| 1 | Sync | **同速执行** → 龙门平移 |
| 2 | Diff | 子功能由 `eDiffFunc` **输入选定** |

## Diff 子功能 `eDiffFunc`（由输入决定）

| 值 | 名称 | 行为 |
|----|------|------|
| 0 | **纠偏** | 两侧**同向**、不等速：`V±Δ`，扶正 |
| 1 | **原地旋转** | **M1 / M2 一正一反**，绕龙门中心转角度（不平移） |
| 2 | **差速拐弯** | 两侧**都动且同向为主**、速度不同：边走边弯（可叠 `ω` 与跨距） |

转向/旋转方向由 `xJogDiffPos/Neg` 决定。

## 接口

```iecst
FUNCTION_BLOCK FB_XDiff
VAR_INPUT
    eMode           : INT;    (* 0 Indep  1 Sync  2 Diff *)
    eDiffFunc       : INT;    (* 0纠偏  1原地旋转(一正一反)  2差速拐弯 *)
    xJogSyncPos     : BOOL;
    xJogSyncNeg     : BOOL;
    xJogDiffPos     : BOOL;
    xJogDiffNeg     : BOOL;
    xStop           : BOOL;
    xEnable         : BOOL;
    rJogVel         : REAL;   (* 基速；原地旋转时为两侧 |速度| *)
    rDiffDelta      : REAL;   (* 纠偏 Δ *)
    rTurnOmega      : REAL;   (* 差速拐弯可选；原地旋转也可用 ω*L/2 代替 rJogVel *)
    rWheelBase      : REAL;   (* 当前跨距 4..6 m *)
END_VAR
VAR_OUTPUT
    rVelCmdM1       : REAL;
    rVelCmdM2       : REAL;
    xActive         : BOOL;
    xUsePairVel     : BOOL;
    xWheelBaseOk    : BOOL;
END_VAR
```

> 已取消 `ePivotSide`「单侧停转当原点」；原地转角统一为 **一正一反**。若以后要单腿枢轴再另开子功能。

## 合成

```iecst
rVelCmdM1 := 0.0;
rVelCmdM2 := 0.0;
xUsePairVel := FALSE;
xActive := FALSE;
xWheelBaseOk := (rWheelBase >= 4.0) AND (rWheelBase <= 6.0);

IF NOT xEnable OR xStop OR eMode = 0 THEN
    RETURN;
END_IF;

IF eMode = 1 THEN
    IF xJogSyncPos XOR xJogSyncNeg THEN
        xUsePairVel := TRUE;
        xActive := TRUE;
        rVelCmdM1 := SEL(xJogSyncPos, -rJogVel, rJogVel);
        rVelCmdM2 := rVelCmdM1;
    END_IF;
    RETURN;
END_IF;

IF NOT (xJogDiffPos XOR xJogDiffNeg) THEN
    RETURN;
END_IF;

IF (eDiffFunc = 1 OR eDiffFunc = 2) AND NOT xWheelBaseOk THEN
    RETURN;
END_IF;

xUsePairVel := TRUE;
xActive := TRUE;

CASE eDiffFunc OF
    0: (* 纠偏：同向 V±Δ *)
        IF xJogDiffPos THEN
            rVelCmdM1 := rJogVel + rDiffDelta;
            rVelCmdM2 := rJogVel - rDiffDelta;
        ELSE
            rVelCmdM1 := -(rJogVel + rDiffDelta);
            rVelCmdM2 := -(rJogVel - rDiffDelta);
        END_IF;

    1: (* 原地旋转：一正一反，转角度 *)
        (* 线速度幅值：优先 ω·L/2，否则用 rJogVel *)
        IF ABS(rTurnOmega) > 1.0E-6 THEN
            rVelCmdM1 := rTurnOmega * rWheelBase * 0.5;
        ELSE
            rVelCmdM1 := rJogVel;
        END_IF;
        rVelCmdM2 := -rVelCmdM1;   (* 一正一反 *)
        IF xJogDiffNeg THEN
            rVelCmdM1 := -rVelCmdM1;
            rVelCmdM2 := -rVelCmdM2;  (* 整体换向 = 反转 *)
        END_IF;

    2: (* 差速拐弯：两侧同向为主，速度差 *)
        IF ABS(rTurnOmega) > 1.0E-6 THEN
            rVelCmdM1 := rJogVel + rTurnOmega * rWheelBase * 0.5;
            rVelCmdM2 := rJogVel - rTurnOmega * rWheelBase * 0.5;
        ELSE
            rVelCmdM1 := rJogVel + rDiffDelta;
            rVelCmdM2 := rJogVel - rDiffDelta;
        END_IF;
        IF xJogDiffNeg THEN
            rVelCmdM1 := -rVelCmdM1;
            rVelCmdM2 := -rVelCmdM2;
        END_IF;

ELSE
    xUsePairVel := FALSE;
    xActive := FALSE;
END_CASE;
```

## 输入来源（现行）

HMI **不直接** 选 eMode/eDiffFunc。由 Axis 根据 `AxisCmd_xJogX*` / `AxisCmd_xSpin*` 置位：

| AxisCmd | FB_XDiff |
|---------|----------|
| JogX± | Sync，`rJogVel`←`AxisCmd_rJogVelX` |
| Spin± | Diff 原地转，`rJogVel`←`AxisCmd_rSpinVel` |
| `rWheelBase` | 跨距(=Y行程) 4~6 |

纠偏 / 差速拐弯 / Indep **本期不用**。
