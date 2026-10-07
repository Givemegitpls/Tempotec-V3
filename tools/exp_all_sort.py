#!/usr/bin/env python3
"""Список «All»: сортировка по `character,name` (а не физический порядок строк).

Список «All» строится SQL `SELECT * FROM MEDIA_TABLE limit ? offset ?` — без
ORDER BY, т.е. в порядке rowid (физический порядок). После «обновления
медиатеки» `MEDIA_TABLE` пересобирается из `MEDIA2_TABLE`, где `character` —
буква исполнителя, а триггер `fix_char_MEDIA_TABLE` затем переписывает её на
букву названия. Физический порядок перестаёт совпадать с `character`, и треки
на `!$"`, цифры и т.п. (буква `~`) оказываются в начале списка, а полоска
прыгает мимо.

Правка: добавить `ORDER BY character,name` в SQL списка «All». Тогда порядок
всегда совпадает с `character` (и с прыжком по полоске), независимо от
физического порядка `MEDIA_TABLE`.

Строка длиннее исходной, поэтому пишется в свободный «хвост» нулей в `.rodata`
(0x93fa00), а указатели во ВСЕХ слотах таблицы 0x9b7730, указывающих на старую
строку, переписываются.

Идемпотентно, `--check`.

    python3 tools/exp_all_sort.py <hiby_player> [--check]
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

VTO = 0x400000
SQL_TABLE = 0x9B7730
SQL_TABLE_SLOTS = 400  # с запасом
NEW_VA = 0x93FA00  # свободный хвост .rodata (нули)
OLD = b"SELECT * FROM MEDIA_TABLE limit ? offset ?"
NEW = b"SELECT * FROM MEDIA_TABLE ORDER BY character,name limit ? offset ?"


def main() -> int:
    argv = sys.argv[1:]
    check = "--check" in argv
    args = [a for a in argv if a != "--check"]
    if len(args) != 1:
        raise SystemExit(__doc__)
    path = Path(args[0])
    d = bytearray(path.read_bytes())

    base = SQL_TABLE - VTO
    slots = []
    for i in range(SQL_TABLE_SLOTS):
        off = base + 4 * i
        if off + 4 > len(d):
            break
        if struct.unpack_from("<I", d, off)[0] == 0x9C2438:
            slots.append(i)

    done = len(slots) > 0 and all(
        struct.unpack_from("<I", d, base + 4 * i)[0] == NEW_VA for i in slots
    )

    if check:
        print(f"слоты на 0x9c2438: {slots}")
        for i in slots:
            v = struct.unpack_from("<I", d, base + 4 * i)[0]
            print(f"  слот {i}: {v:#x}")
        print(f"строка @{NEW_VA:#x}: {d[NEW_VA - VTO:NEW_VA - VTO + len(NEW) + 1]!r}")
        return 0

    if not slots:
        raise SystemExit("не найдено слотов, указывающих на 0x9c2438")
    if done:
        print("уже пропатчено (All sort)")
        return 0

    # проверить, что все слоты ещё указывают на старую строку
    for i in slots:
        v = struct.unpack_from("<I", d, base + 4 * i)[0]
        if v not in (0x9C2438, NEW_VA):
            raise SystemExit(f"слот {i}: неожиданный указатель {v:#x}")

    off = NEW_VA - VTO
    if not all(b == 0 for b in d[off : off + len(NEW) + 1]):
        raise SystemExit(f"место {NEW_VA:#x} в .rodata занято")
    d[off : off + len(NEW) + 1] = NEW + b"\x00"

    for i in slots:
        struct.pack_into("<I", d, base + 4 * i, NEW_VA)

    path.write_bytes(bytes(d))
    print(f"{path}: список «All» -> ORDER BY character,name (слоты {slots}, строка @{NEW_VA:#x})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
