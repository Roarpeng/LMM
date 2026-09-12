#!/usr/bin/env python3
"""patch_g068.py — 由 LMM_g_0.67.xml 幂等生成 LMM_g_0.68.xml。

0.68 改动（命令/状态镜像 64W -> 96W + 全轴视觉/操作员直控）：
- GVL：MB_CmdIn/MB_StatusOut ARRAY[0..63] -> [0..95]；
  新增直控命令镜像/影子、状态、AxisCmd 通道与 Cfg 配置（word39..45、60..75）。
- POU：从 plc/g/*.st 注入 FB_Servo / FB_XDual / PRG_Axis_Control / PRG_Logic /
  PRG_TcpHmi（PRG_TcpHmi 为 0.68 新增 g 线源）。
- 设备树 / EtherCAT / 任务 / GVL 对象 addData 一律不动。
按字节读写，保留 BOM 与 CRLF（GVL 区）。幂等：输入已含 0.68 标记则直接复制。

用法:
    python3 tools/patch_g068.py [输入.xml] [输出.xml]
    默认 输入 LMM_g_0.67.xml 输出 LMM_g_0.68.xml
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from inject_st import parse_st, inject_pou  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "plc" / "g"
DEFAULT_IN = ROOT / "LMM_g_0.67.xml"
DEFAULT_OUT = ROOT / "LMM_g_0.68.xml"
MARK = 'name="HMI_wDirectSeq"'
EOL = "\r\n"
IND = "        "


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def var_xml(name: str, typ: str, doc: str, init: str | None = None, retain: bool = False) -> str:
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


# (name, type, doc, init, retain) —— 0.68 相对 0.67 新增的 GVL 变量
GVL_VARS = [
    # R7 命令镜像
    ("HMI_iDirectModeX", "UINT", "【直控·X模式】命令 word60；0idle 1vel（X 仅速度）", None, False),
    ("HMI_rDirectPosX", "REAL", "【直控·X整机目标位置】命令 word61/62 ×1000；整机速度环可选", None, False),
    ("HMI_iDirectModeY", "UINT", "【直控·Y模式】命令 word63；0idle 1vel 2posAbs 3posRel", None, False),
    ("HMI_rDirectVelY", "REAL", "【直控·Y速度】命令 word64 ×1000；m/s", None, False),
    ("HMI_rDirectPosY", "REAL", "【直控·Y目标位置】命令 word65/66 ×1000；m", None, False),
    ("HMI_iDirectModeZ", "UINT", "【直控·Z模式】命令 word67；0idle 1vel 2posAbs 3posRel", None, False),
    ("HMI_rDirectVelZ", "REAL", "【直控·Z速度】命令 word68 ×1000；m/s", None, False),
    ("HMI_rDirectPosZ", "REAL", "【直控·Z目标位置】命令 word69/70 ×1000；m", None, False),
    ("HMI_iDirectModeR", "UINT", "【直控·R模式】命令 word71；0idle 1vel 2posAbs 3posRel", None, False),
    ("HMI_rDirectVelR", "REAL", "【直控·R速度】命令 word72 ×1000；工程单位/s", None, False),
    ("HMI_rDirectPosR", "REAL", "【直控·R目标位置】命令 word73/74 ×1000；工程单位", None, False),
    ("HMI_wDirectSeq", "WORD", "【直控·心跳序号】命令 word75；300ms 不变退出直控", None, False),
    # R7 状态 / 反馈
    ("Direct2_xActiveX", "BOOL", "【只读·直控·X在役】Logic 写；状态 word42 bit0", None, False),
    ("Direct2_xActiveY", "BOOL", "【只读·直控·Y在役】Logic 写；状态 word42 bit1", None, False),
    ("Direct2_xActiveZ", "BOOL", "【只读·直控·Z在役】Logic 写；状态 word42 bit2", None, False),
    ("Direct2_xActiveR", "BOOL", "【只读·直控·R在役】Logic 写；状态 word42 bit3", None, False),
    ("Direct2_xOnline", "BOOL", "【只读·直控·心跳在线】Logic 写；状态 word42 bit4", None, False),
    ("Direct2_xSafe", "BOOL", "【只读·直控·安全允许】Logic 写；状态 word42 bit5", None, False),
    ("Direct2_wSeqEcho", "WORD", "【只读·直控·心跳回显】Logic 写；状态 word43", None, False),
    ("HMI_rForceSetEcho", "REAL", "【只读·力设定回显】Logic 写；状态 word44/45 ×100", None, False),
    ("AxisFb_rVelActY", "REAL", "【只读·Y实际速度】Axis 任务写；状态 word39 ×1000；仅 Axis 任务写", None, False),
    ("AxisFb_rVelActZ", "REAL", "【只读·Z实际速度】Axis 任务写；状态 word40 ×1000；仅 Axis 任务写", None, False),
    ("AxisFb_rVelActR", "REAL", "【只读·R实际速度】Axis 任务写；状态 word41 ×1000；仅 Axis 任务写", None, False),
    # R7 AxisCmd 直控通道（仅 Logic 写）
    ("AxisCmd_xDirectVelY", "BOOL", "【直控·Y速度命令】仅 Logic 写", None, False),
    ("AxisCmd_rDirectVelY", "REAL", "【直控·Y进给速度】m/s；模式 1 速度，2/3 定位限速", None, False),
    ("AxisCmd_xDirectAbsY", "BOOL", "【直控·Y绝对命令】仅 Logic 写", None, False),
    ("AxisCmd_rDirectAbsY", "REAL", "【直控·Y绝对目标】已钳位软限位", None, False),
    ("AxisCmd_xDirectRelY", "BOOL", "【直控·Y相对命令】仅 Logic 写", None, False),
    ("AxisCmd_rDirectRelY", "REAL", "【直控·Y相对距离】FB_Servo 内钳位", None, False),
    ("AxisCmd_xDirectVelZ", "BOOL", "【直控·Z速度命令】仅 Logic 写", None, False),
    ("AxisCmd_rDirectVelZ", "REAL", "【直控·Z进给速度】m/s", None, False),
    ("AxisCmd_xDirectAbsZ", "BOOL", "【直控·Z绝对命令】仅 Logic 写", None, False),
    ("AxisCmd_rDirectAbsZ", "REAL", "【直控·Z绝对目标】已钳位软限位", None, False),
    ("AxisCmd_xDirectRelZ", "BOOL", "【直控·Z相对命令】仅 Logic 写", None, False),
    ("AxisCmd_rDirectRelZ", "REAL", "【直控·Z相对距离】FB_Servo 内钳位", None, False),
    ("AxisCmd_xDirectVelR", "BOOL", "【直控·R速度命令】仅 Logic 写", None, False),
    ("AxisCmd_rDirectVelR", "REAL", "【直控·R进给速度】工程单位/s", None, False),
    ("AxisCmd_xDirectAbsR", "BOOL", "【直控·R绝对命令】仅 Logic 写", None, False),
    ("AxisCmd_rDirectAbsR", "REAL", "【直控·R绝对目标】已钳位软限位", None, False),
    ("AxisCmd_xDirectRelR", "BOOL", "【直控·R相对命令】仅 Logic 写", None, False),
    ("AxisCmd_rDirectRelR", "REAL", "【直控·R相对距离】FB_Servo 内钳位", None, False),
    # R7b 命令影子（仅 PRG_TcpHmi 解码写）
    ("Tcp_iDirectModeX", "UINT", "【影子·X模式】word60", None, False),
    ("Tcp_rDirectPosX", "REAL", "【影子·X整机目标】word61/62 ×1000", None, False),
    ("Tcp_iDirectModeY", "UINT", "【影子·Y模式】word63", None, False),
    ("Tcp_rDirectVelY", "REAL", "【影子·Y速度】word64 ×1000", None, False),
    ("Tcp_rDirectPosY", "REAL", "【影子·Y目标】word65/66 ×1000", None, False),
    ("Tcp_iDirectModeZ", "UINT", "【影子·Z模式】word67", None, False),
    ("Tcp_rDirectVelZ", "REAL", "【影子·Z速度】word68 ×1000", None, False),
    ("Tcp_rDirectPosZ", "REAL", "【影子·Z目标】word69/70 ×1000", None, False),
    ("Tcp_iDirectModeR", "UINT", "【影子·R模式】word71", None, False),
    ("Tcp_rDirectVelR", "REAL", "【影子·R速度】word72 ×1000", None, False),
    ("Tcp_rDirectPosR", "REAL", "【影子·R目标】word73/74 ×1000", None, False),
    ("Tcp_wDirectSeq", "WORD", "【影子·直控心跳】word75", None, False),
    # R8 直控配置（RETAIN）
    ("Cfg_rDirectVelMaxX", "REAL", "【直控速度上限·X】m/s", "0.5", True),
    ("Cfg_rDirectVelMaxY", "REAL", "【直控速度上限·Y】m/s", "0.5", True),
    ("Cfg_rDirectVelMaxZ", "REAL", "【直控速度上限·Z】m/s", "0.2", True),
    ("Cfg_rDirectVelMaxR", "REAL", "【直控速度上限·R】工程单位/s", "30.0", True),
    ("Cfg_tDirectTimeout", "TIME", "【直控看门狗】HMI_wDirectSeq 不变即退出", "TIME#300ms", True),
]


def patch_gvl(text: str) -> str:
    text, n1 = re.subn(
        r'(<variable name="MB_CmdIn"[^>]*>.*?)upper="63"(.*?Holding 1000\.\.)1063',
        r'\g<1>upper="95"\g<2>1095', text, count=1, flags=re.S)
    text, n2 = re.subn(
        r'(<variable name="MB_StatusOut"[^>]*>.*?)upper="63"(.*?Holding 1100\.\.)1163',
        r'\g<1>upper="95"\g<2>1195', text, count=1, flags=re.S)
    if n1 != 1 or n2 != 1:
        raise SystemExit("找不到 MB_CmdIn/MB_StatusOut ARRAY[0..63] 锚点")
    close = text.index("</globalVars>")
    add_start = text.rindex("<addData>", 0, close)
    block = EOL.join(var_xml(*v) for v in GVL_VARS) + EOL
    return text[:add_start] + block + text[add_start:]


VIND = " " * 22  # Modbus 从站 <Value> 行缩进；设备区为 LF


def expand_modbus_param(text: str, param_id: str, prefix: str, channel: str, base: int) -> str:
    """把 Modbus 从站 Holding 参数 ARRAY[0..63] 扩到 [0..95] 并补齐 64..95 索引。"""
    pat = re.compile(
        r'(<Parameter ParameterId="' + param_id + r'" type="std: )ARRAY\[0\.\.63\]( OF WORD">)(.*?)(\s*<Name>)',
        re.S)
    kind = "READ" if channel == "01" else "WRITE"

    def fn(m):
        extra = "\n".join(
            f'{VIND}<Value name="{prefix}{i}_0_0" '
            f'visiblename="Channel {channel}[{i}]" '
            f'desc="{kind} 16#{base + i:X}(={base + i})" />'
            for i in range(64, 96))
        return (m.group(1) + "ARRAY[0..95]" + m.group(2) + m.group(3)
                + "\n" + extra + m.group(4))

    text, n = pat.subn(fn, text, count=1)
    if n != 1:
        raise SystemExit(f"找不到 Modbus 从站参数 {param_id} ARRAY[0..63] 锚点")
    return text


def patch_modbus_device(text: str) -> str:
    """MODBUS_TCP_1 命令(读 Holding1000)/状态(写 Holding1100) 各扩到 96 字。"""
    text = expand_modbus_param(text, "1000", "_x0031_000_", "01", 0x1000)
    text = expand_modbus_param(text, "2001", "_x0032_001_", "02", 0x1100)
    return text


def main() -> None:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_IN
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUT
    text = src.read_bytes().decode("utf-8")
    if MARK in text:
        print(f"已含 0.68 标记（{MARK}），直接复制 -> {dst.name}")
        dst.write_bytes(text.encode("utf-8"))
        return
    text = patch_gvl(text)
    text = patch_modbus_device(text)
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
