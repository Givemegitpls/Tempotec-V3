#!/usr/bin/env python3
"""Список «альбомы артиста»: фильтр по `album_artist` вместо `artist`.

Почему: поле `artist` у трека хранит склейку совместных исполнителей
(`"Дэн Субботин;Green Crow"`), а `album_artist` плеер уже разбивает по одному
автору. Список «Артисты» строится из `album_artist`, а список альбомов
фильтровался по `artist` — из-за чего у авторов с фитами список альбомов пустой
(напр. «Дэн Субботин»), а у некоторых — мусор.

Данные (реальная БД): `artist` со `;` — 17 строк, `album_artist` — 0; у 3 артистов
по `album_artist` альбомы есть, по `artist` — нет; ни один артист/альбом при этом
не теряется. Итог: `album_artist` — чистое подмножество без потерь.

Правка — по месту (строка умеет влезть), без переноса:
  было:  SELECT DISTINCT album FROM MEDIA_TABLE WHERE artist like ? ORDER BY album collate pinyin
  стало: SELECT DISTINCT album FROM MEDIA_TABLE WHERE album_artist like ? ORDER BY album

Использование:
    python3 tools/exp_albums_by_album_artist.py <hiby_player> [--check]
"""
from __future__ import annotations

import sys
from pathlib import Path

VTO = 0x400000
STR_VA = 0x9C284C
STR_OFF = STR_VA - VTO

OLD = (
    "SELECT DISTINCT album FROM MEDIA_TABLE WHERE artist like ? ORDER BY album collate pinyin"
)
NEW = "SELECT DISTINCT album FROM MEDIA_TABLE WHERE album_artist like ? ORDER BY album"
# следующий литерал начинается через 92 байта от начала строки (88 + 4 NUL слака)
SPAN = 92


def main() -> int:
    argv = sys.argv[1:]
    check = "--check" in argv
    args = [a for a in argv if a != "--check"]
    if len(args) != 1:
        raise SystemExit(__doc__)
    path = Path(args[0])
    data = bytearray(path.read_bytes())

    raw = bytes(data[STR_OFF : STR_OFF + SPAN])
    nul = raw.find(b"\x00")
    cur = raw[:nul].decode("utf-8", "replace") if nul >= 0 else raw.decode("utf-8", "replace")

    if cur == NEW:
        state = "done"
    elif cur == OLD:
        state = "stock"
    else:
        state = "unknown"

    if check:
        print(f"строка альбомов артиста ({STR_VA:#x}): {state}")
        print(f"  текущая: {cur!r}")
        return 0

    if state == "done":
        print("уже пропатчено (album_artist)")
        return 0
    if state != "stock":
        raise SystemExit(f"неожиданная строка: {cur!r}")

    if len(NEW) + 1 > SPAN:
        raise SystemExit("новая строка не влезает по месту")
    if data[STR_OFF + SPAN : STR_OFF + SPAN + 16] != b"SELECT DISTINCT ":
        raise SystemExit("за строкой не ожидаемое продолжение — прерывание")

    data[STR_OFF : STR_OFF + SPAN] = NEW.encode() + b"\x00" * (SPAN - len(NEW))
    path.write_bytes(bytes(data))
    print(f"{path}: список альбомов артиста -> album_artist ({STR_VA:#x})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
