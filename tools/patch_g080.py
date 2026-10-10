#!/usr/bin/env python3
"""patch_g080.py — 由 LMM_g_0.79.xml 幂等生成 LMM_g_0.80.xml。

0.80 改动（外部工步模式，接口见 docs/plc/STEP_MODE.md）：
- GVL：新增工步命令 HMI_xStepMode / HMI_iStepCmd / HMI_wStepId / HMI_wStepFlags / HMI_rStep*，
  工步回报 Step_*。
- POU：从 plc/g/*.st 注入（本次涉及 PRG_TcpHmi / PRG_Logic）：
  命令 word5 bit12 + word76..94 → HMI_*（不受 eCtrlSrc 门控）；状态 word75..87；
  eOpMode=2 外部工步状态机；力参数改为扫描末尾一次性写 AxisCmd_rForce*；
  航向误差非远程源时清零（修面板点动冻结旧航向）。
- 设备树 / EtherCAT / 任务 / GVL 对象 addData 一律不动。
按字节读写，保留 BOM 与 CRLF（GVL 区）。幂等：输入已含 0.80 标记则直接复制。

用法:
    python3 tools/patch_g080.py [输入.xml] [输出.xml]
    默认 输入 LMM_g_0.79.xml 输出 LMM_g_0.80.xml
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from inject_st import parse_st, inject_pou  # noqa: E402
from patch_g070 import var_xml  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "plc" / "g"
DEFAULT_IN = ROOT / "LMM_g_0.79.xml"
DEFAULT_OUT = ROOT / "LMM_g_0.80.xml"
MARK = 'name="HMI_iStepCmd"'
EOL = "\r\n"

GVL_VARS = [
    # ---- 命令（PRG_TcpHmi 每个新快照直写，不受 eCtrlSrc 门控）----
    ("HMI_xStepMode", "BOOL", "【外部工步·模式请求】命令 word5 bit12；自动模式优先；网关离线清零"),
    ("HMI_iStepCmd", "UINT", "【外部工步·命令】word76：0中止 1X走距 2Z压到力 3Y恒力行程 4YZR点位"),
    ("HMI_wStepId", "WORD", "【外部工步·命令号】word77：变化即新命令（锁存参数）"),
    ("HMI_wStepFlags", "WORD", "【外部工步·标志】word78：bit0/1/2 点位选 Y/Z/R；bit3 压力前去皮"),
    ("HMI_rStepDist", "REAL", "【外部工步·距离】m，word79/80 ×1000；工步1 X / 工步3 Y 相对距离"),
    ("HMI_rStepVel", "REAL", "【外部工步·速度】m/s，word81 ×1000；工步1 X / 工步3 Y / 工步4 Y·Z"),
    ("HMI_rStepVelR", "REAL", "【外部工步·R速度】°/s，word82 ×100；工步4"),
    ("HMI_rStepPosY", "REAL", "【外部工步·Y目标】m，word83/84 ×1000；工步4"),
    ("HMI_rStepPosZ", "REAL", "【外部工步·Z目标】m，word85/86 ×1000；工步4（向下为负）"),
    ("HMI_rStepPosR", "REAL", "【外部工步·R目标】°，word87/88 ×1000；工步4"),
    ("HMI_rStepForce", "REAL", "【外部工步·恒力目标】N，word89/90 ×100；工步2/3"),
    ("HMI_rStepKpForce", "REAL", "【外部工步·力控Kp】(m/s)/N，word91/92 ×1e6；工步2/3"),
    ("HMI_rStepVelZMax", "REAL", "【外部工步·力跟随Z限速】m/s，word93 ×1000；工步2/3"),
    ("HMI_rStepTimeout", "REAL", "【外部工步·超时】s，word94 ×10；0=PLC默认"),
    # ---- 回报（PRG_Logic 写，PRG_TcpHmi 编码到状态 word75..87）----
    ("Step_wIdEcho", "WORD", "【只读·工步·命令号回显】状态 word75"),
    ("Step_iCmdEcho", "UINT", "【只读·工步·命令回显】状态 word76"),
    ("Step_iState", "INT", "【只读·工步·状态】word77：0空闲 1执行 2完成 3失败"),
    ("Step_iErr", "INT", "【只读·工步·错误码】word78：1模式 2参数 3越限 4忙 10超时 11安全 12心跳 20未接触"),
    ("Step_iPhase", "INT", "【只读·工步·子阶段】word79（诊断）"),
    ("Step_xModeActive", "BOOL", "【只读·工步·模式在役】eOpMode=2；word80 bit0"),
    ("Step_xForceFollow", "BOOL", "【只读·工步·力跟随中】word80 bit1"),
    ("Step_xForceReached", "BOOL", "【只读·工步·力已达】word80 bit2"),
    ("Step_xForceLow", "BOOL", "【只读·工步·恒力行程力偏低(<0.8F)】word80 bit3"),
    ("Step_xRHold", "BOOL", "【只读·工步·R保持中】word80 bit4"),
    ("Step_rProgress", "REAL", "【只读·工步·已走距离】m，word81/82 ×1000"),
    ("Step_rKpForceEcho", "REAL", "【只读·工步·力控Kp回显】word83/84 ×1e6"),
    ("Step_rRHoldPos", "REAL", "【只读·工步·R保持目标】°，word85/86 ×1000"),
    ("Step_rElapsed", "REAL", "【只读·工步·已用时】s，word87 ×10"),
]


def patch_gvl(text: str) -> str:
    """把 0.80 变量插到唯一 GVL 的对象级 addData 之前（保持 CRLF）。"""
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
        print(f"已含 0.80 标记（{MARK}），直接复制 -> {dst.name}")
        dst.write_bytes(text.encode("utf-8"))
        return
    for name, _, _ in GVL_VARS:
        if f'<variable name="{name}">' in text:
            raise SystemExit(f"GVL 已存在 {name}，基线不是 0.79？")
    text = patch_gvl(text)
    for st in sorted(SRC_DIR.glob("*.st")):
        kind, name, scopes, body = parse_st(st)
        nvars = sum(len(v) for v in scopes.values())
        text = inject_pou(text, name, kind, scopes, body)
        print(f"注入 {name}: {kind}, {nvars} vars, body {len(body)} chars")
    if text.count(MARK) != 1:
        raise SystemExit(f"标记出现 {text.count(MARK)} 次，预期 1")
    raw = text.encode("utf-8")
    dst.write_bytes(raw)
    print(f"完成 -> {dst} ({len(raw)} bytes)")


if __name__ == "__main__":
    main()
