#!/usr/bin/env python3
"""Пересортировка таблиц медиатеки по колонке `character`.

Плеер считает позицию для прыжка по букве как «сколько записей с character
меньше выбранной буквы» и берёт строку с этим номером. Значит порядок строк в
таблице списка обязан совпадать с порядком по `character` — иначе прыжок
уезжает. Скрипт перестраивает таблицы так, чтобы строки шли
`ORDER BY character, <имя>`.

Использование:
    python3 tools/reorder_db.py <media.db>
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

# таблицы списков: (таблица, колонка с именем)
LIST_TABLES = [
    ("ARTIST_TABLE", "artist"),
    ("ARTIST2_TABLE", "artist"),
    ("ALBUM_TABLE", "album"),
    ("ALBUM2_TABLE", "album"),
    ("ALBUM_ARTIST_TABLE", "album_artist"),
    ("ALBUM_ARTIST2_TABLE", "album_artist"),
    ("GENRE_TABLE", "genre"),
    ("GENRE2_TABLE", "genre"),
    # из MEDIA_TABLE читается список «All» — его тоже держим в порядке букв
    ("MEDIA_TABLE", "name"),
    ("MEDIA3_TABLE", "name"),
]


def reorder(db: sqlite3.Connection, table: str, name_col: str) -> str:
    ddl = db.execute("select sql from sqlite_master where type='table' and name=?", (table,)).fetchone()
    if not ddl or not ddl[0]:
        return "нет таблицы"
    count = db.execute(f"select count(*) from {table}").fetchone()[0]
    if count == 0:
        return "пусто"
    old = f"{table}__old"
    db.execute(f"drop table if exists {old}")
    db.execute(f"alter table {table} rename to {old}")
    db.execute(ddl[0])
    db.execute(
        f"insert into {table} select * from {old} order by character, {name_col} COLLATE NOCASE"
    )
    db.execute(f"drop table {old}")
    return f"пересортировано {count} записей"


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    path = Path(sys.argv[1])
    db = sqlite3.connect(path)
    db.execute("pragma foreign_keys=off")
    for table, name_col in LIST_TABLES:
        cols = [r[1] for r in db.execute(f"pragma table_info({table})")]
        if not cols or "character" not in cols or name_col not in cols:
            continue
        print(f"  {table}: {reorder(db, table, name_col)}")
    db.commit()
    db.execute("pragma journal_mode=delete")
    db.execute("vacuum")
    db.commit()
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
