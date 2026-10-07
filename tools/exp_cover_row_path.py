#!/usr/bin/env python3
"""Эксперимент: per-row путь обложки в «альбомы артиста» (col2 = rec+0x20c).

Предпосылка (Ghidra + устройство):
- `FUN_004a52a0` строка 151 (asm 0x4a5528) кладёт в запись обложки
  (+0x524) путь, с которого парсер `FUN_004ca500` ищет картинку.
- Хак `exp_cover_artist_path.py` уже подменял источник на `local_ec0+4`
  (rec+0x004 = SQL col1) — но в kind9+combo col1 = ИМЯ альбома, поэтому
  у всех строк одинаковая обложка.
- Путь альбома лежит в col2 (rec+0x20c, $sp+0x22c): combo-шаблон INSERT
  (`exp_coverpath_combo.py`) кладёт туда подзапрос path из MEDIA_TABLE;
  код и так копирует его в cover+0x738 (asm 0x4a5708+) — проверено.

Правка. Вариант на устройстве: 0x4a5528 = addiu a1, sp, 0x24 (кол1);
меняем на rec+0x20c. Вариант со стока: 0x4a5528 = addiu a1, s0, 0x3de0.

    0x4a5528: addiu a1, sp, 0x24   ->   addiu a1, sp, 0x22c
           (или addiu a1, s0, 0x3de0  ->  addiu a1, sp, 0x22c)

Использование:
    python3 tools/exp_cover_row_path.py <hiby_player> [--check]
"""

from __future__ import annotations

import sys
from pathlib import Path

VA = 0x4A5528
OFFSET = VA - 0x400000
TARGET = bytes.fromhex("2c02a527")  # addiu a1, sp, 0x22c  (rec + 0x20c = col2)
SOURCES = {
    bytes.fromhex("2400a527"): "addiu a1, sp, 0x24    (col1, exp_cover_artist_path)",
    bytes.fromhex("e03d0526"): "addiu a1, s0, 0x3de0  (view+0x3de0, сток)",
}


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--check"]
    if len(args) != 1:
        raise SystemExit(__doc__)
    check = "--check" in sys.argv
    path = Path(args[0])
    data = bytearray(path.read_bytes())
    cur = bytes(data[OFFSET : OFFSET + 4])
    if cur == TARGET:
        print("правка уже стоит (a1 = sp+0x22c, col2/path)")
        return 0
    if cur not in SOURCES:
        raise SystemExit(
            f"по смещению {OFFSET:#x} неожиданное слово {cur.hex()} — см. докстринг"
        )
    if check:
        print("правки нет")
        return 0
    data[OFFSET : OFFSET + 4] = TARGET
    path.write_bytes(bytes(data))
    print(f"{path}: путь обложки -> rec+0x20c (col2, path); было: {SOURCES[cur]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
