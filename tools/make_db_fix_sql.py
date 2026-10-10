#!/usr/bin/env python3
"""Генератор SQL-фикса медиатеки (компактный), который плеер выполняет сам.

Файл кладётся в образ (`fw/SYSTEM/usr/share/hiby_db_fix.sql`), а бинарь
(`tools/exp_db_autofix.py`) читает его и выполняет через `sqlite3_exec` при
завершении скана. Так образ становится самодостаточным: после «обновления
медиатеки» буквы/порядок/разбор `artist` по `;` приходят в порядок без внешних
скриптов.

Размер файла критичен: rootfs-образ не должен вырасти (апдейтер виснет на UBI
размера оригинала). Поэтому вместо повторения большого CASE в каждом триггере
используется таблица `CYR_MAP` (кириллица → латиница) и короткое выражение.

Содержимое (идемпотентно):
  * таблица CYR_MAP + ARTIST_SPLIT_NUM;
  * триггеры `fix_char_*` (буква: кириллица → латиница, A-Z, иначе `~`;
    для треков — по названию) и `split_ARTIST2_TABLE` (разбор `;`);
  * одноразовая починка существующих записей и пересборка таблиц списков.

Использование:
    python3 tools/make_db_fix_sql.py [--out fw/SYSTEM/usr/share/hiby_db_fix.sql]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import translit_db as T  # noqa: E402

TARGETS = [
    ("ARTIST2_TABLE", "artist"),
    ("ALBUM2_TABLE", "album"),
    ("ALBUM_ARTIST2_TABLE", "album_artist"),
    ("GENRE2_TABLE", "genre"),
    ("FORMAT2_TABLE", "format"),
    ("MEDIA2_TABLE", "name"),
    ("MEDIA_TABLE", "name"),
    ("MEDIA3_TABLE", "name"),
]

LIST_TABLES = [
    ("ARTIST_TABLE", "artist"),
    ("ALBUM_TABLE", "album"),
    ("ALBUM_ARTIST_TABLE", "album_artist"),
    ("GENRE_TABLE", "genre"),
    ("FORMAT_TABLE", "format"),
]


def letter_expr(col: str) -> str:
    """Компактное выражение буквы (кириллица → CYR_MAP, A-Z, иначе '~')."""
    f = f"substr({col},1,1)"
    return (
        f"coalesce((SELECT lat FROM CYR_MAP WHERE cyr={f}),"
        f"CASE WHEN {f} BETWEEN 'A' AND 'Z' THEN {f} "
        f"WHEN {f} BETWEEN 'a' AND 'z' THEN upper({f}) ELSE '~' END)"
    )


SPLIT_TRIGGER = """
DROP TRIGGER IF EXISTS split_ARTIST2_TABLE;
CREATE TRIGGER split_ARTIST2_TABLE AFTER INSERT ON ARTIST2_TABLE
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

# одноразовый разбор существующих склеек (top-level WITH RECURSIVE, любой
# глубины). `substr(x,1,length(x))` снимает хвостовой NUL: replace(x,char(0),'')
# NUL НЕ вырезает (проверено на вшитом SQLite 3.12.2).
SPLIT_EXISTING = """
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
SPLIT_TRIGGER_AA = """
DROP TRIGGER IF EXISTS split_ALBUM_ARTIST2_TABLE;
CREATE TRIGGER split_ALBUM_ARTIST2_TABLE AFTER INSERT ON ALBUM_ARTIST2_TABLE
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

SPLIT_EXISTING_AA = """
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


def build() -> str:
    L: list[str] = []
    A = L.append
    A("-- autogenerated by tools/make_db_fix_sql.py")
    A("CREATE TABLE IF NOT EXISTS CYR_MAP(cyr TEXT PRIMARY KEY, lat TEXT);")
    pairs = ",".join(f"('{k}','{v}')" for k, v in T.CYR_TO_LAT.items() if v)
    A(f"INSERT OR IGNORE INTO CYR_MAP(cyr,lat) VALUES {pairs};")
    A("CREATE TABLE IF NOT EXISTS ARTIST_SPLIT_NUM(n INTEGER);")
    A("INSERT OR IGNORE INTO ARTIST_SPLIT_NUM(n) VALUES (1),(2),(3),(4),(5),(6),(7),(8);")

    for table, col in TARGETS:
        e = letter_expr(col)
        A(f"CREATE TRIGGER IF NOT EXISTS fix_char_{table} AFTER INSERT ON {table} "
          f"BEGIN UPDATE {table} SET character = {e} WHERE rowid=new.rowid; END;")
        A(f"CREATE TRIGGER IF NOT EXISTS fix_char_upd_{table} AFTER UPDATE OF {col} ON {table} "
          f"BEGIN UPDATE {table} SET character = {e} WHERE rowid=new.rowid; END;")

    A(SPLIT_TRIGGER.strip())
    A(SPLIT_TRIGGER_AA.strip())

    # одноразово: разобрать существующие склейки ARTIST2_TABLE (CTE, любой глубины)
    A(SPLIT_EXISTING.strip())
    # одноразово: то же для ALBUM_ARTIST2_TABLE
    A(SPLIT_EXISTING_AA.strip())

    # одноразово: починить буквы у существующих записей (прогон upd-триггеров)
    for table, col in TARGETS:
        A(f"UPDATE {table} SET {col} = {col};")

    # пересборка таблиц списков по character
    for table, col in LIST_TABLES:
        src = table.replace("_TABLE", "2_TABLE")
        A(f"DELETE FROM {table};")
        A(f"INSERT INTO {table} SELECT * FROM {src} ORDER BY character,{col};")
    A("DELETE FROM MEDIA_TABLE;")
    A("INSERT INTO MEDIA_TABLE SELECT * FROM MEDIA2_TABLE ORDER BY character,name;")
    A("")
    return "\n".join(L)


def main() -> int:
    args = sys.argv[1:]
    out = Path("fw/SYSTEM/usr/share/hiby_db_fix.sql")
    if "--out" in args:
        out = Path(args[args.index("--out") + 1])
    out.parent.mkdir(parents=True, exist_ok=True)
    sql = build()
    out.write_text(sql, encoding="utf-8")
    print(f"{out}: {len(sql)} байт")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
