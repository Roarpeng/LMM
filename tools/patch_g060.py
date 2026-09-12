#!/usr/bin/env python3
"""patch_g060.py — 为 g 线 XML 加入 X 视觉直控的 GVL 变量与 PRG_TcpHmi 编解码。

- 0.60 功能：X 轴 M1/M2 速度视觉直控（eMode=4）+ Web/视觉双源使能。
- CRLF 安全：按字节读写，行级插入，不改动行尾与 BOM。
- 幂等：检测到 HMI_xDirectEnable 已存在则跳过。
用法:
    python3 tools/patch_g060.py LMM_g_0.60.xml
"""
import sys
from pathlib import Path

EOL = "\r\n"


def gvl_block():
    def var(name, typ, doc):
        return [
            f'        <variable name="{name}">',
            "          <type>",
            f"            <{typ} />",
            "          </type>",
            "          <documentation>",
            f'            <xhtml xmlns="http://www.w3.org/1999/xhtml">{doc}</xhtml>',
            "          </documentation>",
            "        </variable>",
        ]

    lines = []
    lines += var("HMI_xDirectEnable", "BOOL", "【X直控·Web使能】命令镜像 word5 bit10；与 Vis_xEnable 取或，视觉优先")
    lines += var("HMI_rVelM1Set", "REAL", "【X直控·M1设定速度】m/s；命令镜像 word54 (INT×1000)")
    lines += var("HMI_rVelM2Set", "REAL", "【X直控·M2设定速度】m/s；命令镜像 word55 (INT×1000)")
    lines += var("Vis_xEnable", "BOOL", "【视觉直控使能】命令镜像 word56 bit0（视觉侧写）")
    lines += var("Vis_wSeq", "WORD", "【视觉心跳序号】命令镜像 word57；变化即在线，>200ms 不变离线")
    lines += var("Vis_rVelM1Set", "REAL", "【视觉直控·M1速度】命令镜像 word58 (INT×1000)")
    lines += var("Vis_rVelM2Set", "REAL", "【视觉直控·M2速度】命令镜像 word59 (INT×1000)")
    lines += var("Direct_xEnable", "BOOL", "【X直控·在役】PRG_Logic 仲裁后给 AxisCmd_xDirectVel")
    lines += var("Direct_xOnline", "BOOL", "【X直控·视觉在线】Vis_wSeq 200ms 内变化")
    lines += var("Direct_wSeqEcho", "WORD", "【X直控·视觉序号回显】状态镜像 word31")
    lines += var("Direct_xActive", "BOOL", "【X直控·FB在役】状态镜像 word28 bit0")
    lines += var("Direct_rVelM1Act", "REAL", "【X直控·M1实际速度】状态镜像 word29 (INT×1000)")
    lines += var("Direct_rVelM2Act", "REAL", "【X直控·M2实际速度】状态镜像 word30 (INT×1000)")
    lines += var("AxisCmd_xDirectVel", "BOOL", "【X直控·命令】TRUE=FB_XDual 走 eMode=4 外部直控")
    lines += var("AxisCmd_rVelM1Set", "REAL", "【X直控·M1目标速度】m/s")
    lines += var("AxisCmd_rVelM2Set", "REAL", "【X直控·M2目标速度】m/s")
    return lines


DECODE_LINES = [
    "(* 0.60 X 直控：Web 通道 word5 bit10 + word54/55；视觉块 word56..59 每周期直读 *)",
    "HMI_xDirectEnable := (MB_CmdIn[5] AND 1024) &lt;&gt; 0;",
    "HMI_rVelM1Set := INT_TO_REAL(WORD_TO_INT(MB_CmdIn[54])) / 1000.0;",
    "HMI_rVelM2Set := INT_TO_REAL(WORD_TO_INT(MB_CmdIn[55])) / 1000.0;",
    "Vis_xEnable := (MB_CmdIn[56] AND 1) &lt;&gt; 0;",
    "Vis_wSeq := MB_CmdIn[57];",
    "Vis_rVelM1Set := INT_TO_REAL(WORD_TO_INT(MB_CmdIn[58])) / 1000.0;",
    "Vis_rVelM2Set := INT_TO_REAL(WORD_TO_INT(MB_CmdIn[59])) / 1000.0;",
]

STATUS_LINES = [
    "(* 0.60 X 直控状态 word28..31（word5..62 每周期已清零） *)",
    "MB_StatusOut[28] := 0;",
    "IF Direct_xActive THEN MB_StatusOut[28] := MB_StatusOut[28] OR 1; END_IF;",
    "IF Direct_xOnline THEN MB_StatusOut[28] := MB_StatusOut[28] OR 2; END_IF;",
    "IF Direct_xEnable THEN MB_StatusOut[28] := MB_StatusOut[28] OR 4; END_IF;",
    "MB_StatusOut[29] := INT_TO_WORD(REAL_TO_INT(Direct_rVelM1Act * 1000.0));",
    "MB_StatusOut[30] := INT_TO_WORD(REAL_TO_INT(Direct_rVelM2Act * 1000.0));",
    "MB_StatusOut[31] := Direct_wSeqEcho;",
]


def find_line(lines, predicate):
    for i, ln in enumerate(lines):
        if predicate(ln):
            return i
    return -1


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("LMM_g_0.60.xml")
    text = path.read_bytes().decode("utf-8")
    if "HMI_xDirectEnable" in text:
        print("已打过补丁，跳过")
        return
    lines = text.split(EOL)

    # 1. GVL：在 Cfg_rSyncFault 变量之后、GVL 级 <addData> 之前插入
    i_doc = find_line(lines, lambda s: "【同步跳闸】已废" in s)
    if i_doc < 0:
        raise SystemExit("找不到 GVL 锚点（Cfg_rSyncFault 文档）")
    i_close = find_line(lines[i_doc:], lambda s: s.strip() == "</variable>")
    if i_close < 0:
        raise SystemExit("找不到 Cfg_rSyncFault 的 </variable>")
    i_close += i_doc
    lines[i_close + 1:i_close + 1] = gvl_block()

    # 2. PRG_TcpHmi 解码：在 Tcp_xForceGuide 行后插入（沿用其缩进）
    i_dec = find_line(lines, lambda s: "Tcp_xForceGuide := (MB_CmdIn[5] AND 512)" in s)
    if i_dec < 0:
        raise SystemExit("找不到 PRG_TcpHmi 解码锚点")
    ind = lines[i_dec][:len(lines[i_dec]) - len(lines[i_dec].lstrip())]
    dec = [ind + s for s in DECODE_LINES]
    lines[i_dec + 1:i_dec + 1] = dec

    # 3. PRG_TcpHmi 状态编码：在 MB_StatusOut[63] 之前插入（沿用其缩进）
    i_st = find_line(lines, lambda s: s.strip() == "MB_StatusOut[63] := Tcp_wStatusSeq;")
    if i_st < 0:
        raise SystemExit("找不到 PRG_TcpHmi 状态编码锚点")
    ind2 = lines[i_st][:len(lines[i_st]) - len(lines[i_st].lstrip())]
    st = [ind2 + s for s in STATUS_LINES]
    lines[i_st:i_st] = st

    path.write_bytes((EOL.join(lines)).encode("utf-8"))
    print(f"已打补丁 -> {path}")


if __name__ == "__main__":
    main()
