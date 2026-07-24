FUNCTION_BLOCK FB_XLineTrack
(* FB_XLineTrack — X 直行按航向误差纠偏差速 / 原地左右转。
   eMode: 0=无  1=直行(rBaseVel 带符号 + 纠偏)  2=左旋  3=右旋 *)
VAR_INPUT
    xEnable : BOOL;
    xStop : BOOL;
    eMode : INT;
    rBaseVel : REAL;        (* 直行基础速度（可正可负） *)
    rSpinVel : REAL;        (* 原地旋转速度（正值） *)
    rHeadingErr : REAL;     (* 航向误差（视觉/外部；手动传 0） *)
    rKpTrack : REAL;        (* 纠偏 Kp *)
    rTrimMax : REAL;        (* 纠偏限幅 *)
END_VAR
VAR_OUTPUT
    rVelM1 : REAL;          (* M1 速度指令 *)
    rVelM2 : REAL;          (* M2 速度指令 *)
    xActive : BOOL;
END_VAR
VAR
    rTrim : REAL;
END_VAR

rTrim := LIMIT(-ABS(rTrimMax), rKpTrack * rHeadingErr, ABS(rTrimMax));

CASE eMode OF
    1:
        rVelM1 := rBaseVel + rTrim;
        rVelM2 := rBaseVel - rTrim;
    2:
        rVelM1 := ABS(rSpinVel);
        rVelM2 := -ABS(rSpinVel);
    3:
        rVelM1 := -ABS(rSpinVel);
        rVelM2 := ABS(rSpinVel);
ELSE
    rVelM1 := 0.0;
    rVelM2 := 0.0;
END_CASE;

IF xStop OR NOT xEnable THEN
    rVelM1 := 0.0;
    rVelM2 := 0.0;
END_IF;

xActive := (eMode <> 0) AND xEnable AND NOT xStop;
