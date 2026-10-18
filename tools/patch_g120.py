#!/usr/bin/env python3
"""patch_g120.py — 由 LMM_g_1.1.xml 幂等生成 LMM_g_1.2.xml。

1.2 = 1.1（X双驱CSV速度模式现场修复 + 自动循环v1.1）+ 0.80 外部工步模式（eOpMode=2）。
两个分支各自演进了同名 POU，body 为逐 POU 三方合并结果（base=0.79 镜像 ST，
ours=1.1 XML 内嵌 ST，theirs=0.80 工步 ST），镜像已合并进 plc/g/*.st：

- GVL：新增 0.80 工步命令/回报 28 变量（复用 patch_g080.GVL_VARS）。
- PRG_Logic：localVars 追加工步状态机 35 个局部变量（镜像有而 1.1 接口没有的），
  body = 1.1 自动循环 + 0.80 eOpMode=2 工步状态机。
- PRG_TcpHmi：localVars 追加 xStepModePrev；body = 1.1 + 0.80 编解码：
  命令 word5 bit12 + word76..94 直写 HMI_*（不受 eCtrlSrc 门控），
  状态 word75..87 工步回报，航向误差非远程源时清零。
- word76..81 冲突：1.1 的 Y 宽度/R 角度解码与 0.80 工步区共享字 ——
  工步模式下让出（不解码），退出工步模式时恢复默认值（重设后再开自动循环）。
- 其余 POU（FB_XDual CSV 现场修复等）保持 1.1 原样；设备树/EtherCAT/任务不动。

用法:
    python3 tools/patch_g120.py [输入.xml] [输出.xml]
    默认 输入 LMM_g_1.1.xml 输出 LMM_g_1.2.xml
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from inject_st import parse_st, var_xml, body_xml  # noqa: E402
from patch_g080 import GVL_VARS, patch_gvl  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IN = ROOT / "LMM_g_1.1.xml"
DEFAULT_OUT = ROOT / "LMM_g_1.2.xml"
MARK = 'name="HMI_iStepCmd"'
POUS = ["PRG_Logic", "PRG_TcpHmi"]


def pou_span(text, name):
    m = re.search(r'<pou name="' + re.escape(name) + r'" pouType="[^"]+">', text)
    if not m:
        raise SystemExit(f"输入 XML 中未找到 POU {name}")
    end = text.index("</pou>", m.end())
    return m.start(), end


def insert_local_vars(text, name, scopes):
    """把镜像 VAR 作用域中 XML interface 缺失的变量插到 localVars 尾部。"""
    s, e = pou_span(text, name)
    block = text[s:e]
    im = re.search(r"<interface>(.*?)</interface>", block, re.S)
    if not im:
        raise SystemExit(f"{name}: 无 <interface>")
    have = set(re.findall(r'<variable name="(\w+)"', im.group(1)))
    missing = [v for v in scopes.get("VAR", []) if v["name"] not in have]
    if missing:
        lm = re.search(r"\s*</localVars>", im.group(1))
        if not lm:
            raise SystemExit(f"{name}: 无 localVars 块")
        add = "\n".join(var_xml(v, 12) for v in missing)
        inner = im.group(1)[:lm.start()] + "\n" + add + "\n          </localVars>"
        block = block[:im.start(1)] + inner + block[im.end(1):]
        text = text[:s] + block + text[e:]
    return text, len(missing)


def replace_body(text, name, body):
    s, e = pou_span(text, name)
    block = text[s:e]
    b0 = block.index("<body>")
    b1 = block.index("</body>") + len("</body>")
    block = block[:b0] + body_xml(body.replace("\n", "\r\n")) + block[b1:]
    return text[:s] + block + text[e:]


def fix_opmode_doc(text):
    """eOpMode/HMI_eOpMode 注释补 2=外部工步（存在旧注释时）。"""
    for name in ("eOpMode", "HMI_eOpMode"):
        vm = re.search(
            r'(<variable name="' + name + r'">.*?<xhtml[^>]*>)([^<]*)(</xhtml>)',
            text, re.S)
        if vm and vm.group(2).strip().endswith("0手动 1自动"):
            text = text[:vm.start(2)] + vm.group(2).rstrip() + " 2外部工步" + text[vm.end(2):]
        else:
            print(f"提示: {name} 文档未更新（无旧注释或格式不同）")
    return text


def main() -> None:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_IN
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUT
    text = src.read_bytes().decode("utf-8")
    if MARK in text:
        print(f"已含 1.2 标记（{MARK}），直接复制 -> {dst.name}")
        dst.write_bytes(text.encode("utf-8"))
        return
    for name, _, _ in GVL_VARS:
        if f'<variable name="{name}">' in text:
            raise SystemExit(f"GVL 已存在 {name}，基线不是 1.1？")
    text = patch_gvl(text)
    print(f"GVL: +{len(GVL_VARS)} 工步变量")
    for pou in POUS:
        _, _, scopes, body = parse_st(ROOT / "plc" / "g" / f"{pou}.st")
        text, n = insert_local_vars(text, pou, scopes)
        text = replace_body(text, pou, body)
        print(f"{pou}: +{n} localVars, body {len(body)} chars")
    text = fix_opmode_doc(text)
    if text.count(MARK) != 1:
        raise SystemExit(f"标记出现 {text.count(MARK)} 次，预期 1")
    raw = text.encode("utf-8")
    dst.write_bytes(raw)
    print(f"完成 -> {dst} ({len(raw)} bytes)")


if __name__ == "__main__":
    main()
