#!/usr/bin/env python3
"""Патч чистки скана: не удалять разобранные составляющие `artist`/`album_artist`.

Проблема: при скане слот 143 (`ARTIST2_TABLE`) и слот 146 (`ALBUM_ARTIST2_TABLE`)
удаляют записи, которых нет как отдельного тега в `MEDIA2_TABLE`:
`DELETE FROM ARTIST2_TABLE WHERE artist not in (SELECT DISTINCT artist FROM
MEDIA2_TABLE)`. `MEDIA2_TABLE` хранит СКЛЕЕННЫЙ тег (`A;B`), поэтому
составляющие, добавленные split-триггером, удаляются → разбор «самоубивается»
на следующем обновлении медиатеки.

Правка: условие → «удалять, только если составляющей НЕТ ни в одном теге
`MEDIA2_TABLE` (с учётом `;`)». Строки длиннее стоковых → переносятся в свободные
места: слот 143 → `.rodata` `0x93f90c`; слот 146 → RX-зазор `0xa7ee1c`.

Инвариант: stock-143 на реальной БД удаляет 184 из 244 артистов, patched — 0.

Идемпотентно, `--check`.

    python3 tools/patch_artist_cleanup.py <hiby_player> [--check]
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

VTO = 0x400000
SQL_TABLE = 0x9B7730

# (slot, old_va, new_va, new_limit, old_sql, new_sql)
ARTIST = (
    143, 0x9C2090, 0x93F90C, 0x93FA00,
    b"DELETE FROM ARTIST2_TABLE WHERE artist not in (SELECT DISTINCT artist from MEDIA2_TABLE)",
    b"DELETE FROM ARTIST2_TABLE WHERE NOT EXISTS "
    b"(SELECT 1 FROM MEDIA2_TABLE m WHERE "
    b"(';'||substr(m.artist,1,length(m.artist))||';') LIKE '%;'||"
    b"substr(ARTIST2_TABLE.artist,1,length(ARTIST2_TABLE.artist))||';%')",
)
ALBUM_ARTIST = (
    146, 0x9C219C, 0xA7EE1C, 0xA7EF80,
    b"DELETE FROM ALBUM_ARTIST2_TABLE WHERE album_artist not in (SELECT DISTINCT album_artist from MEDIA2_TABLE)",
    b"DELETE FROM ALBUM_ARTIST2_TABLE WHERE NOT EXISTS "
    b"(SELECT 1 FROM MEDIA2_TABLE m WHERE "
    b"(';'||substr(m.album_artist,1,length(m.album_artist))||';') LIKE '%;'||"
    b"substr(ALBUM_ARTIST2_TABLE.album_artist,1,length(ALBUM_ARTIST2_TABLE.album_artist))||';%')",
)
SPECS = (ARTIST, ALBUM_ARTIST)


def main() -> int:
    argv = sys.argv[1:]
    check = "--check" in argv
    args = [a for a in argv if a != "--check"]
    if len(args) != 1:
        raise SystemExit(__doc__)
    path = Path(args[0])
    d = bytearray(path.read_bytes())

    states = []
    all_done = True
    for slot, old_va, new_va, limit, old, new in SPECS:
        slot_off = SQL_TABLE - VTO + 4 * slot
        cur_va = struct.unpack_from("<I", d, slot_off)[0]
        at_new = cur_va == new_va
        cur = bytes(d[new_va - VTO:new_va - VTO + len(new) + 1]) if at_new else b""
        done = at_new and cur == new + b"\x00"
        all_done &= done
        states.append((slot, cur_va, old_va, new_va, limit, old, new, done))

    if check:
        for slot, cur_va, old_va, new_va, limit, old, new, done in states:
            state = ("новая" if done else "иное" if cur_va == new_va
                     else "сток" if cur_va == old_va else f"неизвестно {cur_va:#x}")
            print(f"слот {slot}: {cur_va:#x} ({state})")
        return 0

    if all_done:
        print("уже пропатчено (cleanup artist+album_artist)")
        return 0

    for slot, cur_va, old_va, new_va, limit, old, new, done in states:
        if done:
            continue
        need = len(new) + 1
        if new_va + need > limit:
            raise SystemExit(f"слот {slot}: строка не влезает: {new_va:#x}+{need} > {limit:#x}")
        if cur_va == old_va:
            got = bytes(d[old_va - VTO:old_va - VTO + len(old) + 1])
            if got != old + b"\x00":
                raise SystemExit(f"слот {slot}: строка по {old_va:#x} не совпала: {got[:100]!r}")
            off = new_va - VTO
            if not all(b == 0 for b in d[off:off + need]):
                raise SystemExit(f"слот {slot}: место {new_va:#x} занято")
        elif cur_va != new_va:
            raise SystemExit(f"слот {slot}: ожидался {old_va:#x} или {new_va:#x}, найдено {cur_va:#x}")
        d[new_va - VTO:new_va - VTO + need] = new + b"\x00"
        struct.pack_into("<I", d, SQL_TABLE - VTO + 4 * slot, new_va)
        print(f"слот {slot} cleanup -> {new_va:#x} ({len(new)} байт SQL)")

    path.write_bytes(bytes(d))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
