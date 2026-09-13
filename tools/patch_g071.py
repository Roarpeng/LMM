#!/usr/bin/env python3
"""patch_g071.py — 由 LMM_g_0.70.xml 幂等生成 LMM_g_0.71.xml。

0.71 改动（X 双驱 M1/M2 转矩/电流回传；CoE 0x6077/0x6078 慢速 SDO）：
- GVL：新增 AxisFb_rTorqueM1/M2、AxisFb_rCurrentM1/M2、AxisFb_xParamErr，
  以及 RETAIN 配置 Cfg_wSdoDevM1/M2（EtherCAT 从站物理地址，默认 1001/1002）。
- POU：从 plc/g/*.st 注入（FB_XDual / PRG_Axis_Control / PRG_TcpHmi）：
  FB_XDual 用 ETC_CO_SdoRead 慢速轮询 0x6077/0x6078；
  状态镜像 word49..52 = M1/M2 转矩/电流（SCALED_INT x1000；线上值=千分比额定，
  网关解码后 1.0 = 100% 额定），word53 bit0 = AxisFb_xParamErr。
- 设备树 / EtherCAT / 任务 / GVL 对象 addData 一律不动。
按字节读写，保留 BOM 与 CRLF（GVL 区）。幂等：输入已含 0.71 标记则直接复制。

用法:
    python3 tools/patch_g071.py [输入.xml] [输出.xml]
    默认 输入 LMM_g_0.70.xml 输出 LMM_g_0.71.xml
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from inject_st import parse_st, inject_pou  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "plc" / "g"
DEFAULT_IN = ROOT / "LMM_g_0.70.xml"
DEFAULT_OUT = ROOT / "LMM_g_0.71.xml"
MARK = 'name="AxisFb_rTorqueM1"'
EOL = "\r\n"
IND = "        "


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def var_xml(name: str, typ: str, doc: str, init=None, retain: bool = False) -> str:
    out = [f'{IND}<variable name="{name}">',
           f'{IND}  <type>',
           f'{IND}    <{typ} />',
           f'{IND}  </type>']
    if init is not None:
        out += [f'{IND}  <initialValue>',
                f'{IND}    <simpleValue value="{esc(init)}" />',
                f'{IND}  </initialValue>']
    if retain:
        out += [f'{IND}  <addData>',
                f'{IND}    <data name="http://www.3s-software.com/plcopenxml/attributes" handleUnknown="implementation">',
                f'{IND}      <Attributes>',
                f'{IND}        <Attribute Name="retain" Value="" />',
                f'{IND}      </Attributes>',
                f'{IND}    </data>',
                f'{IND}  </addData>']
    out += [f'{IND}  <documentation>',
            f'{IND}    <xhtml xmlns="http://www.w3.org/1999/xhtml">{esc(doc)}</xhtml>',
            f'{IND}  </documentation>',
            f'{IND}</variable>']
    return EOL.join(out)


GVL_VARS = [
    ("AxisFb_rTorqueM1", "REAL",
     "【只读·M1转矩实际】‰额定转矩（CoE 0x6077 慢速 SDO，1000=100%）；状态 word49", None, False),
    ("AxisFb_rTorqueM2", "REAL",
     "【只读·M2转矩实际】‰额定转矩（CoE 0x6077）；状态 word50", None, False),
    ("AxisFb_rCurrentM1", "REAL",
     "【只读·M1电流实际】‰额定电流（CoE 0x6078）；状态 word51", None, False),
    ("AxisFb_rCurrentM2", "REAL",
     "【只读·M2电流实际】‰额定电流（CoE 0x6078）；状态 word52", None, False),
    ("AxisFb_xParamErr", "BOOL",
     "【只读·CoE读取错误】M1/M2 转矩电流 SDO 读失败；状态 word53 bit0", None, False),
    ("Cfg_wSdoDevM1", "UINT",
     "【CoE SDO 站号·M1】MDX_EC 的 EtherCAT 物理地址（InoProShop 设备树 Address）", "1001", True),
    ("Cfg_wSdoDevM2", "UINT",
     "【CoE SDO 站号·M2】MDX_EC_1 的 EtherCAT 物理地址", "1002", True),
]


def patch_gvl(text: str) -> str:
    """把 0.71 变量插到唯一 GVL 的对象级 addData 之前（保持 CRLF）。"""
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
        print(f"已含 0.71 标记（{MARK}），直接复制 -> {dst.name}")
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
