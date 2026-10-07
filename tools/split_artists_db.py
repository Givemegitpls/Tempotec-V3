#!/usr/bin/env python3
"""БД: разбор тега `artist` по `;` на отдельных соавторов.

Совместные треки хранят в теге `artist` склейку вида `Noize MC;Anacondaz`.
Плеер считает её одним автором, поэтому в «Артистах» такая склейка — одна
строка, а совместный трек/альбом не виден у каждого соавтора.

Скрипт:
  1) создаёт helper-таблицу `ARTIST_SPLIT_NUM` (1..8) и триггер
     `split_ARTIST2_TABLE` (AFTER INSERT на `ARTIST2_TABLE`): если в `artist`
     есть `;`, вставляет каждую составляющую отдельной строкой (транслит-триггер
     `fix_char_ARTIST2_TABLE` проставит ей `character`) и удаляет склейку. Так
     разбор переживает «Обновление медиатеки»;
  2) разбирает уже существующие склейки в `ARTIST2_TABLE`;
  3) пересобирает `ARTIST_TABLE` из `ARTIST2_TABLE` (как в прошивке, слот 125).

`ALBUM_ARTIST2_TABLE`/`ALBUM_ARTIST_TABLE` НЕ трогаются (альбомы собираются по
`album_artist` и должны быть полными).

Список альбомов артиста фильтруется в прошивке (`tools/exp_albums_by_component.py`)
по составляющей тега `artist`.

Использование:
    python3 tools/split_artists_db.py <usrlocal_media.db> [--check]
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

NUM_TABLE = "ARTIST_SPLIT_NUM"
TRIGGER = "split_ARTIST2_TABLE"

# Триггер разбирает ПЕРВУЮ ';': вставляет обе составляющие (OR IGNORE — чтобы не
# ловить конфликт PK, если составляющая уже есть) и удаляет склейку. Без UPDATE
# (UPDATE головы падал по PK, если голова уже существует). Работает для 2
# составляющих (все текущие склейки такие). ВНИМАНИЕ: recursive_triggers по
# умолчанию OFF, поэтому 3+ составляющих в ОДНОЙ вставке не разбираются —
# обрабатывать повторным прогоном скрипта.
TRIGGER_SQL = f"""
CREATE TRIGGER IF NOT EXISTS {TRIGGER} AFTER INSERT ON ARTIST2_TABLE
WHEN instr(replace(NEW.artist,char(0),''),';')>0
BEGIN
  INSERT OR IGNORE INTO ARTIST2_TABLE(id,artist,character,cn,ctime,mtime,pinyin_charater)
  SELECT NEW.id,
         substr(replace(NEW.artist,char(0),''),
                1, instr(replace(NEW.artist,char(0),''),';')-1)||char(0),
         NEW.character, NEW.cn, NEW.ctime, NEW.mtime, NEW.pinyin_charater;
  INSERT OR IGNORE INTO ARTIST2_TABLE(id,artist,character,cn,ctime,mtime,pinyin_charater)
  SELECT NEW.id,
         substr(replace(NEW.artist,char(0),''),
                instr(replace(NEW.artist,char(0),''),';')+1)||char(0),
         NEW.character, NEW.cn, NEW.ctime, NEW.mtime, NEW.pinyin_charater;
  DELETE FROM ARTIST2_TABLE WHERE rowid=NEW.rowid;
END
"""

REBUILD_ARTIST = (
    "INSERT INTO ARTIST_TABLE SELECT id,artist,"
    "(CASE WHEN character BETWEEN 'A' AND 'Z' THEN character ELSE '~' END),"
    "cn,ctime,mtime,pinyin_charater FROM ARTIST2_TABLE ORDER BY 3,artist"
)


def split(artist: str) -> list[str]:
    # значения в БД хранятся с хвостовым NUL (C-строка) — сохраняем стиль
    core = artist.rstrip("\x00")
    return [p + "\x00" for p in core.split(";") if p != ""]


def main() -> int:
    argv = sys.argv[1:]
    check = "--check" in argv
    args = [a for a in argv if a != "--check"]
    if len(args) != 1:
        raise SystemExit(__doc__)
    path = Path(args[0])

    db = sqlite3.connect(path)
    db.isolation_level = None
    c = db.cursor()

    combined = [
        r[0]
        for r in c.execute("SELECT artist FROM ARTIST2_TABLE WHERE instr(artist,';')>0")
    ]
    has_trigger = bool(
        c.execute(
            "SELECT 1 FROM sqlite_master WHERE type='trigger' AND name=?", (TRIGGER,)
        ).fetchone()
    )

    if check:
        print(f"склеек в ARTIST2_TABLE: {len(combined)} {combined}")
        print(f"триггер {TRIGGER}: {'есть' if has_trigger else 'нет'}")
        return 0

    if not has_trigger:
        c.execute(f"CREATE TABLE IF NOT EXISTS {NUM_TABLE}(n INTEGER)")
        c.executemany(
            f"INSERT OR IGNORE INTO {NUM_TABLE} VALUES (?)", [(i,) for i in range(1, 9)]
        )
        c.execute(TRIGGER_SQL)
        print(f"создан триггер {TRIGGER} + {NUM_TABLE}")

    if combined:
        for artist in combined:
            row = c.execute(
                "SELECT id,character,cn,ctime,mtime,pinyin_charater FROM ARTIST2_TABLE "
                "WHERE artist=?",
                (artist,),
            ).fetchone()
            for part in split(artist):
                c.execute(
                    "INSERT OR IGNORE INTO ARTIST2_TABLE"
                    "(id,artist,character,cn,ctime,mtime,pinyin_charater) VALUES (?,?,?,?,?,?,?)",
                    (row[0], part, row[1], row[2], row[3], row[4], row[5]),
                )
            c.execute("DELETE FROM ARTIST2_TABLE WHERE artist=?", (artist,))
        print(f"разобрано склеек: {len(combined)}")

    c.execute("DELETE FROM ARTIST_TABLE")
    c.execute(REBUILD_ARTIST)
    total = c.execute("SELECT count(*) FROM ARTIST_TABLE").fetchone()[0]
    left = c.execute(
        "SELECT count(*) FROM ARTIST_TABLE WHERE instr(artist,';')>0"
    ).fetchone()[0]
    print(f"ARTIST_TABLE пересобрана: {total} записей, склеек осталось {left}")

    db.commit()
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
