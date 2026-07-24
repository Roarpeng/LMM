#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LMM.xml 3-POU + 4-FB 重构脚本（确定性、可重跑）。

按 docs/plc/REFACTOR_3POU.md 契约执行：
  - 重写 FB_Servo（加 xReady / MoveRel / MoveAbs）
  - 重写 PRG_Axis_Control（组装 5xFB_Servo + FB_Force + FB_ForceFollow + FB_XLineTrack）
  - 重写 PRG_Logic（安全去耦 + 手动 + 自动多道循环 + 回零 + 1007 诊断）
  - 重写 PLC_PRG（PRG_TcpHmi -> PRG_Logic）
  - FB_XDiff  改名重写为 FB_XLineTrack
  - 新增 FB_Force / FB_ForceFollow
  - PRG_TcpHmi 外科插入（保留 socket 收发）：新增局部变量 / 新键解析 / 三源仲裁
  - 删除 PRG_Force485
  - GVL 追加新符号
  - ProjectStructure 增删对象
最后做 XML 良构校验。
"""
import re
import sys
import shutil
import xml.dom.minidom as minidom

SRC = "LMM.xml"
BAK = "LMM.xml.bak.refactor3pou"

# GUID
G_SERVO = "095f55bd-5910-4f8e-b349-f7b40f09358c"
G_AXIS  = "a1b2c3d4-e5f6-4789-a012-444444444444"
G_LOGIC = "a1b2c3d4-e5f6-4789-a012-333333333333"
G_TCP   = "a1b2c3d4-e5f6-4789-a012-555555555555"
G_MAIN  = "ff3e658d-23f1-4e79-9e6a-94708f19c17b"
G_XLINE = "a1b2c3d4-e5f6-4789-a012-222222222222"   # 复用原 FB_XDiff
G_FORCE = "a1b2c3d4-e5f6-4789-a012-888888888888"
G_FF    = "a1b2c3d4-e5f6-4789-a012-999999999999"

FB_FOLDER_GUID = "2dc75837-520f-43d9-90dd-47cded0212a2"


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------- interface 变量构造 ----------
def v(name, typ, indent=12):
    p = " " * indent
    return (f"{p}<variable name=\"{name}\">\n"
            f"{p}  <type>\n{p}    <{typ} />\n{p}  </type>\n"
            f"{p}</variable>\n")


def dv(name, deriv, indent=12):
    p = " " * indent
    return (f"{p}<variable name=\"{name}\">\n"
            f"{p}  <type>\n{p}    <derived name=\"{deriv}\" />\n{p}  </type>\n"
            f"{p}</variable>\n")


# ---------- addData 构造 ----------
def adddata(name, guid, fb_folder=False):
    head = (
        '        <addData>\n'
        '          <data name="http://www.3s-software.com/plcopenxml/pathstructure" handleUnknown="discard">\n'
        '            <pathStructure isFolder="False" name="Device" namespace="1ee21fdd-5562-44a0-a3ce-665d74916d50" factoryName="Inovance.InoPro.InoDeviceObject.DeviceObjectFactory" factoryGuid="{84d12aa5-3225-473b-9df6-18af40889bdf}" objectGuid="d7de5ac3-3f30-45ac-8468-ec250b4e523b">\n'
        '              <pathStructure isFolder="False" name="Plc Logic" namespace="00000000-0000-0000-0000-000000000000" factoryName="_3S.CoDeSys.PlcLogicObject.PlcLogicObjectFactory" factoryGuid="{8ceeba4e-ac7a-4fbd-9415-bfb2d98668ab}" objectGuid="8a291c6e-c5c5-4a07-8c04-1100df0e1491">\n'
        '                <pathStructure isFolder="False" name="Application" namespace="e5b60c93-5445-4e40-ada9-cd9c005549b4" factoryName="_3S.CoDeSys.ApplicationObject.ApplicationObjectFactory" factoryGuid="{ECADC42E-716E-4ff3-A93C-0CD143F9743F}" objectGuid="69822df8-b9c0-4a01-9450-b2cdc030688c">\n'
    )
    if fb_folder:
        mid = (
            '                  <pathStructure isFolder="True" name="FB" namespace="00000000-0000-0000-0000-000000000000" factoryName="Inovance.InoPro.InoNavigators.FolderObjectFactory" factoryGuid="{BA66A801-C738-4176-B072-DFE26ACE36D3}" objectGuid="' + FB_FOLDER_GUID + '">\n'
            '                    <pathStructure isFolder="False" name="' + name + '" namespace="e5b60c93-5445-4e40-ada9-cd9c005549b4" factoryName="Inovance.InoPro.InoPOUObject.POUObjectFactory" factoryGuid="{39C4ED2B-903C-464c-9041-7DF4ECEE9609}" objectGuid="' + guid + '" />\n'
            '                  </pathStructure>\n'
        )
    else:
        mid = (
            '                  <pathStructure isFolder="False" name="' + name + '" namespace="e5b60c93-5445-4e40-ada9-cd9c005549b4" factoryName="Inovance.InoPro.InoPOUObject.POUObjectFactory" factoryGuid="{39C4ED2B-903C-464c-9041-7DF4ECEE9609}" objectGuid="' + guid + '" />\n'
        )
    tail = (
        '                </pathStructure>\n'
        '              </pathStructure>\n'
        '            </pathStructure>\n'
        '          </data>\n'
        '          <data name="http://www.3s-software.com/plcopenxml/objectid" handleUnknown="discard">\n'
        '            <ObjectId>' + guid + '</ObjectId>\n'
        '          </data>\n'
        '        </addData>\n'
    )
    return head + mid + tail


def make_pou(name, pou_type, guid, interface_inner, body_plain, fb_folder=False):
    body = esc(body_plain)
    return (
        f'      <pou name="{name}" pouType="{pou_type}">\n'
        f'        <interface>\n{interface_inner}        </interface>\n'
        f'        <body>\n          <ST>\n'
        f'            <xhtml xmlns="http://www.w3.org/1999/xhtml">{body}</xhtml>\n'
        f'          </ST>\n        </body>\n'
        f'{adddata(name, guid, fb_folder)}'
        f'      </pou>\n'
    )


# ============================================================
# FB_Servo
# ============================================================
IF_SERVO = (
    "          <inputVars>\n"
    + v("xEnable", "BOOL") + v("xJogPos", "BOOL") + v("xJogNeg", "BOOL")
    + v("xStop", "BOOL") + v("xResetFault", "BOOL") + v("xHome", "BOOL")
    + v("xUseVelCmd", "BOOL") + v("rVelCmd", "REAL") + v("rJogVel", "REAL")
    + v("xMoveRel", "BOOL") + v("rDist", "REAL")
    + v("xMoveAbs", "BOOL") + v("rTargetPos", "REAL")
    + v("rVel", "REAL") + v("rAcc", "REAL") + v("rDec", "REAL")
    + "          </inputVars>\n"
    + "          <outputVars>\n"
    + v("xPowered", "BOOL") + v("xReady", "BOOL") + v("xMoving", "BOOL")
    + v("xStandstill", "BOOL") + v("xHomed", "BOOL") + v("xFault", "BOOL")
    + v("xMoveRelDone", "BOOL") + v("xMoveAbsDone", "BOOL") + v("rActPos", "LREAL")
    + "          </outputVars>\n"
    + "          <inOutVars>\n" + dv("Axis", "AXIS_REF_SM3") + "          </inOutVars>\n"
    + "          <localVars>\n"
    + dv("fbPower", "MC_Power") + dv("fbJog", "MC_MoveVelocity") + dv("fbStop", "MC_Stop")
    + dv("fbHome", "MC_Home") + dv("fbReset", "MC_Reset") + dv("fbReadStatus", "MC_ReadStatus")
    + dv("fbReadPos", "MC_ReadActualPosition") + dv("fbSetPos", "MC_SetPosition")
    + dv("fbMoveRel", "MC_MoveRelative") + dv("fbMoveAbs", "MC_MoveAbsolute")
    + v("xEnInternal", "BOOL") + v("xHomePrev", "BOOL") + v("xZeroReq", "BOOL")
    + v("rVelAbs", "REAL") + v("xDirPos", "BOOL") + v("xDirPosPrev", "BOOL")
    + v("xVelActive", "BOOL") + v("xJogExec", "BOOL")
    + "          </localVars>\n"
)

BODY_SERVO = r"""(* FB_Servo — 单轴原子。仲裁：停止/故障 > 回零 > 绝对 > 相对 > 速度 > 点动 > 空闲 *)
(* SM3: MC_MoveVelocity.Velocity 必须 >=0；方向用 Direction，禁止用负速度 *)
fbReadStatus(Axis := Axis, Enable := TRUE);
fbReadPos(Axis := Axis, Enable := TRUE);
rActPos := fbReadPos.Position;
xStandstill := fbReadStatus.StandStill;
xMoving := fbReadStatus.DiscreteMotion OR fbReadStatus.ContinuousMotion;
xFault := fbReadStatus.Errorstop;

fbReset(Axis := Axis, Execute := xResetFault);

xEnInternal := xEnable AND NOT xStop AND NOT fbReadStatus.Errorstop;
fbPower(Axis := Axis, Enable := TRUE, bRegulatorOn := xEnInternal, bDriveStart := xEnInternal);
xPowered := fbPower.Status;
xReady := fbPower.Status AND NOT fbReadStatus.Errorstop;

IF xHome AND NOT xHomePrev THEN
	xHomed := FALSE;
	xZeroReq := FALSE;
END_IF;
xHomePrev := xHome;

rVelAbs := 0.0;
xDirPos := TRUE;
xVelActive := FALSE;

IF xStop OR NOT xEnable OR fbReadStatus.Errorstop THEN
	fbMoveRel(Axis := Axis, Execute := FALSE);
	fbMoveAbs(Axis := Axis, Execute := FALSE);
	fbJog(Axis := Axis, Execute := FALSE);
	fbHome(Axis := Axis, Execute := FALSE, Position := 0.0);
	fbStop(Axis := Axis, Execute := TRUE, Deceleration := rDec);
	xZeroReq := FALSE;
	xMoveRelDone := FALSE;
	xMoveAbsDone := FALSE;
	xJogExec := FALSE;

ELSIF xHome THEN
	fbStop(Axis := Axis, Execute := FALSE);
	fbJog(Axis := Axis, Execute := FALSE);
	fbMoveRel(Axis := Axis, Execute := FALSE);
	fbMoveAbs(Axis := Axis, Execute := FALSE);
	fbHome(Axis := Axis, Execute := TRUE, Position := 0.0);
	IF fbHome.Done THEN
		xZeroReq := TRUE;
	END_IF;
	xJogExec := FALSE;

ELSIF xMoveAbs THEN
	fbStop(Axis := Axis, Execute := FALSE);
	fbJog(Axis := Axis, Execute := FALSE);
	fbHome(Axis := Axis, Execute := FALSE, Position := 0.0);
	fbMoveRel(Axis := Axis, Execute := FALSE);
	fbMoveAbs(Axis := Axis, Execute := xPowered, Position := rTargetPos,
		Velocity := ABS(rVel), Acceleration := rAcc, Deceleration := rDec);
	xMoveAbsDone := fbMoveAbs.Done;
	xJogExec := FALSE;

ELSIF xMoveRel THEN
	fbStop(Axis := Axis, Execute := FALSE);
	fbJog(Axis := Axis, Execute := FALSE);
	fbHome(Axis := Axis, Execute := FALSE, Position := 0.0);
	fbMoveAbs(Axis := Axis, Execute := FALSE);
	fbMoveRel(Axis := Axis, Execute := xPowered, Distance := rDist,
		Velocity := ABS(rVel), Acceleration := rAcc, Deceleration := rDec);
	xMoveRelDone := fbMoveRel.Done;
	xJogExec := FALSE;

ELSIF xUseVelCmd THEN
	fbStop(Axis := Axis, Execute := FALSE);
	fbHome(Axis := Axis, Execute := FALSE, Position := 0.0);
	fbMoveRel(Axis := Axis, Execute := FALSE);
	fbMoveAbs(Axis := Axis, Execute := FALSE);
	rVelAbs := ABS(rVelCmd);
	xDirPos := (rVelCmd >= 0.0);
	xVelActive := (rVelAbs > 1.0E-6) AND xPowered;

ELSIF xJogPos XOR xJogNeg THEN
	fbStop(Axis := Axis, Execute := FALSE);
	fbHome(Axis := Axis, Execute := FALSE, Position := 0.0);
	fbMoveRel(Axis := Axis, Execute := FALSE);
	fbMoveAbs(Axis := Axis, Execute := FALSE);
	rVelAbs := ABS(rJogVel);
	xDirPos := xJogPos;
	xVelActive := (rVelAbs > 1.0E-6) AND xPowered;

ELSE
	fbJog(Axis := Axis, Execute := FALSE);
	fbHome(Axis := Axis, Execute := FALSE, Position := 0.0);
	fbMoveRel(Axis := Axis, Execute := FALSE);
	fbMoveAbs(Axis := Axis, Execute := FALSE);
	fbStop(Axis := Axis, Execute := FALSE);
	xMoveRelDone := FALSE;
	xMoveAbsDone := FALSE;
	xJogExec := FALSE;
	xVelActive := FALSE;
END_IF;

IF xVelActive THEN
	IF xDirPos <> xDirPosPrev THEN
		xJogExec := FALSE;
	ELSE
		xJogExec := TRUE;
	END_IF;
	IF xDirPos THEN
		fbJog(Axis := Axis, Execute := xJogExec, ContinuousUpdate := TRUE,
			Velocity := rVelAbs, Acceleration := rAcc, Deceleration := rDec,
			Direction := mcPositiveDirection);
	ELSE
		fbJog(Axis := Axis, Execute := xJogExec, ContinuousUpdate := TRUE,
			Velocity := rVelAbs, Acceleration := rAcc, Deceleration := rDec,
			Direction := mcNegativeDirection);
	END_IF;
ELSIF NOT (xStop OR NOT xEnable OR fbReadStatus.Errorstop OR xHome OR xMoveAbs OR xMoveRel) THEN
	fbJog(Axis := Axis, Execute := FALSE);
	xJogExec := FALSE;
END_IF;
xDirPosPrev := xDirPos;

fbSetPos(Axis := Axis, Execute := xZeroReq, Position := 0.0);
IF fbSetPos.Done THEN
	xHomed := TRUE;
	xZeroReq := FALSE;
END_IF;
"""

# ============================================================
# FB_Force
# ============================================================
IF_FORCE = (
    "          <inputVars>\n"
    + v("wRaw", "WORD") + v("rScale", "REAL") + v("xEnable", "BOOL")
    + v("xTare", "BOOL") + v("xUntare", "BOOL")
    + "          </inputVars>\n"
    + "          <outputVars>\n"
    + v("rForceN", "REAL") + v("iRaw", "INT") + v("xCommOk", "BOOL") + v("xTimeout", "BOOL")
    + "          </outputVars>\n"
    + "          <localVars>\n"
    + v("rTare", "REAL") + v("xTarePrev", "BOOL") + v("xUntarePrev", "BOOL")
    + v("wPrev", "WORD") + dv("tonStale", "TON") + v("rRawScaled", "REAL")
    + "          </localVars>\n"
)

BODY_FORCE = r"""(* FB_Force — Modbus 原始力换算 + 软件去皮 + 通讯看门狗（仅提示） *)
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
"""

# ============================================================
# FB_ForceFollow
# ============================================================
IF_FF = (
    "          <inputVars>\n"
    + v("rForceSet", "REAL") + v("rForceAct", "REAL") + v("rKp", "REAL")
    + v("rVelMax", "REAL") + v("rDeadband", "REAL") + v("rPosZ", "LREAL")
    + v("xHomedZ", "BOOL") + v("xEnable", "BOOL") + v("xInvert", "BOOL")
    + "          </inputVars>\n"
    + "          <outputVars>\n"
    + v("rZVelCmd", "REAL") + v("xInBand", "BOOL")
    + "          </outputVars>\n"
    + "          <localVars>\n"
    + v("rErr", "REAL") + v("rV", "REAL")
    + "          </localVars>\n"
)

BODY_FF = r"""(* FB_ForceFollow — Z 恒力 P 控制律；向下=负；回零后夹紧 [-0.7,0] *)
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

IF xHomedZ THEN
	IF (rPosZ >= 0.0) AND (rV > 0.0) THEN
		rV := 0.0;
	END_IF;
	IF (rPosZ <= -0.7) AND (rV < 0.0) THEN
		rV := 0.0;
	END_IF;
END_IF;

rZVelCmd := rV;
"""

# ============================================================
# FB_XLineTrack
# ============================================================
IF_XLINE = (
    "          <inputVars>\n"
    + v("xEnable", "BOOL") + v("xStop", "BOOL") + v("eMode", "INT")
    + v("rBaseVel", "REAL") + v("rSpinVel", "REAL") + v("rHeadingErr", "REAL")
    + v("rKpTrack", "REAL") + v("rTrimMax", "REAL")
    + "          </inputVars>\n"
    + "          <outputVars>\n"
    + v("rVelM1", "REAL") + v("rVelM2", "REAL") + v("xActive", "BOOL")
    + "          </outputVars>\n"
    + "          <localVars>\n"
    + v("rTrim", "REAL")
    + "          </localVars>\n"
)

BODY_XLINE = r"""(* FB_XLineTrack — X 直行按航向角纠偏差速 / 原地左右转 *)
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
"""

# ============================================================
# PRG_Axis_Control
# ============================================================
IF_AXIS = (
    "          <localVars>\n"
    + dv("fbM1", "FB_Servo") + dv("fbM2", "FB_Servo") + dv("fbY", "FB_Servo")
    + dv("fbZ", "FB_Servo") + dv("fbR", "FB_Servo")
    + dv("fbForce", "FB_Force") + dv("fbFF", "FB_ForceFollow") + dv("fbTrack", "FB_XLineTrack")
    + v("iTrackMode", "INT") + v("rXBase", "REAL") + v("rXStart", "LREAL")
    + v("xMoveRelXPrev", "BOOL") + v("xXVelActive", "BOOL")
    + "          </localVars>\n"
)

BODY_AXIS = r"""(* PRG_Axis_Control — 运动独立任务(ETHERCAT)。只读 AxisCmd_*，写 AxisFb_*/rForceAct *)

(* ===== 力传感转换（本 POU 拥有 rForceAct） ===== *)
fbForce(wRaw := Force_wInRaw, rScale := Force_rScale, xEnable := Force_xEnable,
	xTare := HMI_xForceTare OR Logic_xForceTare, xUntare := HMI_xForceUntare);
Force_iRaw := fbForce.iRaw;
Force_xCommOk := fbForce.xCommOk;
Force_xTimeout := fbForce.xTimeout;
IF NOT HMI_xForceSimEnable THEN
	rForceAct := fbForce.rForceN;
END_IF;

(* ===== X 直线纠偏 / 原地转 ===== *)
iTrackMode := 0;
rXBase := 0.0;
IF AxisCmd_xMoveRelX THEN
	iTrackMode := 1;
	rXBase := ABS(AxisCmd_rMoveVelX);
ELSIF AxisCmd_xSpinLeft THEN
	iTrackMode := 2;
ELSIF AxisCmd_xSpinRight THEN
	iTrackMode := 3;
ELSIF AxisCmd_xJogXPos THEN
	iTrackMode := 1;
	rXBase := ABS(AxisCmd_rJogVelX);
ELSIF AxisCmd_xJogXNeg THEN
	iTrackMode := 1;
	rXBase := -ABS(AxisCmd_rJogVelX);
END_IF;

IF AxisCmd_xMoveRelX AND NOT xMoveRelXPrev THEN
	rXStart := fbM1.rActPos;
	AxisFb_xMoveDoneX := FALSE;
END_IF;
xMoveRelXPrev := AxisCmd_xMoveRelX;
IF AxisCmd_xMoveRelX THEN
	IF ABS(fbM1.rActPos - rXStart) >= ABS(AxisCmd_rMoveDistX) THEN
		AxisFb_xMoveDoneX := TRUE;
	END_IF;
ELSE
	AxisFb_xMoveDoneX := FALSE;
END_IF;

xXVelActive := (iTrackMode <> 0) AND NOT (AxisCmd_xMoveRelX AND AxisFb_xMoveDoneX);

fbTrack(xEnable := AxisCmd_xPower, xStop := AxisCmd_xStopAll, eMode := iTrackMode,
	rBaseVel := rXBase, rSpinVel := AxisCmd_rSpinVel,
	rHeadingErr := AxisCmd_rHeadingErr, rKpTrack := AxisCmd_rTrackKp, rTrimMax := 0.2);

fbM1(Axis := Axis, xEnable := AxisCmd_xPower, xStop := AxisCmd_xStopAll, xResetFault := AxisCmd_xResetFault,
	xUseVelCmd := xXVelActive, rVelCmd := fbTrack.rVelM1, rAcc := AxisCmd_rAcc, rDec := AxisCmd_rDec);
fbM2(Axis := Axis_1, xEnable := AxisCmd_xPower, xStop := AxisCmd_xStopAll, xResetFault := AxisCmd_xResetFault,
	xUseVelCmd := xXVelActive, rVelCmd := fbTrack.rVelM2, rAcc := AxisCmd_rAcc, rDec := AxisCmd_rDec);

(* ===== Y：回零 > 绝对(归位) > 相对(横移) > 点动 ===== *)
fbY(Axis := Axis_2, xEnable := AxisCmd_xPower, xStop := AxisCmd_xStopAll, xResetFault := AxisCmd_xResetFault,
	xHome := AxisCmd_xHomeY,
	xMoveAbs := AxisCmd_xMoveAbsY, rTargetPos := AxisCmd_rMoveAbsPosY,
	xMoveRel := AxisCmd_xMoveRelY, rDist := AxisCmd_rMoveDistY,
	xJogPos := AxisCmd_xJogYPos, xJogNeg := AxisCmd_xJogYNeg, rJogVel := AxisCmd_rJogVelY,
	rVel := AxisCmd_rMoveVelY, rAcc := AxisCmd_rAcc, rDec := AxisCmd_rDec);
AxisFb_xMoveDoneY := fbY.xMoveRelDone;

(* ===== Z：力跟随速度 > 回零 > 点动 ===== *)
fbFF(rForceSet := AxisCmd_rForceSet, rForceAct := rForceAct, rKp := AxisCmd_rForceKp,
	rVelMax := AxisCmd_rForceVelMax, rDeadband := 0.5, rPosZ := fbZ.rActPos,
	xHomedZ := fbZ.xHomed, xEnable := AxisCmd_xForceFollow, xInvert := FALSE);
fbZ(Axis := Axis_3, xEnable := AxisCmd_xPower, xStop := AxisCmd_xStopAll, xResetFault := AxisCmd_xResetFault,
	xHome := AxisCmd_xHomeZ,
	xUseVelCmd := AxisCmd_xForceFollow, rVelCmd := fbFF.rZVelCmd,
	xJogPos := AxisCmd_xJogZPos, xJogNeg := AxisCmd_xJogZNeg, rJogVel := AxisCmd_rJogVelZ,
	rAcc := AxisCmd_rAcc, rDec := AxisCmd_rDec);

(* ===== R：回零 > 保持角(绝对) > 点动；M5 门控 ===== *)
fbR(Axis := Axis_4, xEnable := AxisCmd_xPower AND xM5Ready, xStop := AxisCmd_xStopAll, xResetFault := AxisCmd_xResetFault,
	xHome := AxisCmd_xHomeR,
	xMoveAbs := AxisCmd_xHoldR, rTargetPos := AxisCmd_rRHoldPos,
	xJogPos := AxisCmd_xJogRPos, xJogNeg := AxisCmd_xJogRNeg, rJogVel := AxisCmd_rJogVelR,
	rVel := AxisCmd_rJogVelR, rAcc := AxisCmd_rAcc, rDec := AxisCmd_rDec);

(* ===== 反馈回写 ===== *)
AxisFb_rVelCmdM1 := fbTrack.rVelM1;
AxisFb_rVelCmdM2 := fbTrack.rVelM2;
AxisFb_rPosM1 := fbM1.rActPos; AxisFb_rPosM2 := fbM2.rActPos;
AxisFb_rPosY := fbY.rActPos; AxisFb_rPosZ := fbZ.rActPos; AxisFb_rPosR := fbR.rActPos;
AxisFb_xMovingM1 := fbM1.xMoving; AxisFb_xMovingM2 := fbM2.xMoving;
AxisFb_xMovingY := fbY.xMoving; AxisFb_xMovingZ := fbZ.xMoving; AxisFb_xMovingR := fbR.xMoving;
AxisFb_xStandstill1 := fbM1.xStandstill; AxisFb_xStandstill2 := fbM2.xStandstill;
AxisFb_xStandstillY := fbY.xStandstill; AxisFb_xStandstillZ := fbZ.xStandstill; AxisFb_xStandstillR := fbR.xStandstill;
AxisFb_xPoweredM1 := fbM1.xPowered; AxisFb_xPoweredM2 := fbM2.xPowered;
AxisFb_xPoweredY := fbY.xPowered; AxisFb_xPoweredZ := fbZ.xPowered; AxisFb_xPoweredR := fbR.xPowered;
AxisFb_xReadyM1 := fbM1.xReady; AxisFb_xReadyM2 := fbM2.xReady;
AxisFb_xReadyY := fbY.xReady; AxisFb_xReadyZ := fbZ.xReady; AxisFb_xReadyR := fbR.xReady;
AxisFb_xHomedY := fbY.xHomed; AxisFb_xHomedZ := fbZ.xHomed; AxisFb_xHomedR := fbR.xHomed;
AxisFb_xFaultM1 := fbM1.xFault; AxisFb_xFaultM2 := fbM2.xFault;
AxisFb_xFaultY := fbY.xFault; AxisFb_xFaultZ := fbZ.xFault; AxisFb_xFaultR := fbR.xFault;
AxisFb_xReady := fbM1.xReady AND fbM2.xReady AND fbY.xReady AND fbZ.xReady AND (NOT xM5Ready OR fbR.xReady);
"""

# ============================================================
# PRG_Logic
# ============================================================
IF_LOGIC = (
    "          <localVars>\n"
    + dv("tonHold", "TON") + dv("tonReady", "TON")
    + v("xResetPulse", "BOOL") + v("xResetPrev", "BOOL") + v("xSafe", "BOOL")
    + v("xAutoStartPrev", "BOOL") + v("xAutoStartEdge", "BOOL")
    + v("rRHold", "REAL") + v("iPass", "INT") + v("xAutoTareSent", "BOOL")
    + v("xHomeTrigY", "BOOL") + v("xHomeTrigZ", "BOOL") + v("xHomeTrigR", "BOOL")
    + v("xHomeTrigYPrev", "BOOL") + v("xHomeTrigZPrev", "BOOL") + v("xHomeTrigRPrev", "BOOL")
    + v("xAnyHomeBusy", "BOOL") + v("xReadyAll", "BOOL")
    + "          </localVars>\n"
)

BODY_LOGIC = r"""(* PRG_Logic — 消费已仲裁 HMI_*；写 AxisCmd_*；状态只读派生（无状态机耦合） *)

(* 急停锁存 / 长按复位 *)
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

(* 故障汇总：仅各轴 Errorstop *)
xFaultAggregate := AxisFb_xFaultM1 OR AxisFb_xFaultM2 OR AxisFb_xFaultY OR AxisFb_xFaultZ
	OR (xM5Ready AND AxisFb_xFaultR);

IF HMI_xAutoMode THEN eOpMode := 1; ELSE eOpMode := 0; END_IF;
HMI_eOpMode := eOpMode;

(* 安全 / 使能 —— 去耦：只看急停 + 故障 *)
xSafe := HMI_xEStop AND NOT xEStopLatched;
AxisCmd_xPower := xSafe;
AxisCmd_xStopAll := HMI_xStop OR NOT xSafe OR xFaultAggregate OR HMI_xAutoAbort;

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

AxisCmd_rJogVelX := HMI_rJogVelX;
AxisCmd_rSpinVel := HMI_rSpinVel;
AxisCmd_rJogVelY := HMI_rJogVelY;
AxisCmd_rJogVelZ := HMI_rJogVelZ;
AxisCmd_rJogVelR := HMI_rJogVelR;
AxisCmd_rWheelBase := LIMIT(4.0, HMI_rWheelBase, 6.0);
AxisCmd_rAcc := JogACC;
AxisCmd_rDec := JogDEC;
IF AxisCmd_rAcc < 1.0 THEN AxisCmd_rAcc := 100.0; END_IF;
IF AxisCmd_rDec < 1.0 THEN AxisCmd_rDec := 100.0; END_IF;

(* 限位联锁；Z 回零后软限位 [-0.7,0] *)
xIlk_BlockYPlus := I_xLimYPos;
xIlk_BlockYNeg := I_xLimYNeg;
xIlk_BlockZPlus := I_xLimZPos OR (AxisFb_xHomedZ AND (AxisFb_rPosZ >= 0.0));
xIlk_BlockZNeg := I_xLimZNeg OR (AxisFb_xHomedZ AND (AxisFb_rPosZ <= -0.7));

(* 每拍清命令 *)
AxisCmd_xJogXPos := FALSE; AxisCmd_xJogXNeg := FALSE;
AxisCmd_xSpinLeft := FALSE; AxisCmd_xSpinRight := FALSE;
AxisCmd_xJogYPos := FALSE; AxisCmd_xJogYNeg := FALSE;
AxisCmd_xJogZPos := FALSE; AxisCmd_xJogZNeg := FALSE;
AxisCmd_xJogRPos := FALSE; AxisCmd_xJogRNeg := FALSE;
AxisCmd_xForceFollow := FALSE;
AxisCmd_xMoveRelX := FALSE;
AxisCmd_xMoveRelY := FALSE;
AxisCmd_xMoveAbsY := FALSE;
AxisCmd_xHoldR := FALSE;
AxisCmd_rTrackKp := 0.0;
Logic_xForceTare := FALSE;

xAutoStartEdge := HMI_xAutoStart AND NOT xAutoStartPrev;
xAutoStartPrev := HMI_xAutoStart;

IF HMI_xAutoAbort OR NOT xSafe OR xFaultAggregate THEN
	iAutoStep := 0;
	iPass := 0;
	HMI_xAutoBusy := FALSE;
END_IF;

(* ===== 手动 ===== *)
IF xSafe AND (eOpMode = 0) AND NOT HMI_xStop AND NOT xFaultAggregate THEN
	IF HMI_xSpinLeft XOR HMI_xSpinRight THEN
		AxisCmd_xSpinLeft := HMI_xSpinLeft;
		AxisCmd_xSpinRight := HMI_xSpinRight;
	ELSIF HMI_xJogXPos XOR HMI_xJogXNeg THEN
		AxisCmd_xJogXPos := HMI_xJogXPos;
		AxisCmd_xJogXNeg := HMI_xJogXNeg;
	END_IF;
	AxisCmd_xJogYPos := HMI_xJogYPos AND NOT xIlk_BlockYPlus;
	AxisCmd_xJogYNeg := HMI_xJogYNeg AND NOT xIlk_BlockYNeg;
	IF HMI_xForceGuide THEN
		AxisCmd_xForceFollow := TRUE;
	ELSE
		AxisCmd_xJogZPos := HMI_xJogZPos AND NOT xIlk_BlockZPlus;
		AxisCmd_xJogZNeg := HMI_xJogZNeg AND NOT xIlk_BlockZNeg;
	END_IF;
	IF xM5Ready THEN
		AxisCmd_xJogRPos := HMI_xJogRPos;
		AxisCmd_xJogRNeg := HMI_xJogRNeg;
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
			AxisCmd_xHoldR := TRUE;
			AxisCmd_rRHoldPos := rRHold;
			AxisCmd_rTrackKp := HMI_rKpTrack;
			AxisCmd_rMoveDistX := HMI_rAutoDistX;
			AxisCmd_rMoveVelX := HMI_rAutoVelX;
			AxisCmd_xMoveRelX := TRUE;
			IF AxisFb_xMoveDoneX THEN
				AxisCmd_xMoveRelX := FALSE;
				iAutoStep := 2;
			END_IF;
		2:
			AxisCmd_xHoldR := TRUE;
			AxisCmd_rRHoldPos := rRHold;
			AxisCmd_rMoveAbsPosY := 0.0;
			AxisCmd_rMoveVelY := HMI_rAutoVelY;
			AxisCmd_xMoveAbsY := TRUE;
			IF AxisFb_xStandstillY AND (ABS(AxisFb_rPosY) < 0.005) THEN
				AxisCmd_xMoveAbsY := FALSE;
				xAutoTareSent := FALSE;
				iAutoStep := 3;
			END_IF;
		3:
			AxisCmd_xHoldR := TRUE;
			AxisCmd_rRHoldPos := rRHold;
			IF NOT xAutoTareSent THEN
				Logic_xForceTare := TRUE;
				xAutoTareSent := TRUE;
			END_IF;
			AxisCmd_xForceFollow := TRUE;
			IF rForceAct >= HMI_rForceSet THEN
				iAutoStep := 4;
			END_IF;
		4:
			AxisCmd_xHoldR := TRUE;
			AxisCmd_rRHoldPos := rRHold;
			AxisCmd_xForceFollow := TRUE;
			AxisCmd_rMoveDistY := AxisCmd_rWheelBase;
			AxisCmd_rMoveVelY := HMI_rAutoVelY;
			AxisCmd_xMoveRelY := TRUE;
			IF AxisFb_xMoveDoneY THEN
				AxisCmd_xMoveRelY := FALSE;
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

IF AxisCmd_xHomeY THEN AxisCmd_xJogYPos := FALSE; AxisCmd_xJogYNeg := FALSE; END_IF;
IF AxisCmd_xHomeZ THEN AxisCmd_xJogZPos := FALSE; AxisCmd_xJogZNeg := FALSE; AxisCmd_xForceFollow := FALSE; END_IF;
IF AxisCmd_xHomeR THEN AxisCmd_xJogRPos := FALSE; AxisCmd_xJogRNeg := FALSE; END_IF;

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
ELSIF xFaultAggregate THEN
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
"""

# ============================================================
# PLC_PRG
# ============================================================
BODY_PLCPRG = r"""(* MainTask 入口：HMI 交互 -> 设备逻辑；Axis 在 ETHERCAT 任务独立运行 *)
PRG_TcpHmi();
PRG_Logic();
"""


# ---------- GVL 新增变量 ----------
def gv(name, typ, init=None):
    s = f'        <variable name="{name}">\n          <type>\n            <{typ} />\n          </type>\n'
    if init is not None:
        s += f'          <initialValue>\n            <simpleValue value="{init}" />\n          </initialValue>\n'
    s += '        </variable>\n'
    return s


GVL_NEW = (
    gv("HMI_iAutoPasses", "INT", "1")
    + gv("Tcp_iAutoPasses", "INT", "1")
    + gv("HMI_rHeadingErr", "REAL", "0.0")
    + gv("Tcp_rHeadingErr", "REAL", "0.0")
    + gv("HMI_rKpTrack", "REAL", "0.0")
    + gv("HMI_rKpForce", "REAL", "1.0")
    + gv("HMI_xStartReq", "BOOL")
    + gv("HMI_xStopReq", "BOOL")
    + gv("HMI_xResetReq", "BOOL")
    + gv("HMI_xEStopReq", "BOOL", "TRUE")
    + gv("HMI_xAutoStartReq", "BOOL")
    + gv("HMI_xAutoAbortReq", "BOOL")
    + gv("AxisCmd_rHeadingErr", "REAL")
    + gv("AxisCmd_rTrackKp", "REAL")
    + gv("AxisCmd_rForceSet", "REAL")
    + gv("AxisCmd_rForceKp", "REAL")
    + gv("AxisCmd_rForceVelMax", "REAL")
    + gv("AxisCmd_rMoveAbsPosY", "REAL")
    + gv("AxisCmd_xForceFollow", "BOOL")
    + gv("AxisCmd_xMoveAbsY", "BOOL")
    + gv("AxisFb_xReadyM1", "BOOL")
    + gv("AxisFb_xReadyM2", "BOOL")
    + gv("AxisFb_xReadyY", "BOOL")
    + gv("AxisFb_xReadyZ", "BOOL")
    + gv("AxisFb_xReadyR", "BOOL")
)


# ---------- PRG_TcpHmi 外科插入片段 ----------
TCP_LOCALVARS_INS = (
    '            <variable name="eCtrlSrc">\n              <type>\n                <INT />\n              </type>\n            </variable>\n'
    '            <variable name="xTcpAct">\n              <type>\n                <BOOL />\n              </type>\n            </variable>\n'
)

TCP_INIT_INS = "\tTcp_iAutoPasses := 1;\n\tTcp_rHeadingErr := 0.0;\n"

TCP_PARSE_INS = (
    "\tp := FIND(strLine, '\"HMI_iAutoPasses\":');\n"
    "\tIF p &gt; 0 THEN Tcp_iAutoPasses := STRING_TO_INT(MID(strLine, p + 18, 8)); END_IF;\n"
    "\tp := FIND(strLine, '\"HMI_rHeadingErr\":');\n"
    "\tIF p &gt; 0 THEN Tcp_rHeadingErr := STRING_TO_REAL(MID(strLine, p + 18, 16)); END_IF;\n"
)

TCP_ARB_INS = esc(r"""

(* ================= 面板 / 触摸屏 / Web 三源仲裁 -> HMI_* ================= *)
Tcp_xOnline := Tcp_xConnected AND NOT Tcp_xTimeout;
xTcpAct := Tcp_xOnline AND (
	Tcp_xStart OR Tcp_xStop OR Tcp_xStopHold3s OR Tcp_xEnable
	OR Tcp_xJogXPos OR Tcp_xJogXNeg OR Tcp_xSpinLeft OR Tcp_xSpinRight
	OR Tcp_xJogYPos OR Tcp_xJogYNeg OR Tcp_xJogZPos OR Tcp_xJogZNeg
	OR Tcp_xJogRPos OR Tcp_xJogRNeg
	OR Tcp_xHomeY OR Tcp_xHomeZ OR Tcp_xHomeR OR Tcp_xHomeExec
	OR Tcp_xAutoStart OR Tcp_xAutoAbort
	OR Tcp_xForceGuide OR Tcp_xForceTare OR Tcp_xForceUntare);

IF NOT Tcp_xOnline THEN
	eCtrlSrc := 0;
ELSIF xTcpAct THEN
	eCtrlSrc := 1;
END_IF;

IF eCtrlSrc = 1 THEN
	(* Web 独占命令组（web 优先于触摸屏） *)
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
END_IF;
(* eCtrlSrc=0：触摸屏直写 HMI_* 命令组生效，PLC 不覆盖 *)

(* 安全 / 起停：单写者合成（面板 + 触摸屏Req + Web），不自锁 *)
HMI_xEStop := EStop AND Tcp_xEStop AND HMI_xEStopReq;
HMI_xStart := StartBtn OR HMI_xStartReq OR (Tcp_xOnline AND Tcp_xStart);
HMI_xEnable := HMI_xStart;
HMI_xStop := StopBtn OR HMI_xStopReq OR (Tcp_xOnline AND Tcp_xStop);
HMI_xStopHold3s := ResetBtn OR HMI_xResetReq OR (Tcp_xOnline AND Tcp_xStopHold3s);
HMI_xAutoStart := (Tcp_xOnline AND Tcp_xAutoStart) OR ((eCtrlSrc = 0) AND HMI_xAutoStartReq);
HMI_xAutoAbort := HMI_xAutoAbortReq OR (Tcp_xOnline AND Tcp_xAutoAbort);
""")


def rm_pou(content, name, pou_type):
    pat = re.compile(r'      <pou name="%s" pouType="%s">.*?</pou>\n' % (re.escape(name), pou_type), re.DOTALL)
    new, n = pat.subn("", content, count=1)
    assert n == 1, f"remove {name}: matched {n}"
    return new


def rep_pou(content, name, pou_type, newblock):
    pat = re.compile(r'      <pou name="%s" pouType="%s">.*?</pou>\n' % (re.escape(name), pou_type), re.DOTALL)
    new, n = pat.subn(lambda m: newblock, content, count=1)
    assert n == 1, f"replace {name}: matched {n}"
    return new


def main():
    with open(SRC, "r", encoding="utf-8") as f:
        c = f.read()
    shutil.copyfile(SRC, BAK)

    # --- 替换/新增 POU ---
    c = rep_pou(c, "FB_Servo", "functionBlock",
                make_pou("FB_Servo", "functionBlock", G_SERVO, IF_SERVO, BODY_SERVO, fb_folder=True))
    c = rep_pou(c, "PRG_Axis_Control", "program",
                make_pou("PRG_Axis_Control", "program", G_AXIS, IF_AXIS, BODY_AXIS, fb_folder=False))
    c = rep_pou(c, "PRG_Logic", "program",
                make_pou("PRG_Logic", "program", G_LOGIC, IF_LOGIC, BODY_LOGIC, fb_folder=False))
    c = rep_pou(c, "PLC_PRG", "program",
                make_pou("PLC_PRG", "program", G_MAIN, "          <localVars />\n", BODY_PLCPRG, fb_folder=False))
    # FB_XDiff -> FB_XLineTrack
    c = rep_pou(c, "FB_XDiff", "functionBlock",
                make_pou("FB_XLineTrack", "functionBlock", G_XLINE, IF_XLINE, BODY_XLINE, fb_folder=True))
    # 删除 PRG_Force485
    c = rm_pou(c, "PRG_Force485", "program")
    # 新增 FB_Force / FB_ForceFollow（插到 </pous> 前）
    add_fb = (make_pou("FB_Force", "functionBlock", G_FORCE, IF_FORCE, BODY_FORCE, fb_folder=True)
              + make_pou("FB_ForceFollow", "functionBlock", G_FF, IF_FF, BODY_FF, fb_folder=True))
    assert c.count("    </pous>\n") == 1
    c = c.replace("    </pous>\n", add_fb + "    </pous>\n", 1)

    # --- PRG_TcpHmi 外科插入 ---
    anchor_lv = ('            <variable name="xInit">\n              <type>\n                <BOOL />\n'
                 '              </type>\n            </variable>\n          </localVars>')
    assert c.count(anchor_lv) == 1, "tcp localvars anchor"
    c = c.replace(anchor_lv,
                  anchor_lv.replace("          </localVars>", TCP_LOCALVARS_INS + "          </localVars>"), 1)

    anchor_init = "\tIF Tcp_uiPort = 0 THEN Tcp_uiPort := 9100; END_IF;\n\txInit := TRUE;"
    assert c.count(anchor_init) == 1, "tcp init anchor"
    c = c.replace(anchor_init,
                  "\tIF Tcp_uiPort = 0 THEN Tcp_uiPort := 9100; END_IF;\n" + TCP_INIT_INS + "\txInit := TRUE;", 1)

    anchor_parse = ("\tp := FIND(strLine, '\"HMI_rForceSim\":');\n"
                    "\tIF p &gt; 0 THEN Tcp_rForceSim := STRING_TO_REAL(MID(strLine, p + 15, 16)); END_IF;\nEND_IF;")
    assert c.count(anchor_parse) == 1, "tcp parse anchor"
    c = c.replace(anchor_parse,
                  "\tp := FIND(strLine, '\"HMI_rForceSim\":');\n"
                  "\tIF p &gt; 0 THEN Tcp_rForceSim := STRING_TO_REAL(MID(strLine, p + 15, 16)); END_IF;\n"
                  + TCP_PARSE_INS + "END_IF;", 1)

    anchor_arb = "\txSendTrig := TRUE;\nEND_IF;\n</xhtml>"
    assert c.count(anchor_arb) == 1, "tcp arb anchor"
    c = c.replace(anchor_arb, "\txSendTrig := TRUE;\nEND_IF;\n" + TCP_ARB_INS + "</xhtml>", 1)

    # --- GVL 追加 ---
    assert c.count("      </globalVars>\n") == 1
    c = c.replace("      </globalVars>\n", GVL_NEW + "      </globalVars>\n", 1)

    # --- ProjectStructure ---
    old_x = '              <Object Name="FB_XDiff" ObjectId="%s" />' % G_XLINE
    new_x = ('              <Object Name="FB_XLineTrack" ObjectId="%s" />\n'
             '              <Object Name="FB_Force" ObjectId="%s" />\n'
             '              <Object Name="FB_ForceFollow" ObjectId="%s" />' % (G_XLINE, G_FORCE, G_FF))
    assert c.count(old_x) == 1, "projstruct FB_XDiff"
    c = c.replace(old_x, new_x, 1)

    old_f = '\n            <Object Name="PRG_Force485" ObjectId="a1b2c3d4-e5f6-4789-a012-777777777777" />'
    assert c.count(old_f) == 1, "projstruct PRG_Force485"
    c = c.replace(old_f, "", 1)

    # --- 校验良构 ---
    minidom.parseString(c.encode("utf-8"))

    with open(SRC, "w", encoding="utf-8") as f:
        f.write(c)
    print("OK: refactor applied, XML well-formed. backup ->", BAK)


if __name__ == "__main__":
    main()
