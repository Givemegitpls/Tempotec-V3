#!/usr/bin/env python3
"""Авто-фикс медиатеки: бинарь сам выполняет SQL из образа.

Хук в конце `FUN_004e97c0` (@0x4e980c, `lw ra,0x1c(sp)` — эпилог функции
ожидания завершения «обновления медиатеки») читает `/usr/share/hiby_db_fix.sql`
(лежит в образе, генерируется `tools/make_db_fix_sql.py`) и выполняет его через
`sqlite3_exec` (`FUN_005f0be0(db, sql, 0, 0, 0)`). Так образ самодостаточен:
после «обновления медиатеки» буквы/порядок/разбор `artist` по `;` приходят в
порядок без внешних скриптов.

Почему эта точка (разбор субагента): обновление запускается ТОЛЬКО из UI
(меню/настройки, не при загрузке); пересборка таблиц идёт в `FUN_0070eb00`
внутри транзакции (`begin` @0x70eb48, `commit` @0x70ecfc), после неё все
prepared-выражения сброшены. `FUN_004e97c0` — busy-wait главного потока до
`state+0x14` («готово»), т.е. её эпилог = «обновление закончилось, БД свободна».

Delay-слот патча (0x4e9810 `lw s0,0x18(sp)`) исполняется до стаба → `s0` уже
восстановлен; `ra` вызывающего лежит в кадре (0x1c(sp)). Стаб выполняет DBFIX и
повторяет эпилог.

Чтение файла — сырыми syscall'ами MIPS o32 (open=4005, read=4003, close=4006);
буфер — `malloc` (PLT-стаб 0xa7d6e0), освобождается `free` (0xa7dcf0).
ВАЖНО: из RX-зоны `jal`/`j` кодируются с верхним нибблом PC (0xa…), поэтому все
вызовы делаются через `jalr` (lui+addiu+jalr).

Использование:
    python3 tools/exp_db_autofix.py <hiby_player> [--check]
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

VTO = 0x400000
STUB_VA = 0xA7ED00          # RX-зазор (освобождён от неудавшегося ctx-хука)
PATH_VA = 0xA7EF80
HOOK_VA = 0x71D0B0          # jal FUN_00713960 ("Scanner stopped") — проверенная точка
HOOK_ORIG = 0x0C1C4E58      # jal 0x713960
RX_LIMIT = 0xA7F000

PATH = b"/usr/share/hiby_db_fix.sql\x00"

# адреса функций/стабов
F_LOG = 0x00713960          # лог
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


def call(reg: str, target: int) -> list[str]:
    return lui_addiu(reg, target) + [f"jalr {reg}"]


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
    L: list[str] = [
        "DBFIX:",
        "addiu sp, sp, -0x30",
        "sw ra, 0x2c(sp)",
        "sw s0, 0x28(sp)",
        "sw s1, 0x24(sp)",
        "sw s2, 0x20(sp)",
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
    L += call("t9", P_MALLOC)
    L += [
        "ori a0, zero, 0x8000",
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
        "lui t0, 0xbc",
        "lw t0, 0x18f0(t0)",
        "lw a0, 0(t0)",
        "move a1, s1",
        "move a2, zero",
        "move a3, zero",
        "sw zero, 0x10(sp)",
    ]
    L += call("t9", F_EXEC)
    # free(buf)
    L += call("t9", P_FREE)
    L += [
        "move a0, s1",
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


def hook_log() -> list[str]:
    """Вызывается вместо `jal FUN_00713960` (лог "Scanner stopped", 0x71d0b0):
    логирует, затем выполняет DBFIX. Проверенная точка: на ней БД после
    «обновления медиатеки» собирается правильно и висняка нет.

    (Точка 0x4e980c — эпилог `FUN_004e97c0` — ОТВЕРГНУТА: это общая функция
    ожидания, вызывается и при подключении USB, и наш SQL вешал плеер.)"""
    L: list[str] = [
        "addiu sp, sp, -0x20",
        "sw ra, 0x1c(sp)",
        "sw a0, 0x18(sp)",
        "sw a1, 0x14(sp)",
    ]
    L += call("t9", F_LOG)
    L += call("t8", STUB_VA)          # DBFIX (jalr — из RX иначе нельзя)
    L += [
        "nop",                        # delay-слот jalr
        "lw a0, 0x18(sp)",
        "lw a1, 0x14(sp)",
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

    fix = assemble(STUB_VA, dbfix())
    hook_addr = STUB_VA + len(fix)
    hook = assemble(hook_addr, hook_log())
    stub = fix + hook
    expected = 3 << 26 | (hook_addr >> 2)

    cur = struct.unpack_from("<I", d, HOOK_VA - VTO)[0]
    done = cur == expected

    if check:
        print(f"{HOOK_VA:#x} = {cur:#010x} ({'хук' if done else 'сток'})")
        print(f"  DBFIX @ {STUB_VA:#x}, hook @ {hook_addr:#x}, path @ {PATH_VA:#x}")
        return 0

    if done:
        print("уже пропатчено (db autofix)")
        return 0
    if cur != HOOK_ORIG:
        raise SystemExit(f"{HOOK_VA:#x}: ожидался {HOOK_ORIG:#010x}, найдено {cur:#010x}")

    if STUB_VA + len(stub) > PATH_VA:
        raise SystemExit(f"стаб перекрывает путь: {STUB_VA+len(stub):#x} > {PATH_VA:#x}")
    off = STUB_VA - VTO
    if not all(b == 0 for b in d[off : PATH_VA - VTO + len(PATH)]):
        raise SystemExit(f"RX-место {STUB_VA:#x}..{PATH_VA:#x} занято")
    d[off : off + len(stub)] = stub
    d[PATH_VA - VTO : PATH_VA - VTO + len(PATH)] = PATH
    struct.pack_into("<I", d, HOOK_VA - VTO, expected)

    path.write_bytes(bytes(d))
    print(f"{path}: авто-фикс БД по завершении скана (DBFIX @{STUB_VA:#x}, hook @{hook_addr:#x})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
