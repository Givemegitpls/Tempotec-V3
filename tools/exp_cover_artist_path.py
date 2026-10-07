#!/usr/bin/env python3
"""Эксперимент: обложки в списке «альбомы артиста» через путь из записи.

Причина, по которой обложек нет (разобрано по Ghidra + дампам):

    FUN_004a52a0 (обновление записей обложек вида), строка 151:
        FUN_00420f20(record + 0x524, view + 0x3de0, 0x104);
    т.е. wide-путь для поиска обложки берётся из буфера пути САМОГО ВИДА
    (`view+0x3de0`). У категории «Альбомы» там лежит путь выбранного альбома,
    поэтому обложки находятся. У вида `vg_listview_albums_of_an_artist`
    (type 0x12) там служебная строка вида `"artist\\Anacondaz"`, папки нет —
    обложек нет.

Запись обложки наполняется из локальной `local_ec0` (0xa88) тем же кодом:
    memset(&local_ec0, 0, 0xa88);            // 0x4a5380: a0 = $sp+0x20
    FUN_004369a0(view+0x3de0, idx, &local_ec0);  // 0x4a53c4
а `local_ec0` — это медиа-запись, где SQL-колонка `path` лежит по +0x004
(см. FUN_006fc100: колонка 1 -> +0x004, wide).

Правка: в вызове копирования пути (0x4a5528) подставляем источник
`local_ec0 + 4` вместо `view + 0x3de0`:

    0x4a5528:  addiu $a1, $s0, 0x3de0   ->   addiu $a1, $sp, 0x24

($sp+0x20 = local_ec0, +4 — поле wide-path.)

Использование:
    python3 tools/exp_cover_artist_path.py <hiby_player>
"""

from __future__ import annotations

import sys
from pathlib import Path

VA = 0x4A5528
OFFSET = VA - 0x400000
OLD = bytes.fromhex("e03d0526")  # addiu a1, s0, 0x3de0
NEW = bytes.fromhex("2400a527")  # addiu a1, sp, 0x24


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    path = Path(sys.argv[1])
    data = bytearray(path.read_bytes())
    cur = bytes(data[OFFSET : OFFSET + 4])
    if cur == NEW:
        print("правка уже стоит")
        return 0
    if cur != OLD:
        raise SystemExit(
            f"по смещению {OFFSET:#x} ожидалось {OLD.hex()}, найдено {cur.hex()}"
        )
    data[OFFSET : OFFSET + 4] = NEW
    path.write_bytes(bytes(data))
    print(f"{path}: путь обложки -> local_ec0+4 (смещение {OFFSET:#x})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
