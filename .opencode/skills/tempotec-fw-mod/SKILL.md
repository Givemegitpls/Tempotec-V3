---
name: tempotec-fw-mod
description: "Use when unpacking, patching, rebuilding or testing the Tempotec V3 Analog firmware (.upt, SYSTEM.UBI): правки бинаря hiby_player (SQL-строки, UI), сборка образа, проверка, итерации на устройстве через adb, правки базы медиатеки. Trigger keywords: прошивка v3_analog, v3_analog.upt, SYSTEM.UBI, hiby_player, adb push hiby_player, translit_db, patch_player, patch_sql."
---

# Модификация прошивки Tempotec V3 Analog

Прошивка — ISO (`v3_analog.upt.txt`) с `SYSTEM.UBI` (корневая ФС) внутри. Оболочка
и медиатека — один бинарь `/usr/bin/hiby_player` (MIPS32 LE, stripped, SQLite
внутри, SQL-запросы текстом в `.rodata`). Медиатека живёт в **отдельном разделе**
`/data/usrlocal_media.db` и прошивкой не перезаписывается.

Тулчейн — скилл `tempotec-fw-docker`. Глубокие детали (адреса, слоты) —
`.opencode/NOTES.md`.

## Пайплайн

```
./tools/make.sh unpack      # v3_analog.upt.txt -> fw/unpacked (ISO) + fw/SYSTEM (UBIFS)
./tools/make.sh patch       # правки бинаря: tools/patch_player.py + tools/patch_sql.py
./tools/make.sh build [имя] # chown 1004:1004 -> mkfs.ubifs -> md5 в UPDATE.TXT -> out/<имя>
./tools/make.sh verify [имя]# распаковать результат, сверить md5/дерево/состав патчей
./tools/make.sh all         # всё подряд
```

Готовый образ — `out/<имя>` (по умолчанию `v3_analog_patched.upt`). Перед сборкой
убедиться, что `fw/SYSTEM` распакован из нужного образа (после смены исходника —
`unpack` заново).

## Правки бинаря

Два независимых патчера, оба идемпотентны и проверяются флагом `--check`:

- `tools/patch_player.py` — правки кода/строк по фиксированным адресам
  (например SQL-запрос списка треков альбома, 4 байта в обёртке вида);
  флаг `--album-level` включает дополнительную правку интерфейса.
- `tools/patch_sql.py` — правки SQL-строк, которыми плеер собирает таблицы списков.
  Строки адресуются по индексу из таблицы (база `0x9b7730`, 4 байта на запись).
  Если новая строка длиннее старой — она переносится в неиспользуемый «хвост»
  нулей в `.rodata` (`0x93f610`, до `0x93fce0`), а указатель в слоте таблицы
  переписывается.

Проверить состав патчей в готовом бинаре / образе:
```
./docker/fw.sh python3 tools/patch_player.py --check fw/SYSTEM/usr/bin/hiby_player
./docker/fw.sh python3 tools/patch_sql.py --check fw/SYSTEM/usr/bin/hiby_player
```

Семантику нового SQL-запроса проверять на копии реальной БД (обычный python3 +
sqlite3), а не «на глаз»: пример — `tools/test_query.py`.

## Правки базы медиатеки (не в прошивке)

Полоска букв в плеере — это картинка (`a_z.png`), а буква каждой записи хранится
в колонке `character` таблиц. Прыжок по букве считает позицию по числу записей,
поэтому **таблицы списков обязаны идти в порядке `character`**, а чтобы русские
имена искались латиницей — `character` транслитерируется. Логик две: у сущностей
(исполнители, альбомы, авторы альбомов, жанры) буква = транслит кириллицы в
латиницу; у треков — первая буква **названия** (плеер сам ставит её по исполнителю,
поэтому на `MEDIA_TABLE`/`MEDIA3_TABLE` стоит триггер, пересчитывающий её по
названию — иначе поиск в списке «All» не совпадает с порядком).

```
adb pull /data/usrlocal_media.db work/device/media.db
python3 tools/translit_db.py  work/device/media.db   # кириллица -> латиница + триггеры для новых записей
python3 tools/reorder_db.py   work/device/media.db   # порядок строк по character
python3 tools/album_artist_db.py work/device/media.db # «Артисты» = авторы альбомов
adb push work/device/media.db /data/usrlocal_media.db && adb shell 'sync; reboot'
```

Правки переживают перезагрузку и обновление медиатеки в плеере (триггеры `fix_char_*`),
но при полном пересоздании БД с нуля их надо повторить.

## Обложки в «Artists» (отдельная цепочка патчей)

Сток не показывает обложки в разделе «Artists → артист». Рабочая цепочка (после
`patch_player` + `patch_sql`): `tools/exp_album_view.py` → `tools/exp_flags_view21.py`
→ `tools/exp_coverpath_combo.py` → `tools/exp_cover_kind9col.py` →
`tools/exp_cover_kind9id.py` → `tools/exp_albums_by_album_artist.py`.
`exp_cover_kind9id` кладёт в строку списка `MEDIA_TABLE.id` альбома — по нему плеер
разрешает путь обложки; `exp_albums_by_album_artist` меняет фильтр списка с тега
трека `artist` на `album_artist` (совместные треки не мусорят). Порядок важен,
состав проверять `--check` каждого скрипта. Детали/адреса — `.opencode/NOTES.md`.

Кэш списков (`list_tb_*` + `MANAGER_TABLE` в `/data/usrlocal_media.db`) при
перепрошивке НЕ сбрасывается, и вид переиспользует старые строки. После установки
очистить один раз: `tools/clear_list_cache.py` (pull → clear → push → reboot);
медиатеку скрипт не трогает.

## Переключатель «альбомы ⇄ треки» в Artists

`tools/exp_artist_toggle.py` (после `exp_albums_by_album_artist`, до shuffle):
возвращает кнопку `sub_back_iv_list_type` в Artists, сохраняя обложки. Обложки
рисует только тип вида 4 (`vg_listview_album`), а кнопку показывает сборщик
`FUN_004c6ac0` только для типов `0xc–0x12`; обработчик `FUN_004c7ba0`
переключает `vg_listview_albums_of_an_artist` ⇄ `vg_listview_songs_of_artist_all`.
Скрипт: 6× `addiu -0x2d1c→-0x2d58` (обработчик + обёртка «исполнитель альбома»)
и RX-заглушка `0xa7e500` на jump-таблице типа 4 (`0x9642ac`), которая показывает
кнопку для типа 4, кроме ключа `album` (категория «Альбомы»). RX-карта:
shuffle guard `0xa7e370`, artist-toggle `0xa7e500`, kind9-шаблон `0xa7e800`.
Полная релизная цепочка (из базы `4429784b`):
`patch_player --album-level → patch_sql → exp_album_view → exp_flags_view21 →
exp_coverpath_combo → exp_cover_kind9col → exp_cover_kind9id →
exp_shuffle_linear → exp_shuffle_guard → exp_artist_toggle → exp_all_sort`.
`exp_albums_by_album_artist` больше не применяется: Artists снова по тегу `artist`
(слот 125 собирает `ARTIST_TABLE` из `ARTIST2_TABLE`), а слот 182 — стоковый
`WHERE artist like ?`. `exp_all_sort` добавляет `ORDER BY character,name` в SQL
списка «All» (слоты 159/305, строка `0x9c2438`), чтобы порядок не ломался после
обновления медиатеки. Детали — `.opencode/NOTES.md`.

## Итерации на устройстве (быстрее, чем перепрошивка)

На устройстве есть adb (скрипт `etc/init.d/S98adb_debug` в «отладочных» образах;
включается только при наличии файла `/mnt/sd_0/enable_adb` на SD-карте). Устройство
видно как `TempoTec V3`, root-shell есть.

```
adb push work/device/hiby_player.new /usr/bin/hiby_player   # rootfs смонтирован rw
adb shell 'chmod 755 /usr/bin/hiby_player; sync; reboot'
adb shell 'md5sum /usr/bin/hiby_player'                     # сверить, что залилось
```

Важно: убийство `hiby_player` уводит устройство в перезагрузку — это нормальный
способ применить новый бинарь.

## Что учитывать

- **БД не входит в образ** — прошивка отвечает за поведение, а не за содержимое
  медиатеки; при обнулении `/data` правки из предыдущего раздела надо повторить.
- Правки делаются «по месту»: длина строк сохраняется (padding), либо строка
  переносится с переписыванием указателя в слоте таблицы. Новый код в `.rodata`
  не кладём — это данные, не исполняемый сегмент (за исключением мест, где это
  проверено).
- Устройство слабое: избегать фоновых процессов и периодических опросов БД.
  Всё, что можно, вшивать в SQL-строки плеера — тогда расходов в рантайме ноль.
- Перед правкой всегда сохранять копию бинаря/БД (`work/device/*`), а после сборки
  прогонять `./tools/make.sh verify`.
