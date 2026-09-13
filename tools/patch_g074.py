#!/usr/bin/env python3
"""patch_g074.py — 由 LMM_g_0.73.xml 幂等生成 LMM_g_0.74.xml。

0.74 改动（X 双驱强制 CSV 速度模式）：
- 背景：设备树 0x6060=9，但 SM3 DS402 接口运行时按 SMC_position 给了 8(CSP)。
- GVL：新增 Cfg_xForceCsvX(RETAIN, 默认 TRUE) + AxisFb_xModeCsvM1/ErrM1/M2/ErrM2。
- POU：FB_XDual 第 11 节在空闲且使能时调 SMC_SetControllerMode(..., SMC_velocity)
  把 M1/M2 切到 CSV；状态镜像 word74 bit0..3 = M1done/M1err/M2done/M2err。
- 设备树 / EtherCAT / 任务 / GVL 对象 addData 一律不动。幂等。

用法: python3 tools/patch_g074.py [输入.xml] [输出.xml]
     默认 输入 LMM_g_0.73.xml 输出 LMM_g_0.74.xml
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from inject_st import parse_st, inject_pou  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "plc" / "g"
DEFAULT_IN = ROOT / "LMM_g_0.73.xml"
DEFAULT_OUT = ROOT / "LMM_g_0.74.xml"
MARK = 'name="Cfg_xForceCsvX"'
EOL = "\r\n"
IND = "        "


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def var_xml(name, typ, doc, init=None, retain=False):
    out = [f'{IND}<variable name="{name}">', f'{IND}  <type>', f'{IND}    <{typ} />', f'{IND}  </type>']
    if init is not None:
        out += [f'{IND}  <initialValue>', f'{IND}    <simpleValue value="{esc(init)}" />', f'{IND}  </initialValue>']
    if retain:
        out += [f'{IND}  <addData>',
                f'{IND}    <data name="http://www.3s-software.com/plcopenxml/attributes" handleUnknown="implementation">',
                f'{IND}      <Attributes>', f'{IND}        <Attribute Name="retain" Value="" />',
                f'{IND}      </Attributes>', f'{IND}    </data>', f'{IND}  </addData>']
    out += [f'{IND}  <documentation>',
            f'{IND}    <xhtml xmlns="http://www.w3.org/1999/xhtml">{esc(doc)}</xhtml>',
            f'{IND}  </documentation>', f'{IND}</variable>']
    return EOL.join(out)


GVL_VARS = [
    ("Cfg_xForceCsvX", "BOOL", "【0.74 强制 X 双驱 CSV 速度模式】空闲时切 SMC_velocity(0x6060=9)", "TRUE", True),
    ("AxisFb_xModeCsvM1", "BOOL", "【只读·M1 已切 CSV】状态 word74 bit0", None, False),
    ("AxisFb_xModeCsvErrM1", "BOOL", "【只读·M1 切 CSV 失败】状态 word74 bit1", None, False),
    ("AxisFb_xModeCsvM2", "BOOL", "【只读·M2 已切 CSV】状态 word74 bit2", None, False),
    ("AxisFb_xModeCsvErrM2", "BOOL", "【只读·M2 切 CSV 失败】状态 word74 bit3", None, False),
]


def patch_gvl(text):
    gvl_start = text.index('<globalVars name="GVL">')
    close = text.index("</globalVars>", gvl_start)
    add_start = text.rindex("<addData>", gvl_start, close)
    block = EOL.join(var_xml(*v) for v in GVL_VARS) + EOL
    return text[:add_start] + block + text[add_start:]


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_IN
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUT
    text = src.read_bytes().decode("utf-8")
    if MARK in text:
        print(f"已含 0.74 标记（{MARK}），直接复制 -> {dst.name}")
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
