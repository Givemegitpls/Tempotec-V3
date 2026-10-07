#!/usr/bin/env python3
"""Эксперимент: список «альбомы артиста» рисуется видом категории «Альбомы».

В обёртке открытия списка альбомов артиста (0x4a8b20) имя вида загружается парой
    lui   a2, 0x96
    addiu a2, a2, -0x2d1c      ; 0x95d2e4 -> "vg_listview_albums_of_an_artist"
Меняем смещение на -0x2d58 (0x95d2a8 -> "vg_listview_album" — вид категории
«Альбомы», который умеет показывать обложки).

Использование:
    python3 tools/exp_album_view.py <hiby_player>
"""

from __future__ import annotations

import sys
from pathlib import Path

OFFSET = 0x4A8B84 - 0x400000
OLD = bytes.fromhex("e4d2c624")  # addiu a2, a2, -0x2d1c
NEW = bytes.fromhex("a8d2c624")  # addiu a2, a2, -0x2d58


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    path = Path(sys.argv[1])
    data = bytearray(path.read_bytes())
    if data[OFFSET : OFFSET + 4] == NEW:
        print("правка уже стоит")
        return 0
    if data[OFFSET : OFFSET + 4] != OLD:
        raise SystemExit(f"не совпала инструкция: {data[OFFSET:OFFSET+4].hex()}")
    data[OFFSET : OFFSET + 4] = NEW
    path.write_bytes(bytes(data))
    print(f"{path}: вид списка альбомов артиста -> vg_listview_album (0x95d2a8)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
