#!/usr/bin/env python3
"""patch_g063.py — 为 g 线 XML 加入 X 双电机实际速度的通用状态透传（0.63）。

在 0.62（在役，InoProShop 重存）基础上做**纯字符串行插入**，不改设备树 / 任务 /
EtherCAT / GVL addData / 其它 POU，保留原 CRLF/LF 与 BOM。

内容：
  1. GVL 增加 AxisFb_rVelActM1 / AxisFb_rVelActM2（REAL）
  2. PRG_Axis_Control 增加两行赋值（与 plc/g/PRG_Axis_Control.st 同步）
  3. PRG_TcpHmi 状态编码 word32..38：
       32/33 AxisFb_rVelActM1, 34/35 AxisFb_rVelActM2 (SCALED_DINT x1000)
       36     AxisFb_xMovingM1/M2, xPoweredM1/M2, xSyncWarn, xSyncFault (bit0..5)
       37/38 AxisFb_rSyncErr (SCALED_DINT x1000)

幂等：检测到 GVL 已有 AxisFb_rVelActM1 则跳过。
用法：
    python3 tools/patch_g063.py [输入.xml] [输出.xml]
默认 输入 LMM_g_0.62.xml 输出 LMM_g_0.63.xml
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GVL_ANCHOR = 'name="AxisFb_rVelCmdM2"'
AXIS_ANCHOR = 'Direct_rVelM2Act := fbX.rVelActM2Out;'
STATUS_ANCHOR = 'MB_StatusOut[63] := Tcp_wStatusSeq;'


def gvl_var(name, doc):
    return (
        '        <variable name="' + name + '">\r\n'
        '          <type>\r\n'
        '            <REAL />\r\n'
        '          </type>\r\n'
        '          <documentation>\r\n'
        '            <xhtml xmlns="http://www.w3.org/1999/xhtml">' + doc + '</xhtml>\r\n'
        '          </documentation>\r\n'
        '        </variable>'
    )


GVL_BLOCK = (
    gvl_var('AxisFb_rVelActM1', '【只读·M1实际速度】m/s；fbX.rVelActM1Out→状态 word32')
    + '\r\n'
    + gvl_var('AxisFb_rVelActM2', '【只读·M2实际速度】m/s；fbX.rVelActM2Out→状态 word34')
)

AXIS_BLOCK = (
    AXIS_ANCHOR
    + '\nAxisFb_rVelActM1 := fbX.rVelActM1Out;'
    + '\nAxisFb_rVelActM2 := fbX.rVelActM2Out;'
)

STATUS_BLOCK = '\n'.join([
    '(* 0.63 X 双电机实际速度通用透传 word32..38（word5..62 每周期已清零） *)',
    'diTmp := REAL_TO_DINT(AxisFb_rVelActM1 * 1000.0);',
    'dwTmp := DINT_TO_DWORD(diTmp);',
    'MB_StatusOut[32] := DWORD_TO_WORD(SHR(dwTmp, 16));',
    'MB_StatusOut[33] := DWORD_TO_WORD(dwTmp AND 16#FFFF);',
    'diTmp := REAL_TO_DINT(AxisFb_rVelActM2 * 1000.0);',
    'dwTmp := DINT_TO_DWORD(diTmp);',
    'MB_StatusOut[34] := DWORD_TO_WORD(SHR(dwTmp, 16));',
    'MB_StatusOut[35] := DWORD_TO_WORD(dwTmp AND 16#FFFF);',
    'MB_StatusOut[36] := 0;',
    'IF AxisFb_xMovingM1 THEN MB_StatusOut[36] := MB_StatusOut[36] OR 1; END_IF;',
    'IF AxisFb_xMovingM2 THEN MB_StatusOut[36] := MB_StatusOut[36] OR 2; END_IF;',
    'IF AxisFb_xPoweredM1 THEN MB_StatusOut[36] := MB_StatusOut[36] OR 4; END_IF;',
    'IF AxisFb_xPoweredM2 THEN MB_StatusOut[36] := MB_StatusOut[36] OR 8; END_IF;',
    'IF AxisFb_xSyncWarn THEN MB_StatusOut[36] := MB_StatusOut[36] OR 16; END_IF;',
    'IF AxisFb_xSyncFault THEN MB_StatusOut[36] := MB_StatusOut[36] OR 32; END_IF;',
    'diTmp := REAL_TO_DINT(AxisFb_rSyncErr * 1000.0);',
    'dwTmp := DINT_TO_DWORD(diTmp);',
    'MB_StatusOut[37] := DWORD_TO_WORD(SHR(dwTmp, 16));',
    'MB_StatusOut[38] := DWORD_TO_WORD(dwTmp AND 16#FFFF);',
    STATUS_ANCHOR,
])


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'LMM_g_0.62.xml'
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / 'LMM_g_0.63.xml'
    text = src.read_bytes().decode('utf-8')

    if 'name="AxisFb_rVelActM1"' in text:
        print('已是 0.63（GVL 含 AxisFb_rVelActM1），跳过')
        return

    for anchor, label in ((GVL_ANCHOR, 'GVL AxisFb_rVelCmdM2'), (AXIS_ANCHOR, 'Axis_Control'), (STATUS_ANCHOR, 'TcpHmi status')):
        if anchor not in text:
            raise SystemExit('找不到锚点：' + label)

    # 1) GVL：AxisFb_rVelCmdM2 变量块之后
    i = text.index(GVL_ANCHOR)
    j = text.index('</variable>', i) + len('</variable>')
    text = text[:j] + '\r\n' + GVL_BLOCK + text[j:]

    # 2) PRG_Axis_Control：Direct_* 赋值之后
    text = text.replace(AXIS_ANCHOR, AXIS_BLOCK, 1)

    # 3) PRG_TcpHmi：word63 序号之前
    text = text.replace(STATUS_ANCHOR, STATUS_BLOCK, 1)

    dst.write_bytes(text.encode('utf-8'))
    print('完成 -> ' + str(dst) + ' (' + str(dst.stat().st_size) + ' bytes)')


if __name__ == '__main__':
    main()
