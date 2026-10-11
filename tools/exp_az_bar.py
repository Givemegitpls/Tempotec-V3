#!/usr/bin/env python3
"""Полоска A–Z (алфавитный указатель) там, где её нет: «Исполнитель альбома» и «Albums».

Как работает полоска: обработчик списка (`0x4c9078..0x4c90a4`) показывает её,
только если у виджета списка стоит флаг `lg_view+0x1fc != 0`. Ставит флаг
`FUN_0049cca0(view, 1)`, и вызывают её ровно три источника: `FUN_004a73a0`
(All), `FUN_004a8a80` (Artists) и стоковый `FUN_004a95e0` (Albums). Layout менять
не нужно (полоска — общий оверлей `vg_listview_a_z.view`); `view->0x10` — другой
гейт, не наш случай.

Правка 1 — «Исполнитель альбома» (`FUN_004aa160`, pi 62): хук в начале функции,
пещера зовёт `FUN_0049cca0(view,1)` и повторяет исходное тело (36 байт).

Правка 2 — «Albums»: наш патч `exp_cover_kind9col` подменил источник вида
`vg_listview_album` (pi 6, слот `VA 0xABE114`) на kind9 `FUN_004a9180`, и вместе
с этим полоска пропала. Тот же источник обслуживает подсписок «альбомы автора»,
поэтому флаг ставится по ключу вида: слот переводится на пещеру, которая зовёт
`FUN_004627e0(a0)` (вид), сверяет wide-ключ `view+0x3de0` с `"album"` (приём из
рабочего стуба переключателя `exp_artist_toggle`) и только для категории
«Albums» ставит флаг, после чего уходит в оригинальный `FUN_004a9180`.
Список «Albums» при этом берётся из `ALBUM_TABLE` (ветка ключа `album` в
`FUN_0070b020`), а таблица собирается нашим DB-фиксом в порядке `character` —
поэтому прыжки по буквам совпадают.

Правка 3 (обязательна для правки 1) — позиционный запрос прыжка по букве для
ключа `album_artist` (`0x9b99f4`): в подзапросе стоит `ALBUM_TABLE`, где колонки
`album_artist` НЕТ, и SQLite привязывает её к внешней таблице → счёт неверный
(на копии реальной БД 2 вместо 7). Строка длиннее на 7 байт, поэтому
исправленный вариант пишется в RX-пещеру, а пара `lui/addiu` переписывается
(`0x7066f4` — delay-слот `beql`, `0x706744` — delay-слот `jal sprintf`).

Правка 4 — прыжок в «Albums». Обработчик прыжка `FUN_00703320` сравнивает ключ
вида с `album` / `artist` / `album_artist` / `all` и при несовпадении возвращает
-1 (прыжка нет). Вид «Albums» после подмены источника (правка 2) отдаёт тапу
ключ, который ни с одним из них не совпадает (проверено на устройстве:
диагностика «неизвестный ключ → ветка album» включает прыжки). Поэтому ветка
«ключ не `all`» (`0x703634`, обычные буквы) направляется не в возврат -1, а в
ветку `album` (там уже нужные statement'ы `ALBUM_TABLE`, они же используются и
для `#`-пути, который работает и без правки).

Использование:
    python3 tools/exp_az_bar.py <hiby_player> [--check]
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

VTO = 0x400000
VTO_RW = 0x410000               # RW-сегмент (>= 0xa8f000): другой сдвиг

# --- 1. «Исполнитель альбома»: хук источника -----------------------------------
HOOK_VA = 0x4AA160                      # FUN_004aa160 (pi 62, vg_listview_album_artist)
HOOK_ORIG = 0x27BDFFD8                  # addiu sp, sp, -0x28
CAVE_VA = 0xA7E5A0                      # RX-пещера (свободно: 0xa7e557..0xa7e800)
STR_VA = 0xA7E600                       # исправленный позиционный запрос

F_SET_BAR = 0x0049CCA0                  # FUN_0049cca0(view, 1) -> lg_view+0x1fc = 1
F_SOURCE = 0x004A1BA0                   # FUN_004a1ba0(...) — исходный источник

# --- 2. «Albums»: подмена источника вида pi 6 ----------------------------------
SLOT_VA = 0xABE114                      # класс pi 6 (vg_listview_album): источник
SLOT_ORIG = 0x004A9180                  # kind9-источник (exp_cover_kind9col)
CAVE2_VA = 0xA7E680                     # RX-пещера под ключ-чек
F_VIEW_OF = 0x004627E0                  # FUN_004627e0(widget) -> view
F_SOURCE_ALBUM = 0x004A9180             # оригинальный источник (tail-переход)
F_LIST_MODE = 0x0049CC40                # FUN_0049cc40(k) — режим списка
F_SET_MODE = 0x0049CB80                 # FUN_0049cb80(k, v) — регистрация режима (+FUN_007024e0)
RX_FREE_END = 0xA7E800                  # здесь начинается шаблон exp_coverpath_combo

# --- 3. позиционный запрос album_artist ---------------------------------------
LUI_HI_VA = 0x7066F4                    # lui a1, 0x9c   (delay-слот beql -> 0x70673c)
LUI_HI_ORIG = 0x3C05009C
LUI_HI_NEW = 0x3C0500A8                 # lui a1, 0xa8
ADDIU_LO_VA = 0x706744                  # addiu a1, a1, -0x660c  (delay-слот jal sprintf)
ADDIU_LO_ORIG = 0x24A599F4
ADDIU_LO_NEW = 0x24A5E600               # addiu a1, a1, -0x1a00 -> 0xa7e600

SQL_BAD = (b"SELECT count(id) FROM ALBUM_ARTIST_TABLE WHERE rowid < "
           b"(SELECT rowid FROM ALBUM_TABLE WHERE album_artist like ?)")
SQL_FIX = (b"SELECT count(id) FROM ALBUM_ARTIST_TABLE WHERE rowid < "
           b"(SELECT rowid FROM ALBUM_ARTIST_TABLE WHERE album_artist like ?)")
SQL_BAD_VA = 0x9B99F4

# --- 4. прыжок в «Albums»: нераспознанный ключ тапа → ветка album --------------
TAP_KEY_VA = 0x703634                   # bnez v0, <return -1> (ветка «ключ не all»)
TAP_KEY_ORIG = 0x14400018               # bnez v0, 0x703698 (возврат -1)
TAP_KEY_NEW = 0x1440FF69                # bnez v0, 0x7033dc (ветка key == "album")

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


def call_jalr(reg: str, target: int, delay: str = "nop") -> list[str]:
    """Из RX-пещеры `jal`/`j` уходят не туда (верхний ниббл PC) — только `jalr`."""
    return lui_addiu(reg, target) + [f"jalr {reg}", delay]


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
        if delta % 4 or not (-32768 <= delta // 4 <= 32767):
            raise ValueError(f"ветвление вне диапазона: {lbl}")
        return iw(op, rs, rt, delta // 4)

    out = []
    for i, s in enumerate(norm):
        op0 = s.split()[0]
        if op0 in ("lw", "lbu", "sb", "sw"):
            rt, paren = [x.strip() for x in s.split(None, 1)[1].split(",", 1)]
            off, rs = paren.strip().split("(", 1)
            rs = rs.rstrip(")")
            off = off.strip() or "0"
            opc = {"lw": 35, "lbu": 36, "sb": 40, "sw": 43}
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
        elif op == "ori":
            rt, rs, imm = a
            out.append(iw(13, rs, rt, int(imm, 0)))
        elif op == "move":
            rd, rs = a
            out.append(rw(rs, "zero", rd, 0x25))
        elif op == "jalr":
            out.append(rw(a[0], "zero", "ra", 0x09))
        elif op == "jr":
            out.append(rw(a[0], "zero", "zero", 0x08))
        elif op in ("beq", "bne"):
            out.append(branch(4 if op == "beq" else 5, a[0], a[1], a[2], i))
        else:
            raise ValueError(s)
    return b"".join(struct.pack("<I", w) for w in out)


def cave_album_artist() -> list[str]:
    """Повторяет тело FUN_004aa160, но перед вызовом источника ставит флаг полоски.

    Исходное тело (36 байт):
        addiu sp, sp, -0x28 ; sw a3, 0x10(sp) ; lui a3, 0x96 ; sw ra, 0x24(sp)
        jal 0x4a1ba0 ; addiu a3, a3, 0xb30 ; lw ra, 0x24(sp) ; jr ra ; addiu sp, sp, 0x28
    a3 — 4-й аргумент (wide-ключ L"album_artist" = 0x960b30); оригинальный a3
    уезжает в стек как 5-й аргумент.
    """
    L: list[str] = [
        "AZ:",
        "addiu sp, sp, -0x28",
        "sw a3, 0x10(sp)",          # 5-й аргумент источника (как в оригинале)
        "sw ra, 0x24(sp)",
        "sw a0, 0x14(sp)",          # вид — нужен и для флага, и для источника
        "sw a1, 0x18(sp)",
        "sw a2, 0x1c(sp)",
        "addiu a1, zero, 1",
    ]
    L += call_jalr("t9", F_SET_BAR)          # FUN_0049cca0(view, 1)
    L += [
        "lw a2, 0x1c(sp)",
        "lw a1, 0x18(sp)",
        "lw a0, 0x14(sp)",
        "lui a3, 0x96",
    ]
    L += call_jalr("t9", F_SOURCE, "addiu a3, a3, 0xb30")   # FUN_004a1ba0(..., L"album_artist")
    L += [
        "lw ra, 0x24(sp)",
        "jr ra",
        "addiu sp, sp, 0x28",
    ]
    return L


def cave_albums() -> list[str]:
    """Ставит флаг полоски только категории «Albums» (ключ вида == "album").

    Вызывается вместо источника `FUN_004a9180` (слот pi 6). Ключ вида —
    wide-строка `view+0x3de0` (тот же приём, что в стубе `exp_artist_toggle`).
    Подсписки (`artist\\…`, `album_artist\\…`) флаг не получают. В конце —
    tail-переход в оригинальный источник.

    Для категории «Albums» повторяется стоковая прелюдия источника
    `FUN_004a95e0`: `v = FUN_0049cc40(2)` (режим списка), при `v == 0` —
    `FUN_0049cca0(view,1)` (флаг полоски), затем `FUN_0049cb80(2, v)`
    (регистрация режима; внутри — `FUN_007024e0`). Без `FUN_0049cb80` полоска
    рисуется, но прыжок по букве не срабатывает.
    """
    L: list[str] = [
        "AZAL:",
        "addiu sp, sp, -0x28",
        "sw ra, 0x24(sp)",
        "sw a0, 0x18(sp)",
        "sw a1, 0x14(sp)",
        "sw a2, 0x10(sp)",
        "sw a3, 0x0c(sp)",
    ]
    L += call_jalr("t9", F_VIEW_OF)          # v0 = FUN_004627e0(a0) — вид
    L += [
        "beq v0, zero, AZAL_skip",
        "nop",
        "lw t0, 0x3de0(v0)",                 # wide-ключ вида
        "lui t1, 0x006c",
        "ori t1, t1, 0x0061",                # 0x006c0061 = wide "al"
        "bne t0, t1, AZAL_skip",
        "nop",
        "lw t0, 0x3de4(v0)",
        "lui t1, 0x0075",
        "ori t1, t1, 0x0062",                # 0x00750062 = wide "bu"
        "bne t0, t1, AZAL_skip",
        "nop",
        "lw t0, 0x3de8(v0)",
        "ori t1, zero, 0x006d",              # 0x0000006d = wide "m\\0"
        "bne t0, t1, AZAL_skip",
        "nop",
        # стоковая прелюдия источника «Albums» (FUN_004a95e0)
        "addiu a0, zero, 2",                 # ключ режима списка (как в стоке)
    ]
    L += call_jalr("t9", F_LIST_MODE)        # v0 = FUN_0049cc40(2)
    L += [
        "sw v0, 0x20(sp)",
        "bne v0, zero, AZAL_noflag",
        "nop",
        "lw a0, 0x18(sp)",
        "addiu a1, zero, 1",
    ]
    L += call_jalr("t9", F_SET_BAR)          # FUN_0049cca0(view, 1)
    L += [
        "AZAL_noflag:",
        "addiu a0, zero, 2",
        "lw a1, 0x20(sp)",
    ]
    L += call_jalr("t9", F_SET_MODE)         # FUN_0049cb80(2, режим)
    L += [
        "AZAL_skip:",
        "lw a3, 0x0c(sp)",
        "lw a2, 0x10(sp)",
        "lw a1, 0x14(sp)",
        "lw a0, 0x18(sp)",
        "lw ra, 0x24(sp)",
        "addiu sp, sp, 0x28",
    ]
    L += lui_addiu("t9", F_SOURCE_ALBUM)     # tail-переход: только jr, ra уже восстановлен
    L += ["jr t9", "nop"]
    return L


def main() -> int:
    argv = sys.argv[1:]
    check = "--check" in argv
    args = [a for a in argv if a != "--check"]
    if len(args) != 1:
        raise SystemExit(__doc__)
    path = Path(args[0])
    d = bytearray(path.read_bytes())

    code = assemble(CAVE_VA, cave_album_artist())
    hook = 2 << 26 | (CAVE_VA >> 2)          # j CAVE_VA (PC 0x4aa160: верхний ниббл 0)
    sql = SQL_FIX + b"\x00"
    code2 = assemble(CAVE2_VA, cave_albums())

    cur_hook = struct.unpack_from("<I", d, HOOK_VA - VTO)[0]
    cur_lui = struct.unpack_from("<I", d, LUI_HI_VA - VTO)[0]
    cur_addiu = struct.unpack_from("<I", d, ADDIU_LO_VA - VTO)[0]
    cur_sql = bytes(d[STR_VA - VTO:STR_VA - VTO + len(sql)])
    cur_slot = struct.unpack_from("<I", d, SLOT_VA - VTO_RW)[0]
    cur_tap = struct.unpack_from("<I", d, TAP_KEY_VA - VTO)[0]

    done_aa = (cur_hook == hook and cur_lui == LUI_HI_NEW
               and cur_addiu == ADDIU_LO_NEW and cur_sql == sql)
    cur_code2 = bytes(d[CAVE2_VA - VTO:CAVE2_VA - VTO + len(code2)])
    done_alb = cur_slot == CAVE2_VA and cur_code2 == code2
    done_tap = cur_tap == TAP_KEY_NEW

    if check:
        print(f"  [{('применён' if done_aa else 'не применён')}] полоска A–Z у Album Artist")
        print(f"    хук {HOOK_VA:#x} = {cur_hook:#010x} (ожидается {hook:#010x})")
        print(f"    {LUI_HI_VA:#x} = {cur_lui:#010x} ({'ок' if cur_lui == LUI_HI_NEW else 'сток'})")
        print(f"    {ADDIU_LO_VA:#x} = {cur_addiu:#010x} "
              f"({'ок' if cur_addiu == ADDIU_LO_NEW else 'сток'})")
        print(f"    запрос @ {STR_VA:#x}: {'исправлен' if cur_sql == sql else 'нет'} "
              f"(стоковая строка @ {SQL_BAD_VA:#x})")
        print(f"  [{('применён' if done_alb else 'не применён')}] полоска A–Z у Albums")
        print(f"    слот pi 6 {SLOT_VA:#x} = {cur_slot:#010x} "
              f"(ожидается {CAVE2_VA:#010x}, до правки {SLOT_ORIG:#010x})")
        print(f"  [{('применён' if done_tap else 'не применён')}] прыжок в Albums "
              f"(нераспознанный ключ тапа -> ветка album)")
        print(f"    {TAP_KEY_VA:#x} = {cur_tap:#010x} "
              f"(ожидается {TAP_KEY_NEW:#010x}, сток {TAP_KEY_ORIG:#010x})")
        print(f"{path}: полоска A–Z (Album Artist + Albums)")
        return 0

    if done_aa and done_alb and done_tap:
        print("уже пропатчено (полоска A–Z)")
        return 0

    # --- правка 1+3 (Album Artist + запрос) ---
    if not done_aa:
        if cur_hook != HOOK_ORIG:
            raise SystemExit(f"{HOOK_VA:#x}: ожидался {HOOK_ORIG:#010x}, найдено {cur_hook:#010x}")
        if cur_lui != LUI_HI_ORIG:
            raise SystemExit(f"{LUI_HI_VA:#x}: ожидался {LUI_HI_ORIG:#010x}, "
                             f"найдено {cur_lui:#010x}")
        if cur_addiu != ADDIU_LO_ORIG:
            raise SystemExit(f"{ADDIU_LO_VA:#x}: ожидался {ADDIU_LO_ORIG:#010x}, "
                             f"найдено {cur_addiu:#010x}")
        stock_sql = bytes(d[SQL_BAD_VA - VTO:SQL_BAD_VA - VTO + len(SQL_BAD) + 1])
        if stock_sql[:len(SQL_BAD)] != SQL_BAD:
            raise SystemExit(f"стоковая строка @ {SQL_BAD_VA:#x} не совпала: {stock_sql[:40]!r}")
        if len(sql) > len(SQL_BAD) + 8:
            raise SystemExit("исправленный запрос неожиданно длинный")
        taken = bytes(d[STR_VA - VTO:STR_VA - VTO + len(sql)])
        if taken != bytes(len(sql)):
            raise SystemExit(f"{STR_VA:#x} занято: {taken[:24]!r}")
        if CAVE_VA + len(code) > STR_VA:
            raise SystemExit(f"пещера перекрывает строку: {CAVE_VA + len(code):#x} > {STR_VA:#x}")

        d[CAVE_VA - VTO:CAVE_VA - VTO + len(code)] = code
        struct.pack_into("<I", d, HOOK_VA - VTO, hook)
        struct.pack_into("<I", d, HOOK_VA - VTO + 4, 0)      # delay-слот: nop
        struct.pack_into("<I", d, LUI_HI_VA - VTO, LUI_HI_NEW)
        struct.pack_into("<I", d, ADDIU_LO_VA - VTO, ADDIU_LO_NEW)
        d[STR_VA - VTO:STR_VA - VTO + len(sql)] = sql
        print(f"  [ok] Album Artist: хук {HOOK_VA:#x} -> пещера {CAVE_VA:#x} "
              f"({len(code)} байт), запрос @ {STR_VA:#x}")

    # --- правка 2 (Albums) ---
    if not done_alb:
        if STR_VA + len(sql) > CAVE2_VA:
            raise SystemExit(f"строка перекрывает пещеру 2: "
                             f"{STR_VA + len(sql):#x} > {CAVE2_VA:#x}")
        if CAVE2_VA + len(code2) > RX_FREE_END:
            raise SystemExit(f"пещера 2 вышла за свободную зону: "
                             f"{CAVE2_VA + len(code2):#x} > {RX_FREE_END:#x}")
        if cur_slot == CAVE2_VA:
            # слот уже ведёт в пещеру, но код устарел — перезаписываем
            d[CAVE2_VA - VTO:CAVE2_VA - VTO + len(code2)] = code2
            print(f"  [ok] Albums: пещера {CAVE2_VA:#x} обновлена ({len(code2)} байт)")
        else:
            if cur_slot != SLOT_ORIG:
                raise SystemExit(f"слот pi 6 {SLOT_VA:#x}: ожидался {SLOT_ORIG:#010x}, "
                                 f"найдено {cur_slot:#010x}")
            taken2 = bytes(d[CAVE2_VA - VTO:CAVE2_VA - VTO + len(code2)])
            if taken2 != bytes(len(code2)):
                raise SystemExit(f"{CAVE2_VA:#x} занято: {taken2[:24]!r}")
            d[CAVE2_VA - VTO:CAVE2_VA - VTO + len(code2)] = code2
            struct.pack_into("<I", d, SLOT_VA - VTO_RW, CAVE2_VA)
            print(f"  [ok] Albums: слот pi 6 {SLOT_VA:#x} -> пещера {CAVE2_VA:#x} "
                  f"({len(code2)} байт, ключ-чек \"album\")")

    # --- правка 4 (прыжок в Albums) ---
    if not done_tap:
        if cur_tap != TAP_KEY_ORIG:
            raise SystemExit(f"{TAP_KEY_VA:#x}: ожидался {TAP_KEY_ORIG:#010x}, "
                             f"найдено {cur_tap:#010x}")
        struct.pack_into("<I", d, TAP_KEY_VA - VTO, TAP_KEY_NEW)
        print(f"  [ok] Albums: прыжок — нераспознанный ключ тапа -> ветка album "
              f"({TAP_KEY_VA:#x}: {TAP_KEY_ORIG:#010x} -> {TAP_KEY_NEW:#010x})")

    path.write_bytes(bytes(d))
    print(f"{path}: полоска A–Z (Album Artist + Albums)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
