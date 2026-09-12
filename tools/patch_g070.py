#!/usr/bin/env python3
"""patch_g070.py — 由 LMM_g_0.69.xml 幂等生成 LMM_g_0.70.xml。

0.70 改动（力峰值/原始计数回传 + HMI 脉冲复位）：
- GVL：新增 HMI_xForcePeakReset / Force_rPeak / Force_wRaw，
  以及影子 Tcp_xForcePeakReset / Tcp_rForcePeak / Tcp_wForceRaw。
- POU：从 plc/g/*.st 注入（本次涉及 PRG_TcpHmi / PRG_Logic）：
  命令 word5 bit11 -> HMI_xForcePeakReset；
  状态 word46/47 = Force_rPeak ×100（SCALED_DINT 高字在前）、word48 = Force_wRaw。
- 设备树 / EtherCAT / 任务 / GVL 对象 addData 一律不动。
按字节读写，保留 BOM 与 CRLF（GVL 区）。幂等：输入已含 0.70 标记则直接复制。

用法:
    python3 tools/patch_g070.py [输入.xml] [输出.xml]
    默认 输入 LMM_g_0.69.xml 输出 LMM_g_0.70.xml
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from inject_st import parse_st, inject_pou  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "plc" / "g"
DEFAULT_IN = ROOT / "LMM_g_0.69.xml"
DEFAULT_OUT = ROOT / "LMM_g_0.70.xml"
MARK = 'name="Force_rPeak"'
EOL = "\r\n"
IND = "        "


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def var_xml(name: str, typ: str, doc: str) -> str:
    out = [f'{IND}<variable name="{name}">',
           f'{IND}  <type>',
           f'{IND}    <{typ} />',
           f'{IND}  </type>',
           f'{IND}  <documentation>',
           f'{IND}    <xhtml xmlns="http://www.w3.org/1999/xhtml">{esc(doc)}</xhtml>',
           f'{IND}  </documentation>',
           f'{IND}</variable>']
    return EOL.join(out)


GVL_VARS = [
    ("HMI_xForcePeakReset", "BOOL",
     "【力峰值复位】TRUE=清零 Force_rPeak（脉冲，命令 word5 bit11）"),
    ("Force_rPeak", "REAL",
     "【只读·力峰值】N；绝对值峰值，HMI_xForcePeakReset 清零（状态 word46/47 ×100）"),
    ("Force_wRaw", "WORD",
     "【只读·力原始计数】0..65535，来自 Force_wInRaw（状态 word48）"),
    ("Tcp_xForcePeakReset", "BOOL",
     "【Web影子·力峰值复位】命令 word5 bit11"),
    ("Tcp_rForcePeak", "REAL",
     "【Web影子·力峰值】N；镜像 Force_rPeak"),
    ("Tcp_wForceRaw", "WORD",
     "【Web影子·力原始计数】镜像 Force_wRaw"),
]


def patch_gvl(text: str) -> str:
    """把 0.70 变量插到唯一 GVL 的对象级 addData 之前（保持 CRLF）。"""
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
        print(f"已含 0.70 标记（{MARK}），直接复制 -> {dst.name}")
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
