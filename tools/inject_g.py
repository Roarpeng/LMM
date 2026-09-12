#!/usr/bin/env python3
"""inject_g.py — 把 plc/g/*.st 注入 g 线工程 XML。

g 线（虚轴 + MC_GearIn 方案，LMM_g_*.xml）为当前在役 PLC 代码，
与 LMM.xml 的 LineTrack 线（tools/inject_st.py）并行维护。
本工具只替换 plc/g/ 下同名 POU 的 interface/body；
设备树 / EtherCAT / 任务 / GVL / addData 一律不动。

用法:
    python3 tools/inject_g.py                          # LMM_g_0.1.xml -> LMM_g_0.2.xml
    python3 tools/inject_g.py 输入.xml 输出.xml
    python3 tools/inject_g.py --check                  # 只解析校验 plc/g/*.st
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from inject_st import parse_st, inject_pou  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "plc" / "g"


def main():
    if "--check" in sys.argv:
        for st in sorted(SRC_DIR.glob("*.st")):
            kind, name, scopes, body = parse_st(st)
            nvars = sum(len(v) for v in scopes.values())
            print(f"{name}: {kind}, {nvars} vars, body {len(body)} chars")
        print("--check OK")
        return

    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "LMM_g_0.1.xml"
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "LMM_g_0.2.xml"
    # 按字节读写：保留原 BOM 与 CRLF 行尾（read_text 的通用换行会把 \r\n 归一成 \n）
    xml = src.read_bytes().decode("utf-8")

    for st in sorted(SRC_DIR.glob("*.st")):
        kind, name, scopes, body = parse_st(st)
        nvars = sum(len(v) for v in scopes.values())
        xml = inject_pou(xml, name, kind, scopes, body)
        print(f"注入 {name}: {kind}, {nvars} vars, body {len(body)} chars")

    dst.write_bytes(xml.encode("utf-8"))
    print(f"完成 -> {dst} ({dst.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
