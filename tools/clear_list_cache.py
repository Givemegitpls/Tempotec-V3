#!/usr/bin/env python3
"""Очистка кэша списков медиатеки (list_tb_* + MANAGER_TABLE).

Зачем: `list_tb_N` — кэш строк списка, ключ (`artist\\...`, `album\\...`) хранится
в `MANAGER_TABLE`. После прошивки с новой сборкой бинаря старый кэш остаётся в
`/data/usrlocal_media.db`, и вид переиспользует его вместо пересборки. Если обложки
в «Artists → артист» остались старыми/неверными — один раз очистить кэш:

    adb pull /data/usrlocal_media.db work/device/media.db
    python3 tools/clear_list_cache.py work/device/media.db
    adb push work/device/media.db /data/usrlocal_media.db
    adb shell 'sync; reboot'

Медиатеку (`MEDIA_TABLE` и прочие данные) скрипт НЕ трогает — только кэш списков.
Обычное «обновление медиатеки» в плеере тоже помогает, но не гарантированно.
"""
from __future__ import annotations

import sqlite3
import sys
from collections.abc import Iterable


def clear(path: str) -> None:
    con = sqlite3.connect(path)
    tabs: Iterable[str] = [
        r[0]
        for r in con.execute(
            "select name from sqlite_master where type='table' and name like 'list_tb_%'"
        )
    ]
    n = 0
    for t in tabs:
        n += con.execute(f'delete from "{t}"').rowcount
    con.execute("delete from MANAGER_TABLE")
    con.commit()
    con.execute("vacuum")
    con.commit()
    con.close()
    print(f"{path}: очищено list_tb-таблиц={len(list(tabs))}, строк={n}, MANAGER_TABLE очищена")


def main() -> int:
    args = sys.argv[1:]
    if len(args) != 1:
        raise SystemExit(__doc__)
    clear(args[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
