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

# Триггер разбирает ВСЕ составляющие за раз: рекурсивный CTE внутри одного
# INSERT … SELECT (это НЕ рекурсия триггера — recursive_triggers OFF не мешает).
# `substr(x,1,length(x))` снимает хвостовой NUL: replace(x,char(0),'') NUL не
# вырезает (проверено на вшитом SQLite 3.12.2). DROP перед CREATE обязателен —
# `CREATE TRIGGER IF NOT EXISTS` старый (2-составный) триггер не заменит.
TRIGGER_SQL = f"""
DROP TRIGGER IF EXISTS {TRIGGER};
CREATE TRIGGER {TRIGGER} AFTER INSERT ON ARTIST2_TABLE
WHEN instr(substr(NEW.artist,1,length(NEW.artist)),';')>0
BEGIN
  INSERT OR IGNORE INTO ARTIST2_TABLE(id,artist,character,cn,ctime,mtime,pinyin_charater)
  WITH RECURSIVE parts(rest,part) AS (
    SELECT substr(NEW.artist,1,length(NEW.artist))||';',''
    UNION ALL
    SELECT substr(rest,instr(rest,';')+1), substr(rest,1,instr(rest,';')-1)
    FROM parts WHERE rest<>''
  )
  SELECT NEW.id, part||char(0), NEW.character, NEW.cn, NEW.ctime, NEW.mtime,
         NEW.pinyin_charater
  FROM parts WHERE part<>'';
  DELETE FROM ARTIST2_TABLE WHERE rowid=NEW.rowid;
END;
"""

# одноразовый разбор существующих склеек (top-level WITH RECURSIVE, любой глубины)
SPLIT_EXISTING_SQL = """
INSERT OR IGNORE INTO ARTIST2_TABLE(id,artist,character,cn,ctime,mtime,pinyin_charater)
WITH RECURSIVE split(id,rest,part,character,cn,ctime,mtime,pinyin) AS (
  SELECT id, substr(artist,1,length(artist))||';', '', character, cn, ctime, mtime,
         pinyin_charater
    FROM ARTIST2_TABLE WHERE instr(substr(artist,1,length(artist)),';')>0
  UNION ALL
  SELECT id, substr(rest,instr(rest,';')+1), substr(rest,1,instr(rest,';')-1),
         character, cn, ctime, mtime, pinyin
    FROM split WHERE rest<>''
)
SELECT id, part||char(0), character, cn, ctime, mtime, pinyin
FROM split WHERE part<>'';
DELETE FROM ARTIST2_TABLE WHERE instr(substr(artist,1,length(artist)),';')>0;
"""

# то же для album_artist (колонки с mqa)
TRIGGER_AA = "split_ALBUM_ARTIST2_TABLE"
TRIGGER_AA_SQL = f"""
DROP TRIGGER IF EXISTS {TRIGGER_AA};
CREATE TRIGGER {TRIGGER_AA} AFTER INSERT ON ALBUM_ARTIST2_TABLE
WHEN instr(substr(NEW.album_artist,1,length(NEW.album_artist)),';')>0
BEGIN
  INSERT OR IGNORE INTO ALBUM_ARTIST2_TABLE(id,album_artist,character,cn,ctime,mtime,mqa,pinyin_charater)
  WITH RECURSIVE parts(rest,part) AS (
    SELECT substr(NEW.album_artist,1,length(NEW.album_artist))||';',''
    UNION ALL
    SELECT substr(rest,instr(rest,';')+1), substr(rest,1,instr(rest,';')-1)
    FROM parts WHERE rest<>''
  )
  SELECT NEW.id, part||char(0), NEW.character, NEW.cn, NEW.ctime, NEW.mtime,
         NEW.mqa, NEW.pinyin_charater
  FROM parts WHERE part<>'';
  DELETE FROM ALBUM_ARTIST2_TABLE WHERE rowid=NEW.rowid;
END;
"""

SPLIT_EXISTING_AA_SQL = """
INSERT OR IGNORE INTO ALBUM_ARTIST2_TABLE(id,album_artist,character,cn,ctime,mtime,mqa,pinyin_charater)
WITH RECURSIVE split(id,rest,part,character,cn,ctime,mtime,mqa,pinyin) AS (
  SELECT id, substr(album_artist,1,length(album_artist))||';', '', character, cn, ctime,
         mtime, mqa, pinyin_charater
    FROM ALBUM_ARTIST2_TABLE WHERE instr(substr(album_artist,1,length(album_artist)),';')>0
  UNION ALL
  SELECT id, substr(rest,instr(rest,';')+1), substr(rest,1,instr(rest,';')-1),
         character, cn, ctime, mtime, mqa, pinyin
    FROM split WHERE rest<>''
)
SELECT id, part||char(0), character, cn, ctime, mtime, mqa, pinyin
FROM split WHERE part<>'';
DELETE FROM ALBUM_ARTIST2_TABLE WHERE instr(substr(album_artist,1,length(album_artist)),';')>0;
"""

REBUILD_ARTIST = (
    "INSERT INTO ARTIST_TABLE SELECT id,artist,"
    "(CASE WHEN character BETWEEN 'A' AND 'Z' THEN character ELSE '~' END),"
    "cn,ctime,mtime,pinyin_charater FROM ARTIST2_TABLE ORDER BY 3,artist"
)
REBUILD_ALBUM_ARTIST = (
    "INSERT INTO ALBUM_ARTIST_TABLE SELECT id,album_artist,"
    "(CASE WHEN character BETWEEN 'A' AND 'Z' THEN character ELSE '~' END),"
    "cn,ctime,mtime,mqa,pinyin_charater FROM ALBUM_ARTIST2_TABLE ORDER BY 3,album_artist"
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

    combined = c.execute(
        "SELECT count(*) FROM ARTIST2_TABLE "
        "WHERE instr(substr(artist,1,length(artist)),';')>0"
    ).fetchone()[0]
    combined_aa = c.execute(
        "SELECT count(*) FROM ALBUM_ARTIST2_TABLE "
        "WHERE instr(substr(album_artist,1,length(album_artist)),';')>0"
    ).fetchone()[0]
    has_trigger = bool(
        c.execute(
            "SELECT 1 FROM sqlite_master WHERE type='trigger' AND name=?", (TRIGGER,)
        ).fetchone()
    )
    has_trigger_aa = bool(
        c.execute(
            "SELECT 1 FROM sqlite_master WHERE type='trigger' AND name=?", (TRIGGER_AA,)
        ).fetchone()
    )

    if check:
        print(f"склеек в ARTIST2_TABLE: {combined}")
        print(f"триггер {TRIGGER}: {'есть' if has_trigger else 'нет'}")
        print(f"склеек в ALBUM_ARTIST2_TABLE: {combined_aa}")
        print(f"триггер {TRIGGER_AA}: {'есть' if has_trigger_aa else 'нет'}")
        return 0

    # всегда пересоздаём триггеры: DROP+CREATE внутри *_SQL (старый 2-составный
    # триггер на устройстве иначе не заменится)
    c.execute(f"CREATE TABLE IF NOT EXISTS {NUM_TABLE}(n INTEGER)")
    c.executemany(
        f"INSERT OR IGNORE INTO {NUM_TABLE} VALUES (?)", [(i,) for i in range(1, 9)]
    )
    c.executescript(TRIGGER_SQL)
    c.executescript(TRIGGER_AA_SQL)
    print(f"триггеры {TRIGGER}, {TRIGGER_AA} пересозданы")

    if combined:
        c.executescript(SPLIT_EXISTING_SQL)
        print(f"разобрано склеек artist (было {combined})")
    if combined_aa:
        c.executescript(SPLIT_EXISTING_AA_SQL)
        print(f"разобрано склеек album_artist (было {combined_aa})")

    c.execute("DELETE FROM ARTIST_TABLE")
    c.execute(REBUILD_ARTIST)
    c.execute("DELETE FROM ALBUM_ARTIST_TABLE")
    c.execute(REBUILD_ALBUM_ARTIST)
    total = c.execute("SELECT count(*) FROM ARTIST_TABLE").fetchone()[0]
    left = c.execute(
        "SELECT count(*) FROM ARTIST_TABLE WHERE instr(artist,';')>0"
    ).fetchone()[0]
    total_aa = c.execute("SELECT count(*) FROM ALBUM_ARTIST_TABLE").fetchone()[0]
    left_aa = c.execute(
        "SELECT count(*) FROM ALBUM_ARTIST_TABLE WHERE instr(album_artist,';')>0"
    ).fetchone()[0]
    print(f"ARTIST_TABLE: {total} записей, склеек {left}; "
          f"ALBUM_ARTIST_TABLE: {total_aa} записей, склеек {left_aa}")

    db.commit()
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
