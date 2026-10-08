#!/usr/bin/env python3
"""ДИАГНОСТИКА: выгрузить на SD фактические ключи при сборке списка альбомов.

Ставит хук на `0x4a9288` (`jal FUN_0070a3a0` в `FUN_004a9180`) — перед сборкой
списка альбомов. Хук пишет в `/mnt/sd_0/diag.bin` (append, читается на хосте без
adb) четыре блока по 0x40 байт wide:

  1) `view+0x3de0`            — ключ открытого вида;
  2) `*(view+0x7c)+0x3de0`    — ключ «родительского» вида;
  3) `rec+4`                  — ключ, который попадает в буфер записи (его копирует
                                `FUN_00420ee0` из родительского);
  4) `view+0x40` (type, 4 б) + `view+0x74` (flags, 4 б).

Затем вызывает оригинальный `FUN_0070a3a0` (аргументы сохраняются) — поведение
не меняется. Собрать от базы `4429784b`, залить, открыть Artists→артист и
Исполнитель альбома→автор, потом прислать `/mnt/sd_0/diag.bin`.

    python3 tools/diag_album_keys.py <hiby_player> [--check]
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

VTO = 0x400000
STUB_VA = 0x419400
PATH_VA = 0x93FD00
HOOK_VA = 0x4A9288          # jal FUN_0070a3a0 (в FUN_004a9180)
HOOK_ORIG = 0x0C1C28E8      # jal 0x70a3a0
F_TARGET = 0x0070A3A0

PATH = b"/mnt/sd_0/diag.bin\x00"

R = {n: i for i, n in enumerate(
    "zero at v0 v1 a0 a1 a2 a3 t0 t1 t2 t3 t4 t5 t6 t7 s0 s1 s2 s3 s4 s5 s6 s7 "
    "t8 t9 k0 k1 gp sp fp ra".split())}


def iw(op: int, rs: str, rt: str, imm: int) -> int:
    return op << 26 | R[rs] << 21 | R[rt] << 16 | (imm & 0xFFFF)


def rw(rs: str, rt: str, rd: str, funct: int) -> int:
    return R[rs] << 21 | R[rt] << 16 | R[rd] << 11 | funct


def lui_addiu(reg: str, va: int) -> list[str]:
    lo = va & 0xFFFF
    if lo >= 0x8000:
        lo -= 0x10000
    hi = (va - lo) >> 16
    return [f"lui {reg}, {hi:#x}", f"addiu {reg}, {reg}, {lo:#x}"]


def assemble(base: int, lines: list[str]) -> bytes:
    loc: dict[str, int] = {}
    norm: list[str] = []
    for line in lines:
        s = line.split("#")[0].strip()
        if not s:
            continue
        if s.endswith(":"):
            loc[s[:-1]] = len(norm)
            continue
        norm.append(s)

    def pc(i: int) -> int:
        return base + i * 4

    out = []
    for i, s in enumerate(norm):
        op0 = s.split()[0]
        if op0 in ("lw", "sw"):
            rt, paren = [x.strip() for x in s.split(None, 1)[1].split(",", 1)]
            off, rs = paren.strip().split("(", 1)
            rs = rs.rstrip(")")
            off = off.strip() or "0"
            opc = {"lw": 35, "sw": 43}
            out.append(opc[op0] << 26 | R[rs] << 21 | R[rt] << 16 | (int(off, 0) & 0xFFFF))
            continue
        p = [x for x in s.replace(",", " ").split() if x]
        op, a = p[0], p[1:]
        if op == "nop":
            out.append(0)
        elif op == "syscall":
            out.append(0x0000000C)
        elif op == "addiu":
            rt, rs, imm = a
            out.append(iw(9, rs, rt, int(imm, 0)))
        elif op == "lui":
            rt, imm = a
            out.append(iw(15, "zero", rt, int(imm, 0)))
        elif op == "move":
            rd, rs = a
            out.append(rw(rs, "zero", rd, 0x25))
        elif op == "jalr":
            out.append(rw(a[0], "zero", "ra", 0x09))
        elif op == "bltz":
            rs, lbl = a
            out.append(iw(1, rs, "zero", (pc(loc[lbl]) - pc(i) - 4) // 4))
        elif op == "b":
            out.append(iw(4, "zero", "zero", (pc(loc[a[0]]) - pc(i) - 4) // 4))
        elif op == "jr":
            out.append(rw(a[0], "zero", "zero", 0x08))
        else:
            raise ValueError(s)
    return b"".join(struct.pack("<I", w) for w in out)


def w4(buf_reg: str, off: int | None, reg: str | None) -> list[str]:
    """write(fd=t4, ptr, 4 или 0x40) — заготовка под syscall write (v0=4004)."""
    L = ["addiu v0, zero, 4004", "move a0, t4"]
    L += [f"addiu a1, {buf_reg}, {off:#x}"] if off is not None else [f"move a1, {reg}"]
    return L


def stub() -> list[str]:
    L = [
        "addiu sp, sp, -0x40",
        "sw ra, 0x3c(sp)",
        "sw a0, 0x38(sp)",
        "sw a1, 0x34(sp)",
        "sw a2, 0x30(sp)",
        "sw a3, 0x2c(sp)",
        # open(path, O_WRONLY|O_CREAT|O_APPEND, 0644)
        "addiu v0, zero, 4005",
    ]
    L += lui_addiu("a0", PATH_VA)
    L += ["addiu a1, zero, 0x109", "addiu a2, zero, 0x1a4", "syscall",
          "bltz v0, DG_done", "move t4, v0"]
    # 1) view+0x3de0
    L += w4("s0", 0x3de0, None) + ["addiu a2, zero, 0x40", "syscall"]
    # 2) *(view+0x7c)+0x3de0
    L += ["lw t5, 0x7c(s0)", "addiu v0, zero, 4004", "move a0, t4",
          "addiu a1, t5, 0x3de0", "addiu a2, zero, 0x40", "syscall"]
    # 3) rec+4 = caller sp+0x24 (= our sp+0x64)
    L += ["addiu v0, zero, 4004", "move a0, t4", "addiu a1, sp, 0x64",
          "addiu a2, zero, 0x40", "syscall"]
    # 4) type + flags
    L += w4("s0", 0x40, None) + ["addiu a2, zero, 4", "syscall"]
    L += w4("s0", 0x74, None) + ["addiu a2, zero, 4", "syscall"]
    # close
    L += ["addiu v0, zero, 4006", "move a0, t4", "syscall"]
    # восстановить аргументы и вызвать оригинал
    L += ["DG_done:",
          "lw a0, 0x38(sp)", "lw a1, 0x34(sp)", "lw a2, 0x30(sp)", "lw a3, 0x2c(sp)"]
    L += lui_addiu("t9", F_TARGET)
    L += ["jalr t9", "nop", "lw ra, 0x3c(sp)", "jr ra", "addiu sp, sp, 0x40"]
    return L


def main() -> int:
    argv = sys.argv[1:]
    check = "--check" in argv
    args = [a for a in argv if a != "--check"]
    if len(args) != 1:
        raise SystemExit(__doc__)
    path = Path(args[0])
    d = bytearray(path.read_bytes())

    hook = struct.unpack_from("<I", d, HOOK_VA - VTO)[0]
    done = hook == (3 << 26 | (STUB_VA >> 2))

    if check:
        print(f"{HOOK_VA:#x} = {hook:#010x} ({'хук' if done else 'сток'})")
        return 0
    if done:
        print("уже пропатчено (diag)")
        return 0
    if hook != HOOK_ORIG:
        raise SystemExit(f"{HOOK_VA:#x}: ожидался {HOOK_ORIG:#010x}, найдено {hook:#010x}")

    stub_b = assemble(STUB_VA, stub())
    for va, blob in ((STUB_VA, stub_b), (PATH_VA, PATH)):
        off = va - VTO
        if not all(b == 0 for b in d[off : off + len(blob)]):
            raise SystemExit(f"место {va:#x} занято")
    d[STUB_VA - VTO : STUB_VA - VTO + len(stub_b)] = stub_b
    d[PATH_VA - VTO : PATH_VA - VTO + len(PATH)] = PATH
    struct.pack_into("<I", d, HOOK_VA - VTO, 3 << 26 | (STUB_VA >> 2))

    path.write_bytes(bytes(d))
    print(f"{path}: диагностика ключей (хук @{HOOK_VA:#x} -> {STUB_VA:#x})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
