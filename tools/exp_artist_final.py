#!/usr/bin/env python3
r"""Финальная интеграция «альбомы артиста» с обложками (подменённый вид).

Состав (база = fw/SYSTEM/usr/bin/hiby_player, уже с patch_player + patch_sql,
затем exp_album_view + exp_flags_view21, потом ЭТОТ скрипт):

1. Слот источника данных kind2 VA 0xABE114 (file 0x6AE114): 0x4a95e0 → 0x4a9dc0
   (kind5-сборщик; обложки per-album, путь из col1 — ветка D9/diag7b).
2. Хук тайтла строки (family0), jal @0x4a3d14 → RX 0xa7e48c:
   тайтл = rec+0x42c (col3=album) при (param_1+0x40 == 4 [класс «album»]) И
   col3 непуст; иначе сток (rec+0x20c). Проверка type исключает Files
   (EXPLORER type=2 / MAIN_EXPLORER type=1) — тайтл остаётся стоковым
   (дефект «Files = unknown» diag7b).
3. Хук клика: jal @0x4a7560 (= jal FUN_0049d6e0 в FUN_004a7500) → RX 0xa7e510,
   delay @0x4a7564 addiu a1,sp,0x224 → addiu a1,sp,0x18 (base rec).
   Хук: если корневой вид s0+0x423c == 0x4a9dc0 (наш источник) И rec+0x42c
   непуст → ключ нового вида «album\<col3>» (имя альбома), иначе сток (col2).
4. Дедup: case 5 ветки FUN_00708d20, три пары lui/addiu → один RX-набор:
     main (=0) 0x9BA000  ← 0x708dfc(lui a1)/0x708e08(addiu) → RX T
     ck   (=2) 0x9BB15C  ← 0x708df4(lui v0)/0x708df8(addiu) → RX D
     cue  (=1) 0x9BB2C0  ← 0x708e04(lui v0)/0x708e14(addiu) → RX D
   T = стоковый layout колонок +
   WHERE rowid IN (SELECT MIN(rowid) ... GROUP BY album) (форма D12, безопасна
   на устройстве; GROUP BY в SELECT-списке diag10 — НЕ использовать).
   D = пустая вставка («... WHERE artist like ? AND 0»), ? сохранён для bind.
   Дубликаты носят смешение трёх веток; теперь таблица наполняется ОДНОЙ
   dedup-веткой.
   Пересборка списка происходит при первом открытии вида после «обновления
   медиатеки»/очистки list_tb_* — правка действует на новую сборку.
5. phdr2 filesz/memsz → 0x67f000.

RX-карта (зазор 0xa7e370..0xa7f000):
  0xa7e48c HOOK0   (тайтл family0; family1 НЕ трогаем — сток, как в diag7b)
  0xa7e510 HOOKCLICK
  0xa7e580 T (SQL строка)
  0xa7e780 D (SQL строка)

Использование:
    python3 tools/exp_artist_final.py <hiby_player> [--check]
"""
from __future__ import annotations

import hashlib
import struct
import sys
from pathlib import Path

VTO = 0x400000

# --- слот kind2 (RW: файловый оффсет = VA − 0x410000, см. notes 2026-10-05) ---
SLOT_VA = 0xABE114
SLOT_OFF = 0x6AE114
SLOT_OLD = 0x4A95E0
SLOT_NEW = 0x4A9DC0

# --- тайтл (family0) ---
HOOK0_VA = 0xA7E48C
PATCH0_VA = 0x4A3D14
PATCH0_ORIG = 0x2610020C            # addiu s0, s0, 0x20c

# --- клик ---
HOOKCLICK_VA = 0xA7E510
CLICK_JAL_VA = 0x4A7560
CLICK_JAL_ORIG = 0x0C1275B8         # jal 0x49d6e0
CLICK_DELAY_VA = 0x4A7564
CLICK_DELAY_ORIG = 0x27A50224       # addiu a1, sp, 0x224
CLICK_DELAY_NEW = 0x27A50018        # addiu a1, sp, 0x18

# --- SQL-пары case 5 ---
SQL_MAIN_LUI_VA = 0x708DFC
SQL_MAIN_LUI_ORIG = 0x3C05009C      # lui  a1, 0x9c
SQL_MAIN_ADDIU_VA = 0x708E08
SQL_MAIN_ADDIU_ORIG = 0x24A5A000    # addiu a1, a1, -0x6000  (=0x9BA000)
SQL_CK_LUI_VA = 0x708DF4
SQL_CK_LUI_ORIG = 0x3C02009C        # lui  v0, 0x9c
SQL_CK_ADDIU_VA = 0x708DF8
SQL_CK_ADDIU_ORIG = 0x2442B15C      # addiu v0, v0, -0x4ea4 (=0x9BB15C)
SQL_CUE_LUI_VA = 0x708E04
SQL_CUE_LUI_ORIG = 0x3C02009C       # lui  v0, 0x9c
SQL_CUE_ADDIU_VA = 0x708E14
SQL_CUE_ADDIU_ORIG = 0x2442B2C0     # addiu v0, v0, -0x4d40 (=0x9BB2C0)

# RX адреса строк (вычисляются после сборки кода; уложиться до 0xa7f000)
T_VA = 0xA7E580
D_VA = 0xA7E780
RX_END_MAX = 0xA7EF60

LUI_A1_T = (15 << 26) | (5 << 16) | ((T_VA >> 16) & 0xFFFF)
ADDIU_A1_T = (9 << 26) | (5 << 21) | (5 << 16) | (T_VA & 0xFFFF)
LUI_V0_D = (15 << 26) | (2 << 16) | ((D_VA >> 16) & 0xFFFF)
ADDIU_V0_D = (9 << 26) | (2 << 21) | (2 << 16) | (D_VA & 0xFFFF)

PHDR_FILESZ = 0x67E370
PHDR_NEW = 0x67F000

T_SQL = (
    "INSERT INTO %s%d SELECT id,path,name,album,artist,genre,year,dis_id,ck_id,"
    "has_child_file,begin_time,end_time,cue_id,character,size,sample_rate,"
    "bit_rate,bit,channel,format,quality,album_pic_path,lrc_path,track_gain,"
    "track_peak,ctime,mtime FROM MEDIA_TABLE WHERE rowid IN (SELECT MIN(rowid) "
    "FROM MEDIA_TABLE WHERE artist like ? AND has_child_file IN (0,1,2) "
    "GROUP BY album) ORDER BY 4,name        "
)

D_SQL = "INSERT INTO %s%d SELECT id FROM MEDIA_TABLE WHERE artist like ? AND 0        "

# --- мини-ассемблер (копия exp_cover_title_album.py + lhu/move через addiu) ---
R = {n: i for i, n in enumerate(
    "zero at v0 v1 a0 a1 a2 a3 t0 t1 t2 t3 t4 t5 t6 t7 s0 s1 s2 s3 s4 s5 s6 s7 "
    "t8 t9 k0 k1 gp sp fp ra".split())}


def _asm(base_va: int, lines: list[str]) -> bytes:
    norm = []
    loc = {}
    for line in lines:
        s = line.split("#")[0].strip()
        if not s:
            continue
        if s.endswith(":"):
            assert s[:-1] not in loc
            loc[s[:-1]] = len(norm)
            continue
        norm.append(s)

    def pc_of(i: int, lbl: str) -> int:
        return base_va + loc[lbl] * 4
    words = []
    for i, s in enumerate(norm):
        p = s.replace(",", " ").split()
        op = p[0]

        def pc() -> int:
            return base_va + i * 4
        if op == "nop":
            words.append(0)
        elif op in ("lw", "lbu", "lhu", "sw"):
            rt, paren = p[1], p[2]
            off, rs = paren.split("(", 1)
            rs = rs.rstrip(")")
            off = off.strip() or "0"
            opc = {"lw": 35, "lbu": 36, "lhu": 33, "sw": 43}[op]
            words.append(opc << 26 | R[rs] << 21 | R[rt] << 16 | (int(off, 0) & 0xFFFF))
        elif op in ("addiu", "move"):
            if op == "move":
                rt, rs = p[1], p[2]
                imm = 0
            else:
                rt, rs, imm = p[1], p[2], int(p[3], 0)
            words.append(9 << 26 | R[rs] << 21 | R[rt] << 16 | (imm & 0xFFFF))
        elif op == "lui":
            rt, imm = p[1], int(p[2], 0)
            words.append(15 << 26 | R["zero"] << 21 | R[rt] << 16 | (imm & 0xFFFF))
        elif op == "ori":
            rs, rt, imm = p[1], p[2], int(p[3], 0)
            words.append(13 << 26 | R[rs] << 21 | R[rt] << 16 | (imm & 0xFFFF))
        elif op in ("beq", "bne"):
            rs, rt, lbl = p[1], p[2], p[3]
            delta = (pc_of(i, lbl) - pc() - 4) // 4
            assert -32768 <= delta <= 32767
            words.append((4 if op == "beq" else 5) << 26 | R[rs] << 21 | R[rt] << 16 | (delta & 0xFFFF))
        elif op == "b":
            delta = (pc_of(i, p[1]) - pc() - 4) // 4
            words.append(4 << 26 | (delta & 0xFFFF))
        elif op == "jr":
            words.append(R[p[1]] << 21 | 8)
        elif op == "jal":
            t = loc[p[1]] * 4 + base_va if p[1] in loc else int(p[1], 0)
            words.append(3 << 26 | (t >> 2))
        else:
            raise ValueError(s)
    return b"".join(struct.pack("<I", w) for w in words)


def hook0_lines() -> list[str]:
    """тайтл family0: view=$v1 (param_1), rec=$s0, out=$v0; delay sw $s0,(v0)
    уже отработал на stoke — хук перезаписывает значение."""
    yes, stk, swx = "yes", "stk", "swx"
    L: list[str] = []
    A = L.append
    A("lw t0, 0x40(v1)")          # type класса (диагностика diag4: чтение безопасно)
    A("addiu t1, zero, 4")
    A("bne t0, t1, " + stk)
    A("nop")
    A("lhu t0, 0x42c(s0)")        # первый wide-символ col3
    A("beq t0, zero, " + stk)
    A("nop")
    A("addiu t0, s0, 0x42c")
    A(yes + ":")
    A("b " + swx)
    A("nop")
    A(stk + ":")
    A("addiu t0, s0, 0x20c")
    A(swx + ":")
    A("sw t0, (v0)")
    A("jr ra")
    A("nop")
    return L


def click_lines() -> list[str]:
    """клик: s0 = корневой вид, a1 = base rec (из delay), a0 = буфер ключа."""
    stk, swx = "stk", "swx"
    L: list[str] = []
    A = L.append
    A("lw t0, 0x423c(s0)")
    A("lui t1, 0x4a")
    A("ori t1, t1, 0x9dc0")
    A("bne t0, t1, " + stk)
    A("nop")
    A("lhu t0, 0x42c(a1)")
    A("beq t0, zero, " + stk)
    A("nop")
    A("addiu t0, a1, 0x42c")
    A("b " + swx)
    A("nop")
    A(stk + ":")
    A("addiu t0, a1, 0x20c")
    A(swx + ":")
    A("move a1, t0")
    A("jal 0x49d6e0")
    A("nop")
    A("jr ra")
    A("nop")
    return L


def find_phdr2(d: bytes) -> int:
    phoff = struct.unpack_from("<I", d, 28)[0]
    es, n = struct.unpack_from("<HH", d, 42)
    for i in range(n):
        ph = phoff + i * es
        if struct.unpack_from("<I", d, ph)[0] == 1 and \
           struct.unpack_from("<I", d, ph + 16)[0] in (PHDR_FILESZ, PHDR_NEW):
            return ph
    raise SystemExit("phdr2 не найден")


def put(d: bytearray, va: int, data: bytes, what: str) -> None:
    off = va - VTO
    cur = bytes(d[off : off + len(data)])
    if cur == data:
        print(f"  [skip] {what} {va:#x} уже на месте")
        return
    if any(cur):
        raise SystemExit(f"{what}: RX-зона {va:#x} занята")
    d[off : off + len(data)] = data
    print(f"  [ok] {what} {va:#x}..{va + len(data):#x}")


def word(d: bytearray, va: int, orig: int, new: int, what: str) -> None:
    off = va - VTO
    cur = struct.unpack_from("<I", d, off)[0]
    if cur == new:
        print(f"  [skip] {what} {va:#x}")
        return
    if cur != orig:
        raise SystemExit(f"{va:#x}: неожиданное слово {cur:#010x} (ожидалось {orig:#010x})")
    struct.pack_into("<I", d, off, new)
    print(f"  [ok] {what} {va:#x}")


def main() -> int:
    argv = sys.argv[1:]
    check = "--check" in argv
    skip_sql = "--skip-sql" in argv
    skip_click = "--skip-click" in argv
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 1:
        raise SystemExit(__doc__)
    path = Path(args[0])
    d = bytearray(path.read_bytes())

    hook0 = _asm(HOOK0_VA, hook0_lines())
    click = _asm(HOOKCLICK_VA, click_lines()) if not skip_click else b""
    assert HOOK0_VA + len(hook0) <= HOOKCLICK_VA, "HOOK0 перекрывает HOOKCLICK"

    t_sql = T_SQL.encode() + b"\0"
    d_sql = D_SQL.encode() + b"\0"
    assert T_VA + len(t_sql) <= D_VA and D_VA + len(d_sql) <= RX_END_MAX, \
        f"RX-строки не помещаются: T до {T_VA + len(t_sql):#x}, D до {D_VA + len(d_sql):#x}"

    slot = struct.unpack_from("<I", d, SLOT_OFF)[0]
    checks = [
        (PATCH0_VA, PATCH0_ORIG, "title-jal"),
        (SQL_MAIN_LUI_VA, SQL_MAIN_LUI_ORIG, "sql-main-lui"),
        (SQL_MAIN_ADDIU_VA, SQL_MAIN_ADDIU_ORIG, "sql-main-addiu"),
        (SQL_CK_LUI_VA, SQL_CK_LUI_ORIG, "sql-ck-lui"),
        (SQL_CK_ADDIU_VA, SQL_CK_ADDIU_ORIG, "sql-ck-addiu"),
        (SQL_CUE_LUI_VA, SQL_CUE_LUI_ORIG, "sql-cue-lui"),
        (SQL_CUE_ADDIU_VA, SQL_CUE_ADDIU_ORIG, "sql-cue-addiu"),
    ]
    if not skip_click:
        checks.insert(1, (CLICK_JAL_VA, CLICK_JAL_ORIG, "click-jal"))
        checks.insert(2, (CLICK_DELAY_VA, CLICK_DELAY_ORIG, "click-delay"))
    if skip_sql:
        checks = [c for c in checks if not c[2].startswith("sql-")]

    if check:
        print(f"слот {SLOT_VA:#x} = {slot:#x} ({'kind5' if slot == SLOT_NEW else 'сток/иное'})")
        for va, orig, name in checks:
            cur = struct.unpack_from("<I", d, va - VTO)[0]
            print(f"  {name} {va:#x}: {cur:#010x} ({'запатчено' if cur == _NEW(va) else ('сток' if cur == orig else 'ЧУЖОЕ')})")
        ph = find_phdr2(d)
        print(f"phdr2 filesz = {struct.unpack_from('<I', d, ph + 16)[0]:#x}")
        return 0

    put(d, HOOK0_VA, hook0, "HOOK0")
    if click:
        put(d, HOOKCLICK_VA, click, "HOOKCLICK")
    if not skip_sql:
        put(d, T_VA, t_sql, "SQL-T")
        put(d, D_VA, d_sql, "SQL-D")

    if slot != SLOT_NEW:
        if slot != SLOT_OLD:
            raise SystemExit(f"неожиданный слот {slot:#x}")
        struct.pack_into("<I", d, SLOT_OFF, SLOT_NEW)
        print(f"слот {SLOT_VA:#x}: {SLOT_OLD:#x} → {SLOT_NEW:#x}")
    else:
        print(f"слот {SLOT_VA:#x} уже {SLOT_NEW:#x}")

    for va, orig, name in checks:
        word(d, va, orig, _NEW(va), name)

    ph = find_phdr2(d)
    if struct.unpack_from("<I", d, ph + 16)[0] == PHDR_FILESZ:
        struct.pack_into("<I", d, ph + 16, PHDR_NEW)
        struct.pack_into("<I", d, ph + 20, PHDR_NEW)
        print("phdr2 → 0x67f000")
    else:
        print("phdr2 уже расширен")

    path.write_bytes(bytes(d))
    print(f"{path}: записано; md5 {hashlib.md5(bytes(d)).hexdigest()}")
    return 0


def _NEW(va: int) -> int:
    table = {
        PATCH0_VA: 3 << 26 | HOOK0_VA >> 2,
        CLICK_JAL_VA: 3 << 26 | HOOKCLICK_VA >> 2,
        CLICK_DELAY_VA: CLICK_DELAY_NEW,
        SQL_MAIN_LUI_VA: LUI_A1_T,
        SQL_MAIN_ADDIU_VA: ADDIU_A1_T,
        SQL_CK_LUI_VA: LUI_V0_D,
        SQL_CK_ADDIU_VA: ADDIU_V0_D,
        SQL_CUE_LUI_VA: LUI_V0_D,
        SQL_CUE_ADDIU_VA: ADDIU_V0_D,
    }
    return table[va]


if __name__ == "__main__":
    raise SystemExit(main())
