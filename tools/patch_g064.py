#!/usr/bin/env python3
"""patch_g064.py — 修偶尔误报 1005：力通讯状态单一写者。

背景：Force_xTimeout / Force_xCommOk 有两个写者：
  - PRG_Force485（MainTask）：按“读回文”状态机判定，真实反映通讯；
  - PRG_Axis_Control（ETHERCAT 4ms）：用 FB_Force 的“原始值 2s 不变”看门狗覆盖，
    力稳定（未压料/读数不跳）时误置 Force_xTimeout=TRUE → 报警 1005。

本补丁删除 PRG_Axis_Control 里对该状态的两行赋值，使 PRG_Force485 成为唯一写者；
FB_Force 仍负责换算/去皮（rForceAct / Force_iRaw 不变）。

按字节读写，保留 CRLF/LF 与 BOM；幂等。
用法: python3 tools/patch_g064.py [输入.xml] [输出.xml]
默认 输入 LMM_g_0.63.xml 输出 LMM_g_0.64.xml
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARK = '收发回文状态机唯一判定'
OLD = ('Force_iRaw := fbForce.iRaw;\n'
       'Force_xCommOk := fbForce.xCommOk;\n'
       'Force_xTimeout := fbForce.xTimeout;\n'
       'IF NOT HMI_xForceSimEnable THEN')
NEW = ('Force_iRaw := fbForce.iRaw;\n'
       '(* 力通讯状态由 PRG_Force485 的收发回文状态机唯一判定；\n'
       '   不再用 FB_Force 的“原始值 2s 不变”看门狗覆盖，避免力稳定时误报 1005。 *)\n'
       'IF NOT HMI_xForceSimEnable THEN')


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'LMM_g_0.63.xml'
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / 'LMM_g_0.64.xml'
    text = src.read_bytes().decode('utf-8')

    if MARK in text:
        print('已打过补丁，跳过')
        return
    if OLD not in text:
        raise SystemExit('找不到 PRG_Axis_Control 力状态赋值锚点')

    text = text.replace(OLD, NEW, 1)
    dst.write_bytes(text.encode('utf-8'))
    print('完成 -> ' + str(dst) + ' (' + str(dst.stat().st_size) + ' bytes)')


if __name__ == '__main__':
    main()
