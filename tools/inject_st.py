#!/usr/bin/env python3
"""inject_st.py — 把 plc/src/*.st 与 plc/GVL.st 注入 LMM.xml（PLCopen TC6）。

用法:
    python3 tools/inject_st.py            # 注入并备份 LMM.xml -> LMM.xml.bak.inject
    python3 tools/inject_st.py --check    # 只解析校验 .st，不写 XML

.st 格式:
    第一行: PROGRAM <名> 或 FUNCTION_BLOCK <名>
    随后:   VAR_INPUT/VAR_OUTPUT/VAR_IN_OUT/VAR ... END_VAR 声明块（可没有）
    其余:   本体 ST
    变量行: name [AT %地址] : 类型 [:= 初值] ;  (* 注释 -> documentation *)
GVL.st: 单个 VAR_GLOBAL ... END_VAR。

注入 = 替换对应 POU 的 <interface>/<body>、替换 GVL、删除死 POU。
设备树 / EtherCAT / 任务 / addData 一律不动。
"""
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
XML_PATH = ROOT / "LMM.xml"
BAK_PATH = ROOT / "LMM.xml.bak.inject"
SRC_DIR = ROOT / "plc" / "src"
GVL_ST = ROOT / "plc" / "GVL.st"

DEAD_POUS = ["FB_TCPServer", "PRG_Force485", "FB_XDiff"]

ELEMENTARY = {
    "BOOL", "SINT", "INT", "DINT", "LINT",
    "USINT", "UINT", "UDINT", "ULINT",
    "BYTE", "WORD", "DWORD", "LWORD",
    "REAL", "LREAL", "TIME", "DATE", "STRING",
}

VAR_BLOCK_RE = re.compile(r"^\s*(VAR_INPUT|VAR_OUTPUT|VAR_IN_OUT|VAR_GLOBAL|VAR)\b")
END_VAR_RE = re.compile(r"^\s*END_VAR\b")
HEADER_RE = re.compile(r"^\s*(PROGRAM|FUNCTION_BLOCK)\s+(\w+)")
COMMENT_RE = re.compile(r"\(\*.*?\*\)", re.S)
DECL_RE = re.compile(
    r"^\s*(\w+)\s*(?:AT\s+(%[IQMX][\w.]+)\s*)?:\s*"
    r"(ARRAY\s*\[\s*(-?\d+)\s*\.\.\s*(-?\d+)\s*\]\s*OF\s+(\w+)|\w+)"
    r"\s*(?::=\s*(.+?))?\s*;\s*$"
)


def strip_comments(text):
    return COMMENT_RE.sub("", text)


def parse_var_line(line):
    """解析一行变量声明 -> dict 或 None（注释/空行）。"""
    m = COMMENT_RE.search(line)
    doc = ""
    if m:
        doc = m.group(0)[2:-2].strip()
        line = COMMENT_RE.sub("", line)
    if not line.strip():
        return None
    d = DECL_RE.match(line)
    if not d:
        raise ValueError(f"无法解析变量行: {line.strip()!r}")
    name, addr, _type, lo, hi, base, init = d.groups()
    if base:
        vtype = ("ARRAY", int(lo), int(hi), base)
    else:
        vtype = ("SIMPLE", _type)
    return {"name": name, "addr": addr, "type": vtype,
            "init": init.strip() if init else None, "doc": doc}


def parse_st(path):
    """返回 (pou_kind, pou_name, scopes, body)。scopes: {scope: [var]}。"""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    kind = name = None
    scopes = {}
    body_lines = []
    scope = None
    in_comment = False
    for i, line in enumerate(lines):
        if i == 0 or (kind is None and line.strip()):
            h = HEADER_RE.match(line)
            if h and kind is None:
                kind, name = h.group(1), h.group(2)
                continue
        if kind is None:
            if VAR_BLOCK_RE.match(line) and "VAR_GLOBAL" in line:
                kind, name = "GLOBAL", "GVL"
            else:
                continue
        # 跨行注释跟踪（仅声明区内需要；本体内注释原样保留）
        if in_comment:
            if "*)" in line:
                in_comment = False
            if scope is not None:
                continue
        elif scope is not None:
            stripped = strip_comments(line)
            if "(*" in stripped:
                in_comment = True
                continue
            if not stripped.strip() and "(*" in line and "*)" not in line:
                in_comment = True
                continue
        vm = VAR_BLOCK_RE.match(line)
        if vm and scope is None:
            scope = vm.group(1)
            scopes.setdefault(scope, [])
            continue
        if END_VAR_RE.match(line) and scope is not None:
            scope = None
            continue
        if scope is not None:
            v = parse_var_line(line)
            if v:
                scopes[scope].append(v)
        else:
            body_lines.append(line)
    if kind is None:
        raise ValueError(f"{path}: 缺少 PROGRAM/FUNCTION_BLOCK 头")
    body = "\n".join(body_lines).strip("\n")
    return kind, name, scopes, body


def esc(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def type_xml(vtype):
    kind = vtype[0]
    if kind == "SIMPLE":
        t = vtype[1]
        if t in ELEMENTARY:
            return f"<{t} />"
        return f'<derived name="{t}" />'
    _, lo, hi, base = vtype
    bt = f"<{base} />" if base in ELEMENTARY else f'<derived name="{base}" />'
    return (f'<array><dimension lower="{lo}" upper="{hi}" />'
            f"<baseType>{bt}</baseType></array>")


def var_xml(v, indent):
    pad = " " * indent
    addr = f' address="{v["addr"]}"' if v["addr"] else ""
    out = [f'{pad}<variable name="{v["name"]}"{addr}>',
           f"{pad}  <type>{type_xml(v['type'])}</type>"]
    if v["init"] is not None:
        out.append(f'{pad}  <initialValue><simpleValue value="{esc(v["init"])}" /></initialValue>')
    if v["doc"]:
        out.append(f'{pad}  <documentation><xhtml xmlns="http://www.w3.org/1999/xhtml">'
                   f"{esc(v['doc'])}</xhtml></documentation>")
    out.append(f"{pad}</variable>")
    return "\n".join(out)


POU_SCOPE_TAG = [("inputVars", "VAR_INPUT"), ("outputVars", "VAR_OUTPUT"),
                 ("localVars", "VAR"), ("inOutVars", "VAR_IN_OUT")]


def interface_xml(scopes):
    blocks = []
    for tag, scope in POU_SCOPE_TAG:
        vars_ = scopes.get(scope)
        if not vars_:
            continue
        inner = "\n".join(var_xml(v, 12) for v in vars_)
        blocks.append(f"          <{tag}>\n{inner}\n          </{tag}>")
    if not blocks:
        return "<interface />"
    return "<interface>\n" + "\n".join(blocks) + "\n        </interface>"


def body_xml(body):
    return ("<body>\n          <ST>\n"
            '            <xhtml xmlns="http://www.w3.org/1999/xhtml">'
            + esc(body) +
            "</xhtml>\n          </ST>\n        </body>")


def replace_block(xml, start_re, end_str, repl_fn):
    """替换 <tag ...>...</tag> 的内部，repl_fn(old_inner)->new_inner。"""
    m = start_re.search(xml)
    if not m:
        raise ValueError(f"未找到块: {start_re.pattern}")
    end = xml.index(end_str, m.end())
    inner = xml[m.end():end]
    return xml[:m.end()] + repl_fn(inner) + xml[end:]


def inject_pou(xml, name, kind, scopes, body):
    pou_re = re.compile(r'<pou name="' + re.escape(name) + r'" pouType="[^"]+">')
    m = pou_re.search(xml)
    if not m:
        raise ValueError(f"LMM.xml 中未找到 POU {name}")
    end = xml.index("</pou>", m.end())
    block = xml[m.start():end]

    iface = interface_xml(scopes)
    if "<interface />" in block:
        block = block.replace("<interface />", iface, 1)
    else:
        i0 = block.index("<interface>") + len("<interface>")
        i1 = block.index("</interface>")
        block = block[:i0] + "\n" + iface.split("\n", 1)[1].rsplit("\n", 1)[0] + "\n        " + block[i1:]

    b0 = block.index("<body>")
    b1 = block.index("</body>") + len("</body>")
    block = block[:b0] + body_xml(body) + block[b1:]
    return xml[:m.start()] + block + xml[end:]


def inject_gvl(xml, vars_):
    gvl_re = re.compile(r'<globalVars name="GVL">')
    m = gvl_re.search(xml)
    if not m:
        raise ValueError("未找到 GVL globalVars")
    end = xml.index("</globalVars>", m.end())
    inner = xml[m.end():end]
    # 保留尾部 addData
    add = ""
    am = re.search(r"<addData>.*</addData>\s*$", inner, re.S)
    if am:
        add = "\n" + am.group(0).rstrip() + "\n      "
    vars_xml = "\n".join(var_xml(v, 8) for v in vars_)
    return xml[:m.end()] + "\n" + vars_xml + add + xml[end:]


def remove_dead_pous(xml):
    for name in DEAD_POUS:
        pou_re = re.compile(r'\s*<pou name="' + re.escape(name) + r'" pouType="[^"]+">.*?</pou>', re.S)
        xml, n = pou_re.subn("", xml)
        if n == 0:
            print(f"提示: 死 POU {name} 已不存在（幂等跳过）")
        xml = re.sub(r'\s*<Object Name="' + re.escape(name) + r'" ObjectId="[^"]+" />', "", xml)
    return xml


def fix_ethercat_task(xml):
    """ETHERCAT 任务只跑 PRG_Axis_Control；去掉误挂的 PLC_PRG（它在 MainTask）。"""
    t = xml.index('<task name="ETHERCAT"')
    e = xml.index("</task>", t)
    block = xml[t:e]
    block2 = re.sub(
        r'\s*<pouInstance name="PLC_PRG" typeName="">.*?</pouInstance>',
        "", block, flags=re.S)
    return xml[:t] + block2 + xml[e:]


def main():
    check_only = "--check" in sys.argv

    # 1. 解析 GVL
    kind, name, scopes, _ = parse_st(GVL_ST)
    gvl_vars = scopes.get("VAR_GLOBAL", [])
    print(f"GVL: {len(gvl_vars)} vars")

    # 2. 解析 POU
    pous = []
    for st in sorted(SRC_DIR.glob("*.st")):
        kind, name, scopes, body = parse_st(st)
        nvars = sum(len(v) for v in scopes.values())
        print(f"{name}: {kind}, {nvars} vars, body {len(body)} chars")
        pous.append((name, kind, scopes, body))

    if check_only:
        print("--check OK")
        return

    # 3. 备份 + 注入
    shutil.copy2(XML_PATH, BAK_PATH)
    print(f"备份 -> {BAK_PATH.name}")
    xml = XML_PATH.read_text(encoding="utf-8")

    xml = inject_gvl(xml, gvl_vars)
    for name, kind, scopes, body in pous:
        xml = inject_pou(xml, name, kind, scopes, body)
    xml = remove_dead_pous(xml)
    xml = fix_ethercat_task(xml)

    XML_PATH.write_text(xml, encoding="utf-8")
    print(f"注入完成 -> {XML_PATH} ({len(xml)} bytes)")


if __name__ == "__main__":
    main()
