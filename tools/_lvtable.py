#!/usr/bin/env python3
"""Dump the generic listview registration records.

Array base 0x95d6d8 (from FUN_004ac980 disasm), stride 0x20c.
String at record+0x1c; callbacks at 0xabd4cc+0x00 / 0xabd4d0+0x04 / 0xabd534+0x68 /
0xabd538+0x6c / 0xabd53c+0x70 (each with stride 0x20c for its own array).

Usage: ./docker/fw.sh python3 tools/_lvtable.py <bin> [filter]
"""
from __future__ import annotations

import struct
import sys

PATHBASE = 0x95D6D8
STRIDE = 0x20C
CB = {
    "423c(datasrc)": 0xABD4CC,
    "4248": 0xABD4D0,
    "4240": 0xABD534,
    "4244": 0xABD538,
    "424c": 0xABD53C,
}


def main() -> int:
    path = sys.argv[1]
    filt = sys.argv[2] if len(sys.argv) > 2 else ""
    data = open(path, "rb").read()

    def rd(v: int, n: int = 4) -> bytes:
        return data[v - 0x400000 : v - 0x400000 + n]

    for i in range(0x68):
        pv = PATHBASE + i * STRIDE + 0x1C
        raw = rd(pv, 0x40)
        s = raw.split(bytes([0]))[0].decode("utf-8", "replace")
        if not s.startswith("vg_"):
            continue
        if filt and filt not in s:
            continue
        cbs = {k: struct.unpack("<I", rd(b + i * STRIDE, 4))[0] for k, b in CB.items()}
        print(f"idx {i:>3}  {s}")
        print("      " + "  ".join(f"{k}={v:#x}" for k, v in cbs.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
