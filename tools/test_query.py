#!/usr/bin/env python3
"""Проверка семантики исправленного запроса на обычной SQLite (python3).

Условия берутся из tools/patch_player.py — те же строки, что правятся в бинаре.
Тест воспроизводит сценарий: альбом, часть треков которого записана с гостями
(artist отличается от album_artist), плюс одноимённый альбом другого артиста.

Запуск: python3 tools/test_query.py
"""

from __future__ import annotations

import sqlite3

from patch_player import NEW_ALBUM_AND_ARTIST, OLD_ALBUM_AND_ARTIST

SCHEMA = """\
CREATE TABLE MEDIA_TABLE(
  id INT, path TEXT, name TEXT, album TEXT, artist TEXT, album_artist TEXT,
  genre TEXT, has_child_file INT, ck_id INT, cue_id INT
);
CREATE TABLE RESULT(id INT, path TEXT, name TEXT, album TEXT, artist TEXT);
"""

INSERT = (
    "INSERT INTO RESULT SELECT id,path,name,album,artist FROM MEDIA_TABLE "
    "WHERE rowid IN (SELECT rowid FROM MEDIA_TABLE {where} ORDER BY name"
)

TRACKS = [
    (1, "01 track", "Joints", "Band", "Band"),
    (2, "02 feat guest", "Joints", "Band feat. Guest", "Band"),
    (3, "03 track", "Joints", "Band", "Band"),
    (4, "01 track", "Joints", "Other Band", "Other Band"),
]


def make_db() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.executescript(SCHEMA)
    for tid, name, album, artist, album_artist in TRACKS:
        db.execute(
            "INSERT INTO MEDIA_TABLE VALUES (?,?,?,?,?,?,?,0,0,0)",
            (tid, f"/m/{tid}.flac", name, album, artist, album_artist, "Rock"),
        )
    return db


def tracks(db: sqlite3.Connection, clause: bytes, params: tuple[str, str]) -> list[str]:
    where = clause.decode()
    if not where.startswith("WHERE "):
        where = "WHERE " + where
    db.execute("DELETE FROM RESULT")
    db.execute(INSERT.format(where=where), params)
    return [row[0] for row in db.execute("SELECT name FROM RESULT")]


def main() -> int:
    db = make_db()
    old = tracks(db, OLD_ALBUM_AND_ARTIST, ("Joints", "Band"))
    new = tracks(db, NEW_ALBUM_AND_ARTIST, ("Joints", "Band"))
    print(f"до правки: {old}")
    print(f"после:     {new}")
    assert old == ["01 track", "03 track"], old
    assert new == ["01 track", "02 feat guest", "03 track"], new
    print("ок: совместный трек не теряется, одноимённый альбом другого артиста не подмешивается")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
