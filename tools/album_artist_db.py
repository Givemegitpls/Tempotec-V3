#!/usr/bin/env python3
"""Наполнить ARTIST_TABLE авторами альбомов (из ALBUM_ARTIST2_TABLE).

Идея: категория «Артисты» в плеере умеет алфавитную полоску, а «исполнитель
альбома» — нет. Поэтому проще показывать в «Артистах» авторов альбомов: тогда
список артистов, полоска и уровень альбомов работают вместе.

Скрипт пересобирает ARTIST2_TABLE и ARTIST_TABLE из ALBUM_ARTIST2_TABLE
(берём album_artist как имя артиста) и сортирует их по (character, имя).

Использование:
    python3 tools/album_artist_db.py <media.db>
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


def fill(db: sqlite3.Connection, target: str, reorder: str, name_col: str) -> str:
    ddl = db.execute(
        "select sql from sqlite_master where type='table' and name=?", (target,)
    ).fetchone()
    if not ddl or not ddl[0]:
        return "нет таблицы"
    old = f"{target}__old"
    db.execute(f"drop table if exists {old}")
    db.execute(f"alter table {target} rename to {old}")
    db.execute(ddl[0])
    db.execute(
        f"insert into {target} (id, {name_col}, character, cn, ctime, mtime, pinyin_charater) "
        f"select id, album_artist, character, cn, ctime, mtime, pinyin_charater "
        f"from ALBUM_ARTIST2_TABLE"
    )
    db.execute(f"drop table {old}")
    # пересортировка по букве (иначе прыжки по алфавиту уезжают)
    return reorder_table(db, target, name_col)


def reorder_table(db: sqlite3.Connection, table: str, name_col: str) -> str:
    ddl = db.execute(
        "select sql from sqlite_master where type='table' and name=?", (table,)
    ).fetchone()[0]
    count = db.execute(f"select count(*) from {table}").fetchone()[0]
    old = f"{table}__old2"
    db.execute(f"drop table if exists {old}")
    db.execute(f"alter table {table} rename to {old}")
    db.execute(ddl)
    db.execute(f"insert into {table} select * from {old} order by character, {name_col} COLLATE NOCASE")
    db.execute(f"drop table {old}")
    return f"{count} записей, первые буквы: " + "".join(
        r[0] for r in db.execute(f"select character from {table} order by rowid")
    )


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    db = sqlite3.connect(Path(sys.argv[1]))
    for target, name_col in (("ARTIST2_TABLE", "artist"), ("ARTIST_TABLE", "artist")):
        print(f"  {target}: {fill(db, target, target, name_col)}")
    db.commit()
    db.execute("pragma journal_mode=delete")
    db.execute("vacuum")
    db.commit()
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
