#!/usr/bin/env python3
"""Список «альбомы артиста»: фильтр по составляющей тега `artist` (разбор по `;`).

`tools/split_artists_db.py` разбирает склейки `artist` (`Noize MC;Anacondaz`) в
`ARTIST2_TABLE` на отдельных соавторов. Чтобы у соавтора были видны альбомы
совместных треков, фильтр списка альбомов должен матчить составляющую, а не
строку целиком.

Было (сток):  ... WHERE artist like ? ORDER BY album collate pinyin
Стало:        ... WHERE (';'||substr(artist,1,length(artist))||';')
                        LIKE '%;'||substr(?1,1,length(?1))||';%' ORDER BY album collate pinyin

ПОЧЕМУ НЕ `replace(...,char(0),'')` (первый черновик — НЕ работает):
значения в БД хранятся с хвостовым NUL (`'Green Crow\\x00'`). `replace` с образцом
`char(0)` NUL не вырезает (образец обрезается до пустой строки), а встроенный LIKE
обходит субъект как C-строку и обрывается на NUL — поэтому `';'||artist||';'`
теряет завершающую `';'` и последняя составляющая/одиночный артист не матчатся.
`substr(x,1,length(x))` снимает NUL (`length()` считает символы до NUL). Проверено
на копии реальной БД: «Дурной Вкус» 0 -> 4 альбома (сток 4), «Дэн Субботин» 0 -> 5,
«Green Crow» 10 -> 14.

Строка длиннее исходной, поэтому пишется в свободный «хвост» нулей `.rodata`
(0x93fb00), а указатель в слоте 182 таблицы SQL (база 0x9b7730) переписывается.

Идемпотентно, `--check`; умеет перезаписывать прежний (сломанный) вариант строки.

    python3 tools/exp_albums_by_component.py <hiby_player> [--check]
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

VTO = 0x400000
SQL_TABLE = 0x9B7730
SLOT = 182
OLD_VA = 0x9C284C
NEW_VA = 0x93FB00
# верхняя граница свободного места (дальше .rodata-дыра кончается)
NEW_LIMIT = 0x93FD00

OLD = b"SELECT DISTINCT album FROM MEDIA_TABLE WHERE artist like ? ORDER BY album collate pinyin"
BROKEN = (
    b"SELECT DISTINCT album FROM MEDIA_TABLE WHERE "
    b"(';'||replace(artist,char(0),'')||';') LIKE '%;'||replace(?,char(0),'')||';%' "
    b"ORDER BY album collate pinyin"
)
NEW = (
    b"SELECT DISTINCT album FROM MEDIA_TABLE WHERE "
    b"(';'||substr(artist,1,length(artist))||';') "
    b"LIKE '%;'||substr(?1,1,length(?1))||';%' "
    b"ORDER BY album collate pinyin"
)


def main() -> int:
    argv = sys.argv[1:]
    check = "--check" in argv
    args = [a for a in argv if a != "--check"]
    if len(args) != 1:
        raise SystemExit(__doc__)
    path = Path(args[0])
    d = bytearray(path.read_bytes())

    slot_off = SQL_TABLE - VTO + 4 * SLOT
    cur_va = struct.unpack_from("<I", d, slot_off)[0]
    cur = bytes(d[NEW_VA - VTO : NEW_VA - VTO + 400].split(b"\x00")[0]) if cur_va == NEW_VA else b""

    if check:
        state = ("сток" if cur_va == OLD_VA else
                 "рабочая" if cur == NEW else
                 "сломанная replace/char(0)" if cur == BROKEN else "иное")
        print(f"слот {SLOT}: {cur_va:#x} ({state})")
        print(f"строка @{NEW_VA:#x}: {cur[:200]!r}")
        return 0

    if cur_va == NEW_VA:
        if cur == NEW:
            print("уже пропатчено (album list by component)")
            return 0
        if cur != BROKEN:
            raise SystemExit(f"@{NEW_VA:#x} неожиданная строка: {cur[:120]!r}")
    elif cur_va == OLD_VA:
        old = bytes(d[OLD_VA - VTO : OLD_VA - VTO + len(OLD) + 1])
        if old != OLD + b"\x00":
            raise SystemExit(f"строка по {OLD_VA:#x} не совпала: {old[:120]!r}")
    else:
        raise SystemExit(f"слот {SLOT}: ожидался {OLD_VA:#x} или {NEW_VA:#x}, найдено {cur_va:#x}")

    off = NEW_VA - VTO
    need = len(NEW) + 1
    if NEW_VA + need > NEW_LIMIT:
        raise SystemExit(f"строка не влезает: {NEW_VA:#x}+{need} > {NEW_LIMIT:#x}")
    if cur_va == OLD_VA and not all(b == 0 for b in d[off : off + need]):
        raise SystemExit(f"место {NEW_VA:#x} занято")
    d[off : off + need] = NEW + b"\x00"
    struct.pack_into("<I", d, slot_off, NEW_VA)

    path.write_bytes(bytes(d))
    print(f"{path}: список альбомов артиста -> разбор по ';' (слот {SLOT}, строка @{NEW_VA:#x})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
