#!/usr/bin/env python3
"""Find code references to strings in the MIPS hiby_player binary.

Usage (через docker-обёртку, инструменты в образе tempotec-fw-tools):
    ./docker/fw.sh python3 tools/xref.py <binary> "<substring>" [<substring> ...]
    ./docker/fw.sh python3 tools/xref.py <binary> range:0x9b78dc-0x9b7bfc

Выводит для каждой найденной строки её vaddr и адреса инструкций, которые
загружают этот vaddr (пары lui/addiu или lui/ori).
"""
from __future__ import annotations

import sys

from capstone import Cs, CS_ARCH_MIPS, CS_MODE_MIPS32, CS_MODE_LITTLE_ENDIAN
from elftools.elf.elffile import ELFFile


def load(path: str):
    with open(path, "rb") as fh:
        elf = ELFFile(fh)
        data = open(path, "rb").read()
        sections = []
        for sec in elf.iter_sections():
            if sec["sh_type"] == "SHT_NOBITS" or sec["sh_size"] == 0:
                continue
            sections.append(
                (sec.name, sec["sh_addr"], sec["sh_offset"], sec["sh_size"])
            )
    return data, sections


def vaddr_to_off(sections, vaddr):
    for _name, addr, off, size in sections:
        if addr <= vaddr < addr + size:
            return off + (vaddr - addr)
    return None


def off_to_vaddr(sections, off):
    for _name, addr, soff, size in sections:
        if soff <= off < soff + size:
            return addr + (off - soff)
    return None


def find_strings(data, sections, needle: bytes):
    out = []
    start = 0
    while True:
        idx = data.find(needle, start)
        if idx < 0:
            break
        start = idx + 1
        vaddr = off_to_vaddr(sections, idx)
        if vaddr is not None:
            out.append((vaddr, idx))
    return out


def disasm_text(data, sections, base):
    text = next(s for s in sections if s[0] == ".text")
    _name, addr, off, size = text
    md = Cs(CS_ARCH_MIPS, CS_MODE_MIPS32 | CS_MODE_LITTLE_ENDIAN)
    md.detail = True
    md.skipdata = True
    highs: dict[int, int] = {}
    known: dict[int, int] = {}  # reg -> абсолютный адрес, построенный la (lui+addiu)
    xrefs: dict[int, list[int]] = {}
    for insn in md.disasm(data[off : off + size], addr):
        mnem = insn.mnemonic
        if mnem == ".byte":
            continue
        ops = insn.operands
        if not ops:
            continue
        if mnem == "lui" and len(ops) == 2:
            highs[ops[0].reg] = ops[1].imm & 0xFFFF
        elif mnem in ("addiu", "ori") and len(ops) == 3:
            dst, src, imm = ops
            if src.reg in highs:
                hi = highs[src.reg]
                if mnem == "ori":
                    target = (hi << 16) + (imm.imm & 0xFFFF)
                else:
                    target = (hi << 16) + imm.imm
                xrefs.setdefault(target, []).append(insn.address)
                if dst.reg != src.reg:
                    known[dst.reg] = target
                else:
                    known.pop(dst.reg, None)
            if dst.reg == src.reg:
                highs.pop(src.reg, None)
                known.pop(dst.reg, None)
            elif dst.reg in highs or dst.reg in known:
                if dst.reg not in known:
                    highs.pop(dst.reg, None)
        elif mnem in ("lw", "sw", "lb", "lbu", "sb", "sh", "lhu", "lh") and len(ops) == 2:
            # доступ по адресу от заведомо известного указателя: base + смещение
            mem, _val = ops[0], ops[1]
            if mem.type == 3 and mem.base in known:
                xrefs.setdefault(known[mem.base] + mem.disp, []).append(insn.address)
    _ = base
    return xrefs


def main() -> int:
    path = sys.argv[1]
    needles = sys.argv[2:]
    data, sections = load(path)
    xrefs = disasm_text(data, sections, 0)
    for needle in needles:
        if needle == "stats":
            from collections import Counter

            c = Counter((t >> 16) for t in xrefs)
            for k in sorted(c):
                print(f"{k << 16:#010x} {c[k]}")
            continue
        if needle.startswith("range:"):
            lo_s, hi_s = needle[6:].split("-")
            lo, hi = int(lo_s, 16), int(hi_s, 16)
            for tgt in sorted(xrefs):
                if lo <= tgt <= hi:
                    print(f"{tgt:#010x} <- {[hex(x) for x in xrefs[tgt]]}")
            continue
        if needle.startswith("0x"):
            vaddr = int(needle, 16)
            end = data.find(b"\x00", vaddr_to_off(sections, vaddr))
            text = data[vaddr_to_off(sections, vaddr) : end][:90].decode(
                "utf-8", "replace"
            )
            for r in xrefs.get(vaddr, []):
                print(f"{vaddr:#010x} ref {r:#010x}  {text}")
            continue
        for vaddr, off in find_strings(data, sections, needle.encode()):
            end = data.find(b"\x00", off)
            text = data[off:end][:90].decode("utf-8", "replace")
            refs = xrefs.get(vaddr, [])
            print(f"{vaddr:#010x} refs={len(refs)}  {text}")
            for r in refs:
                print(f"      from {r:#010x}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
