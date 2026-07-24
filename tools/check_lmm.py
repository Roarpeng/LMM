#!/usr/bin/env python3
"""check_lmm.py — LMM.xml 静态校验（注入后 / 导入 InoProShop 前必跑）。

检查项:
  1. XML 可解析；POU 恰好为契约的 8 个；死 POU 无残留引用
  2. 每个 POU 有 interface + body/ST
  3. ST 结构配对（IF/CASE/FOR/WHILE 与 END_* 计数）、END_* 后分号
  4. ST 不得引用已删除的 GVL 变量；GVL 无未使用变量（AT 地址映射除外）
  5. Modbus 编解码与 config/modbus-map.json 字段一致
  6. 任务挂载：ETHERCAT={EtherCAT_Task, PRG_Axis_Control}；MainTask={PLC_PRG}
退出码: 0=全部通过, 1=有错误
"""
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NS = "{http://www.plcopen.org/xml/tc6_0200}"

EXPECTED_POUS = {
    "PLC_PRG", "PRG_TcpHmi", "PRG_Logic", "PRG_Axis_Control",
    "FB_Servo", "FB_Force", "FB_ForceFollow", "FB_XLineTrack",
}
DEAD_POUS = ["FB_TCPServer", "PRG_Force485", "FB_XDiff"]
DEAD_GVL = ["JogVel", "HomeReq", "CaliForReq", "ClearBruch", "yLength",
            "eDevState", "xEnablePermit", "xIlk_BlockYWhenZ",
            "I_xLimRPos", "I_xLimRNeg", "I_xHomeY", "I_xHomeZ", "I_xHomeR",
            "Tcp_uiPort", "AxisCmd_rZVelCmd", "AxisCmd_xUseZVelCmd"]

errors = []
warnings = []


def err(msg):
    errors.append(msg)


def warn(msg):
    warnings.append(msg)


def strip_comments(text):
    return re.sub(r"\(\*.*?\*\)", "", text, flags=re.S)


def main():
    raw = (ROOT / "LMM.xml").read_text(encoding="utf-8")
    tree = ET.parse(ROOT / "LMM.xml")
    root = tree.getroot()

    # ---- 1. POU 集合 ----
    pous = {p.get("name"): p for p in root.iter(NS + "pou")}
    if set(pous) != EXPECTED_POUS:
        err(f"POU 集合不符: {sorted(pous)}")
    for d in DEAD_POUS:
        if d in raw:
            err(f"死 POU 残留引用: {d}")

    # ---- 2/3. 每个 POU 的结构与 ST 语法 ----
    all_st = {}
    for name, pou in pous.items():
        if pou.find(NS + "interface") is None:
            err(f"{name}: 缺 interface")
        st = pou.find(".//" + NS + "ST")
        if st is None:
            err(f"{name}: 缺 body/ST")
            continue
        body = "".join(st.itertext())
        all_st[name] = body
        code = strip_comments(body)
        for kw, end in [("IF", "END_IF"), ("CASE", "END_CASE"),
                        ("FOR", "END_FOR"), ("WHILE", "END_WHILE")]:
            opens = len(re.findall(rf"\b{kw}\b", code))
            closes = len(re.findall(rf"\b{end}\b", code))
            if kw == "IF":
                opens -= len(re.findall(r"\bEND_IF\b", code))  # END_IF 含 IF 字串
                opens = len(re.findall(r"(?<![A-Z_])IF\b", code))
            if opens != closes:
                err(f"{name}: {kw}={opens} 与 {end}={closes} 不配对")
        for m in re.finditer(r"\b(END_IF|END_CASE|END_FOR|END_WHILE)\b(?!\s*;)", code):
            err(f"{name}: {m.group(1)} 后缺分号 (位置 {m.start()})")
        if "Implicit_Enum" in body or "Implicit_Enum" in ET.tostring(pou, encoding="unicode"):
            err(f"{name}: 仍含 Implicit_Enum")

    # ---- 4. GVL 引用闭环 ----
    gvl = None
    for g in root.iter(NS + "globalVars"):
        gvl = g
    gvars = {v.get("name"): v for v in gvl.findall(NS + "variable")}
    code_all = strip_comments("\n".join(all_st.values()))
    for d in DEAD_GVL:
        if re.search(rf"\b{re.escape(d)}\b", code_all):
            err(f"ST 仍引用已删变量: {d}")
        if d in gvars:
            err(f"GVL 仍声明已删变量: {d}")
    # POU 局部变量名（排除误报）
    local_names = set()
    for name, pou in pous.items():
        iface = pou.find(NS + "interface")
        if iface is not None:
            for v in iface.iter(NS + "variable"):
                local_names.add(v.get("name"))
    for gn, gv in gvars.items():
        if gv.get("address"):
            continue  # AT 地址变量由设备映射消费
        if gn in local_names:
            continue
        if not re.search(rf"\b{re.escape(gn)}\b", code_all):
            warn(f"GVL 变量未被任何 ST 引用: {gn}")

    # ---- 5. Modbus 契约一致性 ----
    mmap = json.load(open(ROOT / "config" / "modbus-map.json"))
    tcp = all_st.get("PRG_TcpHmi", "")
    for sec, arr in [("command", "MB_CmdIn"), ("status", "MB_StatusOut")]:
        for f in mmap[sec]["fields"]:
            nm = f["name"]
            if nm.startswith("_"):
                continue
            if not re.search(rf"\b{re.escape(nm)}\b", strip_comments(tcp)):
                err(f"PRG_TcpHmi 未编解码 {sec} 字段: {nm}")
        used = {int(x) for x in re.findall(arr + r"\[(\d+)\]", strip_comments(tcp))}
        need = {f["offset"] for f in mmap[sec]["fields"]}
        if sec == "status":
            # 状态区 FOR 循环清零 5..62 属正常；只核对头部和字段偏移存在
            need |= {0, 1, 2, 3, 4, 63}
        else:
            need |= {0, 1, 2, 3, 63}
        missing = need - used
        if missing:
            err(f"{arr} 偏移未使用: {sorted(missing)}")

    # ---- 6. 任务挂载 ----
    def task_pous(task_name):
        for t in root.iter(NS + "task"):
            if t.get("name") == task_name:
                return {p.get("name") for p in t.iter(NS + "pouInstance")}
        return None
    ec = task_pous("ETHERCAT")
    mt = task_pous("MainTask")
    if ec != {"ETHERCAT.EtherCAT_Task", "PRG_Axis_Control"}:
        err(f"ETHERCAT 任务挂载异常: {sorted(ec or [])}")
    if mt != {"PLC_PRG"}:
        err(f"MainTask 任务挂载异常: {sorted(mt or [])}")

    # ---- 报告 ----
    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")
    print(f"\n{len(errors)} error(s), {len(warnings)} warning(s)")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
