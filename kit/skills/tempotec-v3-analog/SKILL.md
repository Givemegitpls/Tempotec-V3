---
name: tempotec-v3-analog
description: "Use for Tempotec V3 Analog firmware work specifically: known base binary md5, patch chain for album covers in Artists, album_artist filter, Cyrillic alphabet search, media DB scripts, ADB iteration. Trigger keywords: v3_analog.upt, Tempotec V3, hiby_player 4429784b, v3_analog_coverid, exp_cover_kind9id, exp_albums_by_album_artist, list_tb_, clear_list_cache."
---

# Tempotec V3 Analog — конкретика

Общий метод — скилл `hiby-firmware-patching`; глубина — `reference/NOTES-v3.md`.

## Базы и адреса

- Эталонный бинарь (база всех патчей): md5 `4429784bfb605f8743b15e4e06660d01`
  (`/usr/bin/hiby_player`, MIPS32 LE, `VA = file_offset + 0x400000`).
- RX-запас: `0x67e370..0x67f000` (VA `0xa7e370..0xa80000`); phdr2 `filesz/memsz → 0x67f000`.
- Свободный хвост `.rodata`: `0x93f610..0x93fce0`.
- Таблица SQL-строк: база `0x9b7730`, шаг 4. Таблица видов: `0x95e770`, запись `0x3c`.
- Слот источника вида: `0xABE114` (file `0x6ae114`).

## Релиз с фичами

- **Текущий релиз:** `out/v3_analog_selfdb5.upt` — бинарь `c7de2e50…` (ISO
  `38e4c70f…`, UBI `18d3dff3…`): **самодостаточная медиатека** (после «обновления
  медиатеки» плеер сам правит БД) + всё из версий 1–7; adb — по маркеру
  `/mnt/sd_0/enable_adb`.
- Предыдущие: `out/v3_analog_artist_stock.upt` (`edcb682f…`),
  `out/v3_analog_artist_toggle.upt` (`865e6d3a…`),
  `out/v3_analog_shuffle.upt` (`0c8d1ef1…`),
  `out/v3_analog_coverid.upt` (`60df95e4…`).

## Порядок патчей (важно)

```
база 4429784b
+ patch_player.py --album-level + patch_sql.py
+ exp_album_view.py             # вид-21 -> vg_listview_album
+ exp_flags_view21.py           # w4=1,w5=1 (поток обложек)
+ exp_coverpath_combo.py        # RX-шаблон INSERT + path, phdr2, источник пути
+ exp_cover_kind9col.py         # слот 0xABE114 := 0x4A9180, col3=?2
+ exp_cover_kind9id.py          # col0 = MEDIA_TABLE.id (обложка своего альбома)
+ exp_shuffle_linear.py         # обратимый shuffle (nop @ 0x42dd8c)
+ exp_shuffle_guard.py          # сброс состояния шафла при смене списка (хук @0xa7e370)
+ exp_artist_toggle.py          # кнопка «альбомы ⇄ треки» в Artists (заглушка @0xa7e500)
+ exp_all_sort.py               # ORDER BY character,name в SQL «All» (слоты 159/305)
+ exp_albums_by_component.py    # список альбомов артиста — матч по составляющей artist
+ exp_artist_tracks_component.py# списки треков артиста — то же (0x9ba000/0x9bb000)
+ exp_db_autofix.py             # самодостаточная БД: хук @0x71D0B0 -> /usr/share/hiby_db_fix.sql
```

`exp_albums_by_album_artist` больше не применяется (Artists снова по тегу `artist`).
Формула матча по составляющей — `substr(x,1,length(x))`, НЕ `replace(...,char(0),'')`
(NUL в значениях БД ломает LIKE). RX-карта: shuffle guard `0xa7e370`, artist-toggle
`0xa7e500`, kind9-шаблон `0xa7e800`, строки треков `0xa7e900/0xa7eb00`, авто-фикс
`0xa7ed00` (DBFIX) + путь `0xa7ef80`.

## Медиатека

**Самодостаточно (в образе):** `exp_db_autofix.py` (хук `0x71D0B0`, «Scanner
stopped») выполняет `/usr/share/hiby_db_fix.sql` (генерируется
`make_db_fix_sql.py`) через `sqlite3_exec` — после «обновления медиатеки» плеер
сам расставляет буквы, разбирает `artist` по `;` и пересобирает списки.
Компьютер и adb не нужны. Проверено: 17 триггеров, склеек 0, «сырых» букв 0.
Точку `0x4E980C` (эпилог `FUN_004e97c0`) НЕ использовать — общая функция
ожидания, вызывается и при подключении USB, плеер вешается.

**Офлайн (скрипты, для копии базы или начальной настройки):**

```
adb pull /data/usrlocal_media.db work/device/media.db
python3 tools/examples/translit_db.py     work/device/media.db   # буквы + триггеры
python3 tools/examples/reorder_db.py      work/device/media.db   # порядок по character
python3 tools/examples/split_artists_db.py work/device/media.db  # разбор artist по ';'
adb push work/device/media.db /data/usrlocal_media.db && adb shell 'sync; reboot'
```

Порядок `translit → reorder → translit → split` (reorder пересоздаёт таблицы и
сносит триггеры).

Кэш списков после смены логики сбрасывать один раз:
`python3 tools/examples/clear_list_cache.py <db>` (чистит `list_tb_*` и `MANAGER_TABLE`,
медиатеку не трогает).

## Итерации на устройстве

```
adb push work/test/hiby_player.new /usr/bin/hiby_player
adb shell 'chmod 755 /usr/bin/hiby_player; sync; md5sum /usr/bin/hiby_player; reboot'
```
Канал adb живёт первые минуты после включения; при отвале `adb kill-server`.
Откат — релизный образ или ранее сохранённый `hiby_player.release`.

## Известные ограничения

- **Artists и «Исполнитель альбома» показывают одинаковый список альбомов** (общий
  запрос, слот 182). Ожидаемо: Artists — по составляющей `artist`, Album Artist —
  по `album_artist`. Следующая задача (правка кода; прошлый черновик хука не
  сработал из-за `jal` из RX — нужен `jalr`).
- Полоски нет в «Жанрах», «Исполнителе альбома» и на подуровнях (особенность
  прошивки). Жанры на `É` — без транслита.
- Кириллица в самой полоске не делается (стоковая `a_z.png` A–Z + `#`); поиск
  работает через транслит в колонке `character`.

## Грабли (кратко)

- **Права `usr/bin/hiby_player` = `775`** — иначе образ соберётся, но плеер не
  запустится (бутлуп на заставке). Проверяет `tools/verify_build.py`.
- **`jal`/`j` из RX-зоны уходят не туда** (верхний ниббл PC) — из RX только `jalr`;
  помни про delay-слот `jalr`.
- **adb — по маркеру** `/mnt/sd_0/enable_adb` (иначе гаджет стоковый; активный adb
  ломает обычное подключение к ПК).
- **Хук на «общей» функции вешается на все вызовы** — проверяй вызывающих.
- Апдейтер виснет на битом `.upt` — сверяй md5 файла на карте.
