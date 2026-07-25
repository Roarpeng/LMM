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

DEAD_POUS = ["FB_TCPServer", "PRG_Force485", "FB_XDiff", "FB_GantryX"]

ELEMENTARY = {
    "BOOL", "SINT", "INT", "DINT", "LINT",
    "USINT", "UINT", "UDINT", "ULINT",
    "BYTE", "WORD", "DWORD", "LWORD",
    "REAL", "LREAL", "TIME", "DATE", "STRING",
}

VAR_BLOCK_RE = re.compile(r"^\s*(VAR_INPUT|VAR_OUTPUT|VAR_IN_OUT|VAR_GLOBAL(?:\s+RETAIN)?|VAR)\b")
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
            if scope == "VAR_GLOBAL RETAIN":
                scope = "VAR_GLOBAL_RETAIN"
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
    # InoPro：同一 data/globalvars 下只能有一个 globalVars；RETAIN 变量并入 GVL，
    # 用变量级 retain 属性（勿再拆 GVL_RETAIN 兄弟节点）。
    if v.get("retain"):
        out.append(
            f"{pad}  <addData>\n"
            f'{pad}    <data name="http://www.3s-software.com/plcopenxml/attributes" '
            f'handleUnknown="implementation">\n'
            f"{pad}      <Attributes>\n"
            f'{pad}        <Attribute Name="retain" Value="" />\n'
            f"{pad}      </Attributes>\n"
            f"{pad}    </data>\n"
            f"{pad}  </addData>"
        )
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


# 新建 POU 时使用的稳定 GUID（与 ProjectStructure 对齐）
NEW_POU_GUIDS = {
    "FB_XDual": "d4e5f6a7-b8c9-4012-c345-d6e7f8a90002",
}
FB_FOLDER_GUID = "2dc75837-520f-43d9-90dd-47cded0212a2"


def _pou_adddata(name, guid, fb_folder=True):
    mid = (
        f'                  <pathStructure isFolder="True" name="FB" namespace="00000000-0000-0000-0000-000000000000" '
        f'factoryName="Inovance.InoPro.InoNavigators.FolderObjectFactory" factoryGuid="{{BA66A801-C738-4176-B072-DFE26ACE36D3}}" '
        f'objectGuid="{FB_FOLDER_GUID}">\n'
        f'                    <pathStructure isFolder="False" name="{name}" namespace="e5b60c93-5445-4e40-ada9-cd9c005549b4" '
        f'factoryName="Inovance.InoPro.InoPOUObject.POUObjectFactory" factoryGuid="{{39C4ED2B-903C-464c-9041-7DF4ECEE9609}}" '
        f'objectGuid="{guid}" />\n'
        f'                  </pathStructure>\n'
    ) if fb_folder else (
        f'                  <pathStructure isFolder="False" name="{name}" namespace="e5b60c93-5445-4e40-ada9-cd9c005549b4" '
        f'factoryName="Inovance.InoPro.InoPOUObject.POUObjectFactory" factoryGuid="{{39C4ED2B-903C-464c-9041-7DF4ECEE9609}}" '
        f'objectGuid="{guid}" />\n'
    )
    return (
        '        <addData>\n'
        '          <data name="http://www.3s-software.com/plcopenxml/pathstructure" handleUnknown="discard">\n'
        '            <pathStructure isFolder="False" name="Device" namespace="1ee21fdd-5562-44a0-a3ce-665d74916d50" '
        'factoryName="Inovance.InoPro.InoDeviceObject.DeviceObjectFactory" factoryGuid="{84d12aa5-3225-473b-9df6-18af40889bdf}" '
        'objectGuid="d7de5ac3-3f30-45ac-8468-ec250b4e523b">\n'
        '              <pathStructure isFolder="False" name="Plc Logic" namespace="00000000-0000-0000-0000-000000000000" '
        'factoryName="_3S.CoDeSys.PlcLogicObject.PlcLogicObjectFactory" factoryGuid="{8ceeba4e-ac7a-4fbd-9415-bfb2d98668ab}" '
        'objectGuid="8a291c6e-c5c5-4a07-8c04-1100df0e1491">\n'
        '                <pathStructure isFolder="False" name="Application" namespace="e5b60c93-5445-4e40-ada9-cd9c005549b4" '
        'factoryName="_3S.CoDeSys.ApplicationObject.ApplicationObjectFactory" factoryGuid="{ECADC42E-716E-4ff3-A93C-0CD143F9743F}" '
        'objectGuid="69822df8-b9c0-4a01-9450-b2cdc030688c">\n'
        + mid +
        '                </pathStructure>\n'
        '              </pathStructure>\n'
        '            </pathStructure>\n'
        '          </data>\n'
        '          <data name="http://www.3s-software.com/plcopenxml/objectid" handleUnknown="discard">\n'
        f'            <ObjectId>{guid}</ObjectId>\n'
        '          </data>\n'
        '        </addData>\n'
    )


def ensure_pou_exists(xml, name, kind):
    """若 POU 不存在则在 FB_XLineTrack 后插入空壳，并登记 ProjectStructure。"""
    pou_re = re.compile(r'<pou name="' + re.escape(name) + r'" pouType="[^"]+">')
    if pou_re.search(xml):
        return xml
    guid = NEW_POU_GUIDS.get(name)
    if not guid:
        raise ValueError(f"LMM.xml 中未找到 POU {name}，且无新建 GUID")
    pou_type = "functionBlock" if kind == "FUNCTION_BLOCK" else "program"
    stub = (
        f'      <pou name="{name}" pouType="{pou_type}">\n'
        f'        <interface />\n'
        f'        <body>\n          <ST>\n'
        f'            <xhtml xmlns="http://www.w3.org/1999/xhtml"></xhtml>\n'
        f'          </ST>\n        </body>\n'
        f'{_pou_adddata(name, guid, fb_folder=(kind == "FUNCTION_BLOCK"))}'
        f'      </pou>\n'
    )
    anchor = xml.find('</pou>', xml.find('<pou name="FB_XLineTrack"'))
    if anchor < 0:
        raise ValueError("无法定位 FB_XLineTrack 作为新建 POU 锚点")
    anchor = anchor + len('</pou>')
    xml = xml[:anchor] + "\n" + stub + xml[anchor:]
    obj = f'              <Object Name="{name}" ObjectId="{guid}" />\n'
    if f'Object Name="{name}"' not in xml:
        marker = '              <Object Name="FB_XLineTrack"'
        mi = xml.find(marker)
        if mi < 0:
            raise ValueError("ProjectStructure 中未找到 FB_XLineTrack")
        line_end = xml.find("\n", mi) + 1
        xml = xml[:line_end] + obj + xml[line_end:]
    print(f"新建 POU 壳: {name} ({guid})")
    return xml


def inject_pou(xml, name, kind, scopes, body):
    xml = ensure_pou_exists(xml, name, kind)
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


def strip_extra_globalvars(xml):
    """删除 GVL 之外的非法 globalVars 兄弟（如错误注入的 GVL_RETAIN）。"""
    # 仅保留 data/.../globalvars 下的第一个 globalVars(GVL)
    pattern = re.compile(
        r'(<data name="http://www\.3s-software\.com/plcopenxml/globalvars"[^>]*>\s*)'
        r'(<globalVars name="GVL">.*?</globalVars>)'
        r'(\s*<globalVars name="[^"]+".*?</globalVars>)+'
        r'(\s*</data>)',
        re.S,
    )

    def _keep_gvl(m):
        print(f"移除非法额外 globalVars（保留 GVL）")
        return m.group(1) + m.group(2) + m.group(4)

    return pattern.sub(_keep_gvl, xml)


def inject_gvl(xml, vars_):
    """注入唯一 GVL（InoPro 每个 globalvars data 仅允许一个 globalVars 子元素）。"""
    xml = strip_extra_globalvars(xml)
    gvl_re = re.compile(r'<globalVars name="GVL">')
    m = gvl_re.search(xml)
    if not m:
        raise ValueError("未找到 globalVars GVL")
    vars_xml = "\n".join(var_xml(v, 8) for v in vars_)
    end = xml.index("</globalVars>", m.end())
    inner = xml[m.end():end]
    keep = ""
    # 只保留 GVL 对象级 addData（pathstructure/objectid），
    # 勿匹配变量内的 retain <addData>（否则会截断/重复破坏 XML）。
    am = re.search(
        r'<addData>\s*'
        r'<data name="http://www\.3s-software\.com/plcopenxml/pathstructure"'
        r'.*?</addData>\s*$',
        inner,
        re.S,
    )
    if am:
        keep = "\n" + am.group(0).rstrip() + "\n      "
    return xml[:m.end()] + "\n" + vars_xml + keep + xml[end:]


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

    # 1. 解析 GVL（RETAIN 段并入同一 GVL，变量带 retain 标记）
    kind, name, scopes, _ = parse_st(GVL_ST)
    gvl_vars = scopes.get("VAR_GLOBAL", [])
    retain_vars = scopes.get("VAR_GLOBAL_RETAIN", [])
    for v in retain_vars:
        v["retain"] = True
    all_gvl = gvl_vars + retain_vars
    print(f"GVL: {len(gvl_vars)} vars + {len(retain_vars)} RETAIN (merged)")

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

    xml = inject_gvl(xml, all_gvl)
    for name, kind, scopes, body in pous:
        xml = inject_pou(xml, name, kind, scopes, body)
    xml = remove_dead_pous(xml)
    xml = fix_ethercat_task(xml)

    XML_PATH.write_text(xml, encoding="utf-8")
    print(f"注入完成 -> {XML_PATH} ({len(xml)} bytes)")


if __name__ == "__main__":
    main()
