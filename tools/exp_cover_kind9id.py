#!/usr/bin/env python3
"""Обложки «Artists → артист»: уникальный id в list_tb (kind9) — фикс «одной» обложки.

Причина «одна обложка на весь список» (подтверждено офлайн-симуляцией на реальной БД
и разбором асма/декомпилята):

  FUN_004a52a0 (заполнение cover-записи) вызывает FUN_00707840(cov, 1, &cov, key),
  а тот выполняет `SELECT path FROM list_tb_N WHERE id = ?`, где `?` = col0
  строки списка. Ограничение: `WHERE id = ?` берёт ПЕРВУЮ строку с этим id.

  В kind9-ветке (`FUN_00708d20 case 9`) шаблон вставки биндит `?1 = 0` для ВСЕХ
  строк (FUN_005b3100(stmt, 1, 0)), т.е. list_tb_N.id = 0 у каждого альбома.
  Итог: для любой строки `WHERE id=0` возвращает путь ПЕРВОГО альбома →
  все cover-записи получают один и тот же путь → одна картинка на список.

  В kind5 (D9, FUN_004a9dc0) list_tb_N.id — настоящий id из MEDIA_TABLE (уникален),
  поэтому путь per-row корректный и обложки «свои».

Фикс: в RX-шаблоне kind9 (0xa7e800) первый столбец (id) заменить с `?1` на
`(SELECT MIN(rowid) FROM MEDIA_TABLE WHERE album=?2)` — уникальный числовой id
на каждый альбом. Позиции bind'ов (?2=альбом, ?3, ?4, ?5, ?6) не меняются;
`?1` больше не встречается в тексте, но sqlite3_bind_parameter_count()=6
(максимальный индекс ?6), поэтому существующий bind(stmt,1,0) остаётся валидным
no-op'ом.

Применять ПОСЛЕ: exp_album_view + exp_flags_view21 + exp_coverpath_combo +
exp_cover_kind9col (последний и создаёт этот шаблон).

Использование:
    python3 tools/exp_cover_kind9id.py <hiby_player> [--check]
"""
from __future__ import annotations

import sys
from pathlib import Path

VTO = 0x400000
TPL_VA = 0xA7E800
TPL_OFF = TPL_VA - VTO

# шаблон до фикса (создаётся exp_cover_kind9col)
BASE_TPL = (
    "INSERT INTO %s%d VALUES (?1,(SELECT path FROM MEDIA_TABLE WHERE album=?2 LIMIT 1),"
    "?2,?2,0,0,0,0,?3,0,0,0,?4,0,?5,0,?6,0,0,0,0,0,0,0,0,0,0)"
)
# промежуточный вариант (пробовали MIN(rowid)) — тоже уметь перезаписывать
OLD_TPL = (
    "INSERT INTO %s%d VALUES ((SELECT MIN(rowid) FROM MEDIA_TABLE WHERE album=?2),"
    "(SELECT path FROM MEDIA_TABLE WHERE album=?2 LIMIT 1),"
    "?2,?2,0,0,0,0,?3,0,0,0,?4,0,?5,0,?6,0,0,0,0,0,0,0,0,0,0)"
)
# рабочий: col0 = id из MEDIA_TABLE (путь разрешается запросом к MEDIA_TABLE по колонке id)
NEW_TPL = (
    "INSERT INTO %s%d VALUES ((SELECT id FROM MEDIA_TABLE WHERE album=?2 LIMIT 1),"
    "(SELECT path FROM MEDIA_TABLE WHERE album=?2 LIMIT 1),"
    "?2,?2,0,0,0,0,?3,0,0,0,?4,0,?5,0,?6,0,0,0,0,0,0,0,0,0,0)"
)
# верхняя граница RX-зазора: phdr2 filesz = 0x67f000 (VA 0xa7f000)
TPL_LIMIT = 0xA7F000 - TPL_VA


def main() -> int:
    argv = sys.argv[1:]
    check = "--check" in argv
    args = [a for a in argv if a != "--check"]
    if len(args) != 1:
        raise SystemExit(__doc__)
    path = Path(args[0])
    data = bytearray(path.read_bytes())

    end = data.find(b"\x00", TPL_OFF)
    if end < 0:
        raise SystemExit("шаблон не найден (нет NUL) — не тот бинарь")
    cur = data[TPL_OFF:end].decode("utf-8", "replace")

    if cur == NEW_TPL:
        state = "done"
    elif cur in (BASE_TPL, OLD_TPL):
        state = "stock"
    else:
        state = "unknown"

    if check:
        print(f"kind9-шаблон (0xa7e800): {state}")
        print(f"длина: {len(cur)}; хвост после NUL: {data[end + 1:end + 5].hex()}")
        return 0

    if state == "done":
        print("уже пропатчено (уникальный id)")
        return 0
    if state != "stock":
        raise SystemExit(f"неожиданный шаблон: {cur[:64]!r}")

    need = len(NEW_TPL) + 1
    if need > TPL_LIMIT:
        raise SystemExit(f"не влезает в RX-зазор ({need} > {TPL_LIMIT})")
    tail = data[TPL_OFF + need : TPL_OFF + need + 16]
    if any(b != 0 for b in tail):
        raise SystemExit(f"за шаблоном не нули: {tail.hex()}")

    data[TPL_OFF:TPL_OFF + need] = NEW_TPL.encode() + b"\x00"
    path.write_bytes(bytes(data))
    print(f"{path}: kind9-шаблон 0xa7e800 -> col0 = id из MEDIA_TABLE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
