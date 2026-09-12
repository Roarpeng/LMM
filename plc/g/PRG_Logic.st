PROGRAM PRG_Logic
(* PRG_Logic — 消费已仲裁 HMI_* + 面板键；写 AxisCmd_*；状态只读派生（无状态机耦合）。
   禁止 CALL Axis / FB_Servo。 *)
VAR
    tonHold : TON;
    tonReady : TON;
    xResetPulse : BOOL;
    xResetPrev : BOOL;
    xSafe : BOOL;
    xAutoStartPrev : BOOL;
    xAutoStartEdge : BOOL;
    rRHold : REAL;
    iPass : INT;
    xAutoTareSent : BOOL;
    xHomeTrigY : BOOL;
    xHomeTrigZ : BOOL;
    xHomeTrigR : BOOL;
    xHomeTrigYPrev : BOOL;
    xHomeTrigZPrev : BOOL;
    xHomeTrigRPrev : BOOL;
    xAnyHomeBusy : BOOL;
    xReadyAll : BOOL;
    xPanelSrc : BOOL;       (* eCtrlSrc=0：面板/触摸屏源 *)
    xJogXPosM : BOOL;       (* 合并后点动（HMI/Web OR 面板键） *)
    xJogXNegM : BOOL;
    xJogYPosM : BOOL;
    xJogYNegM : BOOL;
    xJogZPosM : BOOL;
    xJogZNegM : BOOL;
    xJogRPosM : BOOL;
    xJogRNegM : BOOL;
    xCmdJogXPos : BOOL;
    xCmdJogXNeg : BOOL;
    xCmdSpinL : BOOL;
    xCmdSpinR : BOOL;
    xCmdJogYPos : BOOL;
    xCmdJogYNeg : BOOL;
    xCmdJogZPos : BOOL;
    xCmdJogZNeg : BOOL;
    xCmdJogRPos : BOOL;
    xCmdJogRNeg : BOOL;
    xCmdForceFollow : BOOL;
    xCmdMoveRelX : BOOL;
    xCmdMoveRelY : BOOL;
    xCmdMoveAbsY : BOOL;
    xCmdHoldR : BOOL;
    (* 0.60 X 视觉直控仲裁 / 看门狗 *)
    tonDirectWd : TON;
    xVisSeen : BOOL;
    xVisReq : BOOL;
    xDirectSafe : BOOL;
    Vis_wSeqPrev : WORD;
    rVelM1Sel : REAL;
    rVelM2Sel : REAL;
    (* 0.68 全轴直控：心跳 + 模式仲裁中间量 *)
    tonDirect2 : TON;
    xDirectSeen : BOOL;
    wDirectSeqPrev : WORD;
    xDirect2Enable : BOOL;
    xHmiDirectVelX : BOOL;
    xDirectVelY : BOOL;
    xDirectVelZ : BOOL;
    xDirectVelR : BOOL;
    xDirectAbsY : BOOL;
    xDirectAbsZ : BOOL;
    xDirectAbsR : BOOL;
    xDirectRelY : BOOL;
    xDirectRelZ : BOOL;
    xDirectRelR : BOOL;
    rDirectFeedY : REAL;
    rDirectFeedZ : REAL;
    rDirectFeedR : REAL;
    rDirectVelYSel : REAL;
    rDirectVelZSel : REAL;
    rDirectVelRSel : REAL;
    rDirectPosYSel : REAL;
    rDirectPosZSel : REAL;
    rDirectPosRSel : REAL;
END_VAR

(* ===== 急停锁存 / 长按复位 ===== *)
IF NOT HMI_xEStop THEN
    xEStopLatched := TRUE;
END_IF;
tonHold(IN := HMI_xStop AND HMI_xEStop, PT := T#3S);
xResetPulse := (HMI_xStopHold3s OR tonHold.Q) AND NOT xResetPrev;
xResetPrev := HMI_xStopHold3s OR tonHold.Q;
IF xResetPulse THEN
    xEStopLatched := FALSE;
    AxisCmd_xResetFault := TRUE;
    iAutoStep := 0;
    iPass := 0;
    Force_xSlaveFail := FALSE;
ELSE
    AxisCmd_xResetFault := FALSE;
END_IF;

(* 故障汇总：各轴 Errorstop（同步跳闸已废，不再 OR AxisFb_xSyncFault） *)
xFaultAggregate := AxisFb_xFaultM1 OR AxisFb_xFaultM2 OR AxisFb_xFaultY OR AxisFb_xFaultZ
    OR (xM5Ready AND AxisFb_xFaultR);

IF HMI_xAutoMode THEN eOpMode := 1; ELSE eOpMode := 0; END_IF;
HMI_eOpMode := eOpMode;

(* 安全 / 使能 —— 去耦：只看急停 + 故障 *)
xSafe := HMI_xEStop AND NOT xEStopLatched;
AxisCmd_xPower := xSafe;
AxisCmd_xStopAll := HMI_xStop OR NOT xSafe OR xFaultAggregate OR HMI_xAutoAbort;

(* ===== 0.68 全轴直控：心跳看门狗 + 安全门（视觉与操作员共用） ===== *)
(* HMI_wDirectSeq 300ms 不变 -> 心跳丢失，退出直控并停 *)
IF HMI_wDirectSeq <> wDirectSeqPrev THEN
    wDirectSeqPrev := HMI_wDirectSeq;
    xDirectSeen := TRUE;
    tonDirect2(IN := FALSE);
    tonDirect2(IN := TRUE, PT := Cfg_tDirectTimeout);
END_IF;
tonDirect2();
Direct2_xOnline := xDirectSeen AND NOT tonDirect2.Q;
Direct2_wSeqEcho := HMI_wDirectSeq;
(* 直控安全门：手动模式 + 安全 + 未停止 + 无轴故障 *)
Direct2_xSafe := xSafe AND (eOpMode = 0) AND NOT HMI_xStop AND NOT xFaultAggregate;
xDirect2Enable := HMI_xDirectEnable AND Direct2_xOnline AND Direct2_xSafe;

(* ===== 0.60/0.68 X 视觉/Web 直控：视觉(Vis_*)优先，Web 走 HMI_* 全轴通道 ===== *)
(* 视觉心跳：Vis_wSeq 变化则复位看门狗；200ms 无变化 -> 离线 *)
IF Vis_wSeq <> Vis_wSeqPrev THEN
    Vis_wSeqPrev := Vis_wSeq;
    xVisSeen := TRUE;
    tonDirectWd(IN := FALSE);
    tonDirectWd(IN := TRUE, PT := T#200MS);
END_IF;
tonDirectWd();
Direct_xOnline := xVisSeen AND NOT tonDirectWd.Q;
Direct_wSeqEcho := Vis_wSeq;

xVisReq := Vis_xEnable AND Direct_xOnline;
xDirectSafe := Direct2_xSafe;
xHmiDirectVelX := HMI_xDirectEnable AND (HMI_iDirectModeX = UINT#1) AND Direct2_xOnline;
IF xVisReq THEN
    rVelM1Sel := Vis_rVelM1Set;
    rVelM2Sel := Vis_rVelM2Set;
ELSIF xHmiDirectVelX THEN
    rVelM1Sel := LIMIT(-Cfg_rDirectVelMaxX, HMI_rVelM1Set, Cfg_rDirectVelMaxX);
    rVelM2Sel := LIMIT(-Cfg_rDirectVelMaxX, HMI_rVelM2Set, Cfg_rDirectVelMaxX);
ELSE
    rVelM1Sel := 0.0;
    rVelM2Sel := 0.0;
END_IF;

Direct_xEnable := (xVisReq OR xHmiDirectVelX) AND xDirectSafe;
AxisCmd_xDirectVel := Direct_xEnable;
AxisCmd_rVelM1Set := rVelM1Sel;
AxisCmd_rVelM2Set := rVelM2Sel;
Direct2_xActiveX := Direct_xEnable;

(* ===== 0.68 Y/Z/R 直控：0=idle(减速停) 1=速度 2=绝对 3=相对 ===== *)
(* 先清本地指令，模式仲裁后扫描末尾一次性写 AxisCmd_*，避免同扫描 TRUE->FALSE 空窗 *)
xDirectVelY := FALSE; xDirectVelZ := FALSE; xDirectVelR := FALSE;
xDirectAbsY := FALSE; xDirectAbsZ := FALSE; xDirectAbsR := FALSE;
xDirectRelY := FALSE; xDirectRelZ := FALSE; xDirectRelR := FALSE;
rDirectVelYSel := 0.0; rDirectVelZSel := 0.0; rDirectVelRSel := 0.0;
rDirectPosYSel := 0.0; rDirectPosZSel := 0.0; rDirectPosRSel := 0.0;
(* 限幅后的进给速度；模式 2/3 用同一进给速度，避免位置模式下速度=0 *)
rDirectFeedY := LIMIT(0.0, ABS(HMI_rDirectVelY), Cfg_rDirectVelMaxY);
IF rDirectFeedY < 1.0E-4 THEN rDirectFeedY := Cfg_rDirectVelMaxY; END_IF;
rDirectFeedZ := LIMIT(0.0, ABS(HMI_rDirectVelZ), Cfg_rDirectVelMaxZ);
IF rDirectFeedZ < 1.0E-4 THEN rDirectFeedZ := Cfg_rDirectVelMaxZ; END_IF;
rDirectFeedR := LIMIT(0.0, ABS(HMI_rDirectVelR), Cfg_rDirectVelMaxR);
IF rDirectFeedR < 1.0E-4 THEN rDirectFeedR := Cfg_rDirectVelMaxR; END_IF;

IF xDirect2Enable THEN
    CASE HMI_iDirectModeY OF
        1:
            xDirectVelY := TRUE;
            rDirectVelYSel := LIMIT(-Cfg_rDirectVelMaxY, HMI_rDirectVelY, Cfg_rDirectVelMaxY);
        2:
            xDirectAbsY := TRUE;
            rDirectPosYSel := LIMIT(Cfg_rLimYNeg, HMI_rDirectPosY, Cfg_rLimYPos);
            rDirectVelYSel := rDirectFeedY;
        3:
            xDirectRelY := TRUE;
            rDirectPosYSel := HMI_rDirectPosY;
            rDirectVelYSel := rDirectFeedY;
    END_CASE;
    CASE HMI_iDirectModeZ OF
        1:
            xDirectVelZ := TRUE;
            rDirectVelZSel := LIMIT(-Cfg_rDirectVelMaxZ, HMI_rDirectVelZ, Cfg_rDirectVelMaxZ);
        2:
            xDirectAbsZ := TRUE;
            rDirectPosZSel := LIMIT(Cfg_rLimZNeg, HMI_rDirectPosZ, Cfg_rLimZPos);
            rDirectVelZSel := rDirectFeedZ;
        3:
            xDirectRelZ := TRUE;
            rDirectPosZSel := HMI_rDirectPosZ;
            rDirectVelZSel := rDirectFeedZ;
    END_CASE;
    CASE HMI_iDirectModeR OF
        1:
            xDirectVelR := TRUE;
            rDirectVelRSel := LIMIT(-Cfg_rDirectVelMaxR, HMI_rDirectVelR, Cfg_rDirectVelMaxR);
        2:
            xDirectAbsR := TRUE;
            rDirectPosRSel := LIMIT(Cfg_rLimRNeg, HMI_rDirectPosR, Cfg_rLimRPos);
            rDirectVelRSel := rDirectFeedR;
        3:
            xDirectRelR := TRUE;
            rDirectPosRSel := HMI_rDirectPosR;
            rDirectVelRSel := rDirectFeedR;
    END_CASE;
END_IF;
Direct2_xActiveY := xDirect2Enable AND (HMI_iDirectModeY <> UINT#0);
Direct2_xActiveZ := xDirect2Enable AND (HMI_iDirectModeZ <> UINT#0);
Direct2_xActiveR := xDirect2Enable AND (HMI_iDirectModeR <> UINT#0);

(* 力/纠偏参数下发 *)
rForceKp := HMI_rKpForce;
IF rForceKp < 1.0E-6 THEN rForceKp := 1.0; END_IF;
AxisCmd_rForceSet := HMI_rForceSet;
AxisCmd_rForceKp := rForceKp;
AxisCmd_rForceVelMax := ABS(HMI_rAutoVelZ);
IF AxisCmd_rForceVelMax < 1.0E-6 THEN AxisCmd_rForceVelMax := ABS(HMI_rJogVelZ); END_IF;
AxisCmd_rHeadingErr := HMI_rHeadingErr;

IF HMI_xForceSimEnable THEN
    rForceAct := HMI_rForceSim;
END_IF;
HMI_rForceShow := rForceAct;
HMI_rForceSetEcho := HMI_rForceSet;

AxisCmd_rJogVelX := HMI_rJogVelX;
AxisCmd_rSpinVel := HMI_rSpinVel;
AxisCmd_rJogVelY := HMI_rJogVelY;
AxisCmd_rJogVelZ := HMI_rJogVelZ;
AxisCmd_rJogVelR := HMI_rJogVelR;
AxisCmd_rWheelBase := LIMIT(4.0, HMI_rWheelBase, 6.0);
(* 每轴加减速：仅未填(≈0)才兜底 100。X 已调到与点动速度同量级时必须原样下发。 *)
AxisCmd_rAccX := HMI_rAccX; IF AxisCmd_rAccX < 0.05 THEN AxisCmd_rAccX := 100.0; END_IF;
AxisCmd_rDecX := HMI_rDecX; IF AxisCmd_rDecX < 0.05 THEN AxisCmd_rDecX := 100.0; END_IF;
AxisCmd_rAccY := HMI_rAccY; IF AxisCmd_rAccY < 1.0 THEN AxisCmd_rAccY := 100.0; END_IF;
AxisCmd_rDecY := HMI_rDecY; IF AxisCmd_rDecY < 1.0 THEN AxisCmd_rDecY := 100.0; END_IF;
AxisCmd_rAccZ := HMI_rAccZ; IF AxisCmd_rAccZ < 1.0 THEN AxisCmd_rAccZ := 100.0; END_IF;
AxisCmd_rDecZ := HMI_rDecZ; IF AxisCmd_rDecZ < 1.0 THEN AxisCmd_rDecZ := 100.0; END_IF;
AxisCmd_rAccR := HMI_rAccR; IF AxisCmd_rAccR < 1.0 THEN AxisCmd_rAccR := 100.0; END_IF;
AxisCmd_rDecR := HMI_rDecR; IF AxisCmd_rDecR < 1.0 THEN AxisCmd_rDecR := 100.0; END_IF;

(* 限位联锁：物理限位输入 ∨ 可配置硬限位（Cfg_rLim*，FB_Servo 内另有最终闸门） *)
xIlk_BlockYPlus := I_xLimYPos OR (AxisFb_rPosY >= Cfg_rLimYPos);
xIlk_BlockYNeg := I_xLimYNeg OR (AxisFb_rPosY <= Cfg_rLimYNeg);
xIlk_BlockZPlus := I_xLimZPos OR (AxisFb_rPosZ >= Cfg_rLimZPos);
xIlk_BlockZNeg := I_xLimZNeg OR (AxisFb_rPosZ <= Cfg_rLimZNeg);

(* 运动位先写入局部，扫描结束一次性交给 AxisCmd。
   禁止先清 GVL 再置位：ETHERCAT 优先级更高，会采到 FALSE 空窗，点动 Acc 被重爬三次。 *)
xCmdJogXPos := FALSE; xCmdJogXNeg := FALSE;
xCmdSpinL := FALSE; xCmdSpinR := FALSE;
xCmdJogYPos := FALSE; xCmdJogYNeg := FALSE;
xCmdJogZPos := FALSE; xCmdJogZNeg := FALSE;
xCmdJogRPos := FALSE; xCmdJogRNeg := FALSE;
xCmdForceFollow := FALSE;
xCmdMoveRelX := FALSE;
xCmdMoveRelY := FALSE;
xCmdMoveAbsY := FALSE;
xCmdHoldR := FALSE;
(* 视觉差速：手动点动与自动走距都下发 Kp；FB 仅在直行模式用 *)
AxisCmd_rTrackKp := HMI_rKpTrack;
Logic_xForceTare := FALSE;

xAutoStartEdge := HMI_xAutoStart AND NOT xAutoStartPrev;
xAutoStartPrev := HMI_xAutoStart;

IF HMI_xAutoAbort OR NOT xSafe OR xFaultAggregate THEN
    iAutoStep := 0;
    iPass := 0;
    HMI_xAutoBusy := FALSE;
END_IF;

(* ===== 点动源合并：面板键（仅面板/触摸屏源时）OR 触摸屏/Web ===== *)
xPanelSrc := (eCtrlSrc = 0);
xJogXPosM := HMI_xJogXPos OR (xPanelSrc AND JogFwd);
xJogXNegM := HMI_xJogXNeg OR (xPanelSrc AND JogBwd);
xJogYPosM := HMI_xJogYPos OR (xPanelSrc AND JogRight);
xJogYNegM := HMI_xJogYNeg OR (xPanelSrc AND JogLeft);
xJogZPosM := HMI_xJogZPos OR (xPanelSrc AND JogUp);
xJogZNegM := HMI_xJogZNeg OR (xPanelSrc AND JogDown);
xJogRPosM := HMI_xJogRPos OR (xPanelSrc AND JogClockAdd);
xJogRNegM := HMI_xJogRNeg OR (xPanelSrc AND JogClockMis);

(* ===== 手动 ===== *)
IF xSafe AND (eOpMode = 0) AND NOT HMI_xStop AND NOT xFaultAggregate THEN
    (* 直控在役时屏蔽 X 手动（旋转/点动），速度由视觉/Web 直控通道给 *)
    IF (HMI_xSpinLeft XOR HMI_xSpinRight) AND NOT Direct_xEnable THEN
        xCmdSpinL := HMI_xSpinLeft;
        xCmdSpinR := HMI_xSpinRight;
    ELSIF (xJogXPosM XOR xJogXNegM) AND NOT Direct_xEnable THEN
        xCmdJogXPos := xJogXPosM;
        xCmdJogXNeg := xJogXNegM;
    END_IF;
    xCmdJogYPos := xJogYPosM AND NOT xIlk_BlockYPlus AND NOT xDirect2Enable;
    xCmdJogYNeg := xJogYNegM AND NOT xIlk_BlockYNeg AND NOT xDirect2Enable;
    IF HMI_xForceGuide AND NOT xDirect2Enable THEN
        xCmdForceFollow := TRUE;
    ELSE
        xCmdJogZPos := xJogZPosM AND NOT xIlk_BlockZPlus AND NOT xDirect2Enable;
        xCmdJogZNeg := xJogZNegM AND NOT xIlk_BlockZNeg AND NOT xDirect2Enable;
    END_IF;
    IF xM5Ready AND NOT xDirect2Enable THEN
        xCmdJogRPos := xJogRPosM;
        xCmdJogRNeg := xJogRNegM;
    END_IF;
END_IF;

(* ===== 自动多道循环 ===== *)
IF xSafe AND (eOpMode = 1) AND NOT HMI_xStop AND NOT xFaultAggregate THEN
    IF iAutoStep = 0 AND xAutoStartEdge THEN
        rRHold := AxisFb_rPosR;
        xAutoTareSent := FALSE;
        HMI_xAutoDone := FALSE;
        HMI_xAutoBusy := TRUE;
        iPass := 1;
        iAutoStep := 1;
    END_IF;

    CASE iAutoStep OF
        1:
            xCmdHoldR := TRUE;
            AxisCmd_rRHoldPos := rRHold;
            AxisCmd_rTrackKp := HMI_rKpTrack;
            AxisCmd_rMoveDistX := HMI_rAutoDistX;
            AxisCmd_rMoveVelX := HMI_rAutoVelX;
            xCmdMoveRelX := TRUE;
            IF AxisFb_xMoveDoneX THEN
                xCmdMoveRelX := FALSE;
                iAutoStep := 2;
            END_IF;
        2:
            xCmdHoldR := TRUE;
            AxisCmd_rRHoldPos := rRHold;
            AxisCmd_rMoveAbsPosY := 0.0;
            AxisCmd_rMoveVelY := HMI_rAutoVelY;
            xCmdMoveAbsY := TRUE;
            IF AxisFb_xStandstillY AND (ABS(AxisFb_rPosY) < 0.005) THEN
                xCmdMoveAbsY := FALSE;
                xAutoTareSent := FALSE;
                iAutoStep := 3;
            END_IF;
        3:
            xCmdHoldR := TRUE;
            AxisCmd_rRHoldPos := rRHold;
            IF NOT xAutoTareSent THEN
                Logic_xForceTare := TRUE;
                xAutoTareSent := TRUE;
            END_IF;
            xCmdForceFollow := TRUE;
            IF rForceAct >= HMI_rForceSet THEN
                iAutoStep := 4;
            END_IF;
        4:
            xCmdHoldR := TRUE;
            AxisCmd_rRHoldPos := rRHold;
            xCmdForceFollow := TRUE;
            AxisCmd_rMoveDistY := AxisCmd_rWheelBase;
            AxisCmd_rMoveVelY := HMI_rAutoVelY;
            xCmdMoveRelY := TRUE;
            IF AxisFb_xMoveDoneY THEN
                xCmdMoveRelY := FALSE;
                iAutoStep := 5;
            END_IF;
        5:
            IF iPass < HMI_iAutoPasses THEN
                iPass := iPass + 1;
                iAutoStep := 1;
            ELSE
                iAutoStep := 6;
            END_IF;
        6:
            HMI_xAutoBusy := FALSE;
            HMI_xAutoDone := TRUE;
            iAutoStep := 0;
            iPass := 0;
    END_CASE;
END_IF;

(* ===== 回零：Y/Z/R；同时只回一轴 ===== *)
xHomeTrigY := HMI_xHomeY OR ((HMI_iHomeAxis = 1) AND HMI_xHomeExec);
xHomeTrigZ := HMI_xHomeZ OR ((HMI_iHomeAxis = 2) AND HMI_xHomeExec);
xHomeTrigR := HMI_xHomeR OR ((HMI_iHomeAxis = 3) AND HMI_xHomeExec);
xAnyHomeBusy := AxisCmd_xHomeY OR AxisCmd_xHomeZ OR AxisCmd_xHomeR;

IF AxisCmd_xStopAll OR NOT xSafe OR xFaultAggregate THEN
    AxisCmd_xHomeY := FALSE;
    AxisCmd_xHomeZ := FALSE;
    AxisCmd_xHomeR := FALSE;
ELSE
    IF AxisCmd_xHomeY AND AxisFb_xHomedY THEN AxisCmd_xHomeY := FALSE; END_IF;
    IF AxisCmd_xHomeZ AND AxisFb_xHomedZ THEN AxisCmd_xHomeZ := FALSE; END_IF;
    IF AxisCmd_xHomeR AND AxisFb_xHomedR THEN AxisCmd_xHomeR := FALSE; END_IF;
    IF (eOpMode = 0) AND NOT HMI_xStop THEN
        IF xHomeTrigY AND NOT xHomeTrigYPrev AND NOT xAnyHomeBusy THEN
            AxisCmd_xHomeY := TRUE;
        ELSIF xHomeTrigZ AND NOT xHomeTrigZPrev AND NOT xAnyHomeBusy THEN
            AxisCmd_xHomeZ := TRUE;
        ELSIF xHomeTrigR AND NOT xHomeTrigRPrev AND NOT xAnyHomeBusy AND xM5Ready THEN
            AxisCmd_xHomeR := TRUE;
        END_IF;
    END_IF;
END_IF;
xHomeTrigYPrev := xHomeTrigY;
xHomeTrigZPrev := xHomeTrigZ;
xHomeTrigRPrev := xHomeTrigR;

IF AxisCmd_xHomeY THEN xCmdJogYPos := FALSE; xCmdJogYNeg := FALSE; END_IF;
IF AxisCmd_xHomeZ THEN xCmdJogZPos := FALSE; xCmdJogZNeg := FALSE; xCmdForceFollow := FALSE; END_IF;
IF AxisCmd_xHomeR THEN xCmdJogRPos := FALSE; xCmdJogRNeg := FALSE; END_IF;

(* 本扫描只写一次 GVL，ETHERCAT 不会采到中途 FALSE *)
AxisCmd_xJogXPos := xCmdJogXPos; AxisCmd_xJogXNeg := xCmdJogXNeg;
AxisCmd_xSpinLeft := xCmdSpinL; AxisCmd_xSpinRight := xCmdSpinR;
AxisCmd_xJogYPos := xCmdJogYPos; AxisCmd_xJogYNeg := xCmdJogYNeg;
AxisCmd_xJogZPos := xCmdJogZPos; AxisCmd_xJogZNeg := xCmdJogZNeg;
AxisCmd_xJogRPos := xCmdJogRPos; AxisCmd_xJogRNeg := xCmdJogRNeg;
AxisCmd_xForceFollow := xCmdForceFollow;
AxisCmd_xMoveRelX := xCmdMoveRelX;
AxisCmd_xMoveRelY := xCmdMoveRelY;
AxisCmd_xMoveAbsY := xCmdMoveAbsY;
AxisCmd_xHoldR := xCmdHoldR;
(* 0.68 全轴直控：模式仲裁结果一次性写 AxisCmd_*，避免同扫描 TRUE->FALSE 空窗 *)
AxisCmd_xDirectVelY := xDirectVelY; AxisCmd_xDirectVelZ := xDirectVelZ; AxisCmd_xDirectVelR := xDirectVelR;
AxisCmd_xDirectAbsY := xDirectAbsY; AxisCmd_xDirectAbsZ := xDirectAbsZ; AxisCmd_xDirectAbsR := xDirectAbsR;
AxisCmd_xDirectRelY := xDirectRelY; AxisCmd_xDirectRelZ := xDirectRelZ; AxisCmd_xDirectRelR := xDirectRelR;
AxisCmd_rDirectVelY := rDirectVelYSel; AxisCmd_rDirectVelZ := rDirectVelZSel; AxisCmd_rDirectVelR := rDirectVelRSel;
AxisCmd_rDirectAbsY := rDirectPosYSel; AxisCmd_rDirectAbsZ := rDirectPosZSel; AxisCmd_rDirectAbsR := rDirectPosRSel;
AxisCmd_rDirectRelY := rDirectPosYSel; AxisCmd_rDirectRelZ := rDirectPosZSel; AxisCmd_rDirectRelR := rDirectPosRSel;

HMI_xHomedY := AxisFb_xHomedY;
HMI_xHomedZ := AxisFb_xHomedZ;
HMI_xHomedR := AxisFb_xHomedR;
HMI_xHomeBusyY := AxisCmd_xHomeY;
HMI_xHomeBusyZ := AxisCmd_xHomeZ;
HMI_xHomeBusyR := AxisCmd_xHomeR;

(* 使能就绪诊断 → 1007 *)
xReadyAll := AxisFb_xReadyM1 AND AxisFb_xReadyM2 AND AxisFb_xReadyY AND AxisFb_xReadyZ
    AND (NOT xM5Ready OR AxisFb_xReadyR);
tonReady(IN := AxisCmd_xPower AND NOT xReadyAll AND NOT xFaultAggregate, PT := T#2S);

(* 报警 *)
IF xEStopLatched OR NOT HMI_xEStop THEN
    iAlarmID := 1001;
ELSIF AxisFb_xFaultM1 OR AxisFb_xFaultM2 OR AxisFb_xFaultY OR AxisFb_xFaultZ
        OR (xM5Ready AND AxisFb_xFaultR) THEN
    iAlarmID := 1002;
ELSIF tonReady.Q THEN
    iAlarmID := 1007;
ELSIF NOT HMI_xForceSimEnable AND Force_xSlaveFail THEN
    iAlarmID := 1006;
ELSIF NOT HMI_xForceSimEnable AND Force_xTimeout THEN
    iAlarmID := 1005;
ELSE
    iAlarmID := 0;
END_IF;

(* 状态灯（只读派生，不互锁） *)
Dev_xError := xFaultAggregate;
Dev_xRun := xSafe AND NOT HMI_xStop AND NOT xFaultAggregate;
Dev_xStop := NOT Dev_xRun AND NOT Dev_xError;
HMI_xDevError := Dev_xError;
HMI_xDevRun := Dev_xRun;
HMI_xDevStop := Dev_xStop;
IF Dev_xError THEN HMI_eDevState := 2;
ELSIF Dev_xRun THEN HMI_eDevState := 1;
ELSE HMI_eDevState := 0; END_IF;

HMI_iAutoStepShow := iAutoStep;
HMI_xLampEStop := xEStopLatched OR NOT HMI_xEStop;
HMI_xLampEnableOk := Dev_xRun;
HMI_xLampFault := xFaultAggregate;
HMI_iAlarmShow := iAlarmID;

StopLamp := Dev_xStop;
StartLamp := Dev_xRun;
