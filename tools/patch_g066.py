#!/usr/bin/env python3
"""patch_g066.py — 修正 0.65 的 1007 回归。

0.65 曾把 FB_XDual 就绪改为 xPoweredM1/M2 AND NOT xFault；但 xRegOn 在静态
(eMode=0 且非停止) 时为 FALSE，xPowered 随之为 FALSE → 静态一直报 1007。
正确判据为 xEnable AND NOT xFault：不含 xStop、也不要求 xPowered。
按字节读写，保留 CRLF/LF 与 BOM；幂等。
用法: python3 tools/patch_g066.py [输入.xml] [输出.xml]
默认 输入 LMM_g_0.65.xml 输出 LMM_g_0.66.xml
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARK = 'xReadyM1 := xEnable AND NOT xFaultM1;'
OLD = ('xReadyM1 := xPoweredM1 AND NOT xFaultM1;\n'
       'xReadyM2 := xPoweredM2 AND NOT xFaultM2;')
NEW = ('xReadyM1 := xEnable AND NOT xFaultM1;\n'
       'xReadyM2 := xEnable AND NOT xFaultM2;')


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'LMM_g_0.65.xml'
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / 'LMM_g_0.66.xml'
    text = src.read_bytes().decode('utf-8')
    if MARK in text:
        print('已打过补丁，跳过')
        return
    if OLD not in text:
        raise SystemExit('找不到 FB_XDual 的 xReadyM1/M2 (xPowered) 锚点')
    text = text.replace(OLD, NEW, 1)
    dst.write_bytes(text.encode('utf-8'))
    print('完成 -> ' + str(dst) + ' (' + str(dst.stat().st_size) + ' bytes)')


if __name__ == '__main__':
    main()
