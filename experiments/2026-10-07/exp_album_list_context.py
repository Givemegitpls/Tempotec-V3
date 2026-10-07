#!/usr/bin/env python3
"""Список альбомов: развести Artists и «Исполнитель альбома».

Проблема: и Artists, и «Исполнитель альбома» открывают один вид
(`vg_listview_album`) и зовут один запрос — слот 182
(`SELECT DISTINCT album FROM MEDIA_TABLE WHERE artist like ?`). Ключ в запрос
уходит БЕЗ префикса, поэтому разделы неотличимы: у соавтора (напр. «Дэн
Субботин») оба показывают один и тот же список. Нужно: Artists — альбомы, где
артист есть в теге `artist` (по составляющей); «Исполнитель альбома» — только
альбомы, где `album_artist` = этот автор.

Решение (без изменения привязки ключа): источник списка `FUN_004a9180` знает
вид и его ключ (`view+0x3de0`), который начинается с префикса — `L"artist\\…"`
или `L"album_artist\\…"`. Ставим два RX-стаба:

  * `SA` @ 0x4a92a0 (замена `jal FUN_0070b020` в `FUN_004a9180`): по 1-му и
    2-му символу ключа (`'a'`,`'l'` = `album_artist`) выставляет флаг в BSS и
    хвостом уходит в `FUN_0070b020` (ra не трогается — возврат идёт в
    `FUN_004a9180`).
  * `SB` @ 0x70be88 (замена `jal FUN_007060a0` в `FUN_0070b020`): если флаг
    стоит — подменяет на время вызова кэшированный стейтмент менеджера
    (`+0x4ac`) на свой (`SELECT DISTINCT album … WHERE album_artist …`,
    готовится лениво через `FUN_00606140` и кэшируется в BSS), зовёт
    `FUN_007060a0`, восстанавливает стейтмент и снимает флаг; иначе — стоковый
    вызов.

BSS-слова: `0xbe7e30` — флаг, `0xbe7e34` — указатель своего стейтмента.
RX: SA `0xa7ed00`, SB `0xa7ee00`, SQL `0xa7ef00` (за строками треков).

Применять ПОСЛЕ `exp_albums_by_component` и `exp_artist_tracks_component`.

Идемпотентно, `--check`.

    python3 tools/exp_album_list_context.py <hiby_player> [--check]
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

VTO = 0x400000
SA_VA = 0xA7ED00
SB_VA = 0xA7EE00
SQL_VA = 0xA7EF00
BSS_FLAG = 0xBE7E30
BSS_STMT = 0xBE7E34
PATCH_A = 0x4A92A0          # jal FUN_0070b020
PATCH_B = 0x70BE88          # jal FUN_0070a0
ORIG_A = 0x0C1C2C08         # jal 0x70b020
ORIG_B = 0x0C1C1828         # jal 0x7060a0
RX_LIMIT = 0xA7F000

SQL = (
    b"SELECT DISTINCT album FROM MEDIA_TABLE WHERE "
    b"(';'||substr(album_artist,1,length(album_artist))||';') "
    b"LIKE '%;'||substr(?1,1,length(?1))||';%' "
    b"ORDER BY album collate pinyin"
)

R = {n: i for i, n in enumerate(
    "zero at v0 v1 a0 a1 a2 a3 t0 t1 t2 t3 t4 t5 t6 t7 s0 s1 s2 s3 s4 s5 s6 s7 "
    "t8 t9 k0 k1 gp sp fp ra".split())}


def iw(op: int, rs: str, rt: str, imm: int) -> int:
    return op << 26 | R[rs] << 21 | R[rt] << 16 | (imm & 0xFFFF)


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
        if op0 in ("lw", "lbu", "sw"):
            rt, paren = [x.strip() for x in s.split(None, 1)[1].split(",", 1)]
            off, rs = paren.strip().split("(", 1)
            rs = rs.rstrip(")")
            off = off.strip() or "0"
            opc = {"lw": 35, "lbu": 36, "sw": 43}
            out.append(opc[op0] << 26 | R[rs] << 21 | R[rt] << 16 | (int(off, 0) & 0xFFFF))
            continue
        p = [x for x in s.replace(",", " ").split() if x]
        op, a = p[0], p[1:]
        if op == "nop":
            out.append(0)
        elif op == "addiu":
            rt, rs, imm = a
            out.append(iw(9, rs, rt, int(imm, 0)))
        elif op == "lui":
            rt, imm = a
            out.append(iw(15, "zero", rt, int(imm, 0)))
        elif op == "move":
            rd, rs = a
            out.append(R[rs] << 21 | R[rd] << 11 | 0x25)
        elif op in ("beq", "bne"):
            rs, rt, lbl = a
            delta = pc(loc[lbl]) - pc(i) - 4
            out.append(iw(4 if op == "beq" else 5, rs, rt, delta // 4))
        elif op == "b":
            out.append(iw(4, "zero", "zero", (pc(loc[a[0]]) - pc(i) - 4) // 4))
        elif op == "jr":
            out.append(R[a[0]] << 21 | 8)
        elif op == "j":
            out.append(2 << 26 | (int(a[0], 0) >> 2))
        elif op == "jal":
            t = pc(loc[a[0]]) if not a[0].startswith("0x") else int(a[0], 0)
            out.append(3 << 26 | (t >> 2))
        else:
            raise ValueError(s)
    return b"".join(struct.pack("<I", w) for w in out)


def lui_addiu(reg: str, va: int) -> list[str]:
    lo = va & 0xFFFF
    if lo >= 0x8000:
        lo -= 0x10000
    hi = (va - lo) >> 16
    return [f"lui {reg}, {hi:#x}", f"addiu {reg}, {reg}, {lo:#x}"]


def stub_a() -> list[str]:
    L = lui_addiu("t0", BSS_FLAG)
    L += [
        "lbu t1, 0x3de0(s0)",       # 1-й wide-символ ключа
        "addiu t2, zero, 0x61",     # 'a'
        "bne t1, t2, SA_z",
        "nop",
        "lbu t1, 0x3de2(s0)",       # 2-й: 'l' (album_artist) или 'r' (artist)
        "addiu t2, zero, 0x6c",     # 'l'
        "bne t1, t2, SA_z",
        "nop",
        "addiu t3, zero, 1",
        "b SA_s",
        "nop",
        "SA_z:",
        "move t3, zero",
        "SA_s:",
        "sw t3, 0(t0)",
        "j 0x70b020",
        "nop",
    ]
    return L


def stub_b() -> list[str]:
    L = [
        "addiu sp, sp, -0x20",
        "sw ra, 0x1c(sp)",
        "sw a0, 0x18(sp)",          # ключ
    ]
    L += lui_addiu("t0", BSS_FLAG)
    L += [
        "lw t1, 0(t0)",
        "beq t1, zero, SB_orig",
        "nop",
        # сохранить стоковый стейтмент менеджера
        "lui t2, 0xbc",
        "lw t2, 0x18f0(t2)",
        "lw t3, 0x4ac(t2)",
        "sw t3, 0x14(sp)",
    ]
    L += lui_addiu("t0", BSS_STMT)
    L += [
        "lw t4, 0(t0)",
        "bne t4, zero, SB_have",
        "nop",
        # prepare(db, sql, -1, &our_stmt, 0); db = *(manager+0)
        "lui a0, 0xbc",
        "lw a0, 0x18f0(a0)",
        "lw a0, 0(a0)",
    ]
    L += lui_addiu("a1", SQL_VA)
    L += [
        "addiu a2, zero, -1",
    ]
    L += lui_addiu("a3", BSS_STMT)
    L += [
        "sw zero, 0x10(sp)",
        "jal 0x606140",
        "nop",
        "SB_have:",
    ]
    L += lui_addiu("t0", BSS_STMT)
    L += [
        "lw t4, 0(t0)",
        "lui t2, 0xbc",
        "lw t2, 0x18f0(t2)",
        "sw t4, 0x4ac(t2)",
        "lw a0, 0x18(sp)",
        "jal 0x7060a0",
        "nop",
        # восстановить
        "lui t2, 0xbc",
        "lw t2, 0x18f0(t2)",
        "lw t3, 0x14(sp)",
        "sw t3, 0x4ac(t2)",
    ]
    L += lui_addiu("t0", BSS_FLAG)
    L += [
        "sw zero, 0(t0)",
        "b SB_done",
        "nop",
        "SB_orig:",
        "lw a0, 0x18(sp)",
        "jal 0x7060a0",
        "nop",
        "SB_done:",
        "lw ra, 0x1c(sp)",
        "jr ra",
        "addiu sp, sp, 0x20",
    ]
    return L


def main() -> int:
    argv = sys.argv[1:]
    check = "--check" in argv
    args = [a for a in argv if a != "--check"]
    if len(args) != 1:
        raise SystemExit(__doc__)
    path = Path(args[0])
    d = bytearray(path.read_bytes())

    a = struct.unpack_from("<I", d, PATCH_A - VTO)[0]
    b = struct.unpack_from("<I", d, PATCH_B - VTO)[0]
    done = a == (3 << 26 | (SA_VA >> 2)) and b == (3 << 26 | (SB_VA >> 2))

    if check:
        print(f"{PATCH_A:#x} = {a:#010x} ({'хук A' if done else 'сток'}), "
              f"{PATCH_B:#x} = {b:#010x} ({'хук B' if done else 'сток'})")
        print(f"  флаг/стейтмент BSS: {BSS_FLAG:#x} / {BSS_STMT:#x}")
        return 0

    if done:
        print("уже пропатчено (album list context)")
        return 0
    if a != ORIG_A or b != ORIG_B:
        raise SystemExit(f"неожиданные инструкции: {a:#010x} {b:#010x}")

    sa = assemble(SA_VA, stub_a())
    sb = assemble(SB_VA, stub_b())
    sql = SQL + b"\x00"
    end = max(SA_VA + len(sa), SB_VA + len(sb), SQL_VA + len(sql))
    if end > RX_LIMIT:
        raise SystemExit(f"не влезает в RX: {end:#x} > {RX_LIMIT:#x}")
    for va, blob in ((SA_VA, sa), (SB_VA, sb), (SQL_VA, sql)):
        off = va - VTO
        if not all(x == 0 for x in d[off : off + len(blob)]):
            raise SystemExit(f"место {va:#x} занято")

    d[SA_VA - VTO : SA_VA - VTO + len(sa)] = sa
    d[SB_VA - VTO : SB_VA - VTO + len(sb)] = sb
    d[SQL_VA - VTO : SQL_VA - VTO + len(sql)] = sql
    struct.pack_into("<I", d, PATCH_A - VTO, 3 << 26 | (SA_VA >> 2))
    struct.pack_into("<I", d, PATCH_B - VTO, 3 << 26 | (SB_VA >> 2))

    path.write_bytes(bytes(d))
    print(f"{path}: список альбомов разведён (Artists=artist, Album Artist=album_artist)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
