#!/usr/bin/env python3
"""Развести «Artists» и «Исполнитель альбома»: список альбомов по нужному тегу.

Цель: Artists → альбомы по составляющей тега `artist` (у `Дэн Субботин` = 5),
«Исполнитель альбома» → по `album_artist` (у `Дэн Субботин` = 2). Сейчас оба
раздела открывают один вид (`vg_listview_album`) с одним источником
(`FUN_004a9180`, kind 9) и одним запросом (слот 182) → списки одинаковые.

Почему разделы различимы (разобрано, подтверждено heap-дампом):
- открыватель Artists `FUN_004a8b20` передаёт префикс ключа `L"artist"`
  (@0x960b3c), открыватель «Исполнителя альбома» `FUN_004aa1a0` — `L"album_artist"`
  (@0x960b30); ключ дочернего вида = `<префикс>\\<имя>` (FUN_004a7500+FUN_0049d6e0);
- источник `FUN_004a9180`: `param_1` — виджет, `FUN_004627e0(widget)=widget+0x7c=вид`,
  ключ = `view+0x3de0` = `artist\\Дэн` / `album_artist\\Дэн`;
- `FUN_0049d760` (@0x4a9214) ОБРЕЗАЕТ ключ после `\\`, и уже голое имя кладётся в
  `rec+0x52c`; kind 9 (`FUN_00708d20` case 9) биндит `rec+0x52c` к слоту 182.
  Поэтому разделы неразличимы.

Правка (2 точки):
1. `0x4a9214`: `jal FUN_0049d760` (обрезка, 0x0C1275D8) → `jal FUN_00420f20`
   (bounded wide-копия, 0x0C1083C8; a2=0x80 уже выставлен выше). Теперь
   `rec+0x52c` = ПОЛНЫЙ ключ `artist\\ИМЯ` / `album_artist\\ИМЯ`.
2. слот 182 (SQL) → строка в `.rodata` 0x93fb00: фильтр по `album_artist`, если
   ключ начинается с `album_artist\\`, иначе по составляющей `artist`.
   Верхние «Альбомы» (ключ `album`) дают 0 строк, но берут данные из `ALBUM_TABLE`
   через ветку `FUN_0070b020` — поведение не меняется.

Проверено offline на копии реальной БД (3798 треков):
`artist\\Дэн Субботин`→5, `album_artist\\Дэн Субботин`→2, `artist\\Anacondaz`→16,
`album`→0 (в т.ч. с хвостовым NUL, как биндит плеер).

Скрипт заменяет `exp_albums_by_component` (та делала только artist-составляющую).
Идемпотентно, `--check`.

    python3 tools/exp_albums_artist_album_artist.py <hiby_player> [--check]
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

VTO = 0x400000
SQL_TABLE = 0x9B7730
SLOT = 182
NEW_VA = 0x93FB00
NEW_LIMIT = 0x93FD00          # дальше .rodata-дыра кончается (ссылки из кода)

HOOK_VA = 0x4A9214            # jal FUN_0049d760 (обрезка ключа после '\')
HOOK_OLD = 0x0C1275D8         # jal 0x49d760
HOOK_NEW = 0x0C1083C8         # jal 0x420f20 (FUN_00420f20, bounded wide-копия)

OLD_VA = 0x9C284C             # стоковая строка слота 182
OLD = b"SELECT DISTINCT album FROM MEDIA_TABLE WHERE artist like ? ORDER BY album collate pinyin"
# вариант exp_albums_by_component (предыдущее состояние цепочки)
COMPONENT = (
    b"SELECT DISTINCT album FROM MEDIA_TABLE WHERE "
    b"(';'||substr(artist,1,length(artist))||';') LIKE '%;'||substr(?1,1,length(?1))||';%' "
    b"ORDER BY album collate pinyin"
)
NEW = (
    b"SELECT DISTINCT album FROM MEDIA_TABLE WHERE "
    b"(?1 LIKE 'album_artist\\%' AND "
    b"(';'||substr(album_artist,1,length(album_artist))||';') "
    b"LIKE '%;'||substr(substr(?1,14),1,length(substr(?1,14)))||';%') "
    b"OR (?1 LIKE 'artist\\%' AND "
    b"(';'||substr(artist,1,length(artist))||';') "
    b"LIKE '%;'||substr(substr(?1,8),1,length(substr(?1,8)))||';%') "
    b"ORDER BY album collate pinyin"
)


def main() -> int:
    argv = sys.argv[1:]
    check = "--check" in argv
    args = [a for a in argv if a != "--check"]
    if len(args) != 1:
        raise SystemExit(__doc__)
    path = Path(args[0])
    d = bytearray(path.read_bytes())

    slot_off = SQL_TABLE - VTO + 4 * SLOT
    cur_va = struct.unpack_from("<I", d, slot_off)[0]
    hook = struct.unpack_from("<I", d, HOOK_VA - VTO)[0]
    at_new = cur_va == NEW_VA
    cur = bytes(d[NEW_VA - VTO : NEW_VA - VTO + 600].split(b"\x00")[0]) if at_new else b""
    done = at_new and cur == NEW and hook == HOOK_NEW

    if check:
        state = ("новая" if cur == NEW else
                 "component (старое)" if cur == COMPONENT else
                 "иное" if at_new else
                 "сток" if cur_va == OLD_VA else f"неизвестно {cur_va:#x}")
        print(f"слот {SLOT}: {cur_va:#x} ({state})")
        print(f"{HOOK_VA:#x} = {hook:#010x} "
              f"({'копия ключа' if hook == HOOK_NEW else 'обрезка/сток' if hook == HOOK_OLD else 'иное'})")
        return 0

    if done:
        print("уже пропатчено (albums artist vs album_artist)")
        return 0

    # --- SQL ---
    if cur_va == OLD_VA:
        old = bytes(d[OLD_VA - VTO : OLD_VA - VTO + len(OLD) + 1])
        if old != OLD + b"\x00":
            raise SystemExit(f"строка по {OLD_VA:#x} не совпала: {old[:120]!r}")
    elif cur_va == NEW_VA:
        if cur not in (COMPONENT,):
            # допускаем повторный запуск на «сломанных» черновиках: просто перезапишем
            pass
    else:
        raise SystemExit(f"слот {SLOT}: ожидался {OLD_VA:#x} или {NEW_VA:#x}, найдено {cur_va:#x}")

    off = NEW_VA - VTO
    need = len(NEW) + 1
    if NEW_VA + need > NEW_LIMIT:
        raise SystemExit(f"строка не влезает: {NEW_VA:#x}+{need} > {NEW_LIMIT:#x}")
    if cur_va == OLD_VA and not all(b == 0 for b in d[off : off + need]):
        raise SystemExit(f"место {NEW_VA:#x} занято")
    d[off : off + need] = NEW + b"\x00"
    struct.pack_into("<I", d, slot_off, NEW_VA)

    # --- hook ---
    if hook == HOOK_OLD:
        struct.pack_into("<I", d, HOOK_VA - VTO, HOOK_NEW)
    elif hook != HOOK_NEW:
        raise SystemExit(f"{HOOK_VA:#x}: ожидался {HOOK_OLD:#010x}, найдено {hook:#010x}")

    path.write_bytes(bytes(d))
    print(f"{path}: Artists/Album Artist -> {NEW_VA:#x} (слот {SLOT}), "
          f"{HOOK_VA:#x} -> копия полного ключа ({len(NEW)} байт SQL)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
