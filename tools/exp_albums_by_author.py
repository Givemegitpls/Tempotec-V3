#!/usr/bin/env python3
"""Переход к следующему альбому — по автору (только для контекста Artists).

Проблема: при игре альбома из Artists текущий ключ = `album\\<имя>`, а
`FUN_004eae80` (следующий альбом при `album_skip`) ищет текущий трек в ГЛОБАЛЬНОМ
списке `album` и уходит в следующий альбом по всей библиотеке (чужой автор).

Решение (не трогая категорию Albums): хук на входе `FUN_004eae80`
(`0x4eaec4` → RX `0xa7e500`), который:
  - если текущий ключ `DAT_00b05224` начинается с `album\\`:
      берёт имя альбома, запросом достаёт `album_artist` из MEDIA_TABLE и строит
      ключ `artist\\<автор>` (malloc), кладёт указатель на него в стековый слот
      `0(sp)` кадра функции;
    иначе (категория Albums и др.) кладёт указатель на константу `album`.
Три места в `FUN_004eae80`, где использовалась константа `album` для поиска/счёта/
выборки строки (`0x4eaefc`, `0x4eaf08`, `0x4eaf30`), переводятся на `lw a0,0(sp)`.
Ключ для НОВОГО воспроизведения (`album\\<имя>`) по-прежнему строится из константы
`album` — не меняется.

Использование:
    python3 tools/exp_albums_by_author.py <hiby_player> [--check]
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

VTO = 0x400000
HOOK_VA = 0xA7E400
HOOK_OFF = HOOK_VA - VTO
SQL_VA = 0xA7E760
PFX_VA = 0xA7E7A0
PATCH_HOOK = 0x4EAEC4
PATCHES = (0x4EAEFC, 0x4EAF08, 0x4EAF30)  # move a0,s0 / addiu a0,s1,0x6fe0 -> lw a0,0(sp)
ORIG_HOOK = 0xAFA70AA0                      # sw a3, 0xaa0(sp)
ORIG_P = {0x4EAEFC: 0x02002021, 0x4EAF08: 0x02002021, 0x4EAF30: 0x26246FE0}
LW_A0_SP = 0x8FA40000                       # lw a0, 0(sp)
# индекс текущего альбома в списке артиста: подменяем вызов FUN_00706140
HOOK_INDEX_VA = 0xA7E620
PATCH_INDEX = 0x4EAF00
ORIG_INDEX = 0x0C1C1850                     # jal 0x706140
PHDR_FILESZ = 0x67E370
PHDR_NEW = 0x67F000

SQL = b"SELECT album_artist FROM MEDIA_TABLE WHERE album=? LIMIT 1\x00"
PFX = "artist\\".encode("utf-16-le") + b"\x00\x00"  # wide "artist\"

R = {n: i for i, n in enumerate(
    "zero at v0 v1 a0 a1 a2 a3 t0 t1 t2 t3 t4 t5 t6 t7 s0 s1 s2 s3 s4 s5 s6 s7 "
    "t8 t9 k0 k1 gp sp fp ra".split())}

HI_SQL, LO_SQL = (SQL_VA >> 16) & 0xFFFF, SQL_VA & 0xFFFF
HI_PFX, LO_PFX = (PFX_VA >> 16) & 0xFFFF, PFX_VA & 0xFFFF

HOOK = [
    "sw a3, 0xaa0(sp)",              # вытесненная инструкция
    "addiu sp, sp, -0x40",
    "sw ra, 0x18(sp)",
    "sw a0, 0x4(sp)",
    "sw a1, 0x8(sp)",
    "sw a2, 0xc(sp)",
    "sw v0, 0x10(sp)",
    # ключ по умолчанию = &"album"
    "lui t0, 0x96",
    "addiu t0, t0, 0x6fe0",
    "sw t0, 0x40(sp)",               # function_sp+0
    # проверка префикса "album\" (wide) в DAT_00b05224
    "lui t1, 0xb0",
    "addiu t1, t1, 0x5224",
    "lhu t2, 0(t1)",
    "addiu t3, zero, 0x61",
    "bne t2, t3, hdone",
    "lhu t2, 2(t1)",
    "addiu t3, zero, 0x6c",
    "bne t2, t3, hdone",
    "lhu t2, 4(t1)",
    "addiu t3, zero, 0x62",
    "bne t2, t3, hdone",
    "lhu t2, 6(t1)",
    "addiu t3, zero, 0x75",
    "bne t2, t3, hdone",
    "lhu t2, 8(t1)",
    "addiu t3, zero, 0x6d",
    "bne t2, t3, hdone",
    "lhu t2, 10(t1)",
    "addiu t3, zero, 0x5c",
    "bne t2, t3, hdone",
    "nop",
    # prepare: db, SQL, -1, &stmt, 0
    "sw zero, 0x0(sp)",
    "sw zero, 0x14(sp)",
    "lui t5, 0xbc",
    "lw t5, 0x18f0(t5)",
    "lw a0, 0(t5)",
    "lui a1, %d" % HI_SQL,
    "ori a1, a1, %d" % LO_SQL,
    "addiu a2, zero, -1",
    "addiu a3, sp, 0x14",
    "lui t9, 0x60",
    "ori t9, t9, 0x6140",
    "jalr t9",
    "nop",
    "lw t6, 0x14(sp)",
    "beq t6, zero, hdone",
    "nop",
    # bind: stmt, 1, album_name, (len+1)*2, 0
    "sw zero, 0x0(sp)",
    "lui t1, 0xb0",
    "addiu t1, t1, 0x5224",
    "addiu a2, t1, 12",
    "sw a2, 0x1c(sp)",
    "move a0, a2",
    "lui t9, 0x42",
    "ori t9, t9, 0x11a0",
    "jalr t9",
    "nop",
    "addiu v0, v0, 1",
    "sll a3, v0, 1",
    "lw a2, 0x1c(sp)",
    "lw a0, 0x14(sp)",
    "addiu a1, zero, 1",
    "sw zero, 0x0(sp)",
    "lui t9, 0x5b",
    "ori t9, t9, 0x2fa0",
    "jalr t9",
    "nop",
    # step
    "lw a0, 0x14(sp)",
    "lui t9, 0x5e",
    "ori t9, t9, 0xfe80",
    "jalr t9",
    "nop",
    "addiu t7, zero, 100",
    "bne v0, t7, hfin",
    "nop",
    # column_text(0)
    "lw a0, 0x14(sp)",
    "move a1, zero",
    "lui t9, 0x5b",
    "ori t9, t9, 0x9d20",
    "jalr t9",
    "nop",
    "beq v0, zero, hfin",
    "nop",
    "lhu t8, 0(v0)",
    "beq t8, zero, hfin",
    "nop",
    "sw v0, 0x20(sp)",               # artist ptr
    # malloc 0x110
    "addiu a0, zero, 0x110",
    "lui t9, 0x47",
    "ori t9, t9, 0x1120",
    "jalr t9",
    "nop",
    "beq v0, zero, hfin",
    "nop",
    "sw v0, 0x24(sp)",               # buf
    # strcpy(buf, "artist\")
    "move a0, v0",
    "lui a1, %d" % HI_PFX,
    "ori a1, a1, %d" % LO_PFX,
    "lui t9, 0x42",
    "ori t9, t9, 0x0ee0",
    "jalr t9",
    "nop",
    # strcat(buf, artist)
    "lw a0, 0x24(sp)",
    "lw a1, 0x20(sp)",
    "lui t9, 0x42",
    "ori t9, t9, 0x0f60",
    "jalr t9",
    "nop",
    # ключ существует в реестре? иначе оставляем "album"
    "lw a0, 0x24(sp)",
    "lui t9, 0x70",
    "ori t9, t9, 0x6020",
    "jalr t9",
    "nop",
    "bltz v0, hfin",
    "nop",
    "lw t0, 0x24(sp)",
    "sw t0, 0x40(sp)",               # ключ = buf
    "hfin:",
    "lw a0, 0x14(sp)",
    "lui t9, 0x5d",
    "ori t9, t9, 0x34e0",
    "jalr t9",
    "nop",
    "hdone:",
    "lw ra, 0x18(sp)",
    "lw a0, 0x4(sp)",
    "lw a1, 0x8(sp)",
    "lw a2, 0xc(sp)",
    "lw v0, 0x10(sp)",
    "addiu sp, sp, 0x40",
    "lui t9, 0x42",
    "ori t9, t9, 0xaecc",
    "jr t9",
    "nop",
]

# HOOK_INDEX(a0=key, a1=rec): позиция текущего альбома в списке артиста.
# Для ключа "artist\..." — сканируем список (сравнивая имя альбома rec+0x42c);
# иначе — вызываем оригинальный FUN_00706140.
HOOK_INDEX = [
    "addiu sp, sp, -0xaa0",
    "sw ra, 0xa98(sp)",
    "sw a0, 0xa90(sp)",
    "sw a1, 0xa94(sp)",
    "lhu t2, 0(a0)",
    "addiu t3, zero, 0x61",
    "bne t2, t3, orig",
    "lhu t2, 2(a0)",
    "addiu t3, zero, 0x72",
    "bne t2, t3, orig",
    "lhu t2, 4(a0)",
    "addiu t3, zero, 0x74",
    "bne t2, t3, orig",
    "lhu t2, 6(a0)",
    "addiu t3, zero, 0x69",
    "bne t2, t3, orig",
    "lhu t2, 8(a0)",
    "addiu t3, zero, 0x73",
    "bne t2, t3, orig",
    "lhu t2, 0xa(a0)",
    "addiu t3, zero, 0x74",
    "bne t2, t3, orig",
    "lhu t2, 0xc(a0)",
    "addiu t3, zero, 0x5c",
    "bne t2, t3, orig",
    "nop",
    # count = FUN_0070aa60(key)
    "lui t9, 0x70",
    "ori t9, t9, 0xaa60",
    "jalr t9",
    "nop",
    "sw v0, 0xa88(sp)",
    "blez v0, ret0",
    "nop",
    "sw zero, 0xa8c(sp)",
    "loop:",
    "lw t6, 0xa8c(sp)",
    "lw t4, 0xa88(sp)",
    "slt t7, t6, t4",
    "beq t7, zero, ret0",
    "nop",
    # FUN_004369a0(key, i, sp+0)
    "lw a0, 0xa90(sp)",
    "move a1, t6",
    "addiu a2, sp, 0",
    "lui t9, 0x43",
    "ori t9, t9, 0x69a0",
    "jalr t9",
    "nop",
    # FUN_00421020(row+0x42c, rec+0x42c)
    "addiu a0, sp, 0x42c",
    "lw a1, 0xa94(sp)",
    "addiu a1, a1, 0x42c",
    "lui t9, 0x42",
    "ori t9, t9, 0x1020",
    "jalr t9",
    "nop",
    "beq v0, zero, found",
    "nop",
    "lw t6, 0xa8c(sp)",
    "addiu t6, t6, 1",
    "sw t6, 0xa8c(sp)",
    "b loop",
    "nop",
    "found:",
    "lw v0, 0xa8c(sp)",
    "b done",
    "nop",
    "ret0:",
    "move v0, zero",
    "b done",
    "nop",
    "orig:",
    "lw a0, 0xa90(sp)",
    "lw a1, 0xa94(sp)",
    "lui t9, 0x70",
    "ori t9, t9, 0x6140",
    "jalr t9",
    "nop",
    "done:",
    "lw ra, 0xa98(sp)",
    "addiu sp, sp, 0xaa0",
    "jr ra",
    "nop",
]


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

    out = []
    for i, s in enumerate(norm):
        op0 = s.split()[0]
        if op0 in ("lw", "sw", "lhu"):
            rt, paren = [x.strip() for x in s.split(None, 1)[1].split(",", 1)]
            off, rs = paren.strip().split("(", 1)
            rs = rs.rstrip(")")
            opc = {"lw": 35, "sw": 43, "lhu": 37}[op0]
            out.append(opc << 26 | R[rs] << 21 | R[rt] << 16 | (int(off, 0) & 0xFFFF))
            continue
        p = [x for x in s.replace(",", " ").split() if x]
        op, a = p[0], p[1:]

        def br(opc: int, rs: str, rt: str, lbl: str) -> int:
            delta = pc(loc[lbl]) - pc(i) - 4
            assert delta % 4 == 0 and -32768 <= delta // 4 <= 32767, lbl
            return opc << 26 | R[rs] << 21 | R[rt] << 16 | (delta // 4 & 0xFFFF)

        if op == "nop":
            out.append(0)
        elif op == "addiu":
            out.append(9 << 26 | R[a[1]] << 21 | R[a[0]] << 16 | (int(a[2], 0) & 0xFFFF))
        elif op == "lui":
            out.append(15 << 26 | R[a[0]] << 16 | (int(a[1], 0) & 0xFFFF))
        elif op == "ori":
            out.append(13 << 26 | R[a[1]] << 21 | R[a[0]] << 16 | (int(a[2], 0) & 0xFFFF))
        elif op == "move":
            out.append(R[a[1]] << 21 | R[a[0]] << 11 | 0x25)
        elif op == "slt":
            out.append(R[a[1]] << 21 | R[a[2]] << 16 | R[a[0]] << 11 | 0x2A)
        elif op == "sll":
            out.append(R[a[1]] << 16 | R[a[0]] << 11 | (int(a[2], 0) & 0x1F) << 6)
        elif op in ("beq", "bne"):
            out.append(br(4 if op == "beq" else 5, a[0], a[1], a[2]))
        elif op == "blez":
            out.append(br(6, a[0], "zero", a[1]))
        elif op == "bltz":
            out.append(br(1, a[0], "zero", a[1]))
        elif op == "b":
            out.append(br(4, "zero", "zero", a[0]))
        elif op == "jr":
            out.append(R[a[0]] << 21 | 8)
        elif op == "jalr":
            out.append(R[a[0]] << 21 | 31 << 11 | 9)
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

    w = struct.unpack_from("<I", d, PATCH_HOOK - VTO)[0]
    done = (w >> 26 == 3 and (w & 0x3FFFFFF) << 2 == HOOK_VA)

    if check:
        print(f"hook-патч {PATCH_HOOK:#x} = {w:#010x} ({'HOOK' if done else 'сток/иное'})")
        print(f"index-патч {PATCH_INDEX:#x} = {struct.unpack_from('<I', d, PATCH_INDEX - VTO)[0]:#010x}")
        for va in PATCHES:
            print(f"  {va:#x} = {struct.unpack_from('<I', d, va - VTO)[0]:#010x}")
        return 0

    if done:
        print("уже пропатчено (albums by author)")
        return 0
    if w != ORIG_HOOK:
        raise SystemExit(f"неожиданные байты по {PATCH_HOOK:#x}: {w:#010x}")
    wi = struct.unpack_from("<I", d, PATCH_INDEX - VTO)[0]
    if wi != ORIG_INDEX:
        raise SystemExit(f"неожиданные байты по {PATCH_INDEX:#x}: {wi:#010x}")
    for va, orig in ORIG_P.items():
        cur = struct.unpack_from("<I", d, va - VTO)[0]
        if cur != orig:
            raise SystemExit(f"неожиданные байты по {va:#x}: {cur:#010x}")

    code = b"".join(struct.pack("<I", x) for x in _words(HOOK_VA, HOOK))
    assert len(code) <= HOOK_INDEX_VA - HOOK_VA, len(code)
    assert all(b == 0 for b in d[HOOK_OFF:HOOK_OFF + len(code)]), "RX-место занято"
    d[HOOK_OFF:HOOK_OFF + len(code)] = code
    d[SQL_VA - VTO:SQL_VA - VTO + len(SQL)] = SQL
    d[PFX_VA - VTO:PFX_VA - VTO + len(PFX)] = PFX

    idx_code = b"".join(struct.pack("<I", x) for x in _words(HOOK_INDEX_VA, HOOK_INDEX))
    idx_off = HOOK_INDEX_VA - VTO
    assert len(idx_code) <= SQL_VA - HOOK_INDEX_VA, len(idx_code)
    assert all(b == 0 for b in d[idx_off:idx_off + len(idx_code)]), "RX-место HOOK_INDEX занято"
    d[idx_off:idx_off + len(idx_code)] = idx_code

    struct.pack_into("<I", d, PATCH_HOOK - VTO, 3 << 26 | (HOOK_VA >> 2))
    struct.pack_into("<I", d, PATCH_INDEX - VTO, 3 << 26 | (HOOK_INDEX_VA >> 2))
    for va in PATCHES:
        struct.pack_into("<I", d, va - VTO, LW_A0_SP)

    ph = find_phdr2(d)
    if struct.unpack_from("<I", d, ph + 16)[0] == PHDR_FILESZ:
        struct.pack_into("<I", d, ph + 16, PHDR_NEW)
        struct.pack_into("<I", d, ph + 20, PHDR_NEW)

    path.write_bytes(bytes(d))
    print(f"{path}: albums-by-author hook @{HOOK_VA:#x} ({len(code)} байт), "
          f"SQL @{SQL_VA:#x}, PFX @{PFX_VA:#x}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
