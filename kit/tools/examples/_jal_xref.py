#!/usr/bin/env python3
"""Find direct (jal) callers of given target address(es) in .text.

Usage: ./docker/fw.sh python3 tools/_jal_xref.py <bin> 0x4a6c40 [0x...]
Also '-c 0xTARGET' prints the function containing a target (nearest preceding function start).
"""
from __future__ import annotations

import sys

from capstone import Cs, CS_ARCH_MIPS, CS_MODE_MIPS32, CS_MODE_LITTLE_ENDIAN
from elftools.elf.elffile import ELFFile


def main() -> int:
    path = sys.argv[1]
    targets = {int(x, 16) for x in sys.argv[2:] if x.startswith("0x")}
    data = open(path, "rb").read()
    elf = ELFFile(open(path, "rb"))
    text = next((s["sh_addr"], s["sh_offset"], s["sh_size"]) for s in elf.iter_sections() if s.name == ".text")
    addr, off, size = text
    md = Cs(CS_ARCH_MIPS, CS_MODE_MIPS32 | CS_MODE_LITTLE_ENDIAN)
    md.detail = False
    md.skipdata = True
    hits: dict[int, list[str]] = {t: [] for t in targets}
    for insn in md.disasm(data[off : off + size], addr):
        if insn.mnemonic in ("jal", "j") and insn.op_str.startswith("0x"):
            try:
                tgt = int(insn.op_str, 16)
            except ValueError:
                continue
            # MIPS jal stores return addr; target may be in same 256MB region
            for t in targets:
                if tgt == t or (insn.mnemonic == "jal" and tgt == t):
                    hits[t].append(f"{insn.address:#010x}")
    for t in sorted(hits):
        print(f"target {t:#010x}: {len(hits[t])} direct callers")
        for c in hits[t]:
            print(f"    {c}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
