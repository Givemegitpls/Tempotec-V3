#!/usr/bin/env python3
"""Scan .text for sw/sb/sh with a given displacement (op_str based, robust)."""
from __future__ import annotations

import re
import sys

from capstone import Cs, CS_ARCH_MIPS, CS_MODE_MIPS32, CS_MODE_LITTLE_ENDIAN
from elftools.elf.elffile import ELFFile

PAT = re.compile(r"^(sw|sb|sh)\s+(\S+),\s*(-?0x[0-9a-fA-F]+|-?\d+)\((\$\w+)\)$")


def main() -> int:
    path = sys.argv[1]
    disps = {int(x, 16) for x in sys.argv[2:]}
    data = open(path, "rb").read()
    elf = ELFFile(open(path, "rb"))
    text = next((s["sh_addr"], s["sh_offset"], s["sh_size"]) for s in elf.iter_sections() if s.name == ".text")
    addr, o, size = text
    md = Cs(CS_ARCH_MIPS, CS_MODE_MIPS32 | CS_MODE_LITTLE_ENDIAN)
    md.detail = False
    md.skipdata = True
    for insn in md.disasm(data[o : o + size], addr):
        if not insn.mnemonic.startswith(("sw", "sb", "sh")):
            continue
        m = PAT.match(f"{insn.mnemonic} {insn.op_str}")
        if not m:
            continue
        d = int(m.group(3), 0)
        if d in disps:
            print(f"{insn.address:#010x}: {insn.mnemonic} {insn.op_str}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
