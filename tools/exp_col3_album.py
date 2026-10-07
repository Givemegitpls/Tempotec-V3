#!/usr/bin/env python3
"""Эксперимент: col3 (album) в kind9-шаблоне INSERT = ?2 (имя альбома).

Обоснование (разбор FUN_004a34a0 / FUN_004ca2e0, 2026-10-04):
- отрисовка обложки строки: FUN_004a34a0 сначала спрашивает image-кэш
  контроллера через FUN_004cbb40(ctrl, rec+0x82c(narrow), rec+0x004,
  rec+0x42c, ...) = FUN_004ca2e0; если мiss → fallback-цикл по row-структурам;
  если и там miss → *param_4 = *(view+i*0x40+0x2ae8) = ОБЩАЯ ЗОГЛУШКА
  (one picture for all rows — наблюдаемый дефект).
- Правило lookup в FUN_004ca2e0 (вторая ветка): если rec+0x42c (col3=album)
  пуст И entry+0x220 (album) пуст, условие `iVar4 != 0 || *param_4 == 0`
  уводит в "не совпало" (у стоковых списков col3 = имя альбома и ветка
  работает). В kind9+combo шаблоне col3 = 0 (пусто) → заглушка.

Правка: в RX-шаблоне INSERT добавить col3 = ?2 (имя альбома):
    VALUES (?1,(SELECT path … album=?2 LIMIT 1),?2,0,…)
 -> VALUES (?1,(SELECT path … album=?2 LIMIT 1),?2,?2,0,…)

Строка становится на 2 байта длиннее; за шаблоном в RX — нули, места достаточно.

Использование:
    python3 tools/exp_col3_album.py <hiby_player> [--check]
"""

from __future__ import annotations

import sys
from pathlib import Path

VA = 0xA7E800
OFFSET = VA - 0x40000
OFFSET = VA - 0x400000
OLD = b"INSERT INTO %s%d VALUES (?1,(SELECT path FROM MEDIA_TABLE WHERE album=?2 LIMIT 1),?2,0,0,0,0,0,?3"
NEW = b"INSERT INTO %s%d VALUES (?1,(SELECT path FROM MEDIA_TABLE WHERE album=?2 LIMIT 1),?2,?2,0,0,0,0,?3"


def main() -> int:
    argv = sys.argv[1:]
    check = "--check" in argv
    args = [a for a in argv if a != "--check"]
    if len(args) != 1:
        raise SystemExit(__doc__)
    path = Path(args[0])
    data = bytearray(path.read_bytes())
    end = data.find(b"\x00", OFFSET)
    cur = bytes(data[OFFSET:end])
    if cur.startswith(NEW_str := NEW[:-1]):
        print("правка уже стоит (col3 = ?2)")
        return 0
    old_end = end
    old_str = cur
    if not old_str.startswith(OLD[:-1]):
        raise SystemExit(f"шаблон не опознан: {old_str[:64]!r}")
    if check:
        print("правки нет")
        return 0
    # ensure tail zeros beyond old terminator
    if data[old_end + 1 : old_end + 3] != b"\x00\x00":
        raise SystemExit(f"за шаблоном не нули: {data[old_end+1:old_end+3].hex()}")
    data[OFFSET : old_end + 3] = NEW + b"\x00\x00"  # +1 zero for terminator +1 spare
    path.write_bytes(bytes(data))
    print(f"{path}: col3 (album) = ?2 в RX-шаблоне {VA:#x}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
