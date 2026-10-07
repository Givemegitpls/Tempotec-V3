#!/usr/bin/env python3
"""Маркер-тест: исполняет ли плеер SQL-строку сборки ARTIST_TABLE.

В бинаре есть строка
    INSERT INTO ARTIST_TABLE SELECT * FROM ARTIST2_TABLE ORDER BY artist COLLATE pinyin
Прямых ссылок из кода у неё нет (строки берутся по индексу из таблицы), поэтому
неизвестно, используется ли она в этой сборке. Скрипт подменяет хвост `ORDER BY`
на `rowid DESC` (длина сохраняется), и если после обновления медиатеки в плеере
список артистов окажется в обратном порядке — строка исполняется.

Использование:
    python3 tools/exp_marker.py <hiby_player>
"""

from __future__ import annotations

import sys
from pathlib import Path

ORIGINAL = b"INSERT INTO ARTIST_TABLE SELECT * FROM ARTIST2_TABLE ORDER BY artist COLLATE pinyin"
MARKER = b"INSERT INTO ARTIST_TABLE SELECT * FROM ARTIST2_TABLE ORDER BY rowid DESC"


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    path = Path(sys.argv[1])
    data = path.read_bytes()
    if MARKER in data:
        print("маркер уже стоит")
        return 0
    count = data.count(ORIGINAL)
    if count != 1:
        raise SystemExit(f"строка найдена {count} раз, ожидалось 1")
    index = data.index(ORIGINAL)
    replacement = MARKER + b" " * (len(ORIGINAL) - len(MARKER))
    data = data[:index] + replacement + data[index + len(ORIGINAL) :]
    path.write_bytes(data)
    print(f"{path}: маркер установлен (смещение {index:#x}, длина сохранена)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
