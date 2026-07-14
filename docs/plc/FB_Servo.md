# FB_Servo.md — 单轴手动封装（CoDeSys SoftMotion SM3）

> **仅在 Axis_Control 任务内实例化。** 不对 Logic/HMI 暴露 CALL。  
> API 以 **SM3_Basic** 为准（InoProShop / CoDeSys SoftMotion）。

## CoDeSys 要点（勿再写错）

| FB | 正确用法 | 错误用法 |
|----|----------|----------|
| `MC_ReadStatus` | `Disabled/Errorstop/StandStill/DiscreteMotion/ContinuousMotion/...` | **无 `Operational`** |
| `MC_Power` | 使能就绪看 **`Status`**；需 `bRegulatorOn`、`bDriveStart` | 不要用 ReadStatus 冒充 Powered |
| `MC_ReadActualPosition` | `Enable:=TRUE` → `Position` | — |
| 轴故障 | 优先 `fbReadStatus.Errorstop`（及各 FB `.Error`） | 勿假设一定有 `Axis.bError` |

## 接口

```iecst
FUNCTION_BLOCK FB_Servo
VAR_IN_OUT
    Axis            : AXIS_REF_SM3;
END_VAR
VAR_INPUT
    xEnable         : BOOL;
    xJogPos         : BOOL;
    xJogNeg         : BOOL;
    xStop           : BOOL;
    xResetFault     : BOOL;
    xHome           : BOOL;
    xUseVelCmd      : BOOL;   (* TRUE：用 rVelCmd 有符号速度 *)
    rVelCmd         : REAL;
    rJogVel         : REAL;
    rAcc            : REAL;
    rDec            : REAL;
END_VAR
VAR_OUTPUT
    xPowered        : BOOL;   (* := fbPower.Status *)
    xMoving         : BOOL;
    xStandstill     : BOOL;
    xHomed          : BOOL;
    xFault          : BOOL;
    rActPos         : REAL;
END_VAR
VAR
    fbPower         : MC_Power;
    fbJog           : MC_MoveVelocity;
    fbStop          : MC_Stop;
    fbHome          : MC_Home;
    fbReset         : MC_Reset;
    fbReadStatus    : MC_ReadStatus;
    fbReadPos       : MC_ReadActualPosition;
    xEnInternal     : BOOL;
END_VAR
```

## 行为（ST）

```iecst
fbReadStatus(Axis := Axis, Enable := TRUE);
fbReadPos(Axis := Axis, Enable := TRUE);

rActPos := fbReadPos.Position;
xStandstill := fbReadStatus.StandStill;
xMoving := fbReadStatus.DiscreteMotion OR fbReadStatus.ContinuousMotion;

(* 故障：Errorstop + 各运动 FB Error；不用 Axis.bError / Operational *)
xFault := fbReadStatus.Errorstop
       OR fbReadStatus.Error
       OR fbPower.Error
       OR fbJog.Error
       OR fbStop.Error
       OR fbReset.Error;

fbReset(Axis := Axis, Execute := xResetFault);

xEnInternal := xEnable AND NOT xStop AND NOT fbReadStatus.Errorstop;

fbPower(
    Axis := Axis,
    Enable := TRUE,
    bRegulatorOn := xEnInternal,
    bDriveStart := xEnInternal
);
xPowered := fbPower.Status;   (* TRUE = 轴可运动 / 功率级就绪 *)

IF xStop OR NOT xEnable OR fbReadStatus.Errorstop THEN
    fbJog(Axis := Axis, Execute := FALSE);
    fbHome(Axis := Axis, Execute := FALSE);
    fbStop(Axis := Axis, Execute := TRUE, Deceleration := rDec);
ELSIF xHome THEN
    fbStop(Axis := Axis, Execute := FALSE);
    fbJog(Axis := Axis, Execute := FALSE);
    fbHome(Axis := Axis, Execute := TRUE);
ELSIF xUseVelCmd THEN
    fbStop(Axis := Axis, Execute := FALSE);
    fbHome(Axis := Axis, Execute := FALSE);
    IF ABS(rVelCmd) > 1.0E-6 AND xPowered THEN
        fbJog(Axis := Axis, Execute := TRUE, Velocity := rVelCmd,
              Acceleration := rAcc, Deceleration := rDec);
    ELSE
        fbJog(Axis := Axis, Execute := FALSE);
    END_IF;
ELSIF xJogPos XOR xJogNeg THEN
    fbStop(Axis := Axis, Execute := FALSE);
    fbHome(Axis := Axis, Execute := FALSE);
    IF xPowered THEN
        IF xJogPos THEN
            fbJog(Axis := Axis, Execute := TRUE, Velocity := ABS(rJogVel),
                  Acceleration := rAcc, Deceleration := rDec);
        ELSE
            fbJog(Axis := Axis, Execute := TRUE, Velocity := -ABS(rJogVel),
                  Acceleration := rAcc, Deceleration := rDec);
        END_IF;
    ELSE
        fbJog(Axis := Axis, Execute := FALSE);
    END_IF;
ELSE
    fbJog(Axis := Axis, Execute := FALSE);
    fbHome(Axis := Axis, Execute := FALSE);
    fbStop(Axis := Axis, Execute := FALSE);
END_IF;

IF fbHome.Done THEN
    xHomed := TRUE;
END_IF;
```

## 约束

- 正方向：现场顺时针为正（轴参数配置）。  
- M5/R：`xEnable` 由上层门控。  
- **点动**：`xJogPos`/`xJogNeg` 为电平——**TRUE=按 `rJogVel` 移动，FALSE=暂停**（`fbJog.Execute:=FALSE`），不在 JOG 分支内清功率。  
- **使能**：`xEnable`（←`AxisCmd_xPower`）须由 HMI 使能触发闩给出；故障复位后 Logic 清闩，须重新上使能再动。  
