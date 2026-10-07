#!/usr/bin/env python3
"""Shuffle: защита от выхода за диапазон при смене списка (album_skip и т.п.).

Проблема: `exp_shuffle_linear` делает проход линейным (обратимым), но при смене
текущего списка (граница альбома, `album_skip`) таблица-перестановка
`DAT_00b03cbc`/размер `DAT_00b03cc4` и индекс `DAT_00b03c04` могут остаться от
прошлого списка → `table[cursor]` даёт индекс за пределами (`52/9`,
`199852544`), а если индекс не находится в таблице — курсор остаётся старым и
плеер зависает.

Фикс: хук на `FUN_0042da00` (выбор следующего/предыдущего трека). Перед логикой
режима random (mode==2) санируем состояние:
  - если `DAT_00b03c04 >= DAT_00b03bfc` (индекс вне списка) → сбросить в 0;
  - если размер таблицы `DAT_00b03cc4 != DAT_00b03bfc` (таблица от другого списка)
    → вызвать `FUN_0042d720(count, 1)` — пересобрать перестановку (корректно ставит
    курсор).
Внутри одного списка линейная обратимость сохраняется.

Точка хука: `0x42da2c` (`move s3,a2`), уже после сохранения `$ra` в кадре функции
(0x42da24), поэтому `jal`-хук может свободно портить `$ra`. Хук исполняет
вытесненную `move s3,a2` и возвращается на `0x42da30`.

Использование:
    python3 tools/exp_shuffle_guard.py <hiby_player> [--check]
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

VTO = 0x400000
HOOK_VA = 0xA7E370
HOOK_OFF = HOOK_VA - VTO
PATCH_VA = 0x42DA2C
PATCH_OFF = PATCH_VA - VTO
ORIG = 0x00C09821  # move s3, a2
PHDR_FILESZ = 0x67E370
PHDR_NEW = 0x67F000

R = {n: i for i, n in enumerate(
    "zero at v0 v1 a0 a1 a2 a3 t0 t1 t2 t3 t4 t5 t6 t7 s0 s1 s2 s3 s4 s5 s6 s7 "
    "t8 t9 k0 k1 gp sp fp ra".split())}

HOOK = [
    "move s3, a2",              # вытесненная инструкция
    "addiu sp, sp, -0x20",
    "sw a0, 0(sp)",
    "sw a1, 4(sp)",
    "sw a3, 8(sp)",
    "sw v0, 0xc(sp)",
    "sw v1, 0x10(sp)",
    # mode == 2 (random)?
    "lw t1, 0x24(s0)",          # DAT_00b03bf4
    "addiu t2, zero, 2",
    "bne t1, t2, done",
    "nop",
    "lw t3, 0x2c(s0)",          # count = DAT_00b03bfc
    "blez t3, done",
    "nop",
    "lw t6, 0xf4(s0)",          # tbl size = DAT_00b03cc4
    "beq t6, t3, done",         # размер совпал → таблица текущего списка (в т.ч. выбор трека)
    "nop",
    "sw zero, 0x34(s0)",        # список другого размера → индекс 0
    "move a0, t3",
    "addiu a1, zero, 1",
    "lui t9, 0x42",
    "ori t9, t9, 0xd720",       # FUN_0042d720(count,1) — пересобрать перестановку
    "jalr t9",
    "nop",
    "done:",
    "lw a0, 0(sp)",
    "lw a1, 4(sp)",
    "lw a3, 8(sp)",
    "lw v0, 0xc(sp)",
    "lw v1, 0x10(sp)",
    "addiu sp, sp, 0x20",
    "lui t9, 0x42",
    "ori t9, t9, 0xda30",       # возврат в FUN_0042da00 после вытесненной инструкции
    "jr t9",
    "nop",
]


def iw(op: int, rs: str, rt: str, imm: int) -> int:
    return op << 26 | R[rs] << 21 | R[rt] << 16 | (imm & 0xFFFF)


def _words(base: int, lines: list[str]) -> list[int]:
    loc, norm = {}, []
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

    def branch(op: int, rs: str, rt: str, lbl: str, i: int) -> int:
        delta = pc(loc[lbl]) - pc(i) - 4
        assert delta % 4 == 0 and -32768 <= delta // 4 <= 32767, lbl
        return iw(op, rs, rt, delta // 4)

    out = []
    for i, s in enumerate(norm):
        op0 = s.split()[0]
        if op0 in ("lw", "sw"):
            rt, paren = [x.strip() for x in s.split(None, 1)[1].split(",", 1)]
            off, rs = paren.strip().split("(", 1)
            rs = rs.rstrip(")")
            opc = {"lw": 35, "sw": 43}[op0]
            out.append(opc << 26 | R[rs] << 21 | R[rt] << 16 | (int(off, 0) & 0xFFFF))
            continue
        p = [x for x in s.replace(",", " ").split() if x]
        op, a = p[0], p[1:]
        if op == "nop":
            out.append(0)
        elif op == "addiu":
            out.append(iw(9, a[1], a[0], int(a[2], 0)))
        elif op == "lui":
            out.append(iw(15, "zero", a[0], int(a[1], 0)))
        elif op == "ori":
            out.append(iw(13, a[1], a[0], int(a[2], 0)))
        elif op == "move":
            out.append(R[a[1]] << 21 | R["zero"] << 16 | R[a[0]] << 11 | 0x25)
        elif op == "sltu":
            out.append(R[a[1]] << 21 | R[a[2]] << 16 | R[a[0]] << 11 | 0x2B)
        elif op in ("beq", "bne"):
            out.append(branch(4 if op == "beq" else 5, a[0], a[1], a[2], i))
        elif op == "blez":
            out.append(branch(6, a[0], "zero", a[1], i))
        elif op == "jr":
            out.append(R[a[0]] << 21 | 8)
        elif op == "jalr":
            out.append(R[a[0]] << 21 | 31 << 11 | 9)
        elif op == "jal":
            out.append(3 << 26 | (int(a[0], 0) >> 2))
        else:
            raise ValueError(s)
    return out


def find_phdr2(d: bytes) -> int:
    phoff = struct.unpack_from("<I", d, 28)[0]
    es, n = struct.unpack_from("<HH", d, 42)
    for i in range(n):
        ph = phoff + i * es
        if struct.unpack_from("<I", d, ph)[0] == 1 and \
           struct.unpack_from("<I", d, ph + 16)[0] in (PHDR_FILESZ, PHDR_NEW):
            return ph
    raise SystemExit("RX phdr не найден")


def main() -> int:
    argv = sys.argv[1:]
    check = "--check" in argv
    args = [a for a in argv if a != "--check"]
    if len(args) != 1:
        raise SystemExit(__doc__)
    path = Path(args[0])
    d = bytearray(path.read_bytes())

    w = struct.unpack_from("<I", d, PATCH_OFF)[0]
    hook_now = d[HOOK_OFF:HOOK_OFF + 4]
    done = (w >> 26 == 3 and (w & 0x3FFFFFF) << 2 == HOOK_VA)
    ph = find_phdr2(d)
    phsz = struct.unpack_from("<I", d, ph + 16)[0]

    if check:
        print(f"patch {PATCH_VA:#x} = {w:#010x} ({'HOOK' if done else 'сток/иное'})")
        print(f"hook @{HOOK_VA:#x}: {hook_now.hex()}")
        print(f"phdr2 filesz = {phsz:#x}")
        return 0

    if done:
        print("уже пропатчено (shuffle guard)")
        return 0
    if w != ORIG:
        raise SystemExit(f"неожиданные байты по {PATCH_VA:#x}: {w:#010x}")

    code = b"".join(struct.pack("<I", x) for x in _words(HOOK_VA, HOOK))
    assert len(code) <= 0xC90, len(code)
    assert all(b == 0 for b in d[HOOK_OFF:HOOK_OFF + len(code)]), "RX-место занято"
    d[HOOK_OFF:HOOK_OFF + len(code)] = code

    struct.pack_into("<I", d, PATCH_OFF, 3 << 26 | (HOOK_VA >> 2))

    if phsz == PHDR_FILESZ:
        struct.pack_into("<I", d, ph + 16, PHDR_NEW)
        struct.pack_into("<I", d, ph + 20, PHDR_NEW)

    path.write_bytes(bytes(d))
    print(f"{path}: shuffle guard -> hook @{HOOK_VA:#x}, patch @{PATCH_VA:#x} ({len(code)} байт)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
