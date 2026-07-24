#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Upsert Chinese documentation on HMI / WebHMI facing GVL variables in LMM.xml."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "LMM.xml"
BAK = ROOT / "LMM.xml.bak.hmi_annotate"

# name -> (中文名/用途一句话). 触摸屏与 WebHMI 共用语义；Tcp_* 为 Web 影子。
DOCS: dict[str, str] = {
    # —— 安全 / 起停（写：触摸屏或 Web；急停更严 AND）——
    "HMI_xEStop": "【急停请求】TRUE=正常可运行；FALSE=急停按下。触摸屏/Web 均可写；最终 HMI_xEStop=物理急停 AND 触摸屏Req AND Web。非安全认证急停。",
    "HMI_xEStopReq": "【触摸屏急停请求】触摸屏专用；TRUE正常 FALSE按下。与物理急停、Web急停相与。",
    "HMI_xStop": "【停止】电平/短按停机；TRUE=请求停止。面板、触摸屏、Web 任一为真即可停。",
    "HMI_xStopReq": "【触摸屏停止请求】触摸屏写；仲裁后并入 HMI_xStop。",
    "HMI_xStopHold3s": "【复位】TRUE=故障/急停锁存复位脉冲（对应停止键长按3s）。清锁存、轴错误复位。",
    "HMI_xResetReq": "【触摸屏复位请求】触摸屏写；仲裁后并入 HMI_xStopHold3s。",
    "HMI_xStart": "【启动】上升沿有效；与 HMI_xEnable 等效。手动点动不强制先按启动。",
    "HMI_xStartReq": "【触摸屏启动请求】触摸屏写上升沿；仲裁后并入 HMI_xStart。",
    "HMI_xEnable": "【启动别名】与 HMI_xStart 等效，勿单独理解成伺服使能。",

    # —— 模式 ——
    "HMI_xAutoMode": "【模式】FALSE=手动；TRUE=自动。切换时清点动；自动运行中禁止手动JOG。",
    "HMI_eOpMode": "【只读·运行方式显示】0手动 1自动。由 Logic 写，HMI/Web 只读。",
    "HMI_eDevState": "【只读·设备状态码】0停止/待机 1运行 2错误。显示用，不做控制互锁。",
    "HMI_xDevStop": "【只读·停止灯】TRUE=未运行且非电机报警。",
    "HMI_xDevRun": "【只读·运行灯】TRUE=急停正常且未请求停止。",
    "HMI_xDevError": "【只读·故障灯】TRUE=存在电机 ErrorStop 等故障。",
    "HMI_xLampEStop": "【只读·急停指示】TRUE=急停锁存或急停按下。",
    "HMI_xLampEnableOk": "【只读·就绪/可运行灯】与运行条件相关。",
    "HMI_xLampFault": "【只读·故障指示】TRUE=设备故障态。",
    "HMI_iAlarmShow": "【只读·报警号】1001急停 1002轴故障 1005力超时 1006从站失败 1007未就绪等。",

    # —— 手动点动（电平：按住TRUE，松开FALSE）——
    "HMI_xJogXPos": "【手动 X+】电平；M1/M2 同速同向前进。互斥：不可与 X−、左右旋同时。",
    "HMI_xJogXNeg": "【手动 X−】电平；M1/M2 同速同向后退。",
    "HMI_xSpinLeft": "【手动左旋转】电平；M1/M2 差速原地转。与 X±、右旋互斥。",
    "HMI_xSpinRight": "【手动右旋转】电平；与 X±、左旋互斥。",
    "HMI_xJogYPos": "【手动 Y+】电平；受 Y 限位与 Z 互锁约束。",
    "HMI_xJogYNeg": "【手动 Y−】电平。",
    "HMI_xJogZPos": "【手动 Z+】电平；回零后软限位 [−0.7,0] m。",
    "HMI_xJogZNeg": "【手动 Z−】电平；回零后软限位 [−0.7,0] m。",
    "HMI_xJogRPos": "【手动 R+】电平；需 M5 就绪。",
    "HMI_xJogRNeg": "【手动 R−】电平；需 M5 就绪。",
    "HMI_rJogVelX": "【X直行速度】单位 m/s（或工程单位）；仅用于 X±，与旋转速度分开。",
    "HMI_rSpinVel": "【左右旋速度】单位同工程速度；仅用于原地旋转，与 JogVelX 分开。",
    "HMI_rJogVelY": "【Y点动速度】",
    "HMI_rJogVelZ": "【Z点动速度】；力跟随最大速度也常取此值后备。",
    "HMI_rJogVelR": "【R点动速度】",

    # —— 回零 ——
    "HMI_iHomeAxis": "【回零轴选择】0无 1=Y 2=Z 3=R。与 HMI_xHomeExec 配合。",
    "HMI_xHomeExec": "【回零执行】上升沿；对 HMI_iHomeAxis 选定轴回零。同时只回一轴。",
    "HMI_xHomeY": "【Y回零】上升沿独立触发；与 HomeExec 二选一即可。",
    "HMI_xHomeZ": "【Z回零】上升沿；完成后坐标系0，软限位生效。",
    "HMI_xHomeR": "【R回零】上升沿；绝对/编码器回零。",
    "HMI_xHomedY": "【只读·Y已回零】",
    "HMI_xHomedZ": "【只读·Z已回零】",
    "HMI_xHomedR": "【只读·R已回零】",
    "HMI_xHomeBusyY": "【只读·Y回零中】",
    "HMI_xHomeBusyZ": "【只读·Z回零中】",
    "HMI_xHomeBusyR": "【只读·R回零中】",

    # —— 自动 ——
    "HMI_xAutoStart": "【自动启动】上升沿；需自动模式且安全条件满足。",
    "HMI_xAutoStartReq": "【触摸屏自动启动】触摸屏写；仲裁后并入。",
    "HMI_xAutoAbort": "【自动中止】电平/请求；立即结束自动步序。",
    "HMI_xAutoAbortReq": "【触摸屏自动中止】触摸屏写。",
    "HMI_rAutoDistX": "【自动X走距】每道/每段 X 相对距离。",
    "HMI_rAutoVelX": "【自动X速度】",
    "HMI_rAutoVelY": "【自动Y速度】横移（跨距）用。",
    "HMI_rAutoVelZ": "【自动Z速度】下压/力跟随限速参考。",
    "HMI_rWheelBase": "【龙门跨距=Y行程】4~6 m；自动 Y 走距用此值，勿再另设 AutoDistY。",
    "HMI_iAutoPasses": "【自动总道数】≥1；多道循环次数。",
    "HMI_rForceSet": "【恒力设定】单位 N；自动压下与力跟随目标。",
    "HMI_rKpForce": "【力跟随Kp】越大响应越快，过大易抖。",
    "HMI_rKpTrack": "【直线纠偏Kp】航向误差×Kp→M1/M2差速修正。",
    "HMI_rHeadingErr": "【航向/偏角误差】视觉或外部给；自动走直线时纠偏输入。",
    "HMI_xForceGuide": "【力引导电平】TRUE=持续 Z 力跟随；FALSE=停止引导。手动/自动可用。",
    "HMI_xForceTare": "【力去皮】上升沿；自动压下步也可能内部触发。",
    "HMI_xForceUntare": "【取消去皮】上升沿。",
    "HMI_xForceSimEnable": "【力模拟使能】TRUE 时用 HMI_rForceSim 代替真实力（台架）。",
    "HMI_rForceSim": "【力模拟值】N；仅 ForceSimEnable=TRUE 时生效。",
    "HMI_iAutoStepShow": "【只读·自动步号】0 Idle… 详见 Logic 步序。",
    "HMI_xAutoBusy": "【只读·自动忙】TRUE=自动循环进行中。",
    "HMI_xAutoDone": "【只读·自动完成】本轮/全部道次完成脉冲或电平（以 Logic 为准）。",
    "HMI_rForceShow": "【只读·显示力】N；给触摸屏/Web 显示。",

    # —— 力传感只读 ——
    "rForceAct": "【实际力】N；Axis 任务/力转换写。HMI 优先显示 HMI_rForceShow。",
    "Force_xEnable": "【力通讯总使能】一般保持 TRUE。",
    "Force_xCommOk": "【只读·力通讯正常】",
    "Force_xTimeout": "【只读·力通讯超时】报警 1005。",
    "Force_xSlaveFail": "【只读·力从站使能失败】报警 1006。",
    "Force_xTareBusy": "【只读·去皮进行中】",
    "Force_xTareDone": "【只读·去皮完成】",
    "Force_xReadTrig": "【内部·力读触发】勿绑屏。",

    # —— 轴反馈（只读，建议绑监控）——
    "AxisFb_rPosM1": "【只读·M1位置】",
    "AxisFb_rPosM2": "【只读·M2位置】",
    "AxisFb_rPosY": "【只读·Y位置】建议主画面显示。",
    "AxisFb_rPosZ": "【只读·Z位置】",
    "AxisFb_rPosR": "【只读·R位置/角度】",
    "AxisFb_rVelCmdM1": "【只读·M1速度指令】含纠偏后。",
    "AxisFb_rVelCmdM2": "【只读·M2速度指令】含纠偏后。",
    "AxisFb_xReady": "【只读·全轴就绪】FALSE 时报警 1007 可能相关。",
    "AxisFb_xReadyM1": "【只读·M1就绪】",
    "AxisFb_xReadyM2": "【只读·M2就绪】",
    "AxisFb_xReadyY": "【只读·Y就绪】",
    "AxisFb_xReadyZ": "【只读·Z就绪】",
    "AxisFb_xReadyR": "【只读·R就绪】",
    "AxisFb_xHomedY": "【只读·Y已回零(轴任务)】可与 HMI_xHomedY 二选一显示。",
    "AxisFb_xHomedZ": "【只读·Z已回零(轴任务)】",
    "AxisFb_xHomedR": "【只读·R已回零(轴任务)】",
    "AxisFb_xFaultM1": "【只读·M1故障】",
    "AxisFb_xFaultM2": "【只读·M2故障】",
    "AxisFb_xFaultY": "【只读·Y故障】",
    "AxisFb_xFaultZ": "【只读·Z故障】",
    "AxisFb_xFaultR": "【只读·R故障】",
    "AxisFb_xMoveDoneX": "【只读·X相对走距完成】",
    "AxisFb_xMoveDoneY": "【只读·Y相对/绝对完成】",
    "AxisFb_xMovingM1": "【只读·M1运动中】",
    "AxisFb_xMovingM2": "【只读·M2运动中】",
    "AxisFb_xMovingY": "【只读·Y运动中】",
    "AxisFb_xMovingZ": "【只读·Z运动中】",
    "AxisFb_xMovingR": "【只读·R运动中】",
    "AxisFb_xStandstill1": "【只读·M1静止】",
    "AxisFb_xStandstill2": "【只读·M2静止】",
    "AxisFb_xStandstillY": "【只读·Y静止】",
    "AxisFb_xStandstillZ": "【只读·Z静止】",
    "AxisFb_xStandstillR": "【只读·R静止】",
    "AxisFb_xPoweredM1": "【只读·M1已上使能】",
    "AxisFb_xPoweredM2": "【只读·M2已上使能】",
    "AxisFb_xPoweredY": "【只读·Y已上使能】",
    "AxisFb_xPoweredZ": "【只读·Z已上使能】",
    "AxisFb_xPoweredR": "【只读·R已上使能】",

    # —— Web 链路 / 过程映像（WebHMI 读状态；勿当触摸屏命令绑）——
    "Tcp_xConnected": "【只读·远程链路已连接】Web/Modbus 在线。",
    "Tcp_xTimeout": "【只读·远程超时】1s 无心跳变化。",
    "Tcp_xOnline": "【只读·远程在线可用】Connected AND NOT Timeout。",
    "Tcp_iCommStatus": "【只读·通讯诊断】0离线 1在线 2版本错 3序号错 4超时。",
    "MB_CmdIn": "【过程映像·命令入】Holding1000..1063；PLC Master 读自 Gateway。勿绑操作控件。",
    "MB_StatusOut": "【过程映像·状态出】Holding1100..1163；PLC 写回 Gateway。勿绑操作控件。",
    "Tcp_uiPort": "【废弃·旧TCP端口】Modbus 后不再使用；保留兼容。",
    "Tcp_wLastHb": "【内部·上次心跳】",
    "Tcp_wLastSeq": "【内部·上次命令序号】",
    "Tcp_wStatusSeq": "【内部·状态序号】",

    # —— Web 影子（与 HMI_ 同后缀；由 PRG_TcpHmi 解码；触摸屏不要直接写）——
    "Tcp_xEStop": "【Web影子·急停】默认TRUE；掉线强制TRUE。",
    "Tcp_xStop": "【Web影子·停止】",
    "Tcp_xStopHold3s": "【Web影子·复位】",
    "Tcp_xStart": "【Web影子·启动】",
    "Tcp_xEnable": "【Web影子·启动别名】",
    "Tcp_xAutoMode": "【Web影子·模式】",
    "Tcp_xJogXPos": "【Web影子·X+】",
    "Tcp_xJogXNeg": "【Web影子·X−】",
    "Tcp_xSpinLeft": "【Web影子·左旋】",
    "Tcp_xSpinRight": "【Web影子·右旋】",
    "Tcp_xJogYPos": "【Web影子·Y+】",
    "Tcp_xJogYNeg": "【Web影子·Y−】",
    "Tcp_xJogZPos": "【Web影子·Z+】",
    "Tcp_xJogZNeg": "【Web影子·Z−】",
    "Tcp_xJogRPos": "【Web影子·R+】",
    "Tcp_xJogRNeg": "【Web影子·R−】",
    "Tcp_xHomeY": "【Web影子·Y回零】",
    "Tcp_xHomeZ": "【Web影子·Z回零】",
    "Tcp_xHomeR": "【Web影子·R回零】",
    "Tcp_iHomeAxis": "【Web影子·回零轴选择】",
    "Tcp_xHomeExec": "【Web影子·回零执行】",
    "Tcp_rJogVelX": "【Web影子·X直行速度】",
    "Tcp_rSpinVel": "【Web影子·旋转速度】",
    "Tcp_rJogVelY": "【Web影子·Y速度】",
    "Tcp_rJogVelZ": "【Web影子·Z速度】",
    "Tcp_rJogVelR": "【Web影子·R速度】",
    "Tcp_xAutoStart": "【Web影子·自动启动】",
    "Tcp_xAutoAbort": "【Web影子·自动中止】",
    "Tcp_rAutoDistX": "【Web影子·自动X距】",
    "Tcp_rAutoVelX": "【Web影子·自动X速】",
    "Tcp_rAutoVelY": "【Web影子·自动Y速】",
    "Tcp_rAutoVelZ": "【Web影子·自动Z速】",
    "Tcp_rWheelBase": "【Web影子·跨距】",
    "Tcp_rForceSet": "【Web影子·力设定】",
    "Tcp_xForceSimEnable": "【Web影子·力模拟使能】",
    "Tcp_rForceSim": "【Web影子·力模拟值】",
    "Tcp_xForceTare": "【Web影子·去皮】",
    "Tcp_xForceUntare": "【Web影子·取消去皮】",
    "Tcp_xForceGuide": "【Web影子·力引导】",
    "Tcp_iAutoPasses": "【Web影子·自动道数】",
    "Tcp_rHeadingErr": "【Web影子·航向误差】",
    "Tcp_rKpTrack": "【Web影子·纠偏Kp】",
    "Tcp_rKpForce": "【Web影子·力Kp】",

    # —— 内部灯派生（一般绑 HMI_xDev* 即可）——
    "Dev_xError": "【内部·故障派生】优先显示 HMI_xDevError。",
    "Dev_xRun": "【内部·运行派生】优先显示 HMI_xDevRun。",
    "Dev_xStop": "【内部·停止派生】优先显示 HMI_xDevStop。",
}


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def doc_xml(text: str) -> str:
    return (
        "          <documentation>\n"
        '            <xhtml xmlns="http://www.w3.org/1999/xhtml">'
        + esc(text)
        + "</xhtml>\n"
        "          </documentation>\n"
    )


def upsert_var_docs(xml: str) -> tuple[str, int]:
    count = 0

    def repl(m: re.Match) -> str:
        nonlocal count
        name = m.group(1)
        attrs = m.group(2) or ""
        body = m.group(3)
        if name not in DOCS:
            return m.group(0)
        count += 1
        # strip existing documentation
        body2 = re.sub(r"\s*<documentation>[\s\S]*?</documentation>\s*", "\n", body)
        body2 = body2.rstrip() + "\n" + doc_xml(DOCS[name])
        return f'<variable name="{name}"{attrs}>{body2}        </variable>'

    xml2 = re.sub(
        r'<variable name="([^"]+)"([^>]*)>([\s\S]*?)</variable>',
        repl,
        xml,
    )
    return xml2, count


def main() -> int:
    raw = SRC.read_text(encoding="utf-8")
    if raw.startswith("\ufeff"):
        raw = raw[1:]
    shutil.copy2(SRC, BAK)
    xml, n = upsert_var_docs(raw)
    missing = [k for k in DOCS if f'name="{k}"' not in xml]
    SRC.write_text(xml, encoding="utf-8")
    import xml.etree.ElementTree as ET

    ET.parse(SRC)
    print(f"annotated {n} variable blocks; missing_in_xml={missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
