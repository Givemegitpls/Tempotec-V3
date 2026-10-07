#!/usr/bin/env python3
"""Dump view table entries around VG_LISTVIEW_* and decode fields.

Usage: ./docker/fw.sh python3 tools/_views.py <bin>
Table VA 0x95e770, record 0x3c (15 words). Field layout per NOTES.
"""
from __future__ import annotations

import struct
import sys

BASE = 0x95E770
STRIDE = 0x3C


def main() -> int:
    path = sys.argv[1]
    data = open(path, "rb").read()

    def rd(vaddr: int, n: int) -> bytes:
        return data[vaddr - 0x400000 : vaddr - 0x400000 + n]

    def cstr(vaddr: int, n: int = 48) -> str:
        raw = rd(vaddr, n)
        return raw.split(b"\x00", 1)[0].decode("utf-8", "replace")

    # find names: first word is char* to uppercase name
    print(f"{'idx':>3} {'addr':>9} {'type':>4} {'sel':>3} w4 w5 w6 w7 w8 w9 w10 w11 w12  [d] [e]   name")
    for idx in range(0, 109):
        va = BASE + idx * STRIDE
        fields = struct.unpack("<15I", rd(va, STRIDE))
        name = cstr(fields[0])
        if not name.startswith("VG_"):
            continue
        t = fields[1]
        sel = fields[2]
        w = fields[4:13]
        print(
            f"{idx:>3} {va:#09x} {t:#04x} {sel:>3} "
            + "  ".join(str(x) for x in w)
            + f"  {fields[13]:#x} {fields[14]:#x}  {name}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
