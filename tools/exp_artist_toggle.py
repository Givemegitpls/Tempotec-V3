#!/usr/bin/env python3
"""Переключатель «список альбомов ⇄ список треков» в разделе Artists.

Сток: кнопка `sub_back_iv_list_type` показывается сборщиком верхней панели
`FUN_004c6ac0` по типу вида (`view+0x40`): только для типов
0x0c/0x11 (`songs_of_a_genre` / `songs_of_artist_all`) и
0x0d/0x12 (`albums_of_a_genre` / `albums_of_an_artist`).
Обработчик `FUN_004c7ba0` (в таблице имён 0xacaf14) переключает
`vg_listview_albums_of_an_artist` ⇄ `vg_listview_songs_of_artist_all`.

Наши обложки (exp_album_view) подменили вид Artists на `vg_listview_album`
(тип 4) — обложки рисуются, но кнопку для типа 4 сборщик не показывает, и
обработчик это имя не знает. Эта правка возвращает переключатель, сохраняя
обложки:

  1) обработчик `FUN_004c7ba0`: сравнение и переход «назад» — на
     `vg_listview_album` (5 addiu: 0x4c7c44, 0x4c7da4, 0x4c7ea4, 0x4c7eb0,
     0x4c7ec0);
  2) обёртка «исполнитель альбома» (0x4aa21c) открывает тот же вид
     `vg_listview_album`, что и Artists (разделы идентичны, «назад» из списка
     треков возвращается к обложкам);
  3) RX-заглушка (0xa7e500) на записи jump-таблицы типа 4 (0x9642ac):
     показывает `list_type` для типа 4, КРОМЕ вида «Альбомы» (ключ `album`),
     т.е. только для списков альбомов артиста/автора.

Идемпотентно, `--check`.

    python3 tools/exp_artist_toggle.py <hiby_player> [--check]
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

VTO = 0x400000

# RX-заглушка (свободный хвост RX-сегмента; shuffle guard занимает 0xa7e370)
STUB_VA = 0xA7E500
STUB_OFF = STUB_VA - VTO

# jump-таблица switch'а сборщика панели: база 0x96429c, индекс = тип вида
JT_VA = 0x96429C
JT_IDX4_VA = JT_VA + 4 * 4  # тип 4 (VG_LISTVIEW_ALBUM)
JT_IDX4_OFF = JT_IDX4_VA - VTO
JT_STOCK = 0x004C6E8C       # сток: caseD_1 (кнопку не показывать)
CASE_12_VA = 0x4C74F0       # ветка type 0x12: показать list_type + подпись

# 5 addiu в FUN_004c7ba0 + обёртка «исполнитель альбома»:
#   addiu rX, rY, -0x2d1c (0x95d2e4 vg_listview_albums_of_an_artist)
#   ->      rX, rY, -0x2d58 (0x95d2a8 vg_listview_album)
ADDIU_SITES = [0x4C7C44, 0x4C7DA4, 0x4C7EA4, 0x4C7EB0, 0x4C7EC0, 0x4AA21C]
OLD_IMM = 0xD2E4
NEW_IMM = 0xD2A8

PHDR_FILESZ = 0x67E370
PHDR_NEW = 0x67F000

R = {n: i for i, n in enumerate(
    "zero at v0 v1 a0 a1 a2 a3 t0 t1 t2 t3 t4 t5 t6 t7 s0 s1 s2 s3 s4 s5 s6 s7 "
    "t8 t9 k0 k1 gp sp fp ra".split())}

# Заглушка: для типа 4 показать list_type, если ключ вида != "album" (категория
# «Альбомы»); иначе — стоковое поведение (скрыть).
STUB = [
    "lw t0, 0xd58(sp)",         # view (кадр сборщика)
    "lw t1, 0x3de0(t0)",        # key[0..1]
    "lui t2, 0x006c",
    "ori t2, t2, 0x0061",       # 0x006c0061 = wide "al"
    "bne t1, t2, show",
    "nop",
    "lw t1, 0x3de4(t0)",        # key[2..3]
    "lui t2, 0x0075",
    "ori t2, t2, 0x0062",       # 0x00750062 = wide "bu"
    "bne t1, t2, show",
    "nop",
    "lw t1, 0x3de8(t0)",        # key[4..5]
    "ori t2, zero, 0x006d",     # 0x0000006d = wide "m\\0"
    "bne t1, t2, show",
    "nop",
    "lui v0, 0x004c",
    "ori v0, v0, 0x6e8c",       # «Альбомы» -> сток (скрыть кнопку)
    "jr v0",
    "nop",
    "show:",
    "lui v0, 0x004c",
    "ori v0, v0, 0x74f0",       # ветка type 0x12 -> показать кнопку
    "jr v0",
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
        elif op in ("beq", "bne"):
            out.append(branch(4 if op == "beq" else 5, a[0], a[1], a[2], i))
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

    code = b"".join(struct.pack("<I", x) for x in _words(STUB_VA, STUB))

    jt = struct.unpack_from("<I", d, JT_IDX4_OFF)[0]
    hook = (jt == STUB_VA)  # jump-таблица хранит АДРЕС, не инструкцию jal
    imm_ok = all(
        struct.unpack_from("<I", d, va - VTO)[0] & 0xFFFF == NEW_IMM
        for va in ADDIU_SITES
    )
    ph = find_phdr2(d)
    phsz = struct.unpack_from("<I", d, ph + 16)[0]

    if check:
        print(f"jump-таблица тип4 {JT_IDX4_VA:#x} = {jt:#010x} "
              f"({'HOOK' if hook else 'сток/иное'})")
        print(f"addiu -0x2d58 на всех сайтах: {imm_ok}")
        print(f"RX-заглушка @{STUB_VA:#x}: {d[STUB_OFF:STUB_OFF + len(code)].hex()}")
        print(f"phdr2 filesz = {phsz:#x}")
        return 0

    if hook and imm_ok:
        print("уже пропатчено (artist toggle)")
        return 0

    for va in ADDIU_SITES:
        off = va - VTO
        w = struct.unpack_from("<I", d, off)[0]
        if (w >> 26) != 9:
            raise SystemExit(f"{va:#x}: не addiu ({w:#010x})")
        imm = w & 0xFFFF
        if imm == NEW_IMM:
            continue
        if imm != OLD_IMM:
            raise SystemExit(f"{va:#x}: ожидалось -0x2d1c, найдено {imm:#06x}")
        struct.pack_into("<I", d, off, (w & 0xFFFF0000) | NEW_IMM)

    if not hook:
        if jt != JT_STOCK:
            raise SystemExit(f"jump-таблица {JT_IDX4_VA:#x}: ожидался сток {JT_STOCK:#010x}, "
                             f"найдено {jt:#010x}")
        assert all(b == 0 for b in d[STUB_OFF:STUB_OFF + len(code)]), "RX-место занято"
        d[STUB_OFF:STUB_OFF + len(code)] = code
        struct.pack_into("<I", d, JT_IDX4_OFF, STUB_VA)

    if phsz == PHDR_FILESZ:
        struct.pack_into("<I", d, ph + 16, PHDR_NEW)
        struct.pack_into("<I", d, ph + 20, PHDR_NEW)

    path.write_bytes(bytes(d))
    print(f"{path}: artist toggle -> 6 addiu + jump-таблица тип4 -> {STUB_VA:#x} "
          f"({len(code)} байт)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
