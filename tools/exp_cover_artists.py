#!/usr/bin/env python3
"""Обложки в «Artists -> артист -> альбомы» (вариант B).

Источник данных вида «альбомы артиста» — `FUN_004a9180`; он наполняет список
через `list_tb_` (`FUN_0070a3a0(9,...)`), где строки содержат только имя
альбома (без пути), поэтому парсер обложек ничего не находит.

«Albums» использует источник `FUN_004a95e0` -> `FUN_004a1ba0(view, list,
ctx, L"album", ...)`: он создаёт контроллер обложек и резолвит путь из
`ALBUM_TABLE`/`MEDIA_TABLE` по ключу `album`.

Правка: переназначаем класс вида 88 на `FUN_004a95e0` и заменяем литерал
`L"album"` ключом из аргумента контекста (`a2` = имя артиста в этой обёртке).

Использование:
    python3 tools/exp_cover_artists.py <hiby_player>
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

DATA_DELTA = 0x410000
CB_BASE = 0xABD4CC
IDX = 88
CB_OFF = CB_BASE - DATA_DELTA + IDX * 0x20C
CB_OLD = 0x4A9180
CB_NEW = 0x4A95E0

# FUN_004a95e0: хвост с 0x4a9638. Исходно: lw a3, L"album" (0x93bdbc) и вызов
# FUN_004a1ba0(view, list, ctx, key, ...). В этой обёртке a2 (она же s1) держит
# контекст — имя артиста; используем его как ключ, чтобы запросы фильтровали
# по артисту, но работал путь/обложки от «Albums».
CODE_OFF = 0x4A9638 - 0x400000
CODE_NEW = [
    0xAFB30010,  # sw s3, 0x10(sp)
    0x02002021,  # move a0, s0
    0x02203821,  # move a3, s1          (key = контекст/артист)
    0x02402821,  # move a1, s2
    0x0C1286E8,  # jal FUN_004a1ba0
    0x02002021,  # move a0, s0          (delay)
    0x8FBF003C,  # lw ra, 0x3c(sp)
    0x8FB30038,  # lw s3, 0x38(sp)
    0x8FB20034,  # lw s2, 0x34(sp)
    0x8FB10030,  # lw s1, 0x30(sp)
    0x8FB0002C,  # lw s0, 0x2c(sp)
    0x03E00008,  # jr ra
    0x27BD0040,  # addiu sp, sp, 0x40   (delay)
    0x00000000,
    0x00000000,
]


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    path = Path(sys.argv[1])
    data = bytearray(path.read_bytes())

    cb = struct.unpack_from("<I", data, CB_OFF)[0]
    if cb == CB_NEW:
        print("callback уже переназначен")
    elif cb == CB_OLD:
        struct.pack_into("<I", data, CB_OFF, CB_NEW)
        print(f"класс вида 88: {CB_OLD:#x} -> {CB_NEW:#x}")
    else:
        raise SystemExit(f"неожиданный callback по {CB_OFF:#x}: {cb:#x}")

    for i, w in enumerate(CODE_NEW):
        struct.pack_into("<I", data, CODE_OFF + 4 * i, w)
    print(f"FUN_004a95e0: хвост переписан ({len(CODE_NEW)} инструкций)")

    path.write_bytes(bytes(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
