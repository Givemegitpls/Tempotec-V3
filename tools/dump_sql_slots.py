#!/usr/bin/env python3
"""Выгрузка SQL-строк из таблицы слотов бинаря в текстовый файл.

Таблица: база `0x9b7730`, 199 записей по 4 байта (указатель на строку).
Пишет `work/sql_slots.txt` (индекс, VA, строка) — чтобы анализировать, не таща
в контекст.

    python3 tools/dump_sql_slots.py <hiby_player> [--out work/sql_slots.txt]
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

VTO = 0x400000
SQL_TABLE = 0x9B7730
COUNT = 199


def main() -> int:
    args = sys.argv[1:]
    if not args:
        raise SystemExit(__doc__)
    path = Path(args[0])
    out = Path(args[args.index("--out") + 1]) if "--out" in args else Path("work/sql_slots.txt")
    d = path.read_bytes()
    lines = []
    for i in range(COUNT):
        va = struct.unpack_from("<I", d, SQL_TABLE - VTO + 4 * i)[0]
        if not (0x900000 <= va < 0xC00000):
            lines.append(f"slot {i:3}  {va:#010x}  <не строка>")
            continue
        s = d[va - VTO : va - VTO + 400].split(b"\x00")[0].decode("utf-8", "replace")
        lines.append(f"slot {i:3}  {va:#010x}  {s}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{out}: {len(lines)} строк")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
