#!/usr/bin/env python3
"""Списки «треки артиста»: фильтр по составляющей тега `artist` (разбор по `;`).

Переключатель в Artists открывает список «все треки артиста»
(`songs_of_artist_all`), который собирается из MEDIA_TABLE по ключу-артисту.
Таких SQL-строк две, и обе фильтруют точным совпадением:

  * `0x9ba000`: `... WHERE artist like ? AND has_child_file = 0` (kind5-main, файлы);
    адресуется парой `0x708dfc lui a1,0x9c` + `0x708e08 addiu a1,a1,-0x6000`.
  * `0x9bb000`: `... WHERE artist = ? )` (без has_child_file);
    адресуется парой `0x70a078 lui a1,0x9c` + `0x70a084 addiu a1,a1,-0x5000`.
    Именно эта строка используется переключателем «альбомы ⇄ все треки»,
    поэтому без её правки у соавтора список пуст («no music»).

Правка: `artist like ?` / `artist = ?` -> матч по составляющей

    (';'||substr(artist,1,length(artist))||';')
        LIKE '%;'||substr(?1,1,length(?1))||';%'

ПОЧЕМУ НЕ `replace(...,char(0),'')`: значения в БД хранятся с хвостовым NUL, а
`replace` с образцом `char(0)` его не вырезает (образец обрезается до пустой
строки), и встроенный LIKE обходит субъект как C-строку, обрываясь на NUL.
`substr(x,1,length(x))` снимает NUL (`length()` считает символы до NUL).

Обе строки длиннее исходных и в `.rodata` не влезают, поэтому пишутся в свободный
RX-зазор: `0x9bb000` -> `0xa7e900`, `0x9ba000` -> `0xa7eb00` (за kind9-шаблоном
`0xa7e800`). Пары `lui/addiu` перенаправляются на новые адреса
(`lui a1,0xa8` + `addiu a1,a1,-0x1700` / `-0x1500`). RX-строки только читаются.

Идемпотентно, `--check`; умеет перезаписывать прежние (сломанные) варианты.

    python3 tools/exp_artist_tracks_component.py <hiby_player> [--check]
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

VTO = 0x400000
RX_LIMIT = 0xA7F000  # phdr2 filesz = 0x67f000 (VA 0xa7f000)

# рабочий фильтр по составляющей
NEW_SUB = (
    b"(';'||substr(artist,1,length(artist))||';') "
    b"LIKE '%;'||substr(?1,1,length(?1))||';%'"
)
# сломанный черновик (replace/char(0)) — уметь перезаписывать
BROKEN_SUB = (
    b"(';'||replace(artist,char(0),'')||';') LIKE '%;'||replace(?,char(0),'')||';%'"
)

# (старый VA строки, old-sub, LUI_VA, ADDIU_VA, stock_lui, stock_addiu,
#  new_VA, new_lui, new_addiu)
SITES = [
    dict(
        old_va=0x9BB000, old_sub=b"artist = ?",
        lui_va=0x70A078, addiu_va=0x70A084,
        stock_lui=0x3C05009C, stock_addiu=0x24A5B000,
        new_va=0xA7E900, new_lui=0x3C0500A8, new_addiu=0x24A5E900,
    ),
    dict(
        old_va=0x9BA000, old_sub=b"artist like ?",
        lui_va=0x708DFC, addiu_va=0x708E08,
        stock_lui=0x3C05009C, stock_addiu=0x24A5A000,
        new_va=0xA7EB00, new_lui=0x3C0500A8, new_addiu=0x24A5EB00,
    ),
]


def _string_at(d: bytearray, va: int, limit: int = 700) -> bytes:
    off = va - VTO
    return bytes(d[off : off + limit].split(b"\x00")[0])


def main() -> int:
    argv = sys.argv[1:]
    check = "--check" in argv
    args = [a for a in argv if a != "--check"]
    if len(args) != 1:
        raise SystemExit(__doc__)
    path = Path(args[0])
    d = bytearray(path.read_bytes())

    states = []
    for s in SITES:
        lui = struct.unpack_from("<I", d, s["lui_va"] - VTO)[0]
        addiu = struct.unpack_from("<I", d, s["addiu_va"] - VTO)[0]
        moved = lui == s["new_lui"] and addiu == s["new_addiu"]
        cur = _string_at(d, s["new_va"]) if moved else b""
        if moved and NEW_SUB in cur:
            st = "готово"
        elif moved:
            st = "перенесено-иное"
        elif lui == s["stock_lui"] and addiu == s["stock_addiu"]:
            st = "сток"
        else:
            st = "неожиданно"
        states.append((s, st))

    if check:
        for s, st in states:
            print(f"  {s['old_va']:#x} -> {s['new_va']:#x}: {st}")
        return 0

    for s, st in states:
        if st == "готово":
            continue
        if st == "неожиданно":
            raise SystemExit(
                f"сайт {s['lui_va']:#x}: неожиданные инструкции "
                f"{struct.unpack_from('<I', d, s['lui_va']-VTO)[0]:#010x} "
                f"{struct.unpack_from('<I', d, s['addiu_va']-VTO)[0]:#010x}"
            )

        if st == "перенесено-иное":
            base = _string_at(d, s["new_va"])
            if BROKEN_SUB not in base and s["old_sub"] not in base:
                raise SystemExit(f"@{s['new_va']:#x} неожиданная строка: {base[:120]!r}")
        else:  # сток
            base = _string_at(d, s["old_va"])
            if s["old_sub"] not in base:
                raise SystemExit(f"в стоке {s['old_va']:#x} нет {s['old_sub']!r}")

        new = base.replace(BROKEN_SUB, NEW_SUB).replace(s["old_sub"], NEW_SUB)
        off = s["new_va"] - VTO
        need = len(new) + 1
        if s["new_va"] + need > RX_LIMIT:
            raise SystemExit(f"строка {s['new_va']:#x}+{need} не влезает в RX")
        if st == "сток" and not all(b == 0 for b in d[off : off + need]):
            raise SystemExit(f"место {s['new_va']:#x} занято")
        d[off : off + need] = new + b"\x00"
        struct.pack_into("<I", d, s["lui_va"] - VTO, s["new_lui"])
        struct.pack_into("<I", d, s["addiu_va"] - VTO, s["new_addiu"])

    path.write_bytes(bytes(d))
    print(f"{path}: списки треков артиста -> матч по составляющей")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
