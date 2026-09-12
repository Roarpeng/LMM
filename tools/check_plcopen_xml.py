#!/usr/bin/env python3
"""Validate a PLCopenXML file before importing into InoProShop.

Checks: UTF-8 BOM, strict UTF-8, no NUL / control chars, XML well-formed.
Usage: python3 tools/check_plcopen_xml.py [file ...]
"""

import hashlib
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOM = bytes([0xEF, 0xBB, 0xBF])


def check(path: Path) -> bool:
    raw = path.read_bytes()
    problems = []
    if raw[:3] != BOM:
        problems.append("missing UTF-8 BOM (EF BB BF)")
    body = raw[3:] if raw[:3] == BOM else raw
    try:
        body.decode("utf-8")
    except UnicodeDecodeError as exc:
        problems.append("invalid UTF-8: " + str(exc))
    bad = sorted({b for b in raw if b < 32 and b not in (9, 10, 13)})
    if bad:
        problems.append("control chars: " + ", ".join(hex(b) for b in bad))
    nul = raw.count(bytes([0]))
    if nul:
        problems.append("NUL bytes: " + str(nul))
    if not problems:
        try:
            ET.fromstring(body)
        except ET.ParseError as exc:
            problems.append("XML parse error: " + str(exc))
    digest = hashlib.sha256(raw).hexdigest()
    label = "OK  " if not problems else "FAIL"
    print(label, str(path), str(len(raw)) + "B", "sha256=" + digest)
    for p in problems:
        print("     -", p)
    return not problems


def main() -> int:
    args = sys.argv[1:] or [str(ROOT / "LMM_g_0.68.xml")]
    return 0 if all(check(Path(a)) for a in args) else 1


if __name__ == "__main__":
    raise SystemExit(main())
