#!/usr/bin/env python3
"""patch_g076.py — 由 LMM_g_0.75.xml 幂等生成 LMM_g_0.76.xml。

0.76 改动（用 SMC_SetControllerMode 每秒脉冲切 CSV）：
- POU：FB_XDual 第 11 节改为：空闲且使能时每秒给 bExecute 脉冲调
  SMC_SetControllerMode(SMC_velocity)；成功判据 = bDone 或 0x6060 读回=9。
  0.75 的直写 0x6060 保留兜底。无 GVL / 镜像变化。
- 幂等。

用法: python3 tools/patch_g076.py [输入.xml] [输出.xml]
     默认 输入 LMM_g_0.75.xml 输出 LMM_g_0.76.xml
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from inject_st import parse_st, inject_pou  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "plc" / "g"
DEFAULT_IN = ROOT / "LMM_g_0.75.xml"
DEFAULT_OUT = ROOT / "LMM_g_0.76.xml"
MARK = '11. 强制 X 双驱 CSV 速度模式（0.76'


def main() -> None:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_IN
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUT
    text = src.read_bytes().decode("utf-8")
    if MARK in text:
        print(f"已含 0.76 标记，直接复制 -> {dst.name}")
        dst.write_bytes(text.encode("utf-8"))
        return
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
