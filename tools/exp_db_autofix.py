#!/usr/bin/env python3
"""Авто-фикс медиатеки: бинарь сам выполняет SQL из образа.

Хук в `FUN_0070eb00` (пересборка таблиц медиатеки) на инструкции `jal 0x6fbd80`
(`0x70ecfc`, «commit transaction») читает `/usr/share/hiby_db_fix.sql` (лежит в
образе, генерируется `tools/make_db_fix_sql.py`) и выполняет его через
`sqlite3_exec` (`FUN_005f0be0(db, sql, 0, 0, 0)`). Так образ самодостаточен:
после «обновления медиатеки» буквы/порядок/разбор `artist` по `;` приходят в
порядок без внешних скриптов.

Почему эта точка: `FUN_0070eb00` — пересборка таблиц списков; единственный
вызов — `0x7113d8` (в `FUN_007112a0`), а сама `FUN_007112a0` — из воркера
«обновления медиатеки» (`FUN_004e93e0`, `0x4e939c`). `0x70ecfc` — общая точка
схода всех внутренних веток (`0x70edc0 bnez -> 0x70ecfc`) сразу ПОСЛЕ
`commit transaction`, т.е. БД свободна, транзакция закрыта.

Прежняя точка `0x71d0b0` (лог «Scanner stopped») — это FM-радио seek-сканер
(рядом строки `Radio Seek Start/Status/...`), при «обновлении медиатеки» НЕ
исполняется — отсюда «фикс не срабатывает». Хук на ней снимается автоматически.

Чтение файла — сырыми syscall'ами MIPS o32 (open=4005, read=4003, close=4006);
буфер — `malloc` (PLT-стаб `0xa7d6e0`), освобождается `free` (`0xa7dcf0`).
ВАЖНО: из RX-зоны `jal`/`j` кодируются с верхним нибблом PC (0xa…), поэтому все
вызовы делаются через `jalr` (lui+addiu+jalr). Delay-слоты после `jalr`
заполняются явно (без переиспользования t-регистров через вызов).

Использование:
    python3 tools/exp_db_autofix.py <hiby_player> [--check]
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

VTO = 0x400000
STUB_VA = 0xA7ED00          # RX-зазор; стаб не должен пересечь RX_LIMIT
PATH_VA = 0xA7EF80
HOOK_VA = 0x70ECFC          # jal 0x6fbd80 ("commit transaction") в FUN_0070eb00
HOOK_ORIG = 0x0C1BEF60      # jal 0x6fbd80
RX_LIMIT = 0xA7EE1C         # здесь начинается строка слота 146 (patch_artist_cleanup)

# снятие прежней (радио-сканер) точки
LEGACY_HOOK_VA = 0x71D0B0
LEGACY_HOOK_EXPECTED = 0x0C29FB77   # jal 0xa7eddc (старый стаб)
LEGACY_HOOK_ORIG = 0x0C1C4E58       # jal FUN_00713960 (лог)

PATH = b"/usr/share/hiby_db_fix.sql\x00"

# адреса функций/стабов
F_COMMIT = 0x006FBD80       # sqlite3_exec(db, "commit transaction")
F_EXEC = 0x005F0BE0         # sqlite3_exec
P_MALLOC = 0xA7D6E0         # PLT malloc
P_FREE = 0xA7DCF0           # PLT free

R = {n: i for i, n in enumerate(
    "zero at v0 v1 a0 a1 a2 a3 t0 t1 t2 t3 t4 t5 t6 t7 s0 s1 s2 s3 s4 s5 s6 s7 "
    "t8 t9 k0 k1 gp sp fp ra".split())}

SPECIAL = {"addu": 0x21, "subu": 0x23, "move": 0x25, "jr": 0x08, "jalr": 0x09}


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
    """lui/addiu/jalr + явный delay-слот (не переиспользует t-регистры через вызов)."""
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
        elif op == "syscall":
            out.append(0x0000000C)
        elif op == "addiu":
            rt, rs, imm = a
            out.append(iw(9, rs, rt, int(imm, 0)))
        elif op == "lui":
            rt, imm = a
            out.append(iw(15, "zero", rt, int(imm, 0)))
        elif op == "ori":
            rt, rs, imm = a
            out.append(iw(13, rs, rt, int(imm, 0)))
        elif op in ("addu", "subu"):
            rd, rs, rt = a
            out.append(rw(rs, rt, rd, SPECIAL[op]))
        elif op == "move":
            rd, rs = a
            out.append(rw(rs, "zero", rd, 0x25))
        elif op == "jalr":
            out.append(rw(a[0], "zero", "ra", 0x09))
        elif op in ("beq", "bne"):
            rs, rt, lbl = a
            out.append(iw(4 if op == "beq" else 5, rs, rt, (pc(loc[lbl]) - pc(i) - 4) // 4))
        elif op == "blez":
            rs, lbl = a
            out.append(iw(6, rs, "zero", (pc(loc[lbl]) - pc(i) - 4) // 4))
        elif op in ("bltz", "bgez"):
            rs, lbl = a
            out.append(iw(1, rs, "zero" if op == "bltz" else "at", (pc(loc[lbl]) - pc(i) - 4) // 4))
        elif op == "b":
            out.append(iw(4, "zero", "zero", (pc(loc[a[0]]) - pc(i) - 4) // 4))
        elif op == "jr":
            out.append(rw(a[0], "zero", "zero", 0x08))
        elif op == "jal":
            out.append(3 << 26 | (pc(loc[a[0]]) >> 2))
        else:
            raise ValueError(s)
    return b"".join(struct.pack("<I", w) for w in out)


def dbfix() -> list[str]:
    """Читает /usr/share/hiby_db_fix.sql и выполняет его на БД медиатеки.

    Вход: a0 = sqlite3* (тот же handle, что идёт в `commit transaction`).
    """
    L: list[str] = [
        "DBFIX:",
        "addiu sp, sp, -0x30",
        "sw ra, 0x2c(sp)",
        "sw s0, 0x28(sp)",
        "sw s1, 0x24(sp)",
        "sw s2, 0x20(sp)",
        "sw a0, 0x1c(sp)",          # db handle
        # fd = open(path, 0, 0)
        "addiu v0, zero, 4005",
    ]
    L += lui_addiu("a0", PATH_VA)
    L += [
        "move a1, zero",
        "move a2, zero",
        "syscall",
        "bltz v0, DBFIX_end",
        "move s0, v0",
    ]
    # buf = malloc(0x8000)
    L += call_jalr("t9", P_MALLOC, "ori a0, zero, 0x8000")
    L += [
        "move s1, v0",
        "beq s1, zero, DBFIX_close",
        "move s2, zero",
        "DBFIX_rd:",
        # n = read(fd, buf+total, 0x7fff-total)
        "addiu v0, zero, 4003",
        "move a0, s0",
        "addu a1, s1, s2",
        "addiu a2, zero, 0x7fff",
        "subu a2, a2, s2",
        "syscall",
        "blez v0, DBFIX_rdone",
        "addu s2, s2, v0",
        "b DBFIX_rd",
        "nop",
        "DBFIX_rdone:",
        "addu t0, s1, s2",
        "sb zero, 0(t0)",
        # exec(db, buf, 0, 0, 0)
        "lw a0, 0x1c(sp)",
        "move a1, s1",
        "move a2, zero",
        "move a3, zero",
        "sw zero, 0x10(sp)",
    ]
    L += call_jalr("t9", F_EXEC)
    # free(buf)
    L += call_jalr("t9", P_FREE, "move a0, s1")
    L += [
        "DBFIX_close:",
        "addiu v0, zero, 4006",
        "move a0, s0",
        "syscall",
        "DBFIX_end:",
        "lw ra, 0x2c(sp)",
        "lw s0, 0x28(sp)",
        "lw s1, 0x24(sp)",
        "lw s2, 0x20(sp)",
        "jr ra",
        "addiu sp, sp, 0x30",
    ]
    return L


def tramp(dbfix_va: int) -> list[str]:
    """Вызывается вместо `jal 0x6fbd80` (commit). a0 = sqlite3*, ra = 0x70ed04.

    Повторяет commit, затем выполняет DBFIX на том же handle и возвращается.
    """
    L: list[str] = [
        "addiu sp, sp, -0x18",
        "sw ra, 0x14(sp)",
        "sw a0, 0x10(sp)",
    ]
    L += call_jalr("t9", F_COMMIT)          # commit (a0 уже = db)
    L += ["lw a0, 0x10(sp)"]                # db handle для DBFIX
    L += call_jalr("t9", dbfix_va)          # DBFIX
    L += [
        "lw ra, 0x14(sp)",
        "jr ra",
        "addiu sp, sp, 0x18",
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

    dbfix_code = assemble(STUB_VA, dbfix())
    tramp_va = STUB_VA + len(dbfix_code)
    tramp_code = assemble(tramp_va, tramp(STUB_VA))
    stub = dbfix_code + tramp_code
    expected = 3 << 26 | (tramp_va >> 2)

    cur = struct.unpack_from("<I", d, HOOK_VA - VTO)[0]
    done = cur == expected
    legacy = struct.unpack_from("<I", d, LEGACY_HOOK_VA - VTO)[0]

    if check:
        print(f"{HOOK_VA:#x} = {cur:#010x} ({'хук' if done else 'сток'})")
        print(f"  DBFIX @ {STUB_VA:#x}, tramp @ {tramp_va:#x}, path @ {PATH_VA:#x}, "
              f"stub {len(stub)} байт (лимит {RX_LIMIT-STUB_VA})")
        if legacy == LEGACY_HOOK_EXPECTED:
            print(f"  ВНИМАНИЕ: остался legacy-хук @ {LEGACY_HOOK_VA:#x} (радио-сканер)")
        return 0

    if done and legacy != LEGACY_HOOK_EXPECTED:
        print("уже пропатчено (db autofix)")
        return 0
    if cur != HOOK_ORIG:
        raise SystemExit(f"{HOOK_VA:#x}: ожидался {HOOK_ORIG:#010x}, найдено {cur:#010x}")

    # снять прежний хук (иначе он прыгнет в середину нового стаба)
    if legacy == LEGACY_HOOK_EXPECTED:
        struct.pack_into("<I", d, LEGACY_HOOK_VA - VTO, LEGACY_HOOK_ORIG)
        print(f"{LEGACY_HOOK_VA:#x}: legacy-хук снят (радио-сканер)")
    elif legacy != LEGACY_HOOK_ORIG:
        raise SystemExit(f"{LEGACY_HOOK_VA:#x}: неизвестное состояние {legacy:#010x}")

    if STUB_VA + len(stub) > RX_LIMIT:
        raise SystemExit(f"стаб перекрывает RX_LIMIT: {STUB_VA+len(stub):#x} > {RX_LIMIT:#x}")
    path_cur = bytes(d[PATH_VA - VTO : PATH_VA - VTO + len(PATH)])
    if path_cur not in (bytes(len(PATH)), PATH):
        raise SystemExit(f"путь {PATH_VA:#x} занят: {path_cur[:16]!r}")

    off = STUB_VA - VTO
    d[off : off + len(stub)] = stub
    d[PATH_VA - VTO : PATH_VA - VTO + len(PATH)] = PATH
    struct.pack_into("<I", d, HOOK_VA - VTO, expected)

    path.write_bytes(bytes(d))
    print(f"{path}: авто-фикс БД после пересборки медиатеки "
          f"(DBFIX @{STUB_VA:#x}, tramp @{tramp_va:#x}, hook @{HOOK_VA:#x})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
