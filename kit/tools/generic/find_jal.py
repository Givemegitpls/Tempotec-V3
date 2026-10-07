#!/usr/bin/env python3
"""Find all `jal <target>` sites (and j) to a vaddr in hiby_player .text.

Usage:
    ./docker/fw.sh python3 tools/find_jal.py <bin> 0x4a95e0
"""
from __future__ import annotations

import struct
import sys

from elftools.elf.elffile import ELFFile

VADDR_TO_OFFSET = 0x400000


def main() -> int:
    path = sys.argv[1]
    target = int(sys.argv[2], 16)
    data = open(path, "rb").read()
    words = [(target >> 2) & 0x3FFFFFF, target & 0x3FFFFFF]
    hits = []
    for i in range(0, len(data) - 4, 4):
        w = struct.unpack_from("<I", data, i)[0]
        op = w >> 26
        if op not in (2, 3):  # j, jal
            continue
        # jal/j stored absolute in 26-bit word; decode. Value may be either encoding
        # because our assembler uses (target) or (target>>2). Standard MIPS: addr>>2.
        if (w & 0x3FFFFFF) == words[0]:
            hits.append(("jal" if op == 3 else "j", i + VADDR_TO_OFFSET))
    for kind, va in hits:
        print(f"{kind} {va:#010x}")
    print(f"total {len(hits)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
