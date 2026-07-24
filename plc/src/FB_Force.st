FUNCTION_BLOCK FB_Force
(* FB_Force — Modbus 原始力换算 + 软件去皮 + 通讯看门狗（仅提示，不进故障） *)
VAR_INPUT
    wRaw : WORD;            (* 组态映射原始力 %IW102 *)
    rScale : REAL;          (* 倍率，默认 0.01 *)
    xEnable : BOOL;         (* 通讯总使能 *)
    xTare : BOOL;           (* 去皮（上升沿记偏移） *)
    xUntare : BOOL;         (* 取消去皮（上升沿清偏移） *)
END_VAR
VAR_OUTPUT
    rForceN : REAL;         (* 实际力 N *)
    iRaw : INT;             (* 有符号原始计数 *)
    xCommOk : BOOL;         (* 通讯正常 *)
    xTimeout : BOOL;        (* 2s 原始值不变 → 超时（报警 1005） *)
END_VAR
VAR
    rTare : REAL;
    xTarePrev : BOOL;
    xUntarePrev : BOOL;
    wPrev : WORD;
    tonStale : TON;
    rRawScaled : REAL;
END_VAR

iRaw := WORD_TO_INT(wRaw);
rRawScaled := INT_TO_REAL(iRaw) * rScale;

IF xTare AND NOT xTarePrev THEN
    rTare := rRawScaled;
END_IF;
xTarePrev := xTare;
IF xUntare AND NOT xUntarePrev THEN
    rTare := 0.0;
END_IF;
xUntarePrev := xUntare;

rForceN := rRawScaled - rTare;

tonStale(IN := xEnable AND (wRaw = wPrev), PT := T#2S);
wPrev := wRaw;
xTimeout := xEnable AND tonStale.Q;
xCommOk := xEnable AND NOT xTimeout;
