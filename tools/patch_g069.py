#!/usr/bin/env python3
"""patch_g069.py — 由 LMM_g_0.68.xml 修正 Modbus TCP 从站通道长度 (Leg 64 -> 96)。

0.68 扩了变量表 ARRAY[0..63]->[0..95]，但漏改 MODBUSCHANNELSET 的
ReadRegLeg/WriteRegLeg (仍 64)，导致状态输出区只发布 64 字，
MB_StatusOut[95] 读回 0，网关校验 seq==tail 失败 -> 判离线。
本补丁把两条通道的 Leg 改成 96。幂等。
用法: python3 tools/patch_g069.py [输入.xml] [输出.xml]
默认 输入 LMM_g_0.68.xml 输出 LMM_g_0.69.xml
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def patch_leg(text: str, param_id: str, leg_name: str) -> str:
    start = text.find("10F4 0502")
    if start < 0:
        raise SystemExit("找不到 TCP 从站设备 (10F4 0502)")
    j = text.find("ParameterId=" + chr(34) + param_id + chr(34), start)
    if j < 0:
        raise SystemExit("找不到 ParameterId " + param_id)
    k = text.find("</Parameter>", j)
    block = text[j:k]
    pat = re.compile("(<Element name=" + chr(34) + leg_name + chr(34) + "[^>]*>)64(</Element>)")
    new_block, n = pat.subn(lambda m: m.group(1) + "96" + m.group(2), block, count=1)
    if n == 0:
        if ">96</Element>" in block:
            print("  " + param_id + " " + leg_name + " 已是 96")
            return text
        raise SystemExit("找不到 " + param_id + " 的 " + leg_name + "=64")
    print("  " + param_id + " " + leg_name + " 64 -> 96")
    return text[:j] + new_block + text[k:]


def main() -> None:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "LMM_g_0.68.xml"
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "LMM_g_0.69.xml"
    text = src.read_bytes().decode("utf-8")
    text = patch_leg(text, "393218", "ReadRegLeg")
    text = patch_leg(text, "393219", "WriteRegLeg")
    dst.write_bytes(text.encode("utf-8"))
    print("完成 -> " + str(dst) + " (" + str(dst.stat().st_size) + " bytes)")


if __name__ == "__main__":
    main()
