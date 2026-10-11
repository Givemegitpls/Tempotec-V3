---
name: tempotec-fw-mod
description: "Use when unpacking, patching, rebuilding or testing the Tempotec V3 Analog firmware (.upt, SYSTEM.UBI): правки бинаря hiby_player (SQL-строки, UI), сборка образа, проверка, итерации на устройстве через adb, правки базы медиатеки. Trigger keywords: прошивка v3_analog, v3_analog.upt, SYSTEM.UBI, hiby_player, adb push hiby_player, translit_db, patch_player, patch_sql."
---

# Модификация прошивки Tempotec V3 Analog

Прошивка — ISO (`v3_analog.upt`) с `SYSTEM.UBI` (корневая ФС) внутри. Оболочка
и медиатека — один бинарь `/usr/bin/hiby_player` (MIPS32 LE, stripped, SQLite
внутри, SQL-запросы текстом в `.rodata`). Медиатека живёт в **отдельном разделе**
`/data/usrlocal_media.db` и прошивкой не перезаписывается.

Тулчейн — скилл `tempotec-fw-docker`. Глубокие детали (адреса, слоты) —
`.opencode/NOTES.md`.

## Пайплайн

```
./tools/make.sh unpack      # v3_analog.upt -> fw/unpacked (ISO) + fw/SYSTEM (UBIFS)
./tools/make.sh patch       # правки бинаря: tools/patch_player.py + tools/patch_sql.py
./tools/make.sh build [имя] # overlay/ -> make_db_fix_sql -> dedupe дубликатов
                            #   -> chown 1004:1004 -> chmod 775 -> mkfs.ubifs
                            #   -> md5 в UPDATE.TXT -> out/<имя>
./tools/make.sh verify [имя]# распаковать результат, сверить md5/дерево/состав патчей
./tools/make.sh all         # всё подряд
```

Проверки ДО флеша: `python3 tools/verify_build.py <bin> [--image out/x.upt] [--db <копия>]`
— права дерева (иначе бутлуп), наличие вшитого `usr/share/hiby_db_fix.sql`, все
`--check` цепочки, целостность образа, прогон вшитого SQL на копии БД
(триггеры/склейки/буквы/integrity).

Готовый образ — `out/<имя>`; по умолчанию имя **`v3_analog.upt`** (т.е.
`out/v3_analog.upt`). Другое имя: первый аргумент (`build|verify [имя]`) или
переменная окружения `IMAGE=...`; исходник стока — `SRC=...` (по умолчанию
`v3_analog.upt`). На SD-карту образ кладётся строго как `v3_analog.upt`. Перед
сборкой убедиться, что `fw/SYSTEM` распакован из нужного образа (после смены
исходника — `unpack` заново).

**Грабли сборки:** `usr/bin/hiby_player` должен быть исполняемым (`775`) — иначе
образ соберётся, но плеер не запустится (бутлуп на заставке). `make.sh build` и
`verify_build.py` это проверяют.

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

## Медиатека: самодостаточная правка (в прошивке)

Начиная с selfdb-сборки плеер **сам** приводит БД в порядок после «обновления
медиатеки»: `tools/exp_db_autofix.py` (хук `0x70ECFC` — `jal 0x6fbd80`
«commit transaction» в `FUN_0070eb00`, пересборке таблиц) выполняет
`/usr/share/hiby_db_fix.sql` (генерируется `tools/make_db_fix_sql.py` и **вшивается
в образ шагом `make.sh build`**) через `sqlite3_exec`. DBFIX вызывается на том же
handle, что и commit (регистр `a0`), а не через глобал. SQL идемпотентный: карта
`CYR_MAP`, триггеры `fix_char_*`, `split_ARTIST2_TABLE` и
`split_ALBUM_ARTIST2_TABLE` (разбор `;` на **любое** число соавторов — рекурсивный
CTE), одноразовый разбор склеек и пересборка списков по `character`. Компьютер и
adb не нужны. Подробности разбора соавторов — `docs/artist-split.md`.

**Точки, которые НЕ использовать:**
- `0x71D0B0` (лог «Scanner stopped») — это FM-**радио** seek-сканер (рядом строки
  `Radio Seek Start/Status/...`), при «обновлении медиатеки» не исполняется; старая
  версия хука стояла здесь и молча не срабатывала. Новый скрипт снимает этот хук.
- `0x4E980C` (эпилог `FUN_004e97c0`) — общая функция ожидания, вызывается и при
  подключении USB; наш SQL там вешает плеер.

RX-стаб DBFIX: `0xa7ed00..0xa7ee1c` (не пересекать — с `0xa7ee1c` лежит строка
слота 146 от `patch_artist_cleanup`), путь `/usr/share/hiby_db_fix.sql` — `0xa7ef80`.

## Правки базы медиатеки офлайн (скрипты)

Для офлайн-работы с копией базы (или начальной настройки) остались скрипты.
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
python3 tools/translit_db.py  work/device/media.db   # ЕЩЁ РАЗ (reorder снёс триггеры)
python3 tools/split_artists_db.py work/device/media.db # разбор соавторов artist/album_artist по ';'
adb push work/device/media.db /data/usrlocal_media.db && adb shell 'sync; reboot'
```

Порядок важен: `reorder_db` пересоздаёт таблицы (`rename`+`create`) и **сносит**
триггеры, поэтому `translit_db` идёт вторым проходом. `split_artists_db` — последним
(создаёт CTE-триггеры, разбирает существующие склейки, пересобирает
`ARTIST_TABLE`/`ALBUM_ARTIST_TABLE`).

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
Полная релизная цепочка (из базы `4429784b`, порядок = `tools/verify_build.py`
`CHAIN`):
`patch_player --album-level → patch_sql → exp_album_view → exp_flags_view21 →
exp_coverpath_combo → exp_cover_kind9col → exp_cover_kind9id →
exp_shuffle_linear → exp_shuffle_guard → exp_shuffle_hierarchy →
exp_artist_toggle → exp_toggle_album_artist → exp_all_sort →
exp_albums_artist_album_artist → exp_artist_tracks_component → exp_db_autofix →
patch_artist_cleanup → exp_usb_mode_adb`
(+ в образ `overlay/` и `/usr/share/hiby_db_fix.sql`).
`patch_artist_cleanup` — слоты чистки скана 143/146 → component-match, чтобы
разбор соавторов (`split_*_TABLE`, `docs/artist-split.md`) переживал обновление
медиатеки; строки в `.rodata 0x93f90c` и RX `0xa7ee1c`.
`exp_shuffle_hierarchy` — переход «альбом → следующий альбом того же автора»,
«последний альбом автора → следующий автор» и «первый альбом автора → назад →
последний альбом предыдущего автора» (заглушки в `.text`-пещере
`0x4194a0`/`0x419800`; кадр `eos` `0xe00`, буфер последнего альбома `sp+0xc00`;
детали — `docs/album-step.md`, `.opencode/NOTES.md`). `exp_albums_by_album_artist`
больше не применяется: Artists снова по тегу `artist` (слот 125 собирает
`ARTIST_TABLE` из `ARTIST2_TABLE`). `exp_albums_by_component`/`exp_artist_tracks_component`
делают фильтр списков альбомов/треков артиста матчем по составляющей `artist`
(разбор склейки `X;Y` по `;`) — формула через `substr(x,1,length(x))`, НЕ через
`replace(...,char(0),'')` (NUL ломает LIKE). `exp_db_autofix` — самодостаточная БД.
`exp_usb_mode_adb` — пункт «ADB» в меню USB-режима: генератор `FUN_004d2760`
строил 2 строки; третья — код в пещере `0x41a000`, хук `0x4d2800 → jal 0x41a000`.
Плюс пещера `0x41a100`/хук `0x476c80` — старт `/sbin/adbserver.sh` для режима adb
(иначе adbd не поднимается). Метка `<adb>` → `ADB` во всех языках:
`patch_usb_label.py` (в `make.sh build`).
`exp_all_sort` добавляет `ORDER BY character,name` в SQL списка «All»
(слоты 159/305, строка `0x9c2438`). Детали — `.opencode/NOTES.md`.

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
  медиатеки. Но самодостаточная правка (`exp_db_autofix` + SQL-файл) чинит БД
  сама при «обновлении медиатеки», в т.ч. после обнуления `/data`.
- **`jal`/`j` ИЗ RX-зоны (`0xa7e370..0xa7f000`) уходят не туда** — кодируются с
  верхним нибблом PC (`0xa…`). Любой вызов из RX-кода — только `jalr`
  (`lui t9,hi; addiu t9,t9,lo; jalr t9`). И помни про delay-слот `jalr`.
- **adb — только по маркеру** `/mnt/sd_0/enable_adb` (`overlay/etc/init.d/S98adb_debug`);
  без маркера гаджет стоковый. Активный adb-гаджет ломает обычное подключение к ПК.
- **Хук на «общей» функции вешается на все её вызовы.** Перед хуком проверь всех
  вызывающих и что точка реально исполняется в нужном сценарии (примеры провала:
  `0x4E980C` — общая функция ожидания; `0x71D0B0` — радио-сканер, а не медиатека).
- Правки делаются «по месту»: длина строк сохраняется (padding), либо строка
  переносится с переписыванием указателя в слоте таблицы. Новый код в `.rodata`
  не кладём — это данные, не исполняемый сегмент (за исключением мест, где это
  проверено).
- Устройство слабое: избегать фоновых процессов и периодических опросов БД.
  Всё, что можно, вшивать в SQL-строки плеера — тогда расходов в рантайме ноль.
- Перед правкой всегда сохранять копию бинаря/БД (`work/device/*`), а после сборки
  прогонять `./tools/make.sh verify`.
