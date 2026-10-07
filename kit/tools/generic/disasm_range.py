#!/usr/bin/env python3
"""Disassemble a vaddr range of hiby_player (MIPS32 LE) via capstone.

Usage:
    ./docker/fw.sh python3 tools/disasm_range.py <bin> 0x605fe0 0x6060e0
"""
from __future__ import annotations

import sys

from capstone import Cs, CS_ARCH_MIPS, CS_MODE_MIPS32, CS_MODE_LITTLE_ENDIAN
from elftools.elf.elffile import ELFFile


def main() -> int:
    path, lo_s, hi_s = sys.argv[1], sys.argv[2], sys.argv[3]
    lo, hi = int(lo_s, 16), int(hi_s, 16)
    with open(path, "rb") as fh:
        elf = ELFFile(fh)
        for sec in elf.iter_sections():
            a = sec["sh_addr"]
            if a <= lo < a + sec["sh_size"]:
                off = sec["sh_offset"] + (lo - a)
                size = hi - lo
                data = open(path, "rb").read()[off : off + size]
                md = Cs(CS_ARCH_MIPS, CS_MODE_MIPS32 | CS_MODE_LITTLE_ENDIAN)
                md.detail = True
                for insn in md.disasm(data, lo):
                    print(f"{insn.address:#010x}: {insn.bytes.hex():8} {insn.mnemonic:8} {insn.op_str}")
                return 0
    raise SystemExit("section not found")


if __name__ == "__main__":
    raise SystemExit(main())
