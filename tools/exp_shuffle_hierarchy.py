#!/usr/bin/env python3
"""Переход «альбом → следующий альбом того же автора» (без своего SQL).

Задача: после завершения альбома включать следующий альбом ТОГО ЖЕ автора
(для «Artists» — по тегу `artist`, для «Исполнителя альбома» — по `album_artist`),
а не следующий по глобальному `ALBUM_TABLE` (как делает штатный `FUN_004eae80`).

Почему не SQL в хуке: подготовка/биндинг запроса из своего кода в потоке
завершения трека не срабатывают. Поэтому используем ШТАТНУЮ
`FUN_004369a0(key, idx, rec)` — её же зовёт сам `FUN_004eae80` в этом контексте:
она читает строки `list_tb_N` (список альбомов автора, построенный при открытии
раздела).

Схема:
1. Контекст автора (@`.data` `0xb02bf0`: тип + ключ `artist\\X`/`album_artist\\X`)
   запоминается при открытии списка альбомов автора — хук в `FUN_004a9180`
   (`0x4a9288`, `s6` = ключ вида). Любой другой ключ (верхние «Альбомы») — тип 0.
2. Хук `FUN_004eae80` (`0x4eaf2c`, вместо `jal FUN_004369a0`): если контекст задан
   и ключ плейлиста `album\\<Альбом>` —
   - перебираем `FUN_004369a0(ключ_автора, i, scratch)` (i=0..63), ищем запись,
     где `scratch+0x42c` (имя альбома) == `rec+0x20c` (текущий альбом);
   - «вперёд»: берём i+1; если запись пуста или её имя совпало с текущим
     (доиграл последний альбом автора) — переходим к **следующему автору**
     (см. п. 3), иначе копируем имя в `rec+0x20c`;
   - «назад»: берём i-1 (i==0 → fallback), копируем имя в `rec+0x20c`;
   - иначе/ошибка — штатный `FUN_004369a0` (fallback, поведение не меняется).
3. Следующий автор: тип ctx (1=`artist`, 2=`album_artist`) → ключ списка сущностей
   `L"artist"`/`L"album_artist"`; имя текущего автора = `ctx+0x12` / `ctx+0x1e`;
   сканируем список сущностей и ищем текущего автора по `scratch+0x20c`; берём
   j+1 (пусто/совпало → fallback); собираем ключ `artist\\<новый автор>` в буфере,
   строим список альбомов нового автора штатным `FUN_0070a3a0(9,0,rec,0)` и берём
   его первый альбом; пишем в `rec+0x20c` и обновляем ctx-ключ. Так «последний
   альбом автора» больше не зацикливается, а переходит к следующему автору.

   Чтение строк сущностей и первого альбома нового автора идёт НЕ через
   `FUN_004369a0`, а напрямую через `FUN_0070b020(rec, idx, 1, 1, key)` (SQL, минуя
   «живой вид»). Причина: из потока завершения трека (NON-main-thread) путь
   `FUN_004369a0` для ключа-сущности заходит в `FUN_004ec900`→`FUN_004a4b40` и
   делает `trap(7)` (см. `.opencode/NOTES.md`, ловушка view-объектов из EOS-потока).
   `FUN_0070b020` — тот же SQL-fallback, что и внутри `FUN_004369a0` (`0x436a3c`),
   вид не трогает. Запись под `FUN_0070a3a0(9,…)` готовится ровно как штатный
   `FUN_004a9180`: `rec+0x004` = полный ключ `artist\\X`, а `rec+0x52c` (биндинг
   фильтра `artist like ?`) = имя БЕЗ префикса (штатный `FUN_0049d760` срезает
   всё до `\\`).

Верхний список «Альбомы» не трогаем; порядок берётся из актуального списка
автора (Artists и Album Artist — разные списки). Направление «назад» на границе
автора (первый альбом) ведёт к **предыдущему автору** и его **последнему**
альбому — симметрично «вперёд». Идемпотентно, `--check`.

    python3 tools/exp_shuffle_hierarchy.py <hiby_player> [--check]
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

VTO = 0x400000
CTX_VA = 0xB02BF0              # .data-дыра: [+0]=type, [+4]=wide ключ автора (0x104)
STUB_CTX = 0x4194A0
STUB_EOS = 0x419800

# --- диагностика (--diag): stage-маркеры в /mnt/sd_0/hier2.log -------------
DIAG = False
LOG_PATH_VA = 0x41B800         # .text-пещера: путь для open()
LOG_MARK_VA = 0x41B840         # .text-пещера: строка маркеров "0123456X"
LOG_PATH = b"/mnt/sd_0/hier2.log\x00"
# индексы: 0-6 eos_next_author|7=X key setup done|8=a na_scan|9=b entity row|
# 10=c ctx-hook end|11=A ctx artist|12=B ctx album_artist|13=C ctx none|
# 14=d eos entry|15=e eos forward|16=f eos prev|17=g eos done|18=i eos prev_author
LOG_MARKS = b"0123456XabcABCdefghi"

HOOK_CTX = 0x4A9288
HOOK_CTX_OLD = 0x0C1C28E8      # jal 0x70a3a0
HOOK_EOS = 0x4EAF2C
HOOK_EOS_OLD = 0x0C10DA68      # jal 0x4369a0

F_GETROW = 0x004369A0          # FUN_004369a0(key, idx, rec)
F_GETROW_SQL = 0x0070B020      # FUN_0070b020(rec, idx, 1, 1, key) — без пути вида
F_WCMP = 0x00421020            # FUN_00421020(wide,wide)
F_WCPY = 0x00420F20            # FUN_00420f20(dst,src,n)
F_MEMSET = 0x00A7DFB0          # memset(dst,0,n)
F_LISTBUILD = 0x0070A3A0       # FUN_0070a3a0(kind, 0, rec, 0)

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

    def branch(op: int, rs: str, rt: str, lbl: str, i: int) -> int:
        delta = pc(loc[lbl]) - pc(i) - 4
        assert delta % 4 == 0 and -0x8000 <= delta // 4 < 0x8000, lbl
        return iw(op, rs, rt, delta // 4)

    out: list[int] = []
    for i, s in enumerate(norm):
        op0 = s.split()[0]
        if op0 in ("lw", "sw", "lhu", "lbu", "sh", "sb"):
            rt, paren = [x.strip() for x in s.split(None, 1)[1].split(",", 1)]
            off, rs = paren.strip().split("(", 1)
            rs = rs.rstrip(")")
            off = off.strip() or "0"
            opc = {"lw": 35, "sw": 43, "lhu": 37, "lbu": 36, "sh": 41, "sb": 40}[op0]
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
        elif op == "sltiu":
            out.append(iw(0x0B, a[1], a[0], int(a[2], 0)))
        elif op == "move":
            out.append(R[a[1]] << 21 | R["zero"] << 16 | R[a[0]] << 11 | 0x25)
        elif op in ("beq", "bne"):
            out.append(branch(4 if op == "beq" else 5, a[0], a[1], a[2], i))
        elif op == "bltz":
            out.append(branch(1, a[0], "zero", a[1], i))
        elif op == "b":
            out.append(branch(4, "zero", "zero", a[0], i))
        elif op == "jal":
            tgt = a[0]
            tgt_va = pc(loc[tgt]) if tgt in loc else int(tgt, 0)
            assert 0 <= tgt_va < 0x10000000, tgt
            out.append(3 << 26 | (tgt_va >> 2))
        elif op == "jalr":
            out.append(R[a[0]] << 21 | 31 << 11 | 9)
        elif op == "jr":
            out.append(R[a[0]] << 21 | 8)
        elif op == "syscall":
            out.append(0x0000000C)
        else:
            raise ValueError(s)
    return b"".join(struct.pack("<I", w) for w in out)


def lui_addiu(reg: str, va: int) -> list[str]:
    lo = va & 0xFFFF
    if lo >= 0x8000:
        lo -= 0x10000
    hi = (va - lo) >> 16
    return [f"lui {reg}, {hi:#x}", f"addiu {reg}, {reg}, {lo:#x}"]


def log_instr(marker_off: int) -> list[str]:
    """Диагностика (--diag): дописать 1 байт-маркер в /mnt/sd_0/hier2.log
    (сырые syscall). Сохраняет ra/t0/t1; на точках логирования живых
    t-регистров нет."""
    return [
        "addiu sp, sp, -0x38",
        "sw ra, 0x34(sp)",
        "sw v0, 0x30(sp)",
        "sw t2, 0x2c(sp)",
        "sw t7, 0x28(sp)",
        "sw t8, 0x24(sp)",
        "sw t9, 0x20(sp)",
        "sw t0, 0x1c(sp)",
        "sw t1, 0x18(sp)",
        "addiu v0, zero, 4005",
        *lui_addiu("a0", LOG_PATH_VA),
        "addiu a1, zero, 0x109",      # O_WRONLY|O_CREAT|O_APPEND
        "addiu a2, zero, 0x1a4",
        "syscall",
        "sw v0, 0x14(sp)",
        f"bltz v0, log_skip_{marker_off}",
        "addiu v0, zero, 4004",
        "lw a0, 0x14(sp)",
        *lui_addiu("a1", LOG_MARK_VA + marker_off),
        "addiu a2, zero, 1",
        "syscall",
        "addiu v0, zero, 4006",
        "lw a0, 0x14(sp)",
        "syscall",
        f"log_skip_{marker_off}:",
        "lw t0, 0x1c(sp)",
        "lw t1, 0x18(sp)",
        "lw t9, 0x20(sp)",
        "lw t8, 0x24(sp)",
        "lw t7, 0x28(sp)",
        "lw t2, 0x2c(sp)",
        "lw ra, 0x34(sp)",
        "lw v0, 0x30(sp)",
        "addiu sp, sp, 0x38",
    ]


def lg(marker_off: int) -> list[str]:
    return log_instr(marker_off) if DIAG else []


def getrow_sql(key_lines: list[str], idx_lines: list[str], rec_off: int = 0x20) -> list[str]:
    """FUN_0070b020(rec, idx, 1, 1, key) — чтение строки напрямую из SQL, БЕЗ
    пути «живого вида» (FUN_004ec900/FUN_004a4b40). Вид трогать из EOS-потока
    нельзя (см. NOTES: краш). 5-й аргумент (key) — на стеке, `0x10(sp)`."""
    return [
        *key_lines,
        "sw t0, 0x10(sp)",
        f"addiu a0, sp, {rec_off:#x}",
        *idx_lines,
        "addiu a2, zero, 1",
        "addiu a3, zero, 1",
        *call("t9", F_GETROW_SQL), "nop",
    ]


def getrow_view(key_lines: list[str], idx_lines: list[str], rec_off: int = 0x20) -> list[str]:
    """FUN_004369a0(key, idx, rec) — как в HEAD (использует живой вид, если есть).
    Для ctx-ключа (список альбомов автора) работает; для ключей-сущностей —
    ловушка в FUN_004a4b40, поэтому там используется getrow_sql."""
    return [
        *key_lines,
        "move a0, t0",
        *idx_lines,
        f"addiu a2, sp, {rec_off:#x}",
        *call("t9", F_GETROW), "nop",
    ]


def call(t9reg: str, va: int) -> list[str]:
    return [f"lui {t9reg}, {(va >> 16) & 0xFFFF:#x}",
            f"ori {t9reg}, {t9reg}, {va & 0xFFFF:#x}",
            f"jalr {t9reg}"]


def stub_ctx() -> list[str]:
    """a0=9,a1=0,a2=recbuf,a3=0; s6=ключ вида; ra=0x4a9290."""
    return [
        "addiu sp, sp, -0x20",
        "sw ra, 0x1c(sp)",
        "sw a0, 0x18(sp)",
        "sw a1, 0x14(sp)",
        "sw a2, 0x10(sp)",
        "sw a3, 0x0c(sp)",
        "lui t2, 0x00b0", "addiu t2, t2, 0x2bf0",
        "lw t0, 0(s6)",
        "lui t1, 0x0072", "ori t1, t1, 0x0061",   # "ar" = 0x0072_0061
        "beq t0, t1, c_artist", "nop",
        "lui t1, 0x006c", "ori t1, t1, 0x0061",   # "al" = 0x006c_0061
        "beq t0, t1, c_try_aa", "nop",
        "b c_none", "nop",
        "c_try_aa:",
        "lw t0, 0x0a(s6)",                        # chars 5,6 = "_a"
        "lui t1, 0x0061", "ori t1, t1, 0x005f",
        "bne t0, t1, c_none", "nop",
        *lg(12),
        "addiu t1, zero, 2",
        "sw t1, 0(t2)",
        "b c_copy", "nop",
        "c_artist:",
        *lg(11),
        "addiu t1, zero, 1",
        "sw t1, 0(t2)",
        "b c_copy", "nop",
        "c_none:",
        *lg(13),
        "sw zero, 0(t2)",
        "b c_done", "nop",
        "c_copy:",
        "addiu a0, t2, 4",
        "move a1, s6",
        "addiu a2, zero, 0x82",
        "jal 0x420f20", "nop",
        "c_done:",
        "lw a0, 0x18(sp)",
        "lw a1, 0x14(sp)",
        "lw a2, 0x10(sp)",
        "lw a3, 0x0c(sp)",
        *call("t9", 0x0070A3A0),
        "nop",
        *lg(10),
        "lw ra, 0x1c(sp)",
        "jr ra",
        "addiu sp, sp, 0x20",
    ]


def stub_eos() -> list[str]:
    """a0=&L"album", a1=idx, a2=rec, s2=dir(1=next,0=prev), s3=&DAT_00b05224;
    ra=0x4eaf34. Кадр 0xe00: scratch=0x20(0xa88), keybuf=0xab0(0x104),
    lastbuf=0xc00(0x100);
    ra=0xbfc, a0=0xbf8, a1=0xbf4, a2=0xbf0, ctx=0xbec, i=0xbe8, entkey=0xbe4,
    dst=0xbe0, name=0xbdc, j=0xbd8, k=0xbd4, idx=0xbc8, tmpptr=0xbb8.

    Логика: если контекст автора задан и ключ плейлиста `album\\…` — найти текущий
    альбом в списке автора (штатная FUN_004369a0(ctx_key,i)), взять соседний.
    «Вперёд»: если сосед пуст или совпал с текущим (доиграл последний альбом
    автора) — перейти к следующему автору (список сущностей
    ARTIST_TABLE/ALBUM_ARTIST_TABLE → первый альбом нового автора) и обновить
    ctx-ключ; иначе — просто подменить имя альбома.
    «Назад»: сосед i-1; если i==0 (первый альбом автора) — перейти к ПРЕДЫДУЩЕМУ
    автору и взять его ПОСЛЕДНИЙ альбом (цикл по строкам; ридер за концом списка
    не чистит rec, поэтому берём «последнее валидное» в отдельный буфер).
    Любая ошибка — штатный fallback (FUN_004369a0(L"album", idx, rec))."""
    return [
        "move t7, a0",
        "move t8, a1",
        "move t9, a2",
        *lg(14),
        "move a0, t7",
        "move a1, t8",
        "move a2, t9",
        "addiu sp, sp, -0xe00",
        "sw ra, 0xbfc(sp)",
        "sw a0, 0xbf8(sp)",
        "sw a1, 0xbf4(sp)",
        "sw a2, 0xbf0(sp)",
        "lui t0, 0x00b0", "addiu t0, t0, 0x2bf0",
        "sw t0, 0xbec(sp)",
        "lw t1, 0(t0)",
        "beq t1, zero, eos_fallback", "nop",
        # ключ плейлиста должен начинаться с "album\"
        "lw t0, 0(s3)",
        "lui t1, 0x006c", "ori t1, t1, 0x0061",
        "bne t0, t1, eos_fallback", "nop",
        "lw t0, 8(s3)",
        "lui t1, 0x005c", "ori t1, t1, 0x006d",
        "bne t0, t1, eos_fallback", "nop",
        # ищем текущий альбом в списке автора
        "addiu t0, zero, 0", "sw t0, 0xbe8(sp)",
        "eos_scan:",
        "lw t0, 0xbe8(sp)",
        "sltiu t1, t0, 0x40",
        "beq t1, zero, eos_fallback", "nop",
        *getrow_view(["lw t0, 0xbec(sp)", "addiu t0, t0, 4"], ["lw a1, 0xbe8(sp)"]),
        "lhu t0, 0x44c(sp)",
        "beq t0, zero, eos_fallback", "nop",
        "addiu a0, sp, 0x44c",
        "lw t0, 0xbf0(sp)", "addiu a1, t0, 0x20c",
        *call("t9", F_WCMP), "nop",
        "beq v0, zero, eos_found", "nop",
        "lw t0, 0xbe8(sp)", "addiu t0, t0, 1", "sw t0, 0xbe8(sp)",
        "b eos_scan", "nop",
        "eos_found:",
        "lw t0, 0xbe8(sp)",
        "beq s2, zero, eos_prev", "nop",
        # ---- вперёд ----
        *lg(15),
        "addiu a1, t0, 1",
        "sw a1, 0xbd4(sp)",
        *getrow_view(["lw t0, 0xbec(sp)", "addiu t0, t0, 4"], ["lw a1, 0xbd4(sp)"]),
        "lhu t0, 0x44c(sp)",
        "beq t0, zero, eos_next_author", "nop",
        "addiu a0, sp, 0x44c",
        "lw t0, 0xbf0(sp)", "addiu a1, t0, 0x20c",
        *call("t9", F_WCMP), "nop",
        "beq v0, zero, eos_next_author", "nop",
        "lw t1, 0xbf0(sp)", "addiu a0, t1, 0x20c",
        "addiu a1, sp, 0x44c",
        "addiu a2, zero, 0x103",
        *call("t9", F_WCPY), "nop",
        "b eos_done", "nop",
        # ---- назад ----
        "eos_prev:",
        *lg(16),
        "addiu a1, t0, -1",
        "bltz a1, eos_prev_author", "nop",
        "sw a1, 0xbd4(sp)",
        *getrow_view(["lw t0, 0xbec(sp)", "addiu t0, t0, 4"], ["lw a1, 0xbd4(sp)"]),
        "lhu t0, 0x44c(sp)",
        "beq t0, zero, eos_fallback", "nop",
        "lw t1, 0xbf0(sp)", "addiu a0, t1, 0x20c",
        "addiu a1, sp, 0x44c",
        "addiu a2, zero, 0x103",
        *call("t9", F_WCPY), "nop",
        "b eos_done", "nop",
        # ---- предыдущий автор (назад на границе: первый альбом автора) ----
        "eos_prev_author:",
        *lg(18),
        "lw t2, 0xbec(sp)", "lw t0, 0(t2)",
        "addiu t1, zero, 1",
        "bne t0, t1, pa_aa", "nop",
        # type 1: список сущностей "artist", имя автора в ctx+0x12
        "lui t0, 0x0096", "addiu t0, t0, 0x0b3c",
        "sw t0, 0xbe4(sp)",
        "addiu a0, sp, 0xab0",
        "move a1, t0",
        "addiu a2, zero, 0x82",
        *call("t9", F_WCPY), "nop",
        "addiu t0, zero, 0x5c", "sh t0, 0xabc(sp)",
        "addiu t0, sp, 0xabe", "sw t0, 0xbe0(sp)",
        "lw t0, 0xbec(sp)", "addiu t0, t0, 0x12", "sw t0, 0xbdc(sp)",
        "b pa_scan", "nop",
        "pa_aa:",
        # type 2: список сущностей "album_artist", имя автора в ctx+0x1e
        "lui t0, 0x0096", "addiu t0, t0, 0x0b30",
        "sw t0, 0xbe4(sp)",
        "addiu a0, sp, 0xab0",
        "move a1, t0",
        "addiu a2, zero, 0x82",
        *call("t9", F_WCPY), "nop",
        "addiu t0, zero, 0x5c", "sh t0, 0xac8(sp)",
        "addiu t0, sp, 0xaca", "sw t0, 0xbe0(sp)",
        "lw t0, 0xbec(sp)", "addiu t0, t0, 0x1e", "sw t0, 0xbdc(sp)",
        "pa_scan:",
        "addiu t0, zero, 0", "sw t0, 0xbd8(sp)",
        "pa_loop:",
        "lw t0, 0xbd8(sp)",
        "sltiu t1, t0, 0x40",
        "beq t1, zero, eos_fallback", "nop",
        *getrow_sql(["lw t0, 0xbe4(sp)"], ["lw a1, 0xbd8(sp)"]),
        "lhu t0, 0x22c(sp)",
        "beq t0, zero, eos_fallback", "nop",
        "addiu a0, sp, 0x22c",
        "lw a1, 0xbdc(sp)",
        *call("t9", F_WCMP), "nop",
        "beq v0, zero, pa_found", "nop",
        "lw t0, 0xbd8(sp)", "addiu t0, t0, 1", "sw t0, 0xbd8(sp)",
        "b pa_loop", "nop",
        "pa_found:",
        # индекс предыдущего автора = j-1
        "lw t0, 0xbd8(sp)", "addiu t0, t0, -1", "sw t0, 0xbd4(sp)",
        "bltz t0, eos_fallback", "nop",
        *getrow_sql(["lw t0, 0xbe4(sp)"], ["lw a1, 0xbd4(sp)"]),
        "lhu t0, 0x22c(sp)",
        "beq t0, zero, eos_fallback", "nop",
        "addiu a0, sp, 0x22c",
        "lw a1, 0xbdc(sp)",
        *call("t9", F_WCMP), "nop",
        "beq v0, zero, eos_fallback", "nop",
        # keybuf = "artist"/"album_artist" + '\' + имя предыдущего автора
        "lw a0, 0xbe0(sp)",
        "addiu a1, sp, 0x22c",
        "addiu a2, zero, 0x60",
        *call("t9", F_WCPY), "nop",
        # строим список альбомов предыдущего автора
        "addiu a0, sp, 0x20",
        "move a1, zero",
        "addiu a2, zero, 0xa88",
        *call("t9", F_MEMSET), "nop",
        "addiu a0, sp, 0x24",
        "addiu a1, sp, 0xab0",
        "addiu a2, zero, 0x82",
        *call("t9", F_WCPY), "nop",
        "addiu a0, sp, 0x54c",
        "addiu a1, sp, 0xab0",
        "addiu a2, zero, 0x82",
        *call("t9", F_WCPY), "nop",
        "addiu a0, zero, 9",
        "move a1, zero",
        "addiu a2, sp, 0x20",
        "move a3, zero",
        *call("t9", F_LISTBUILD), "nop",
        # последний альбом: цикл по строкам, сохраняем последнее непустое имя
        # (ридер за концом списка НЕ чистит rec — поэтому берём «последнее
        #  валидное», а результат кладём в отдельный буфер sp+0xc00)
        "addiu a0, sp, 0x20",
        "move a1, zero",
        "addiu a2, zero, 0xa88",
        *call("t9", F_MEMSET), "nop",
        "sh zero, 0xc00(sp)",
        "addiu t0, zero, 0", "sw t0, 0xbc8(sp)",
        "pa_alb_loop:",
        "lw t0, 0xbc8(sp)",
        "sltiu t1, t0, 0x40",
        "beq t1, zero, pa_alb_end", "nop",
        *getrow_view(["addiu t0, sp, 0xab0"], ["lw a1, 0xbc8(sp)"]),
        "lhu t0, 0x44c(sp)",
        "bne t0, zero, pa_alb_hi", "nop",
        "lhu t0, 0x22c(sp)",
        "beq t0, zero, pa_alb_end", "nop",
        "addiu t0, sp, 0x22c", "sw t0, 0xbb8(sp)",
        "b pa_alb_cp", "nop",
        "pa_alb_hi:",
        "addiu t0, sp, 0x44c", "sw t0, 0xbb8(sp)",
        "pa_alb_cp:",
        "addiu a0, sp, 0xc00",
        "lw a1, 0xbb8(sp)",
        "addiu a2, zero, 0x100",
        *call("t9", F_WCPY), "nop",
        "lw t0, 0xbc8(sp)", "addiu t0, t0, 1", "sw t0, 0xbc8(sp)",
        "b pa_alb_loop", "nop",
        "pa_alb_end:",
        "lhu t0, 0xc00(sp)",
        "beq t0, zero, eos_fallback", "nop",
        "lw t1, 0xbf0(sp)", "addiu a0, t1, 0x20c",
        "addiu a1, sp, 0xc00",
        "addiu a2, zero, 0x103",
        *call("t9", F_WCPY), "nop",
        # обновляем ctx-ключ на предыдущего автора
        "lw t0, 0xbec(sp)", "addiu a0, t0, 4",
        "addiu a1, sp, 0xab0",
        "addiu a2, zero, 0x82",
        *call("t9", F_WCPY), "nop",
        "b eos_done", "nop",
        # ---- следующий автор ----
        "eos_next_author:",
        *lg(0),
        "lw t2, 0xbec(sp)", "lw t0, 0(t2)",
        "addiu t1, zero, 1",
        "bne t0, t1, na_aa", "nop",
        # type 1: список сущностей "artist", имя автора в ctx+0x12
        "lui t0, 0x0096", "addiu t0, t0, 0x0b3c",
        "sw t0, 0xbe4(sp)",
        "addiu a0, sp, 0xab0",
        "move a1, t0",
        "addiu a2, zero, 0x82",
        *call("t9", F_WCPY), "nop",
        "addiu t0, zero, 0x5c", "sh t0, 0xabc(sp)",
        "addiu t0, sp, 0xabe", "sw t0, 0xbe0(sp)",
        "lw t0, 0xbec(sp)", "addiu t0, t0, 0x12", "sw t0, 0xbdc(sp)",
        "b na_scan", "nop",
        "na_aa:",
        # type 2: список сущностей "album_artist", имя автора в ctx+0x1e
        # ("album_artist\" = 13 wide-символов = 26 байт, имя с байта 0x1e)
        "lui t0, 0x0096", "addiu t0, t0, 0x0b30",
        "sw t0, 0xbe4(sp)",
        "addiu a0, sp, 0xab0",
        "move a1, t0",
        "addiu a2, zero, 0x82",
        *call("t9", F_WCPY), "nop",
        "addiu t0, zero, 0x5c", "sh t0, 0xac8(sp)",
        "addiu t0, sp, 0xaca", "sw t0, 0xbe0(sp)",
        "lw t0, 0xbec(sp)", "addiu t0, t0, 0x1e", "sw t0, 0xbdc(sp)",
        "na_scan:",
        *lg(7),
        *lg(8),
        "addiu t0, zero, 0", "sw t0, 0xbd8(sp)",
        "na_loop:",
        "lw t0, 0xbd8(sp)",
        "sltiu t1, t0, 0x40",
        "beq t1, zero, eos_fallback", "nop",
        *getrow_sql(["lw t0, 0xbe4(sp)"], ["lw a1, 0xbd8(sp)"]),
        *lg(9),
        "lhu t0, 0x22c(sp)",
        "beq t0, zero, eos_fallback", "nop",
        "addiu a0, sp, 0x22c",
        "lw a1, 0xbdc(sp)",
        *call("t9", F_WCMP), "nop",
        "beq v0, zero, na_found", "nop",
        "lw t0, 0xbd8(sp)", "addiu t0, t0, 1", "sw t0, 0xbd8(sp)",
        "b na_loop", "nop",
        "na_found:",
        *lg(1),
        "lw t0, 0xbd8(sp)", "addiu t0, t0, 1", "sw t0, 0xbd4(sp)",
        *getrow_sql(["lw t0, 0xbe4(sp)"], ["lw a1, 0xbd4(sp)"]),
        "lhu t0, 0x22c(sp)",
        "beq t0, zero, eos_fallback", "nop",
        # имя следующего автора не должно совпасть с текущим (граница списка)
        "addiu a0, sp, 0x22c",
        "lw a1, 0xbdc(sp)",
        *call("t9", F_WCMP), "nop",
        "beq v0, zero, eos_fallback", "nop",
        *lg(2),
        # ключ нового автора: keybuf уже = "artist" / "album_artist"
        "lw a0, 0xbe0(sp)",
        "addiu a1, sp, 0x22c",
        "addiu a2, zero, 0x60",
        *call("t9", F_WCPY), "nop",
        *lg(3),
        # строим list_tb альбомов нового автора. ВАЖНО: сборка применяет
        # exp_albums_artist_album_artist.py (0x4a9214: jal FUN_0049d760 ->
        # jal FUN_00420f20), поэтому rec+0x52c = ПОЛНЫЙ ключ ("artist\\X"),
        # а slot 182 ждёт именно его (`?1 LIKE 'artist\%'` + substr(?1,8)).
        # rec+0x004 (ключ менеджера) — тоже полный ключ. Затем FUN_0070a3a0(9,0,rec,0).
        "addiu a0, sp, 0x20",
        "move a1, zero",
        "addiu a2, zero, 0xa88",
        *call("t9", F_MEMSET), "nop",
        "addiu a0, sp, 0x24",
        "addiu a1, sp, 0xab0",
        "addiu a2, zero, 0x82",
        *call("t9", F_WCPY), "nop",
        "addiu a0, sp, 0x54c",
        "addiu a1, sp, 0xab0",
        "addiu a2, zero, 0x82",
        *call("t9", F_WCPY), "nop",
        "addiu a0, zero, 9",
        "move a1, zero",
        "addiu a2, sp, 0x20",
        "move a3, zero",
        *call("t9", F_LISTBUILD), "nop",
        *lg(4),
        # первый альбом нового автора; имя может лежать в +0x42c (ctx-список)
        # или +0x20c (запись сущности) — берём непустое.
        # ВАЖНО: читаем через FUN_004369a0 (живой вид/менеджер по ключу), а НЕ
        # FUN_0070b020 — последний знает только точные ключи (all/album/artist/…),
        # но не `artist\<имя>`.
        *getrow_view(["addiu t0, sp, 0xab0"], ["move a1, zero"]),
        "lhu t0, 0x44c(sp)",
        "bne t0, zero, na_alb_hi", "nop",
        "lhu t0, 0x22c(sp)",
        "beq t0, zero, eos_fallback", "nop",
        "addiu t0, sp, 0x22c", "sw t0, 0xbb8(sp)",
        "b na_alb_cp", "nop",
        "na_alb_hi:",
        "addiu t0, sp, 0x44c", "sw t0, 0xbb8(sp)",
        "na_alb_cp:",
        *lg(5),
        "lw t1, 0xbf0(sp)", "addiu a0, t1, 0x20c",
        "lw a1, 0xbb8(sp)",
        "addiu a2, zero, 0x103",
        *call("t9", F_WCPY), "nop",
        # обновляем ctx-ключ на нового автора
        "lw t0, 0xbec(sp)", "addiu a0, t0, 4",
        "addiu a1, sp, 0xab0",
        "addiu a2, zero, 0x82",
        *call("t9", F_WCPY), "nop",
        *lg(6),
        "b eos_done", "nop",
        # ---- штатный путь ----
        "eos_fallback:",
        "lw a0, 0xbf8(sp)",
        "lw a1, 0xbf4(sp)",
        "lw a2, 0xbf0(sp)",
        *call("t9", F_GETROW), "nop",
        "eos_done:",
        *lg(17),
        "lw ra, 0xbfc(sp)",
        "jr ra",
        "addiu sp, sp, 0xe00",
    ]


def main() -> int:
    global DIAG
    argv = sys.argv[1:]
    check = "--check" in argv
    DIAG = "--diag" in argv
    args = [a for a in argv if a not in ("--check", "--diag")]
    if len(args) != 1:
        raise SystemExit(__doc__)
    path = Path(args[0])
    d = bytearray(path.read_bytes())

    ctx_code = assemble(STUB_CTX, stub_ctx())
    eos_code = assemble(STUB_EOS, stub_eos())
    hook_ctx = struct.unpack_from("<I", d, HOOK_CTX - VTO)[0]
    hook_eos = struct.unpack_from("<I", d, HOOK_EOS - VTO)[0]
    ctx_new = 3 << 26 | (STUB_CTX >> 2)
    eos_new = 3 << 26 | (STUB_EOS >> 2)
    ctx_ok = bytes(d[STUB_CTX - VTO:STUB_CTX - VTO + len(ctx_code)]) == ctx_code
    eos_ok = bytes(d[STUB_EOS - VTO:STUB_EOS - VTO + len(eos_code)]) == eos_code
    done = hook_ctx == ctx_new and hook_eos == eos_new and ctx_ok and eos_ok

    if check:
        print(f"{HOOK_CTX:#x} = {hook_ctx:#010x} ({'хук ctx' if hook_ctx == ctx_new else 'сток'})")
        print(f"{HOOK_EOS:#x} = {hook_eos:#010x} ({'хук eos' if hook_eos == eos_new else 'сток'})")
        print(f"заглушки: ctx {'ok' if ctx_ok else 'нет'} ({len(ctx_code)}), eos {'ok' if eos_ok else 'нет'} ({len(eos_code)})")
        return 0

    if done:
        print("уже пропатчено (shuffle hierarchy)")
        return 0
    if hook_ctx not in (HOOK_CTX_OLD, ctx_new):
        raise SystemExit(
            f"{HOOK_CTX:#x}: ожидался {HOOK_CTX_OLD:#010x} или {ctx_new:#010x}, найдено {hook_ctx:#010x}")
    if hook_eos not in (HOOK_EOS_OLD, eos_new):
        raise SystemExit(
            f"{HOOK_EOS:#x}: ожидался {HOOK_EOS_OLD:#010x} или {eos_new:#010x}, найдено {hook_eos:#010x}")

    if STUB_CTX + len(ctx_code) > STUB_EOS:
        raise SystemExit(
            f"ctx-заглушка {STUB_CTX:#x}+{len(ctx_code)} перекрывает eos {STUB_EOS:#x}")
    if STUB_EOS + len(eos_code) > 0x41B800:
        raise SystemExit(
            f"eos-заглушка {STUB_EOS:#x}+{len(eos_code)} перекрывает diag-зону 0x41b800")
    d[STUB_CTX - VTO:STUB_CTX - VTO + len(ctx_code)] = ctx_code
    d[STUB_EOS - VTO:STUB_EOS - VTO + len(eos_code)] = eos_code
    if DIAG:
        for va, blob in ((LOG_PATH_VA, LOG_PATH), (LOG_MARK_VA, LOG_MARKS)):
            off = va - VTO
            d[off:off + len(blob)] = blob
    struct.pack_into("<I", d, HOOK_CTX - VTO, ctx_new)
    struct.pack_into("<I", d, HOOK_EOS - VTO, eos_new)

    path.write_bytes(bytes(d))
    tag = " (DIAG)" if DIAG else ""
    print(f"{path}: shuffle hierarchy{tag} -> ctx@{STUB_CTX:#x} ({len(ctx_code)}b), "
          f"eos@{STUB_EOS:#x} ({len(eos_code)}b)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
