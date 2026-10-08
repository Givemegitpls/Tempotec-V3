#!/usr/bin/env python3
"""Переключатель «треки» в разделе «Исполнитель альбома» (по `album_artist`).

Проблема: Artists и «Исполнитель альбома» делят один вид `vg_listview_album`, а
обработчик кнопки `sub_back_iv_list_type` — `FUN_004c7ba0`. Для этого вида он
строит ключ `artist_all\\<имя>` и открывает `vg_listview_songs_of_artist_all`
(kind 5, `WHERE artist like ?`). Поэтому в «Исполнителе альбома» переключатель
показывал треки по тегу `artist` (у `Дэн Субботин` = 13), а не по `album_artist`
(= 2).

Различие разделов — в префиксе ключа вида `view+0x3de0`: `artist\\<имя>` (Artists)
vs `album_artist\\<имя>` (Исполнитель альбома). Правим обработчик:

1. хук `0x4c7c40` (`jal strlen`) → заглушка в `.text`-пещере `0x419328`;
2. заглушка: если вид `vg_listview_songs_of_an_album_artist` → назад в
   `vg_listview_album`; если вид `vg_listview_album` и ключ начинается с
   `album_artist\\` → открыть `vg_listview_songs_of_an_album_artist` (type 0x63,
   kind 0x21, `WHERE album_artist = ?`) с тем же ключом; иначе — `fallback`
   (воспроизвести `strlen` и вернуться в `0x4c7c48`), т.е. Artists/жанры идут
   прежним путём;
3. кнопка на трек-списке: jump-таблица сборщика панели `0x96429c`, запись idx
   `0x63` @`0x964428`: `0x4c7618` (кнопки нет) → `0x4c74f0` (кнопка есть).

Стандартный шаблон `insert`/`sub_back_iv_list_type` уже умеет рисовать кнопку для
type 0x63 — новый код не нужен. `jal` из `.text` (не RX) — обычный.

Идемпотентно, `--check`. Ставить ПОСЛЕ `exp_artist_toggle`/`exp_album_view`
(зависит от того, что вид раздела — `vg_listview_album`).

    python3 tools/exp_toggle_album_artist.py <hiby_player> [--check]
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

VTO = 0x400000
STUB_VA = 0x419328
HOOK_VA = 0x4C7C40
HOOK_OLD = 0x0C29F5C4          # jal 0xa7d710 (strlen "vg_listview_album")
HOOK_NEW = 3 << 26 | (STUB_VA >> 2)
JT_VA = 0x964428               # jump-таблица панели, idx 0x63 (type songs_of_an_album_artist)
JT_OLD = 0x004C7618            # кнопку НЕ показывает
JT_NEW = 0x004C74F0            # показывает sub_back_iv_list_type

STR_SONGS_AA = 0x00960948      # ASCII "vg_listview_songs_of_an_album_artist"
STR_ALBUM = 0x0095D2A8         # ASCII "vg_listview_album"

V_LIST = "vg_listview_album"

R = {n: i for i, n in enumerate(
    "zero at v0 v1 a0 a1 a2 a3 t0 t1 t2 t3 t4 t5 t6 t7 s0 s1 s2 s3 s4 s5 s6 s7 "
    "t8 t9 k0 k1 gp sp fp ra".split())}


def iw(op: int, rs: str, rt: str, imm: int) -> int:
    return op << 26 | R[rs] << 21 | R[rt] << 16 | (imm & 0xFFFF)


def rw_r(rs: str, rt: str, rd: str) -> int:
    return R[rs] << 21 | R[rt] << 16 | R[rd] << 11 | 0x21  # addu


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

    def branch(op: int, rs: str, rt: str, lbl: str, i: int) -> int:
        delta = pc(loc[lbl]) - pc(i) - 4
        assert delta % 4 == 0 and -0x8000 <= delta // 4 < 0x8000, lbl
        return iw(op, rs, rt, delta // 4)

    out: list[int] = []
    for i, s in enumerate(norm):
        op0 = s.split()[0]
        if op0 in ("lw", "sw", "lbu", "lhu", "sb", "sh"):
            rt, paren = [x.strip() for x in s.split(None, 1)[1].split(",", 1)]
            off, rs = paren.strip().split("(", 1)
            rs = rs.rstrip(")")
            opc = {"lw": 35, "sw": 43, "lbu": 36, "lhu": 37, "sb": 40, "sh": 41}[op0]
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
            out.append(rw_r(a[1], "zero", a[0]))
        elif op in ("beq", "bne"):
            out.append(branch(4 if op == "beq" else 5, a[0], a[1], a[2], i))
        elif op == "b":
            out.append(branch(4, "zero", "zero", a[0], i))
        elif op == "jal":
            tgt = int(a[0], 0)
            assert 0 <= tgt < 0x10000000, a[0]
            out.append(3 << 26 | (tgt >> 2))
        elif op == "jr":
            out.append(R[a[0]] << 21 | 8)
        else:
            raise ValueError(s)
    return b"".join(struct.pack("<I", w) for w in out)


def lui_addiu(reg: str, va: int) -> list[str]:
    lo = va & 0xFFFF
    if lo >= 0x8000:
        lo -= 0x10000
    hi = (va - lo) >> 16
    return [f"lui {reg}, {hi:#x}", f"addiu {reg}, {reg}, {lo:#x}"]


def stub_lines() -> list[str]:
    """$s0 = вид, $s1 = менеджер, $s2 = 0x960000, sp+0x220 = ASCII-имя вида,
    sp+0x18 = буфер ключа (кадр FUN_004c7ba0). sp НЕ меняем."""
    L = [
        # --- reverse: текущий вид == vg_listview_songs_of_an_album_artist ---
        "lui a0, 0x0096", "addiu a0, a0, 0x0948",
        "addiu a1, sp, 0x220",
        "jal 0xa7d840", "nop",              # strcmp
        "beq v0, zero, rev", "nop",
        # --- forward-кандидат: вид == vg_listview_album ---
        "lui a0, 0x0096", "addiu a0, a0, -0x2d58",
        "addiu a1, sp, 0x220",
        "jal 0xa7d840", "nop",
        "bne v0, zero, fallback", "nop",
        # --- ключ начинается с "album_artist\\" ---
        "lw t0, 0x3de0(s0)",
        "lui t1, 0x006c", "ori t1, t1, 0x0061",   # "al"
        "bne t0, t1, fallback", "nop",
        "lw t0, 0x3de4(s0)",
        "lui t1, 0x0075", "ori t1, t1, 0x0062",   # "bu"
        "bne t0, t1, fallback", "nop",
        "lw t0, 0x3de8(s0)",
        "lui t1, 0x005f", "ori t1, t1, 0x006d",   # "m_"
        "bne t0, t1, fallback", "nop",
        # --- forward: копия ключа -> vg_listview_songs_of_an_album_artist ---
        "fwd:",
        "addiu a0, sp, 0x18",
        "addiu a1, s0, 0x3de0",
        "addiu a2, zero, 0x208",
        "jal 0x420f20", "nop",              # FUN_00420f20(keybuf, view+0x3de0, 0x208)
        "move a0, s0",
        "jal 0x4a0400", "nop",              # FUN_004a0400(view)
        "move a0, s1",
        "addiu a1, s2, 0x948",
        "jal 0x4403a0", "nop",              # FUN_004403a0(manager, name)
        "move a0, s1",
        "addiu a1, s2, 0x948",
        "jal 0x43eda0", "nop",              # FUN_0043eda0(manager, name)
        "bne v0, zero, ret1", "nop",
        "move a0, s1",
        "addiu a1, s2, 0x948",
        "addiu a2, sp, 0x18",
        "jal 0x49dfe0", "nop",              # FUN_0049dfe0(manager, name, key)
        "b ret1", "nop",
        # --- reverse: копия ключа -> vg_listview_album ---
        "rev:",
        "addiu a0, sp, 0x18",
        "addiu a1, s0, 0x3de0",
        "addiu a2, zero, 0x208",
        "jal 0x420f20", "nop",
        "move a0, s0",
        "jal 0x4a0400", "nop",
        "move a0, s1",
        "addiu a1, s2, -0x2d58",
        "jal 0x4403a0", "nop",
        "move a0, s1",
        "addiu a1, s2, -0x2d58",
        "jal 0x43eda0", "nop",
        "bne v0, zero, ret1", "nop",
        "move a0, s1",
        "addiu a1, s2, -0x2d58",
        "addiu a2, sp, 0x18",
        "jal 0x49dfe0", "nop",
        # --- return 1 через штатный эпилог FUN_004c7ba0 ---
        "ret1:",
        "lui t0, 0x004c", "addiu t0, t0, 0x7d5c",
        "jr t0", "nop",
        # --- не наш случай: воспроизвести заменённую strlen и вернуться ---
        "fallback:",
        "lui a0, 0x0096", "addiu a0, a0, -0x2d58",
        "jal 0xa7d710", "nop",              # strlen("vg_listview_album")
        "lui t0, 0x004c", "addiu t0, t0, 0x7c48",
        "jr t0", "nop",
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

    code = assemble(STUB_VA, stub_lines())
    hook = struct.unpack_from("<I", d, HOOK_VA - VTO)[0]
    jt = struct.unpack_from("<I", d, JT_VA - VTO)[0]
    stub_ok = bytes(d[STUB_VA - VTO : STUB_VA - VTO + len(code)]) == code
    done = hook == HOOK_NEW and jt == JT_NEW and stub_ok

    if check:
        print(f"{HOOK_VA:#x} = {hook:#010x} ({'хук' if hook == HOOK_NEW else 'сток'})")
        print(f"jump-таблица idx0x63 {JT_VA:#x} = {jt:#010x} "
              f"({'кнопка' if jt == JT_NEW else 'скрыта' if jt == JT_OLD else 'иное'})")
        print(f"заглушка @{STUB_VA:#x}: {'на месте' if stub_ok else 'нет'} ({len(code)} байт)")
        return 0

    if done:
        print("уже пропатчено (toggle album artist)")
        return 0
    if hook != HOOK_OLD:
        raise SystemExit(f"{HOOK_VA:#x}: ожидался {HOOK_OLD:#010x}, найдено {hook:#010x}")
    if jt not in (JT_OLD, JT_NEW):
        raise SystemExit(f"{JT_VA:#x}: ожидался {JT_OLD:#010x}, найдено {jt:#010x}")
    if not all(b == 0 for b in d[STUB_VA - VTO : STUB_VA - VTO + len(code)]):
        raise SystemExit(f"место {STUB_VA:#x} занято")

    d[STUB_VA - VTO : STUB_VA - VTO + len(code)] = code
    struct.pack_into("<I", d, HOOK_VA - VTO, HOOK_NEW)
    struct.pack_into("<I", d, JT_VA - VTO, JT_NEW)

    path.write_bytes(bytes(d))
    print(f"{path}: toggle Album Artist -> stub @{STUB_VA:#x} ({len(code)} байт), "
          f"кнопка type 0x63 включена")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
