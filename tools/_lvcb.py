#!/usr/bin/env python3
"""Dump generic listview callback tables at 0xabd4cc / 0xabd3c8 for given path indices.

Usage: ./docker/fw.sh python3 tools/_lvcb.py <bin> <idx> [<idx>...]
Stride 0x20c. Tables (from FUN_004ac980):
  +0x00 -> view+0x423c (0xabd4cc)   data source callback
  +0x04 -> view+0x4248 (0xabd4d0)
  +0x68 -> view+0x4240 (0xabd534)
  +0x6c -> view+0x4244 (0xabd538)
  +0x70 -> view+0x424c (0xabd53c)
Also dump path string at 0xabd3c8 + i*0x20c + 0x18 (after prefix).
"""
from __future__ import annotations

import struct
import sys

CB0 = 0xABD4CC
CB1 = 0xABD4D0
CB2 = 0xABD534
CB3 = 0xABD538
CB4 = 0xABD53C
PATH = 0xABD3C8
STRIDE = 0x20C


def main() -> int:
    path = sys.argv[1]
    idxs = [int(x, 0) for x in sys.argv[2:]]
    data = open(path, "rb").read()

    def rd(v: int, n: int = 4) -> bytes:
        return data[v - 0x400000 : v - 0x400000 + n]

    for i in idxs:
        print(f"--- idx {i} ---")
        pv = PATH + i * STRIDE + 0x1C
        print(f"  path   {pv:#x}: {rd(pv, 0x40).split(bytes([0]))[0].decode('utf-8', 'replace')}")
        for name, base in [("423c", CB0), ("4248", CB1), ("4240", CB2), ("4244", CB3), ("424c", CB4)]:
            v = struct.unpack("<I", rd(base + i * STRIDE, 4))[0]
            print(f"  view+0x{name} = {v:#010x}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
