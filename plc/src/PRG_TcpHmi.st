PROGRAM PRG_TcpHmi
(* PRG_TcpHmi — Modbus TCP 过程映像编解码 + 控制源仲裁。
   PLC=从站；Gateway=主站：FC16 写 Holding1000 命令 / FC03 读 Holding1100 状态。
   eCtrlSrc 为 GVL 变量：0=面板/触摸屏 1=远程(Web)。 *)
VAR
    xInit : BOOL;
    xPanelOp : BOOL;
    xTcpOp : BOOL;
    xValid : BOOL;
    wMagic : WORD;
    wVersion : WORD;
    wSeqHead : WORD;
    wSeqTail : WORD;
    wHeartbeat : WORD;
    dwTmp : DWORD;
    diTmp : DINT;
    i : INT;
    tonHb : TON;
END_VAR

IF NOT xInit THEN
    Tcp_xEStop := TRUE;
    Tcp_rJogVelX := 0.4; Tcp_rSpinVel := 0.3;
    Tcp_rJogVelY := 0.3; Tcp_rJogVelZ := 0.2; Tcp_rJogVelR := 0.2;
    Tcp_rAutoDistX := 1.0; Tcp_rAutoVelX := 0.4;
    Tcp_rAutoVelY := 0.3; Tcp_rAutoVelZ := 0.15;
    Tcp_rWheelBase := 5.0; Tcp_rForceSet := 100.0;
    Tcp_xForceSimEnable := FALSE;
    Tcp_iAutoPasses := 1;
    Tcp_rHeadingErr := 0.0;
    Tcp_rKpTrack := 0.0; Tcp_rKpForce := 1.0;
    Tcp_rAccX := 100.0; Tcp_rDecX := 100.0;
    Tcp_rAccY := 100.0; Tcp_rDecY := 100.0;
    Tcp_rAccZ := 100.0; Tcp_rDecZ := 100.0;
    Tcp_rAccR := 100.0; Tcp_rDecR := 100.0;
    Tcp_iCommStatus := 0;
    Tcp_wLastHb := 0; Tcp_wLastSeq := 16#FFFF; Tcp_wStatusSeq := 0;
    tonHb(IN := FALSE);
    xInit := TRUE;
END_IF;

(* ===== 命令快照解码 ===== *)
wMagic := MB_CmdIn[0];
wVersion := MB_CmdIn[1];
wSeqHead := MB_CmdIn[2];
wHeartbeat := MB_CmdIn[3];
wSeqTail := MB_CmdIn[63];
xValid := (wMagic = 19533) AND (wVersion = 256) AND (wSeqHead = wSeqTail);
IF xValid THEN
    Tcp_iCommStatus := 1;
    IF wHeartbeat <> Tcp_wLastHb THEN
        tonHb(IN := FALSE);
        tonHb(IN := TRUE, PT := T#1S);
        Tcp_wLastHb := wHeartbeat;
    END_IF;
    IF wSeqHead <> Tcp_wLastSeq THEN
        Tcp_wLastSeq := wSeqHead;
        Tcp_xEStop := (MB_CmdIn[4] AND 1) <> 0;
        Tcp_xStop := (MB_CmdIn[4] AND 2) <> 0;
        Tcp_xStopHold3s := (MB_CmdIn[4] AND 4) <> 0;
        Tcp_xStart := (MB_CmdIn[4] AND 8) <> 0;
        Tcp_xEnable := (MB_CmdIn[4] AND 16) <> 0;
        Tcp_xAutoMode := (MB_CmdIn[4] AND 32) <> 0;
        Tcp_xJogXPos := (MB_CmdIn[4] AND 64) <> 0;
        Tcp_xJogXNeg := (MB_CmdIn[4] AND 128) <> 0;
        Tcp_xSpinLeft := (MB_CmdIn[4] AND 256) <> 0;
        Tcp_xSpinRight := (MB_CmdIn[4] AND 512) <> 0;
        Tcp_xJogYPos := (MB_CmdIn[4] AND 1024) <> 0;
        Tcp_xJogYNeg := (MB_CmdIn[4] AND 2048) <> 0;
        Tcp_xJogZPos := (MB_CmdIn[4] AND 4096) <> 0;
        Tcp_xJogZNeg := (MB_CmdIn[4] AND 8192) <> 0;
        Tcp_xJogRPos := (MB_CmdIn[4] AND 16384) <> 0;
        Tcp_xJogRNeg := (MB_CmdIn[4] AND 32768) <> 0;
        Tcp_xHomeY := (MB_CmdIn[5] AND 1) <> 0;
        Tcp_xHomeZ := (MB_CmdIn[5] AND 2) <> 0;
        Tcp_xHomeR := (MB_CmdIn[5] AND 4) <> 0;
        Tcp_xHomeExec := (MB_CmdIn[5] AND 8) <> 0;
        Tcp_xAutoStart := (MB_CmdIn[5] AND 16) <> 0;
        Tcp_xAutoAbort := (MB_CmdIn[5] AND 32) <> 0;
        Tcp_xForceSimEnable := (MB_CmdIn[5] AND 64) <> 0;
        Tcp_xForceTare := (MB_CmdIn[5] AND 128) <> 0;
        Tcp_xForceUntare := (MB_CmdIn[5] AND 256) <> 0;
        Tcp_xForceGuide := (MB_CmdIn[5] AND 512) <> 0;
        Tcp_iHomeAxis := WORD_TO_INT(MB_CmdIn[6]);
        Tcp_iAutoPasses := WORD_TO_INT(MB_CmdIn[7]);
        dwTmp := SHL(WORD_TO_DWORD(MB_CmdIn[8]), 16) OR WORD_TO_DWORD(MB_CmdIn[9]);
        Tcp_rJogVelX := DINT_TO_REAL(DWORD_TO_DINT(dwTmp)) / 1000.0;
        dwTmp := SHL(WORD_TO_DWORD(MB_CmdIn[10]), 16) OR WORD_TO_DWORD(MB_CmdIn[11]);
        Tcp_rSpinVel := DINT_TO_REAL(DWORD_TO_DINT(dwTmp)) / 1000.0;
        dwTmp := SHL(WORD_TO_DWORD(MB_CmdIn[12]), 16) OR WORD_TO_DWORD(MB_CmdIn[13]);
        Tcp_rJogVelY := DINT_TO_REAL(DWORD_TO_DINT(dwTmp)) / 1000.0;
        dwTmp := SHL(WORD_TO_DWORD(MB_CmdIn[14]), 16) OR WORD_TO_DWORD(MB_CmdIn[15]);
        Tcp_rJogVelZ := DINT_TO_REAL(DWORD_TO_DINT(dwTmp)) / 1000.0;
        dwTmp := SHL(WORD_TO_DWORD(MB_CmdIn[16]), 16) OR WORD_TO_DWORD(MB_CmdIn[17]);
        Tcp_rJogVelR := DINT_TO_REAL(DWORD_TO_DINT(dwTmp)) / 1000.0;
        dwTmp := SHL(WORD_TO_DWORD(MB_CmdIn[18]), 16) OR WORD_TO_DWORD(MB_CmdIn[19]);
        Tcp_rAutoDistX := DINT_TO_REAL(DWORD_TO_DINT(dwTmp)) / 1000.0;
        dwTmp := SHL(WORD_TO_DWORD(MB_CmdIn[20]), 16) OR WORD_TO_DWORD(MB_CmdIn[21]);
        Tcp_rAutoVelX := DINT_TO_REAL(DWORD_TO_DINT(dwTmp)) / 1000.0;
        dwTmp := SHL(WORD_TO_DWORD(MB_CmdIn[22]), 16) OR WORD_TO_DWORD(MB_CmdIn[23]);
        Tcp_rAutoVelY := DINT_TO_REAL(DWORD_TO_DINT(dwTmp)) / 1000.0;
        dwTmp := SHL(WORD_TO_DWORD(MB_CmdIn[24]), 16) OR WORD_TO_DWORD(MB_CmdIn[25]);
        Tcp_rAutoVelZ := DINT_TO_REAL(DWORD_TO_DINT(dwTmp)) / 1000.0;
        dwTmp := SHL(WORD_TO_DWORD(MB_CmdIn[26]), 16) OR WORD_TO_DWORD(MB_CmdIn[27]);
        Tcp_rWheelBase := DINT_TO_REAL(DWORD_TO_DINT(dwTmp)) / 1000.0;
        dwTmp := SHL(WORD_TO_DWORD(MB_CmdIn[28]), 16) OR WORD_TO_DWORD(MB_CmdIn[29]);
        Tcp_rForceSet := DINT_TO_REAL(DWORD_TO_DINT(dwTmp)) / 100.0;
        dwTmp := SHL(WORD_TO_DWORD(MB_CmdIn[30]), 16) OR WORD_TO_DWORD(MB_CmdIn[31]);
        Tcp_rForceSim := DINT_TO_REAL(DWORD_TO_DINT(dwTmp)) / 100.0;
        dwTmp := SHL(WORD_TO_DWORD(MB_CmdIn[32]), 16) OR WORD_TO_DWORD(MB_CmdIn[33]);
        Tcp_rHeadingErr := DINT_TO_REAL(DWORD_TO_DINT(dwTmp)) / 1000.0;
        dwTmp := SHL(WORD_TO_DWORD(MB_CmdIn[34]), 16) OR WORD_TO_DWORD(MB_CmdIn[35]);
        Tcp_rKpTrack := DINT_TO_REAL(DWORD_TO_DINT(dwTmp)) / 1000.0;
        dwTmp := SHL(WORD_TO_DWORD(MB_CmdIn[36]), 16) OR WORD_TO_DWORD(MB_CmdIn[37]);
        Tcp_rKpForce := DINT_TO_REAL(DWORD_TO_DINT(dwTmp)) / 1000.0;
        dwTmp := SHL(WORD_TO_DWORD(MB_CmdIn[38]), 16) OR WORD_TO_DWORD(MB_CmdIn[39]);
        Tcp_rAccX := DINT_TO_REAL(DWORD_TO_DINT(dwTmp)) / 1000.0;
        dwTmp := SHL(WORD_TO_DWORD(MB_CmdIn[40]), 16) OR WORD_TO_DWORD(MB_CmdIn[41]);
        Tcp_rDecX := DINT_TO_REAL(DWORD_TO_DINT(dwTmp)) / 1000.0;
        dwTmp := SHL(WORD_TO_DWORD(MB_CmdIn[42]), 16) OR WORD_TO_DWORD(MB_CmdIn[43]);
        Tcp_rAccY := DINT_TO_REAL(DWORD_TO_DINT(dwTmp)) / 1000.0;
        dwTmp := SHL(WORD_TO_DWORD(MB_CmdIn[44]), 16) OR WORD_TO_DWORD(MB_CmdIn[45]);
        Tcp_rDecY := DINT_TO_REAL(DWORD_TO_DINT(dwTmp)) / 1000.0;
        dwTmp := SHL(WORD_TO_DWORD(MB_CmdIn[46]), 16) OR WORD_TO_DWORD(MB_CmdIn[47]);
        Tcp_rAccZ := DINT_TO_REAL(DWORD_TO_DINT(dwTmp)) / 1000.0;
        dwTmp := SHL(WORD_TO_DWORD(MB_CmdIn[48]), 16) OR WORD_TO_DWORD(MB_CmdIn[49]);
        Tcp_rDecZ := DINT_TO_REAL(DWORD_TO_DINT(dwTmp)) / 1000.0;
        dwTmp := SHL(WORD_TO_DWORD(MB_CmdIn[50]), 16) OR WORD_TO_DWORD(MB_CmdIn[51]);
        Tcp_rAccR := DINT_TO_REAL(DWORD_TO_DINT(dwTmp)) / 1000.0;
        dwTmp := SHL(WORD_TO_DWORD(MB_CmdIn[52]), 16) OR WORD_TO_DWORD(MB_CmdIn[53]);
        Tcp_rDecR := DINT_TO_REAL(DWORD_TO_DINT(dwTmp)) / 1000.0;
    END_IF;
ELSIF wMagic <> 0 AND wMagic <> 19533 THEN
    Tcp_iCommStatus := 2;
ELSIF wSeqHead <> wSeqTail THEN
    Tcp_iCommStatus := 3;
END_IF;
tonHb();
IF tonHb.Q OR Tcp_iCommStatus = 0 THEN
    Tcp_xTimeout := TRUE;
    Tcp_xConnected := FALSE;
    Tcp_xOnline := FALSE;
    IF tonHb.Q THEN Tcp_iCommStatus := 4; END_IF;
    Tcp_xJogXPos := FALSE; Tcp_xJogXNeg := FALSE;
    Tcp_xSpinLeft := FALSE; Tcp_xSpinRight := FALSE;
    Tcp_xJogYPos := FALSE; Tcp_xJogYNeg := FALSE;
    Tcp_xJogZPos := FALSE; Tcp_xJogZNeg := FALSE;
    Tcp_xJogRPos := FALSE; Tcp_xJogRNeg := FALSE;
    Tcp_xHomeY := FALSE; Tcp_xHomeZ := FALSE; Tcp_xHomeR := FALSE;
    Tcp_xHomeExec := FALSE;
    Tcp_xStart := FALSE; Tcp_xEnable := FALSE;
    Tcp_xAutoStart := FALSE;
    Tcp_xForceTare := FALSE; Tcp_xForceUntare := FALSE; Tcp_xForceGuide := FALSE;
    Tcp_xStop := TRUE;
    Tcp_xAutoAbort := TRUE;
    Tcp_xEStop := TRUE;
ELSE
    Tcp_xTimeout := FALSE;
    Tcp_xConnected := TRUE;
    Tcp_xOnline := TRUE;
END_IF;

(* ===== 状态快照编码 ===== *)
Tcp_wStatusSeq := Tcp_wStatusSeq + 1;
MB_StatusOut[0] := 19533;
MB_StatusOut[1] := 256;
MB_StatusOut[2] := Tcp_wStatusSeq;
MB_StatusOut[3] := Tcp_wLastSeq;
MB_StatusOut[4] := Tcp_wLastHb;
FOR i := 5 TO 62 DO MB_StatusOut[i] := 0; END_FOR;
MB_StatusOut[5] := INT_TO_WORD(Tcp_iCommStatus);
MB_StatusOut[6] := INT_TO_WORD(HMI_eDevState);
MB_StatusOut[7] := INT_TO_WORD(HMI_eOpMode);
MB_StatusOut[8] := INT_TO_WORD(HMI_iAlarmShow);
MB_StatusOut[9] := INT_TO_WORD(HMI_iAutoStepShow);
IF HMI_xDevStop THEN MB_StatusOut[10] := MB_StatusOut[10] OR 1; END_IF;
IF HMI_xDevRun THEN MB_StatusOut[10] := MB_StatusOut[10] OR 2; END_IF;
IF HMI_xDevError THEN MB_StatusOut[10] := MB_StatusOut[10] OR 4; END_IF;
IF HMI_xLampEStop THEN MB_StatusOut[10] := MB_StatusOut[10] OR 8; END_IF;
IF HMI_xLampEnableOk THEN MB_StatusOut[10] := MB_StatusOut[10] OR 16; END_IF;
IF HMI_xLampFault THEN MB_StatusOut[10] := MB_StatusOut[10] OR 32; END_IF;
IF HMI_xAutoBusy THEN MB_StatusOut[10] := MB_StatusOut[10] OR 64; END_IF;
IF HMI_xAutoDone THEN MB_StatusOut[10] := MB_StatusOut[10] OR 128; END_IF;
IF HMI_xHomedY THEN MB_StatusOut[10] := MB_StatusOut[10] OR 256; END_IF;
IF HMI_xHomedZ THEN MB_StatusOut[10] := MB_StatusOut[10] OR 512; END_IF;
IF HMI_xHomedR THEN MB_StatusOut[10] := MB_StatusOut[10] OR 1024; END_IF;
IF HMI_xHomeBusyY THEN MB_StatusOut[10] := MB_StatusOut[10] OR 2048; END_IF;
IF HMI_xHomeBusyZ THEN MB_StatusOut[10] := MB_StatusOut[10] OR 4096; END_IF;
IF HMI_xHomeBusyR THEN MB_StatusOut[10] := MB_StatusOut[10] OR 8192; END_IF;
IF Tcp_xConnected THEN MB_StatusOut[10] := MB_StatusOut[10] OR 16384; END_IF;
IF Tcp_xTimeout THEN MB_StatusOut[10] := MB_StatusOut[10] OR 32768; END_IF;
IF Force_xCommOk THEN MB_StatusOut[11] := MB_StatusOut[11] OR 1; END_IF;
IF Force_xTimeout THEN MB_StatusOut[11] := MB_StatusOut[11] OR 2; END_IF;
IF Force_xSlaveFail THEN MB_StatusOut[11] := MB_StatusOut[11] OR 4; END_IF;
IF Force_xTareBusy THEN MB_StatusOut[11] := MB_StatusOut[11] OR 8; END_IF;
IF Force_xTareDone THEN MB_StatusOut[11] := MB_StatusOut[11] OR 16; END_IF;
IF AxisFb_xReady THEN MB_StatusOut[11] := MB_StatusOut[11] OR 32; END_IF;
IF AxisFb_xMoveDoneX THEN MB_StatusOut[11] := MB_StatusOut[11] OR 64; END_IF;
IF AxisFb_xMoveDoneY THEN MB_StatusOut[11] := MB_StatusOut[11] OR 128; END_IF;
IF AxisFb_xFaultM1 THEN MB_StatusOut[11] := MB_StatusOut[11] OR 256; END_IF;
IF AxisFb_xFaultM2 THEN MB_StatusOut[11] := MB_StatusOut[11] OR 512; END_IF;
IF AxisFb_xFaultY THEN MB_StatusOut[11] := MB_StatusOut[11] OR 1024; END_IF;
IF AxisFb_xFaultZ THEN MB_StatusOut[11] := MB_StatusOut[11] OR 2048; END_IF;
IF AxisFb_xFaultR THEN MB_StatusOut[11] := MB_StatusOut[11] OR 4096; END_IF;
IF AxisFb_xHomedY THEN MB_StatusOut[11] := MB_StatusOut[11] OR 8192; END_IF;
IF AxisFb_xHomedZ THEN MB_StatusOut[11] := MB_StatusOut[11] OR 16384; END_IF;
IF AxisFb_xHomedR THEN MB_StatusOut[11] := MB_StatusOut[11] OR 32768; END_IF;
diTmp := REAL_TO_DINT(HMI_rForceShow * 100.0);
dwTmp := DINT_TO_DWORD(diTmp);
MB_StatusOut[12] := DWORD_TO_WORD(SHR(dwTmp, 16));
MB_StatusOut[13] := DWORD_TO_WORD(dwTmp AND 16#FFFF);
diTmp := REAL_TO_DINT(AxisFb_rPosM1 * 1000.0);
dwTmp := DINT_TO_DWORD(diTmp);
MB_StatusOut[14] := DWORD_TO_WORD(SHR(dwTmp, 16));
MB_StatusOut[15] := DWORD_TO_WORD(dwTmp AND 16#FFFF);
diTmp := REAL_TO_DINT(AxisFb_rPosM2 * 1000.0);
dwTmp := DINT_TO_DWORD(diTmp);
MB_StatusOut[16] := DWORD_TO_WORD(SHR(dwTmp, 16));
MB_StatusOut[17] := DWORD_TO_WORD(dwTmp AND 16#FFFF);
diTmp := REAL_TO_DINT(AxisFb_rPosY * 1000.0);
dwTmp := DINT_TO_DWORD(diTmp);
MB_StatusOut[18] := DWORD_TO_WORD(SHR(dwTmp, 16));
MB_StatusOut[19] := DWORD_TO_WORD(dwTmp AND 16#FFFF);
diTmp := REAL_TO_DINT(AxisFb_rPosZ * 1000.0);
dwTmp := DINT_TO_DWORD(diTmp);
MB_StatusOut[20] := DWORD_TO_WORD(SHR(dwTmp, 16));
MB_StatusOut[21] := DWORD_TO_WORD(dwTmp AND 16#FFFF);
diTmp := REAL_TO_DINT(AxisFb_rPosR * 1000.0);
dwTmp := DINT_TO_DWORD(diTmp);
MB_StatusOut[22] := DWORD_TO_WORD(SHR(dwTmp, 16));
MB_StatusOut[23] := DWORD_TO_WORD(dwTmp AND 16#FFFF);
diTmp := REAL_TO_DINT(AxisFb_rVelCmdM1 * 1000.0);
dwTmp := DINT_TO_DWORD(diTmp);
MB_StatusOut[24] := DWORD_TO_WORD(SHR(dwTmp, 16));
MB_StatusOut[25] := DWORD_TO_WORD(dwTmp AND 16#FFFF);
diTmp := REAL_TO_DINT(AxisFb_rVelCmdM2 * 1000.0);
dwTmp := DINT_TO_DWORD(diTmp);
MB_StatusOut[26] := DWORD_TO_WORD(SHR(dwTmp, 16));
MB_StatusOut[27] := DWORD_TO_WORD(dwTmp AND 16#FFFF);
MB_StatusOut[63] := Tcp_wStatusSeq;

(* ===== 控制源仲裁 ===== *)
xPanelOp := StartBtn OR StopBtn OR ResetBtn OR JogFwd OR JogBwd OR JogLeft OR JogRight
    OR JogUp OR JogDown OR JogClockAdd OR JogClockMis;
xTcpOp := Tcp_xOnline AND (
    Tcp_xStart OR Tcp_xStop OR Tcp_xStopHold3s OR Tcp_xAutoStart OR Tcp_xAutoAbort
    OR Tcp_xJogXPos OR Tcp_xJogXNeg OR Tcp_xSpinLeft OR Tcp_xSpinRight
    OR Tcp_xJogYPos OR Tcp_xJogYNeg OR Tcp_xJogZPos OR Tcp_xJogZNeg
    OR Tcp_xJogRPos OR Tcp_xJogRNeg
    OR Tcp_xHomeY OR Tcp_xHomeZ OR Tcp_xHomeR OR Tcp_xHomeExec
    OR Tcp_xForceGuide OR Tcp_xForceTare OR Tcp_xForceUntare);
IF NOT Tcp_xOnline THEN
    eCtrlSrc := 0;
ELSIF xTcpOp THEN
    eCtrlSrc := 1;
ELSIF xPanelOp THEN
    eCtrlSrc := 0;
END_IF;

IF eCtrlSrc = 1 THEN
    HMI_xAutoMode := Tcp_xAutoMode;
    HMI_xJogXPos := Tcp_xJogXPos;   HMI_xJogXNeg := Tcp_xJogXNeg;
    HMI_xSpinLeft := Tcp_xSpinLeft; HMI_xSpinRight := Tcp_xSpinRight;
    HMI_xJogYPos := Tcp_xJogYPos;   HMI_xJogYNeg := Tcp_xJogYNeg;
    HMI_xJogZPos := Tcp_xJogZPos;   HMI_xJogZNeg := Tcp_xJogZNeg;
    HMI_xJogRPos := Tcp_xJogRPos;   HMI_xJogRNeg := Tcp_xJogRNeg;
    HMI_xHomeY := Tcp_xHomeY; HMI_xHomeZ := Tcp_xHomeZ; HMI_xHomeR := Tcp_xHomeR;
    HMI_iHomeAxis := Tcp_iHomeAxis; HMI_xHomeExec := Tcp_xHomeExec;
    HMI_xForceGuide := Tcp_xForceGuide;
    HMI_xForceTare := Tcp_xForceTare; HMI_xForceUntare := Tcp_xForceUntare;
    HMI_xForceSimEnable := Tcp_xForceSimEnable;
    HMI_rJogVelX := Tcp_rJogVelX; HMI_rSpinVel := Tcp_rSpinVel;
    HMI_rJogVelY := Tcp_rJogVelY; HMI_rJogVelZ := Tcp_rJogVelZ; HMI_rJogVelR := Tcp_rJogVelR;
    HMI_rAutoDistX := Tcp_rAutoDistX; HMI_rAutoVelX := Tcp_rAutoVelX;
    HMI_rAutoVelY := Tcp_rAutoVelY; HMI_rAutoVelZ := Tcp_rAutoVelZ;
    HMI_rWheelBase := Tcp_rWheelBase; HMI_rForceSet := Tcp_rForceSet;
    HMI_rForceSim := Tcp_rForceSim;
    HMI_iAutoPasses := Tcp_iAutoPasses;
    HMI_rHeadingErr := Tcp_rHeadingErr;
    HMI_rKpTrack := Tcp_rKpTrack;
    HMI_rKpForce := Tcp_rKpForce;
    HMI_rAccX := Tcp_rAccX; HMI_rDecX := Tcp_rDecX;
    HMI_rAccY := Tcp_rAccY; HMI_rDecY := Tcp_rDecY;
    HMI_rAccZ := Tcp_rAccZ; HMI_rDecZ := Tcp_rDecZ;
    HMI_rAccR := Tcp_rAccR; HMI_rDecR := Tcp_rDecR;
END_IF;

HMI_xEStop := EStop AND Tcp_xEStop AND HMI_xEStopReq;
HMI_xStart := StartBtn OR HMI_xStartReq OR (Tcp_xOnline AND Tcp_xStart);
HMI_xEnable := HMI_xStart;
HMI_xStop := StopBtn OR HMI_xStopReq OR (Tcp_xOnline AND Tcp_xStop);
HMI_xStopHold3s := ResetBtn OR HMI_xResetReq OR (Tcp_xOnline AND Tcp_xStopHold3s);
HMI_xAutoStart := (Tcp_xOnline AND Tcp_xAutoStart) OR ((eCtrlSrc = 0) AND HMI_xAutoStartReq);
HMI_xAutoAbort := HMI_xAutoAbortReq OR (Tcp_xOnline AND Tcp_xAutoAbort);
