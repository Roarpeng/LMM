#!/usr/bin/env python3
"""patch_g073.py — 由 LMM_g_0.72.xml 幂等生成 LMM_g_0.73.xml。

0.73 改动（X 双驱 MDX 模式 + 转矩限值回传）：
- GVL：新增 AxisFb_wModeM1 / wTq03M1..wTq06M1 与 M2 同名 5 个（WORD）。
- POU：FB_XDual 每台驱动轮询 12 个对象（0x6077/0x6078/0x6041/0x603F/0x6072/0x60E0/
  0x60E1/0x6060/0x2403/0x2404/0x2405/0x2406），24 时隙；状态镜像 word64..73 =
  M1/M2 模式(0x6060) 与转矩限值(0x2403..0x2406)。
- 设备树 / EtherCAT / 任务 / GVL 对象 addData 一律不动。幂等。

用法: python3 tools/patch_g073.py [输入.xml] [输出.xml]
     默认 输入 LMM_g_0.72.xml 输出 LMM_g_0.73.xml
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from inject_st import parse_st, inject_pou  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "plc" / "g"
DEFAULT_IN = ROOT / "LMM_g_0.72.xml"
DEFAULT_OUT = ROOT / "LMM_g_0.73.xml"
MARK = 'name="AxisFb_wModeM1"'
EOL = "\r\n"
IND = "        "


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def var_xml(name: str, typ: str, doc: str) -> str:
    out = [f'{IND}<variable name="{name}">', f'{IND}  <type>', f'{IND}    <{typ} />',
           f'{IND}  </type>', f'{IND}  <documentation>',
           f'{IND}    <xhtml xmlns="http://www.w3.org/1999/xhtml">{esc(doc)}</xhtml>',
           f'{IND}  </documentation>', f'{IND}</variable>']
    return EOL.join(out)


GVL_VARS = [
    ("AxisFb_wModeM1", "WORD", "【只读·M1运行模式】CoE 0x6060（9=CSV/8=CSP）；状态 word64"),
    ("AxisFb_wTq03M1", "WORD", "【只读·M1转矩限值】CoE 0x2403；状态 word65"),
    ("AxisFb_wTq04M1", "WORD", "【只读·M1转矩限值】CoE 0x2404；状态 word66"),
    ("AxisFb_wTq05M1", "WORD", "【只读·M1转矩限值】CoE 0x2405；状态 word67"),
    ("AxisFb_wTq06M1", "WORD", "【只读·M1转矩限值】CoE 0x2406；状态 word68"),
    ("AxisFb_wModeM2", "WORD", "【只读·M2运行模式】CoE 0x6060；状态 word69"),
    ("AxisFb_wTq03M2", "WORD", "【只读·M2转矩限值】CoE 0x2403；状态 word70"),
    ("AxisFb_wTq04M2", "WORD", "【只读·M2转矩限值】CoE 0x2404；状态 word71"),
    ("AxisFb_wTq05M2", "WORD", "【只读·M2转矩限值】CoE 0x2405；状态 word72"),
    ("AxisFb_wTq06M2", "WORD", "【只读·M2转矩限值】CoE 0x2406；状态 word73"),
]


def patch_gvl(text: str) -> str:
    gvl_start = text.index('<globalVars name="GVL">')
    close = text.index("</globalVars>", gvl_start)
    add_start = text.rindex("<addData>", gvl_start, close)
    block = EOL.join(var_xml(*v) for v in GVL_VARS) + EOL
    return text[:add_start] + block + text[add_start:]


def main() -> None:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_IN
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUT
    text = src.read_bytes().decode("utf-8")
    if MARK in text:
        print(f"已含 0.73 标记（{MARK}），直接复制 -> {dst.name}")
        dst.write_bytes(text.encode("utf-8"))
        return
    text = patch_gvl(text)
    for st in sorted(SRC_DIR.glob("*.st")):
        kind, name, scopes, body = parse_st(st)
        nvars = sum(len(v) for v in scopes.values())
        text = inject_pou(text, name, kind, scopes, body)
        print(f"注入 {name}: {kind}, {nvars} vars, body {len(body)} chars")
    raw = text.encode("utf-8")
    if text.count(MARK) != 1:
        raise SystemExit(f"标记出现 {text.count(MARK)} 次，预期 1")
    dst.write_bytes(raw)
    print(f"完成 -> {dst} ({len(raw)} bytes)")


if __name__ == "__main__":
    main()
