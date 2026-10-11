#!/usr/bin/env python3
"""USB-режим «Dock» (adb) в списке выбора режима при подключении кабеля.

Проблема: режим adb в бинаре есть (`FUN_00476bc0(mode>=2)` → `functions=adb`,
`18D1:0D02`), но (1) в подстранице «USB device mode» пункта нет — генератор
`FUN_004d2760` жёстко строит 2 строки (`dac`/`usb`) и возвращает 2; (2) режим adb
ставит только гаджет, а демон `adbd` не запускает (в стоке его поднимал
`/sbin/adbserver.sh` из `K90adb`).

Правки:
1. Третья строка `adb` в списке (метка `<adb>Dock</adb>`). Код — пещера `0x41a000`;
   хук: эпилог `FUN_004d2760` (`0x4d2800`) → `jal 0x41a000`.
2. Старт `adbd`: хук на общий финал `FUN_00476bc0` (`0x476c80`, `jal 0x719d00`,
   общий для режимов 0 и >=2) → пещера `0x41a100`, которая при `s0 >= 2` (режим adb;
   у mode 0 `s0 == 0`) вызывает `system("/sbin/adbserver.sh &")`, затем исходный
   `FUN_00719d00`.

Клик по строке → `config 8 = индекс` (строка 2 → режим 2 → adb).

Идемпотентно, `--check`.

    python3 tools/exp_usb_mode_adb.py <hiby_player> [--check]
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

VTO = 0x400000
CAVE1_VA = 0x41A000          # добавление строки в список USB-режима
CAVE2_VA = 0x41A100          # старт adbd для режима adb
HOOK1_VA = 0x4D2800          # lw ra,0xab4(sp)  -> jal CAVE1
HOOK1_ORIG = 0x8FBF0AB4
HOOK2_VA = 0x4D2804          # lw s2,0xab0(sp)  -> nop
HOOK2_ORIG = 0x8FB20AB0
HOOK3_VA = 0x476C80          # jal 0x719d00 (общий финал FUN_00476bc0) -> jal CAVE2
HOOK3_ORIG = 0x0C1C6740

# функции/строки
F_LABEL = 0x00422660         # FUN_00422660("sys_set.ini", key, out, len)
F_MEMSET = 0x00A7DFB0
F_FINALIZE = 0x00719D00      # FUN_00719d00()
S_SYSSET = 0x0093F09C        # "sys_set.ini"
S_ADBSRV = 0x009C5A8C        # "/sbin/adbserver.sh &"
F_SYSTEM = 0x00A7E250        # system()

R = {n: i for i, n in enumerate(
    "zero at v0 v1 a0 a1 a2 a3 t0 t1 t2 t3 t4 t5 t6 t7 s0 s1 s2 s3 s4 s5 s6 s7 "
    "t8 t9 k0 k1 gp sp fp ra".split())}


def iw(op: int, rs: str, rt: str, imm: int) -> int:
    return op << 26 | R[rs] << 21 | R[rt] << 16 | (imm & 0xFFFF)


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

    out: list[int] = []
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
        elif op == "addiu":
            out.append(iw(9, a[1], a[0], int(a[2], 0)))
        elif op == "sltiu":
            out.append(iw(0x0B, a[1], a[0], int(a[2], 0)))
        elif op == "lui":
            out.append(iw(15, "zero", a[0], int(a[1], 0)))
        elif op == "ori":
            out.append(iw(13, a[1], a[0], int(a[2], 0)))
        elif op == "move":
            out.append(R[a[1]] << 21 | R["zero"] << 16 | R[a[0]] << 11 | 0x25)
        elif op == "bnez":
            out.append(iw(5, a[0], "zero", (pc(loc[a[1]]) - pc(i) - 4) // 4))
        elif op == "jal":
            tgt = a[0]
            tgt_va = pc(loc[tgt]) if tgt in loc else int(tgt, 0)
            out.append(3 << 26 | (tgt_va >> 2))
        elif op == "jalr":
            out.append(R[a[0]] << 21 | 31 << 11 | 9)
        elif op == "jr":
            out.append(R[a[0]] << 21 | 8)
        else:
            raise ValueError(s)
    return b"".join(struct.pack("<I", w) for w in out)


def cave1(adb_str_va: int) -> list[str]:
    """Третья строка `adb` в списке USB-режима + `return 3`."""
    return [
        "addiu a0, sp, 0x18",
        "move a1, zero",
        "addiu a2, zero, 0xa88",
        *lui_addiu("t9", F_MEMSET),
        "jalr t9",
        "nop",
        *lui_addiu("a0", S_SYSSET),
        *lui_addiu("a1", adb_str_va),
        "addiu a2, sp, 0x224",
        "addiu a3, zero, 0x104",
        *lui_addiu("t9", F_LABEL),
        "jalr t9",
        "nop",
        "lw t9, 0x18(s0)",
        "move a0, s0",
        "jalr t9",
        "addiu a1, sp, 0x18",
        "lw ra, 0xab4(sp)",
        "lw s2, 0xab0(sp)",
        "lw s1, 0xaac(sp)",
        "lw s0, 0xaa8(sp)",
        "addiu v0, zero, 3",
        "jr ra",
        "addiu sp, sp, 0xab8",
    ]


def cave2() -> list[str]:
    """Старт adbd для режима adb (s0 >= 2); режим 0 (Audio) — пропуск."""
    return [
        "addiu sp, sp, -0x28",
        "sw ra, 0x24(sp)",
        "sltiu t0, s0, 2",
        "bnez t0, c_skip",
        "nop",
        *lui_addiu("a0", S_ADBSRV),
        "jal 0x00a7e250",
        "nop",
        "c_skip:",
        "jal 0x00719d00",
        "nop",
        "lw ra, 0x24(sp)",
        "jr ra",
        "addiu sp, sp, 0x28",
    ]


ADB_STR_VA = CAVE1_VA + len(cave1(0)) * 4
ADB_STR = b"adb\x00"


def main() -> int:
    argv = sys.argv[1:]
    check = "--check" in argv
    args = [a for a in argv if a != "--check"]
    if len(args) != 1:
        raise SystemExit(__doc__)
    path = Path(args[0])
    d = bytearray(path.read_bytes())

    c1 = assemble(CAVE1_VA, cave1(ADB_STR_VA)) + ADB_STR
    c2 = assemble(CAVE2_VA, cave2())
    h1_new = 3 << 26 | (CAVE1_VA >> 2)
    h3_new = 3 << 26 | (CAVE2_VA >> 2)

    cur1 = struct.unpack_from("<I", d, HOOK1_VA - VTO)[0]
    cur2 = struct.unpack_from("<I", d, HOOK2_VA - VTO)[0]
    cur3 = struct.unpack_from("<I", d, HOOK3_VA - VTO)[0]
    ok1 = bytes(d[CAVE1_VA - VTO:CAVE1_VA - VTO + len(c1)]) == c1
    ok2 = bytes(d[CAVE2_VA - VTO:CAVE2_VA - VTO + len(c2)]) == c2
    done = cur1 == h1_new and cur2 == 0 and cur3 == h3_new and ok1 and ok2

    if check:
        print(f"{HOOK1_VA:#x} = {cur1:#010x} ({'хук' if cur1 == h1_new else 'сток'})")
        print(f"{HOOK2_VA:#x} = {cur2:#010x} ({'nop' if cur2 == 0 else 'сток'})")
        print(f"{HOOK3_VA:#x} = {cur3:#010x} ({'хук' if cur3 == h3_new else 'сток'})")
        print(f"пещеры: {CAVE1_VA:#x} {'ok' if ok1 else 'нет'} ({len(c1)}), "
              f"{CAVE2_VA:#x} {'ok' if ok2 else 'нет'} ({len(c2)})")
        return 0

    if done:
        print("уже пропатчено (usb mode adb)")
        return 0
    if cur1 not in (HOOK1_ORIG, h1_new):
        raise SystemExit(f"{HOOK1_VA:#x}: ожидался {HOOK1_ORIG:#010x} или {h1_new:#010x}, найдено {cur1:#010x}")
    if cur2 not in (HOOK2_ORIG, 0):
        raise SystemExit(f"{HOOK2_VA:#x}: ожидался {HOOK2_ORIG:#010x} или 0, найдено {cur2:#010x}")
    if cur3 not in (HOOK3_ORIG, h3_new):
        raise SystemExit(f"{HOOK3_VA:#x}: ожидался {HOOK3_ORIG:#010x} или {h3_new:#010x}, найдено {cur3:#010x}")
    if CAVE2_VA + len(c2) > 0x41B800:
        raise SystemExit(f"пещера перекрывает diag-зону: {CAVE2_VA + len(c2):#x}")
    for va, blob in ((CAVE1_VA, c1), (CAVE2_VA, c2)):
        cur = bytes(d[va - VTO:va - VTO + len(blob)])
        if cur not in (bytes(len(blob)), blob):
            raise SystemExit(f"пещера {va:#x} занята")

    d[CAVE1_VA - VTO:CAVE1_VA - VTO + len(c1)] = c1
    d[CAVE2_VA - VTO:CAVE2_VA - VTO + len(c2)] = c2
    struct.pack_into("<I", d, HOOK1_VA - VTO, h1_new)
    struct.pack_into("<I", d, HOOK2_VA - VTO, 0)
    struct.pack_into("<I", d, HOOK3_VA - VTO, h3_new)

    path.write_bytes(bytes(d))
    print(f"{path}: USB-режим adb (меню @{CAVE1_VA:#x}, adbd @{CAVE2_VA:#x}, "
          f"hooks {HOOK1_VA:#x}/{HOOK3_VA:#x})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
