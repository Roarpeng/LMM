FUNCTION_BLOCK FB_ForceFollow
(* FB_ForceFollow — Z 恒力 P 控制律；向下=负增压；硬限位 [rLimNeg, rLimPos] 内跟随 *)
VAR_INPUT
    rForceSet : REAL;       (* 目标力 N *)
    rForceAct : REAL;       (* 实际力 N *)
    rKp : REAL;             (* 比例增益，越大响应越快，过大易抖 *)
    rVelMax : REAL;         (* 速度限幅（正值） *)
    rDeadband : REAL;       (* 死区 N，区内输出 0 *)
    rPosZ : LREAL;          (* Z 实际位置 *)
    rLimPos : REAL;         (* Z 正限位（同 Cfg_rLimZPos） *)
    rLimNeg : REAL;         (* Z 负限位（同 Cfg_rLimZNeg） *)
    xEnable : BOOL;         (* 力跟随使能（电平） *)
    xInvert : BOOL;         (* 现场方向翻转 *)
END_VAR
VAR_OUTPUT
    rZVelCmd : REAL;        (* Z 速度指令输出 *)
    xInBand : BOOL;         (* 力在死区内 *)
END_VAR
VAR
    rErr : REAL;
    rV : REAL;
END_VAR

IF NOT xEnable THEN
    rZVelCmd := 0.0;
    xInBand := FALSE;
    RETURN;
END_IF;

rErr := rForceSet - rForceAct;
rV := -rKp * rErr;
IF xInvert THEN
    rV := -rV;
END_IF;
rV := LIMIT(-ABS(rVelMax), rV, ABS(rVelMax));

xInBand := ABS(rErr) < rDeadband;
IF xInBand THEN
    rV := 0.0;
END_IF;

(* 硬限位：越限方向输出 0（FB_Servo 另有最终闸门） *)
IF (rPosZ >= rLimPos) AND (rV > 0.0) THEN
    rV := 0.0;
END_IF;
IF (rPosZ <= rLimNeg) AND (rV < 0.0) THEN
    rV := 0.0;
END_IF;

rZVelCmd := rV;
