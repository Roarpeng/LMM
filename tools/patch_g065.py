#!/usr/bin/env python3
"""patch_g065.py — 修停止/静默时误报 1007。

FB_XDual 的 M1/M2 就绪判据含 NOT xStop：
    xReadyM1 := xEnable AND NOT xStop AND NOT xFaultM1;
xStop 来自 AxisCmd_xStopAll（HMI_xStop 等）。设备停止/静默时 xStop=TRUE，
xReadyM1/M2 立即变 FALSE，而 AxisCmd_xPower 仍为真且无故障 →
PRG_Logic 的 tonReady 2s 后置 1007。FB_Servo 的判据本应是 xPowered AND NOT xFault。

本补丁改为 xReadyM1/M2 := xPoweredM1/M2 AND NOT xFaultM1/M2。
按字节读写，保留 CRLF/LF 与 BOM；幂等。
用法: python3 tools/patch_g065.py [输入.xml] [输出.xml]
默认 输入 LMM_g_0.64.xml 输出 LMM_g_0.65.xml
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARK = 'xReadyM1 := xPoweredM1'
OLD = ('xReadyM1 := xEnable AND NOT xStop AND NOT xFaultM1;\n'
       'xReadyM2 := xEnable AND NOT xStop AND NOT xFaultM2;')
NEW = ('xReadyM1 := xPoweredM1 AND NOT xFaultM1;\n'
       'xReadyM2 := xPoweredM2 AND NOT xFaultM2;')


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'LMM_g_0.64.xml'
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / 'LMM_g_0.65.xml'
    text = src.read_bytes().decode('utf-8')
    if MARK in text:
        print('已打过补丁，跳过')
        return
    if OLD not in text:
        raise SystemExit('找不到 FB_XDual 的 xReadyM1/M2 锚点')
    text = text.replace(OLD, NEW, 1)
    dst.write_bytes(text.encode('utf-8'))
    print('完成 -> ' + str(dst) + ' (' + str(dst.stat().st_size) + ' bytes)')


if __name__ == '__main__':
    main()
