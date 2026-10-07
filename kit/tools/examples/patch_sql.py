#!/usr/bin/env python3
"""Патч SQL-строк, которыми плеер собирает таблицы списков.

Зачем:
 * алфавитная полоска считает позицию как «сколько записей в диапазоне от 'A'
   до выбранной буквы», поэтому таблица списка обязана быть отсортирована по
   `character`, а записи вне A–Z должны стоять *после* букв. Иначе альбомы,
   начинающиеся с цифры или символа (`[Oops]`, `500 K`, `"…"`), стоят в начале
   списка и сдвигают все прыжки (наблюдалось как «A → символы, C → A»);
 * категория «Артисты» должна показывать авторов альбомов, поэтому её таблица
   собирается из ALBUM_ARTIST2_TABLE.

Сборка списков заменяется на вариант: буква приводится к A–Z (всё остальное —
маркер `~`, он больше `z` и при COLLATE NOCASE уезжает в конец списка),
сортировка идёт по этой букве, затем по имени.

Строки лежат в таблице SQL по базе 0x9b7730 (4 байта на запись). Если новая
строка не влезает на место старой, она пишется в неиспользуемый «хвост» нулей
в .rodata (0x93f610, до 0x93fce0 к нему нет ссылок), а указатель в слоте
таблицы переписывается.

Скрипт идемпотентен: слот считается пропатченным, если в текущей строке есть
маркер (см. TAG), иначе строка обязана начинаться с ожидаемого префикса.

Использование:
    python3 tools/patch_sql.py <hiby_player> [--check]
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

SQL_TABLE_BASE = 0x9B7730
SQL_TABLE_OFFSET = SQL_TABLE_BASE - 0x400000
FREE_SPACE_START = 0x93F610
FREE_SPACE_END = 0x93FCE0
VADDR_TO_OFFSET = 0x400000

# буква -> A-Z как есть, всё остальное в хвост ('~' больше 'z', важно при NOCASE)
LETTER = "(CASE WHEN character BETWEEN 'A' AND 'Z' THEN character ELSE '~' END)"

# (слот, ожидаемый префикс строки, новая строка)
PATCHES: list[tuple[int, bytes, bytes]] = [
    (
        125,
        b"INSERT INTO ARTIST_TABLE ",
        f"INSERT INTO ARTIST_TABLE SELECT id,album_artist,{LETTER},cn,ctime,mtime,"
        f"pinyin_charater FROM ALBUM_ARTIST2_TABLE ORDER BY 3,album_artist".encode(),
    ),
    (
        124,
        b"INSERT INTO ALBUM_TABLE ",
        f"INSERT INTO ALBUM_TABLE SELECT id,album,{LETTER},cn,ctime,mtime,mqa,"
        f"pinyin_charater FROM ALBUM2_TABLE ORDER BY 3,album".encode(),
    ),
    (
        126,
        b"INSERT INTO ALBUM_ARTIST_TABLE ",
        f"INSERT INTO ALBUM_ARTIST_TABLE SELECT id,album_artist,{LETTER},cn,ctime,mtime,mqa,"
        f"pinyin_charater FROM ALBUM_ARTIST2_TABLE ORDER BY 3,album_artist".encode(),
    ),
    (
        127,
        b"INSERT INTO GENRE_TABLE ",
        f"INSERT INTO GENRE_TABLE SELECT id,genre,{LETTER},cn,ctime,mtime,"
        f"pinyin_charater FROM GENRE2_TABLE ORDER BY 3,genre".encode(),
    ),
]

TAG = b"THEN character ELSE '~'"

# Точечные правки *внутри* SQL-строк (длина сохраняется, хвост добивается
# пробелами): список треков тоже должен идти в порядке букв, иначе прыжок по
# полоске не совпадает с позициями (в «All» русские треки лежат в конце списка,
# отсюда «X/Y → Ж»). Порядок применения — от длинных шаблонов к коротким.
TEXT_PATCHES: list[tuple[bytes, bytes]] = [
    (b"ORDER BY has_child_file ASC, name COLLATE pinyin", b"ORDER BY character,has_child_file,name"),
    (b"ORDER BY path COLLATE pinyin, cue_id", b"ORDER BY character,path,cue_id"),
    (b"ORDER BY path COLLATE pinyin,cue_id", b"ORDER BY character,path,cue_id"),
    (b"ORDER BY path COLLATE pinyin,ck_id", b"ORDER BY character,path,ck_id"),
    (b"ORDER BY name COLLATE pinyin", b"ORDER BY character,name"),
    (b"ORDER BY name collate pinyin", b"ORDER BY character,name"),
    (b"ORDER BY path COLLATE pinyin", b"ORDER BY character,path"),
]
TEXT_TAG = b"ORDER BY character"


def read_cstring(data: bytes, vaddr: int) -> bytes:
    offset = vaddr - VADDR_TO_OFFSET
    end = data.find(b"\x00", offset)
    return data[offset:end]


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    check = "--check" in sys.argv
    if len(args) != 1:
        raise SystemExit(__doc__)
    path = Path(args[0])
    data = bytearray(path.read_bytes())
    free_cursor = FREE_SPACE_START

    for slot, prefix, new in PATCHES:
        slot_offset = SQL_TABLE_OFFSET + 4 * slot
        current_vaddr = struct.unpack_from("<I", data, slot_offset)[0]
        current = read_cstring(data, current_vaddr)

        if check:
            state = "patched" if TAG in current else "NЕ ПАТЧЕН"
            print(f"slot {slot}: {state}: {current[:70].decode(errors='replace')}")
            continue

        if TAG in current and current == new:
            print(f"  [skip] слот {slot}: уже пропатчен")
            continue
        if not current.startswith(prefix):
            raise SystemExit(
                f"слот {slot}: строка не похожа на ожидаемую "
                f"({current[:90]!r}, ожидался префикс {prefix!r})"
            )

        pad = (-free_cursor) % 4
        free_cursor += pad
        if free_cursor + len(new) + 1 > FREE_SPACE_END:
            raise SystemExit("не хватило свободного места в .rodata")
        offset = free_cursor - VADDR_TO_OFFSET
        data[offset : offset + len(new) + 1] = new + b"\x00"
        struct.pack_into("<I", data, slot_offset, free_cursor)
        print(f"  [ok]   слот {slot}: {free_cursor:#x} ({len(new)} байт, было {len(current)})")
        free_cursor += len(new) + 1

    if not check:
        for old, new in TEXT_PATCHES:
            count = data.count(old)
            if count == 0:
                continue
            if len(new) > len(old):
                raise SystemExit(f"новая сортировка длиннее исходной: {old!r}")
            replacement = new + b" " * (len(old) - len(new))
            data = data.replace(old, replacement)
            print(f"  [ok]   сортировка: {old.decode()!r} -> {new.decode()!r} ({count} шт.)")

    if check:
        print(f"сортировок вида {TEXT_TAG.decode()!r}: {data.count(TEXT_TAG)}")

    if not check:
        path.write_bytes(bytes(data))
        print(f"{path}: записано")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
