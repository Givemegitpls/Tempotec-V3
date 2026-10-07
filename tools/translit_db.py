#!/usr/bin/env python3
"""Правка колонки `character` медиатеки плеера.

Зачем: алфавитная полоска в плеере считает позицию как «сколько записей в
диапазоне от 'A' до выбранной буквы», и берёт строку с этим номером. Значит в
таблицах списков допустимы только буквы `A..Z`, а всё остальное должно стоять
*после* `Z` — иначе записи, начинающиеся с цифры или символа, стоят в начале
списка и сдвигают все прыжки (в «Альбомах» это было заметно как «A → символы,
C → A» и т.п.).

Что делает скрипт:
  * для каждой записи считает букву по имени: кириллица → латинский эквивалент
    (А→A, Б→B, В→V, …), латиница → заглавная, всё остальное (цифры, символы,
    прочие алфавиты) → маркер `[` (код 0x5B, больше `Z`, поэтому такие записи
    уезжают в конец списка, как и ожидает плеер);
  * ставит триггеры на таблицы `*2_TABLE`, чтобы новые записи при обновлении
    медиатеки сразу получали правильную букву;
  * сводит журнал и вакуумирует файл.

Использование:
    python3 tools/translit_db.py <media.db> [--no-triggers]
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

# Первая кириллическая буква -> латинская
CYR_TO_LAT = {
    "А": "A", "Б": "B", "В": "V", "Г": "G", "Д": "D", "Е": "E", "Ё": "E",
    "Ж": "Z", "З": "Z", "И": "I", "Й": "I", "К": "K", "Л": "L", "М": "M",
    "Н": "N", "О": "O", "П": "P", "Р": "R", "С": "S", "Т": "T", "У": "U",
    "Ф": "F", "Х": "H", "Ц": "C", "Ч": "C", "Ш": "S", "Щ": "S", "Ъ": "",
    "Ы": "Y", "Ь": "", "Э": "E", "Ю": "U", "Я": "Y",
    "É": "E", "À": "A", "Ä": "A", "Ö": "O", "Ü": "U", "Ñ": "N",
}
CYR_TO_LAT.update({k.lower(): v for k, v in CYR_TO_LAT.items() if k.isalpha()})

NON_LETTER = "~"  # всё, что не A-Z, уезжает после Z (важно: '~' больше 'z' и при COLLATE NOCASE)

# имя колонки с названием для каждой таблицы
NAME_COLUMNS = ("artist", "album", "album_artist", "genre", "name", "format")

# Таблицы треков (MEDIA*, HISTORY, COLLECT, SEARCH, RECENT, ...) не обрабатываем:
# у треков плеер ставит букву по ИСПОЛНИТЕЛЮ (например у треков DECO*27
# character='D' независимо от названия), и это его собственное правило — наша
# нормализация по названию трека только ломает буквы и счёт в списке «All».
SKIP_PREFIXES = ("MEDIA", "HISTORY", "COLLECT", "SEARCH", "RECENT", "CTIME", "MTIME")


def letter_for(name: str) -> str:
    """Буква для колонки character: A-Z, либо NON_LETTER."""
    if not name:
        return NON_LETTER
    first = name[0]
    latin = CYR_TO_LAT.get(first)
    if latin:
        return latin
    if "A" <= first <= "Z":
        return first
    if "a" <= first <= "z":
        return first.upper()
    return NON_LETTER


# Таблицы, из которых читается список «All» (все треки). Плеер ставит треку букву
# по ИСПОЛНИТЕЛЮ, а сам список идёт по НАЗВАНИЮ трека — поэтому полоска в «All» не
# совпадает с порядком. Здесь буква считается по названию трека, тогда порядок и
# счёт совпадают.
LIST_TABLES = ("MEDIA_TABLE", "MEDIA3_TABLE")


def sql_letter_expr(col: str) -> str:
    """SQL-выражение, повторяющее логику letter_for для триггеров."""
    cases = " ".join(f"WHEN '{k}' THEN '{v}'" for k, v in CYR_TO_LAT.items() if v)
    first = f"substr({col},1,1)"
    return (
        f"CASE {first} {cases} "
        f"WHEN '' THEN '{NON_LETTER}' "
        f"ELSE CASE WHEN {first} BETWEEN 'A' AND 'Z' THEN {first} "
        f"WHEN {first} BETWEEN 'a' AND 'z' THEN upper({first}) "
        f"ELSE '{NON_LETTER}' END END"
    )


def tables(db: sqlite3.Connection) -> list[tuple[str, str]]:
    out = []
    for (name,) in db.execute("select name from sqlite_master where type='table'"):
        if name.upper().startswith(SKIP_PREFIXES):
            continue
        cols = [r[1] for r in db.execute(f"pragma table_info({name})")]
        if "character" not in cols:
            continue
        for col in NAME_COLUMNS:
            if col in cols:
                out.append((name, col))
                break
    return out


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    path = Path(sys.argv[1])
    with_triggers = "--no-triggers" not in sys.argv

    db = sqlite3.connect(path)
    total = 0
    targets = tables(db) + [(t, "name") for t in LIST_TABLES
                            if "character" in [r[1] for r in db.execute(f"pragma table_info({t})")]]
    for table, col in targets:
        rows = db.execute(f"select rowid, {col}, character from {table}").fetchall()
        changed = 0
        for rowid, name, character in rows:
            want = letter_for(name.rstrip("\x00")[:1] if name else "")
            if character != want:
                db.execute(f"update {table} set character = ? where rowid = ?", (want, rowid))
                changed += 1
        if changed:
            print(f"  {table}: поправлено {changed} из {len(rows)}")
        total += changed

        if with_triggers and (table.endswith("2_TABLE") or table in LIST_TABLES):
            expr = sql_letter_expr(col)
            db.execute(f"drop trigger if exists fix_char_{table}")
            db.execute(
                f"create trigger fix_char_{table} after insert on {table} begin "
                f"update {table} set character = {expr} where rowid = new.rowid; end"
            )
            # тот же расчёт при обновлении записи (пересканирование файла)
            db.execute(f"drop trigger if exists fix_char_upd_{table}")
            db.execute(
                f"create trigger fix_char_upd_{table} after update of {col} on {table} begin "
                f"update {table} set character = {expr} where rowid = new.rowid; end"
            )
            print(f"  {table}: триггеры fix_char_{table} / fix_char_upd_{table} установлены")

    db.commit()
    db.execute("pragma journal_mode=delete")
    db.execute("vacuum")
    db.commit()
    db.close()
    print(f"итого исправлено записей: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
