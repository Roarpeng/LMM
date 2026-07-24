#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Refactor LMM.xml HMI transport: custom TCP/JSON -> Modbus TCP process image.

Preserves existing MODBUS_TCP / modbusTcp device-tree GUIDs.
Expands sample channels to 64 WORD snapshots:
  - Channel 02 (input / FC03): Holding 1000..1063 -> MB_CmdIn AT %IW103
  - Channel 01 (output / FC16): Holding 1100..1163 -> MB_StatusOut AT %QW44
Rewrites PRG_TcpHmi, removes FB_TCPServer, keeps PLC_PRG call order.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "LMM.xml"
BAK = ROOT / "LMM.xml.bak.modbus_hmi"
MAP = json.loads((ROOT / "config" / "modbus-map.json").read_text(encoding="utf-8"))

G_TCP = "a1b2c3d4-e5f6-4789-a012-555555555555"
G_FB_TCP = "7e0c956a-cfc2-4be8-b176-5148d3ef493a"
MAGIC = MAP["protocol"]["magic"]
VER = (MAP["protocol"]["versionMajor"] << 8) | MAP["protocol"]["versionMinor"]


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def strip_bom(s: str) -> str:
    return s[1:] if s.startswith("\ufeff") else s


def rm_pou(xml: str, name: str) -> str:
    return re.sub(
        rf'\s*<pou name="{re.escape(name)}" pouType="[^"]+">.*?</pou>',
        "",
        xml,
        count=1,
        flags=re.S,
    )


def rm_path(xml: str, name: str, guid: str) -> str:
    xml = re.sub(
        rf'\s*<pathStructure isFolder="False" name="{re.escape(name)}"[^>]*objectGuid="{guid}"\s*/>',
        "",
        xml,
    )
    xml = re.sub(
        rf'\s*<data name="http://www\.3s-software\.com/plcopenxml/objectid"[^>]*>\s*'
        rf'<ObjectId>{guid}</ObjectId>\s*</data>',
        "",
        xml,
        flags=re.S,
    )
    xml = re.sub(
        rf'\s*<Object Name="{re.escape(name)}" ObjectId="{guid}"\s*/>',
        "",
        xml,
    )
    return xml


def array_values(param_id: str, channel_name: str, kind: str, base: int, count: int = 64) -> str:
    # param_id 1001 -> _x0031_001 ; 2000 -> _x0032_000
    prefix = f"_x00{param_id[0]}_{param_id[1:]}"
    lines = []
    for i in range(count):
        addr = base + i
        desc = f"{kind} {addr}"
        lines.append(
            f'                      <Value name="{prefix}_{i}_0_0" '
            f'visiblename="{channel_name}[{i}]" desc="{desc}" />'
        )
    return "\n".join(lines)


def expand_modbus_channels(xml: str) -> str:
    # Replace Channel 02 input parameter (1001)
    in_block = (
        '                    <Parameter ParameterId="1001" type="std: ARRAY[0..63] OF WORD">\n'
        '                      <Attributes channel="input" />\n'
        + array_values("1001", "Channel 02", "READ", 1000)
        + "\n"
        "                      <Name>Channel 02</Name>\n"
        "                      <Description>读保持寄存器 命令快照 1000..1063</Description>\n"
        "                    </Parameter>"
    )
    xml = re.sub(
        r'\s*<Parameter ParameterId="1001"[\s\S]*?</Parameter>',
        "\n" + in_block,
        xml,
        count=1,
    )

    # Replace Channel 01 output parameter (2000)
    out_block = (
        '                    <Parameter ParameterId="2000" type="std: ARRAY[0..63] OF WORD">\n'
        '                      <Attributes channel="output" />\n'
        + array_values("2000", "Channel 01", "WRITE", 1100)
        + "\n"
        "                      <Name>Channel 01</Name>\n"
        "                      <Description>写多个寄存器 状态快照 1100..1163</Description>\n"
        "                    </Parameter>"
    )
    xml = re.sub(
        r'\s*<Parameter ParameterId="2000"[\s\S]*?</Parameter>',
        "\n" + out_block,
        xml,
        count=1,
    )

    # Fix channel set offsets/lengths inside modbusTcp only (after MODBUS_TCP config)
    # Channel 01 write: WriteRegOffSet 1100 / WriteRegLeg 64
    xml = re.sub(
        r'(<Element name="ChannelName" visiblename="ChannelName">\'Channel 01\'</Element>[\s\S]*?'
        r'<Element name="WriteRegOffSet" visiblename="WriteRegOffSet">)\d+(</Element>)',
        r"\g<1>1100\2",
        xml,
        count=1,
    )
    # Broader deterministic replacements near WriteRegOffSet=4096 and ReadRegOffSet=4352
    xml = xml.replace(
        '<Element name="WriteRegOffSet" visiblename="WriteRegOffSet">4096</Element>',
        '<Element name="WriteRegOffSet" visiblename="WriteRegOffSet">1100</Element>',
    )
    xml = xml.replace(
        '<Element name="ReadRegOffSet" visiblename="ReadRegOffSet">4352</Element>',
        '<Element name="ReadRegOffSet" visiblename="ReadRegOffSet">1000</Element>',
    )

    # Set both channel lengths to 64 for TCP slave channels that currently are 1
    # Only within modbusTcp: rewrite the two CycleTimes=5 blocks' RegLeg values.
    def fix_legs(m: re.Match) -> str:
        block = m.group(0)
        block = re.sub(
            r'(<Element name="ReadRegLeg" visiblename="ReadRegLeg">)\d+(</Element>)',
            r"\g<1>64\2",
            block,
        )
        block = re.sub(
            r'(<Element name="WriteRegLeg" visiblename="WriteRegLeg">)\d+(</Element>)',
            r"\g<1>64\2",
            block,
        )
        return block

    xml = re.sub(
        r'<configuration name="modbusTcp">[\s\S]*?</configuration>',
        fix_legs,
        xml,
        count=1,
    )
    return xml


def gvl_insert(xml: str) -> str:
    if 'name="MB_CmdIn"' in xml:
        return xml
    block = """
        <variable name="MB_CmdIn" address="%IW103">
          <type>
            <array>
              <dimension lower="0" upper="63" />
              <baseType>
                <WORD />
              </baseType>
            </array>
          </type>
          <documentation>
            <xhtml xmlns="http://www.w3.org/1999/xhtml">Modbus TCP FC03 命令快照 Holding 1000..1063</xhtml>
          </documentation>
        </variable>
        <variable name="MB_StatusOut" address="%QW44">
          <type>
            <array>
              <dimension lower="0" upper="63" />
              <baseType>
                <WORD />
              </baseType>
            </array>
          </type>
          <documentation>
            <xhtml xmlns="http://www.w3.org/1999/xhtml">Modbus TCP FC16 状态快照 Holding 1100..1163</xhtml>
          </documentation>
        </variable>
        <variable name="Tcp_iCommStatus">
          <type>
            <INT />
          </type>
          <documentation>
            <xhtml xmlns="http://www.w3.org/1999/xhtml">0离线 1在线 2版本错误 3序号错误 4超时</xhtml>
          </documentation>
        </variable>
        <variable name="Tcp_wLastHb">
          <type>
            <WORD />
          </type>
        </variable>
        <variable name="Tcp_wLastSeq">
          <type>
            <WORD />
          </type>
        </variable>
        <variable name="Tcp_wStatusSeq">
          <type>
            <WORD />
          </type>
        </variable>
        <variable name="Tcp_rKpTrack">
          <type>
            <REAL />
          </type>
        </variable>
        <variable name="Tcp_rKpForce">
          <type>
            <REAL />
          </type>
        </variable>
"""
    # Insert before Tcp_xConnected if present, else before Force_wInRaw
    if 'name="Tcp_xConnected"' in xml:
        xml = xml.replace(
            '        <variable name="Tcp_xConnected">',
            block + '        <variable name="Tcp_xConnected">',
            1,
        )
    else:
        xml = xml.replace(
            '        <variable name="Force_wInRaw"',
            block + '        <variable name="Force_wInRaw"',
            1,
        )
    return xml


def hmi_name_to_tcp(name: str) -> str:
    if name.startswith("HMI_"):
        return "Tcp_" + name[4:]
    return name


def gen_decode_st() -> str:
    lines = []
    lines.append(f"wMagic := MB_CmdIn[0];")
    lines.append(f"wVersion := MB_CmdIn[1];")
    lines.append(f"wSeqHead := MB_CmdIn[2];")
    lines.append(f"wHeartbeat := MB_CmdIn[3];")
    lines.append(f"wSeqTail := MB_CmdIn[63];")
    lines.append(f"xValid := (wMagic = {MAGIC}) AND (wVersion = {VER}) AND (wSeqHead = wSeqTail);")
    lines.append("IF xValid THEN")
    lines.append("\tTcp_iCommStatus := 1;")
    lines.append("\tIF wHeartbeat <> Tcp_wLastHb THEN")
    lines.append("\t\ttonHb(IN := FALSE);")
    lines.append("\t\ttonHb(IN := TRUE, PT := T#1S);")
    lines.append("\t\tTcp_wLastHb := wHeartbeat;")
    lines.append("\tEND_IF;")
    lines.append("\tIF wSeqHead <> Tcp_wLastSeq THEN")
    lines.append("\t\tTcp_wLastSeq := wSeqHead;")
    # BOOL / UINT / SCALED
    for field in MAP["command"]["fields"]:
        dst = hmi_name_to_tcp(field["name"])
        if field["type"] == "BOOL":
            mask = 1 << field["bit"]
            lines.append(
                f"\t\t{dst} := (MB_CmdIn[{field['offset']}] AND {mask}) <> 0;"
            )
        elif field["type"] == "UINT":
            lines.append(f"\t\t{dst} := WORD_TO_INT(MB_CmdIn[{field['offset']}]);")
        elif field["type"] == "SCALED_DINT":
            off = field["offset"]
            scale = float(field["scale"])
            lines.append(
                f"\t\tdwTmp := SHL(WORD_TO_DWORD(MB_CmdIn[{off}]), 16) OR WORD_TO_DWORD(MB_CmdIn[{off + 1}]);"
            )
            lines.append(
                f"\t\t{dst} := DINT_TO_REAL(DWORD_TO_DINT(dwTmp)) / {scale};"
            )
    lines.append("\tEND_IF;")
    lines.append("ELSIF wMagic <> 0 AND wMagic <> " + str(MAGIC) + " THEN")
    lines.append("\tTcp_iCommStatus := 2;")
    lines.append("ELSIF wSeqHead <> wSeqTail THEN")
    lines.append("\tTcp_iCommStatus := 3;")
    lines.append("END_IF;")
    return "\n".join(lines)


def gen_encode_st() -> str:
    lines = []
    lines.append("Tcp_wStatusSeq := Tcp_wStatusSeq + 1;")
    lines.append(f"MB_StatusOut[0] := {MAGIC};")
    lines.append(f"MB_StatusOut[1] := {VER};")
    lines.append("MB_StatusOut[2] := Tcp_wStatusSeq;")
    lines.append("MB_StatusOut[3] := Tcp_wLastSeq;")
    lines.append("MB_StatusOut[4] := Tcp_wLastHb;")
    # clear words 5..62 then set
    lines.append("FOR i := 5 TO 62 DO MB_StatusOut[i] := 0; END_FOR;")
    for field in MAP["status"]["fields"]:
        src = field["name"]
        if field["type"] == "BOOL":
            lines.append(f"IF {src} THEN MB_StatusOut[{field['offset']}] := MB_StatusOut[{field['offset']}] OR {1 << field['bit']}; END_IF;")
        elif field["type"] == "UINT":
            # Tcp_iCommStatus is INT in GVL
            if src == "Tcp_iCommStatus":
                lines.append(f"MB_StatusOut[{field['offset']}] := INT_TO_WORD(Tcp_iCommStatus);")
            else:
                lines.append(f"MB_StatusOut[{field['offset']}] := INT_TO_WORD({src});")
        elif field["type"] == "SCALED_DINT":
            off = field["offset"]
            scale = float(field["scale"])
            lines.append(f"diTmp := REAL_TO_DINT({src} * {scale});")
            lines.append("dwTmp := DINT_TO_DWORD(diTmp);")
            lines.append(f"MB_StatusOut[{off}] := DWORD_TO_WORD(SHR(dwTmp, 16));")
            lines.append(f"MB_StatusOut[{off + 1}] := DWORD_TO_WORD(dwTmp AND 16#FFFF);")
    lines.append("MB_StatusOut[63] := Tcp_wStatusSeq;")
    return "\n".join(lines)


def make_prg_tcphmi() -> str:
    decode = gen_decode_st()
    encode = gen_encode_st()
    st = f"""(* PRG_TcpHmi — Modbus TCP 过程映像编解码 + 控制源仲裁 *)
(* PLC=Master 读 Holding1000 / 写 Holding1100；Gateway=Server *)
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
	Tcp_iCommStatus := 0;
	Tcp_wLastHb := 0; Tcp_wLastSeq := 16#FFFF; Tcp_wStatusSeq := 0;
	tonHb(IN := FALSE);
	xInit := TRUE;
END_IF;

(* ===== 命令快照解码 ===== *)
{decode}
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
{encode}

(* ===== 控制源仲裁（保留原语义） ===== *)
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
END_IF;

HMI_xEStop := EStop AND Tcp_xEStop AND HMI_xEStopReq;
HMI_xStart := StartBtn OR HMI_xStartReq OR (Tcp_xOnline AND Tcp_xStart);
HMI_xEnable := HMI_xStart;
HMI_xStop := StopBtn OR HMI_xStopReq OR (Tcp_xOnline AND Tcp_xStop);
HMI_xStopHold3s := ResetBtn OR HMI_xResetReq OR (Tcp_xOnline AND Tcp_xStopHold3s);
HMI_xAutoStart := (Tcp_xOnline AND Tcp_xAutoStart) OR ((eCtrlSrc = 0) AND HMI_xAutoStartReq);
HMI_xAutoAbort := HMI_xAutoAbortReq OR (Tcp_xOnline AND Tcp_xAutoAbort);
"""
    iface = """          <localVars>
            <variable name="xInit"><type><BOOL /></type></variable>
            <variable name="eCtrlSrc"><type><INT /></type></variable>
            <variable name="xPanelOp"><type><BOOL /></type></variable>
            <variable name="xTcpOp"><type><BOOL /></type></variable>
            <variable name="xValid"><type><BOOL /></type></variable>
            <variable name="wMagic"><type><WORD /></type></variable>
            <variable name="wVersion"><type><WORD /></type></variable>
            <variable name="wSeqHead"><type><WORD /></type></variable>
            <variable name="wSeqTail"><type><WORD /></type></variable>
            <variable name="wHeartbeat"><type><WORD /></type></variable>
            <variable name="dwTmp"><type><DWORD /></type></variable>
            <variable name="diTmp"><type><DINT /></type></variable>
            <variable name="i"><type><INT /></type></variable>
            <variable name="tonHb"><type><derived name="TON" /></type></variable>
          </localVars>
"""
    add = (
        '        <addData>\n'
        '          <data name="http://www.3s-software.com/plcopenxml/pathstructure" handleUnknown="discard">\n'
        '            <pathStructure isFolder="False" name="Device" namespace="1ee21fdd-5562-44a0-a3ce-665d74916d50" factoryName="Inovance.InoPro.InoDeviceObject.DeviceObjectFactory" factoryGuid="{84d12aa5-3225-473b-9df6-18af40889bdf}" objectGuid="d7de5ac3-3f30-45ac-8468-ec250b4e523b">\n'
        '              <pathStructure isFolder="False" name="Plc Logic" namespace="00000000-0000-0000-0000-000000000000" factoryName="_3S.CoDeSys.PlcLogicObject.PlcLogicObjectFactory" factoryGuid="{8ceeba4e-ac7a-4fbd-9415-bfb2d98668ab}" objectGuid="8a291c6e-c5c5-4a07-8c04-1100df0e1491">\n'
        '                <pathStructure isFolder="False" name="Application" namespace="e5b60c93-5445-4e40-ada9-cd9c005549b4" factoryName="_3S.CoDeSys.ApplicationObject.ApplicationObjectFactory" factoryGuid="{ECADC42E-716E-4ff3-A93C-0CD143F9743F}" objectGuid="69822df8-b9c0-4a01-9450-b2cdc030688c">\n'
        f'                  <pathStructure isFolder="False" name="PRG_TcpHmi" namespace="e5b60c93-5445-4e40-ada9-cd9c005549b4" factoryName="Inovance.InoPro.InoPOUObject.POUObjectFactory" factoryGuid="{{39C4ED2B-903C-464c-9041-7DF4ECEE9609}}" objectGuid="{G_TCP}" />\n'
        '                </pathStructure>\n'
        '              </pathStructure>\n'
        '            </pathStructure>\n'
        '          </data>\n'
        '          <data name="http://www.3s-software.com/plcopenxml/objectid" handleUnknown="discard">\n'
        f'            <ObjectId>{G_TCP}</ObjectId>\n'
        '          </data>\n'
        '        </addData>\n'
    )
    return (
        '      <pou name="PRG_TcpHmi" pouType="program">\n'
        '        <interface>\n'
        + iface
        + '        </interface>\n'
        '        <body>\n'
        '          <ST>\n'
        '            <xhtml xmlns="http://www.w3.org/1999/xhtml">'
        + esc(st)
        + '</xhtml>\n'
        '          </ST>\n'
        '        </body>\n'
        + add
        + '      </pou>\n'
    )


def replace_prg_tcphmi(xml: str) -> str:
    new_pou = make_prg_tcphmi().rstrip() + "\n"
    xml2, n = re.subn(
        r'[ \t]*<pou name="PRG_TcpHmi" pouType="program">.*?</pou>\n?',
        new_pou,
        xml,
        count=1,
        flags=re.S,
    )
    if n != 1:
        raise RuntimeError(f"PRG_TcpHmi replace count={n}")
    return xml2


def main() -> int:
    raw = strip_bom(SRC.read_text(encoding="utf-8"))
    shutil.copy2(SRC, BAK)
    xml = raw
    xml = expand_modbus_channels(xml)
    xml = gvl_insert(xml)
    xml = replace_prg_tcphmi(xml)
    xml = rm_pou(xml, "FB_TCPServer")
    xml = rm_path(xml, "FB_TCPServer", G_FB_TCP)
    SRC.write_text(xml, encoding="utf-8")
    # well-formedness
    import xml.etree.ElementTree as ET
    ET.parse(SRC)
    print(f"OK: wrote {SRC} (backup {BAK})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
