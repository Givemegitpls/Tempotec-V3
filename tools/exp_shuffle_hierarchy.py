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
   - берём соседнюю по направлению `s2` (1=вперёд, 0=назад), копируем её имя в
     `rec+0x20c`, возвращаемся на `0x4eaf34` (дальше всё делает `FUN_004eae80`);
   - иначе/ошибка — штатный `FUN_004369a0` (fallback, поведение не меняется).

Верхний список «Альбомы» не трогаем; порядок берётся из актуального списка
автора (Artists и Album Artist — разные списки). «Следующий автор» пока НЕ
реализован. Идемпотентно, `--check`.

    python3 tools/exp_shuffle_hierarchy.py <hiby_player> [--check]
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

VTO = 0x400000
CTX_VA = 0xB02BF0              # .data-дыра: [+0]=type, [+4]=wide ключ автора (0x104)
STUB_CTX = 0x4194A0
STUB_EOS = 0x419600

HOOK_CTX = 0x4A9288
HOOK_CTX_OLD = 0x0C1C28E8      # jal 0x70a3a0
HOOK_EOS = 0x4EAF2C
HOOK_EOS_OLD = 0x0C10DA68      # jal 0x4369a0

F_GETROW = 0x004369A0          # FUN_004369a0(key, idx, rec)
F_WCMP = 0x00421020            # FUN_00421020(wide,wide)
F_WCPY = 0x00420F20            # FUN_00420f20(dst,src,n)

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
        else:
            raise ValueError(s)
    return b"".join(struct.pack("<I", w) for w in out)


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
        "addiu t1, zero, 2",
        "sw t1, 0(t2)",
        "b c_copy", "nop",
        "c_artist:",
        "addiu t1, zero, 1",
        "sw t1, 0(t2)",
        "b c_copy", "nop",
        "c_none:",
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
        "lw ra, 0x1c(sp)",
        "jr ra",
        "addiu sp, sp, 0x20",
    ]


def stub_eos() -> list[str]:
    """a0=&L"album", a1=idx, a2=rec, s2=dir(1=next,0=prev), s3=&DAT_00b05224;
    ra=0x4eaf34. Кадр 0xb00: scratch=0x20(0xa88), i=0xae8, ctx=0xaec, rec=0xaf0,
    a1=0xaf4, a0=0xaf8, ra=0xafc."""
    return [
        "addiu sp, sp, -0xb00",
        "sw ra, 0xafc(sp)",
        "sw a0, 0xaf8(sp)",
        "sw a1, 0xaf4(sp)",
        "sw a2, 0xaf0(sp)",
        "lui t0, 0x00b0", "addiu t0, t0, 0x2bf0",
        "sw t0, 0xaec(sp)",
        "lw t1, 0(t0)",
        "beq t1, zero, eos_fallback", "nop",
        "lw t0, 0(s3)",
        "lui t1, 0x006c", "ori t1, t1, 0x0061",
        "bne t0, t1, eos_fallback", "nop",
        "lw t0, 8(s3)",
        "lui t1, 0x005c", "ori t1, t1, 0x006d",
        "bne t0, t1, eos_fallback", "nop",
        "addiu t0, zero, 0", "sw t0, 0xae8(sp)",
        "eos_scan:",
        "lw t0, 0xae8(sp)",
        "sltiu t1, t0, 0x40",
        "beq t1, zero, eos_fallback", "nop",
        "lw t0, 0xaec(sp)", "addiu a0, t0, 4",
        "lw a1, 0xae8(sp)",
        "addiu a2, sp, 0x20",
        *call("t9", F_GETROW), "nop",
        "lhu t0, 0x44c(sp)",
        "beq t0, zero, eos_fallback", "nop",
        "addiu a0, sp, 0x44c",
        "lw t0, 0xaf0(sp)", "addiu a1, t0, 0x20c",
        *call("t9", F_WCMP), "nop",
        "beq v0, zero, eos_found", "nop",
        "lw t0, 0xae8(sp)", "addiu t0, t0, 1", "sw t0, 0xae8(sp)",
        "b eos_scan", "nop",
        "eos_found:",
        "lw t0, 0xae8(sp)",
        "beq s2, zero, eos_prev", "nop",
        "addiu a1, t0, 1",
        "b eos_get", "nop",
        "eos_prev:",
        "addiu a1, t0, -1",
        "eos_get:",
        "bltz a1, eos_fallback", "nop",
        "lw t0, 0xaec(sp)", "addiu a0, t0, 4",
        "addiu a2, sp, 0x20",
        *call("t9", F_GETROW), "nop",
        "lhu t0, 0x44c(sp)",
        "beq t0, zero, eos_fallback", "nop",
        "lw t1, 0xaf0(sp)", "addiu a0, t1, 0x20c",
        "addiu a1, sp, 0x44c",
        "addiu a2, zero, 0x103",
        *call("t9", F_WCPY), "nop",
        "b eos_done", "nop",
        "eos_fallback:",
        "lw a0, 0xaf8(sp)",
        "lw a1, 0xaf4(sp)",
        "lw a2, 0xaf0(sp)",
        *call("t9", F_GETROW), "nop",
        "eos_done:",
        "lw ra, 0xafc(sp)",
        "jr ra",
        "addiu sp, sp, 0xb00",
    ]


def main() -> int:
    argv = sys.argv[1:]
    check = "--check" in argv
    args = [a for a in argv if a != "--check"]
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
    if hook_ctx != HOOK_CTX_OLD:
        raise SystemExit(f"{HOOK_CTX:#x}: ожидался {HOOK_CTX_OLD:#010x}, найдено {hook_ctx:#010x}")
    if hook_eos != HOOK_EOS_OLD:
        raise SystemExit(f"{HOOK_EOS:#x}: ожидался {HOOK_EOS_OLD:#010x}, найдено {hook_eos:#010x}")

    for va, blob in ((STUB_CTX, ctx_code), (STUB_EOS, eos_code)):
        off = va - VTO
        if not all(b == 0 for b in d[off:off + len(blob)]):
            raise SystemExit(f"место {va:#x} занято")
    d[STUB_CTX - VTO:STUB_CTX - VTO + len(ctx_code)] = ctx_code
    d[STUB_EOS - VTO:STUB_EOS - VTO + len(eos_code)] = eos_code
    struct.pack_into("<I", d, HOOK_CTX - VTO, ctx_new)
    struct.pack_into("<I", d, HOOK_EOS - VTO, eos_new)

    path.write_bytes(bytes(d))
    print(f"{path}: shuffle hierarchy -> ctx@{STUB_CTX:#x} ({len(ctx_code)}b), "
          f"eos@{STUB_EOS:#x} ({len(eos_code)}b)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
