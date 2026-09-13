#!/usr/bin/env python3
"""patch_g072.py — 由 LMM_g_0.71.xml 幂等生成 LMM_g_0.72.xml。

0.72 改动（X 双驱驱动诊断回传，CoE 慢速 SDO）：
- GVL：新增 AxisFb_wSwM1/wErrM1/wTqMaxM1/wLimPM1/wLimNM1 与 M2 同名 5 个（WORD）。
- POU：FB_XDual 每台驱动轮询 7 个对象（0x6077 转矩 / 0x6078 电流 / 0x6041 状态字 /
  0x603F 错误码 / 0x6072 最大转矩 / 0x60E0 正向限 / 0x60E1 反向限），14 时隙；
  状态镜像 word54..63 = M1/M2 状态字/错误码/最大转矩/正反限幅（原始 16 位）。
- 设备树 / EtherCAT / 任务 / GVL 对象 addData 一律不动。幂等。

用法: python3 tools/patch_g072.py [输入.xml] [输出.xml]
     默认 输入 LMM_g_0.71.xml 输出 LMM_g_0.72.xml
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from inject_st import parse_st, inject_pou  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "plc" / "g"
DEFAULT_IN = ROOT / "LMM_g_0.71.xml"
DEFAULT_OUT = ROOT / "LMM_g_0.72.xml"
MARK = 'name="AxisFb_wSwM1"'
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
    ("AxisFb_wSwM1", "WORD", "【只读·M1状态字】CoE 0x6041；状态 word54"),
    ("AxisFb_wErrM1", "WORD", "【只读·M1错误码】CoE 0x603F；状态 word55"),
    ("AxisFb_wTqMaxM1", "WORD", "【只读·M1最大转矩】CoE 0x6072，0.1%；状态 word56"),
    ("AxisFb_wLimPM1", "WORD", "【只读·M1正向转矩限】CoE 0x60E0；状态 word57"),
    ("AxisFb_wLimNM1", "WORD", "【只读·M1反向转矩限】CoE 0x60E1；状态 word58"),
    ("AxisFb_wSwM2", "WORD", "【只读·M2状态字】CoE 0x6041；状态 word59"),
    ("AxisFb_wErrM2", "WORD", "【只读·M2错误码】CoE 0x603F；状态 word60"),
    ("AxisFb_wTqMaxM2", "WORD", "【只读·M2最大转矩】CoE 0x6072；状态 word61"),
    ("AxisFb_wLimPM2", "WORD", "【只读·M2正向转矩限】CoE 0x60E0；状态 word62"),
    ("AxisFb_wLimNM2", "WORD", "【只读·M2反向转矩限】CoE 0x60E1；状态 word63"),
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
        print(f"已含 0.72 标记（{MARK}），直接复制 -> {dst.name}")
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
