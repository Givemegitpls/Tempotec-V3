#!/usr/bin/env python3
"""Байтовые патчи для `/usr/bin/hiby_player` (MIPS32, Tempotec V3 Analog).

Оболочка `hiby_player` содержит встроенную SQLite, а тексты SQL-запросов лежат
в `.rodata` открытым текстом. Запросы читаются из этих строк в момент открытия
списка, поэтому правка текста запроса = правка поведения медиатеки, без
дизассемблирования и без изменения кода.

Правила, которые соблюдает этот скрипт:
  * строка заменяется байт-в-байт по длине (остаток добивается пробелами) —
    адреса и смещения в бинаре не меняются, пересборка таблиц не нужна;
  * число и порядок параметров (`?1`, `?2`, ...) сохраняются — код биндинга
    не трогаем;
  * каждый патч обязан найтись ровно один раз, иначе сборка падает.

Запускать внутри docker-образа: `python3 tools/patch_player.py <путь к hiby_player>`.
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

# Патч 1: список треков альбома, открытого через артиста.
#
# Исходный запрос фильтрует треки по тегу артиста ТРЕКА, поэтому треки с другим
# artist (гости, feat.) пропадают из альбома. В категории «Альбомы» тот же
# список строится без фильтра по артисту, поэтому там альбом полный.
#
# Правка: фильтруем по автору альбома ИЛИ артисту трека, и оставляем условия
# по типу файла в сокращённом виде (has_child_file IN (0,1,2) эквивалентно
# четырём исходным веткам). Число параметров прежнее: ?1 = альбом, ?2 = артист.
OLD_ALBUM_AND_ARTIST = (
    b"WHERE (album = ? AND artist = ? ) AND ((has_child_file = 0 AND ck_id > 0) "
    b"OR (has_child_file = 0 AND ck_id = 0) OR(has_child_file = 2) OR "
    b"(has_child_file = 1)))"
)
NEW_ALBUM_AND_ARTIST = (
    b"WHERE (album = ?1 AND (artist LIKE ?2 OR album_artist LIKE ?2)) "
    b"AND has_child_file IN (0,1,2))"
)

PATCHES: list[tuple[str, bytes, bytes]] = [
    (
        "album-and-artist: показывать все треки альбома (включая совместные)",
        OLD_ALBUM_AND_ARTIST,
        NEW_ALBUM_AND_ARTIST,
    ),
]

# Патч 2 (экспериментальный, включается флагом --album-level).
#
# Категория «исполнитель альбома» открывает вид `vg_listview_songs_of_an_album_artist`
# (плоский список треков). В обёртке (vaddr 0x4aa1c4) имя вида загружается парой
# lui/addiu; подменяем только смещение, чтобы получить vaddr строки
# `vg_listview_albums_of_an_artist` (0x95d2e4) — вид «список альбомов артиста»,
# который уже используется категорией «Артисты» и сам группирует треки по альбому.
#
# Ключ (u"album_artist") не трогаем: именно он заставляет запрос под этим уровнем
# брать треки по album_artist.
VIEW_NAME_PATCH = (
    "album level: категория «исполнитель альбома» открывает список альбомов",
    0x4AA21C - 0x400000,  # файловое смещение инструкции addiu a2, a2, 0x948
    bytes.fromhex("4809c624"),  # addiu a2, a2, 0x948   -> 0x960948 songs_of_an_album_artist
    bytes.fromhex("e4d2c624"),  # addiu a2, a2, -0x2d1c -> 0x95d2e4 albums_of_an_artist
    # защита от правки не того места: предыдущая инструкция jal fcn.004a7500
    (0x4AA218 - 0x400000, bytes.fromhex("409d120c")),
    (0x4AA208 - 0x400000, bytes.fromhex("9600063c")),  # lui a2, 0x96
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check_statement(data: bytes, old: bytes, new: bytes) -> None:
    """Скобки и параметры проверяем на всём SQL-выражении, а не на фрагменте:
    фрагмент заканчивается до последней закрывающей скобки."""
    start = data.rfind(b"\x00", 0, data.find(new)) + 1
    end = data.find(b"\x00", start)
    sql = data[start:end]
    if sql.count(b"(") != sql.count(b")"):
        raise SystemExit(f"несбалансированные скобки в {sql!r}")
    if b"?1" not in new or b"?2" not in new:
        raise SystemExit(f"потеряна нумерация параметров: {new!r}")
    named = [int(m) for m in re.findall(rb"\?(\d+)", sql)]
    unnamed = re.sub(rb"\?\d+", b"", sql).count(b"?")
    if named != [1, 2, 2] or unnamed:
        raise SystemExit(f"неожиданный набор параметров {named}/{unnamed} в {sql!r}")


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    if len(args) != 1:
        raise SystemExit(__doc__)
    path = Path(args[0])
    data = path.read_bytes()
    before = sha256(data)
    check_only = "--check" in flags
    if check_only:
        for name, old, new in PATCHES:
            state = "применён" if old not in data and new in data else "не применён"
            print(f"  [{state}] {name}")
        name, offset, old, new, *_ = VIEW_NAME_PATCH
        state = "применён" if old not in data and new in data else "не применён"
        print(f"  [{state}] {name}")
        print(f"{path}: sha256 {before}")
        return 0
    print(f"{path}: {len(data)} байт, sha256 {before}")

    for name, old, new in PATCHES:
        if new in data and old not in data:
            print(f"  [skip] {name}: уже применён")
            continue
        if len(new) > len(old):
            raise SystemExit(f"{name}: новая строка длиннее исходной на {len(new) - len(old)}")
        count = data.count(old)
        if count != 1:
            raise SystemExit(f"{name}: найдено вхождений {count}, ожидалось 1")
        replacement = new + b" " * (len(old) - len(new))
        data = data.replace(old, replacement)
        check_statement(data, old, new)
        print(f"  [ok]   {name} ({len(old)} -> {len(new)} байт + padding)")

    if "--album-level" in flags:
        name, offset, old, new, *guards = VIEW_NAME_PATCH
        if new in data and old not in data:
            print(f"  [skip] {name}: уже применён")
        else:
            for guard_off, guard in guards:
                if data[guard_off : guard_off + len(guard)] != guard:
                    raise SystemExit(
                        f"{name}: не совпала защитная последовательность по смещению "
                        f"{guard_off:#x} — бинарь не тот, правка отменена"
                    )
            if data[offset : offset + len(old)] != old:
                raise SystemExit(f"{name}: по смещению {offset:#x} ожидалось {old.hex()}")
            data = (
                data[:offset] + new + data[offset + len(old) :]
            )
            print(f"  [ok]   {name} (смещение {offset:#x})")
    elif "--album-level" not in flags and "--no-album-level" not in flags:
        print("  (флаг --album-level не указан: экспериментальная правка не применена)")

    if sha256(data) == before:
        print("изменений нет")
        return 0
    path.write_bytes(data)
    print(f"{path}: sha256 после правки {sha256(data)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
