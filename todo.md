# TODO — Tempotec V3 Analog (мод прошивки)

Обновлено: 2026-10-08.

## Рабочее состояние

- **Свежая сборка (назад на границе автора):** `out/v3_analog_albumstep6.upt`
  (UBI `f5a8a5e4…`, бинарь `ef105b98…`, ISO `d46ea907…`) — «первый альбом автора
  → назад → последний альбом предыдущего автора» (симметрично «вперёд»), Artists
  и Album Artist. **Проверено на устройстве (2026-10-11).**
- **Свежая сборка (самодостаточная БД):** `out/v3_analog_selfdb10.upt`
  (UBI `f6b7de0e…`, бинарь `4ad95aa1…`) — вшитый DBFIX **починен**: хук перенесён
  с радио-сканера `0x71d0b0` на `commit transaction` в пересборке медиатеки
  `0x70ecfc`; `make.sh build` теперь генерирует `usr/share/hiby_db_fix.sql` в
  образ; `verify_build` проверяет вшитый SQL на копии БД. Offline OK (сырая БД
  0 триггеров/6 склеек → 18/0). **Проверено на устройстве (2026-10-10):** после
  прошивки и «Обновления медиатеки» бинарь `4ad95aa1…` совпадает,
  `/usr/share/hiby_db_fix.sql` на месте, триггеров 18 (`split_*` — новые CTE),
  склеек 0, «сырых» букв 0, integrity ok.
- **Свежая сборка (разбор соавторов):** `out/v3_analog_split2.upt` (UBI
  `b899f2aa…`, бинарь `ad7e7d4f…`) — неограниченный разбор `artist` **и**
  `album_artist` по `;` (CTE-триггеры + патч слотов чистки 143/146). Offline OK;
  на устройстве залито (бинарь + SQL + БД офлайн-разбором). Проверка: соавторы
  раздельны, должны пережить повторное «Обновление медиатеки». Предыдущая —
  `out/v3_analog_split1.upt` (только `artist`, бинарь `5304fa25…`).
- **Свежая сборка (shuffle):** `out/v3_analog_albumstep5.upt` (UBI `67a5d572…`,
  бинарь `a3a29d9c…`) — переход «альбом → следующий альбом автора» **и**
  «последний альбом автора → следующий автор», в Artists **и** Album Artist.
  **Проверено на устройстве 2026-10-10.** Фиксы по ходу: WCPY-аргументы,
  `lg()` сохраняет `t2`; `rec+0x52c` = полный ключ (сборка патчит
  `exp_albums_artist_album_artist`); имя автора в ctx для album_artist = `ctx+0x1e`.
  См. `docs/album-step.md`, `work/next_artist_reader_design.md`, `.opencode/NOTES.md`.
  Предыдущая (альбом→альбом, проверена 2026-10-09):
  `out/v3_analog_albumstep.upt` (бинарь `fde1e6c2…`).
- Предыдущая — `out/v3_analog_aa_toggle.upt` (`c77cc270…`).
- **Эталон цепочки:** бинарь `c7de2e50…` (Версия 8 CHANGELOG, база `4429784b` +
  цепочка). `out/v3_analog_selfdb6.upt` — НЕ чистый эталон: его бинарь содержит
  остаточный провальный `by_section` (stub @0x419328, hook @0x4a92a0).
- **На устройстве сейчас:** `aa_split` (бинарь `1029d446…`) — залит и проверен;
  кэш списков очищен (`tools/clear_list_cache.py`), БД-бэкап
  `work/device/media_dev_20261008.db`.
- **База сборки** `4429784b…` — НЕ сток (сток + `patch_player` + `patch_sql`);
  настоящий сток — `work/hiby_player` (`3a5db0fa…`), см. `docs/stock-baseline.md`.
- Цепочка: `patch_player --album-level → patch_sql → exp_album_view →
  exp_flags_view21 → exp_coverpath_combo → exp_cover_kind9col →
  exp_cover_kind9id → exp_shuffle_linear → exp_shuffle_guard →
  exp_shuffle_hierarchy → exp_artist_toggle → exp_toggle_album_artist → exp_all_sort →
  exp_albums_artist_album_artist → exp_artist_tracks_component → exp_db_autofix →
  patch_artist_cleanup → exp_usb_mode_adb`
  (+ `overlay/`, SQL-файл). (`exp_albums_by_component` заменён новым;
  `exp_albums_by_section` и `exp_albums_album_artist` удалены.)

## Открытые задачи

1. **Последний альбом автора → следующий автор — СДЕЛАНО и проверено на устройстве
   (2026-10-10).** `tools/exp_shuffle_hierarchy.py`. Сборка
   `out/v3_analog_albumstep5.upt` (бинарь `a3a29d9c…`). Работает в Artists и Album
   Artist: после последнего альбома автора включается первый альбом следующего
   автора. Грабли и разбор — `docs/album-step.md`, `work/next_artist_reader_design.md`.
2. **adb: пункт USB-режима «ADB» — СДЕЛАНО и проверено на устройстве (2026-10-11).**
   `tools/exp_usb_mode_adb.py`: генератор `FUN_004d2760` строил 2 строки
   (`dac`/`usb`); добавлена третья `adb` — код в пещере `0x41a000`, хук
   `0x4d2800 → jal 0x41a000`. Режим `FUN_00476bc0(2)` = adb (`18D1:0D02`,
   `functions=adb`), плюс пещера `0x41a100`/хук `0x476c80` — старт
   `/sbin/adbserver.sh` (иначе adbd не поднимался). Метка `<adb>` переименована
   «Dock»→**ADB** во всех языках (`tools/patch_usb_label.py`, в `make.sh build`).
   Сборка `out/v3_analog_usbmode3.upt` (бинарь `86c28f7a…`). Разбор —
   `work/adb_usb_mode_design.md`, `.opencode/NOTES.md`. **Проверено:** режим ADB
   сохранён (config 8); после перезагрузки с кабелем adb поднимается сам; карта
   остаётся у плеера. Маркер `enable_adb` и пасхалка About×10 не нужны.
   - Композит `mass_storage,adb` (карта и ПК, и adb) — отдельная ветка
     `FUN_00719880(1)` (`0x9c5b38`), не из `FUN_00476bc0`; делать по желанию.
   - Референс: `work/hiby_adb_reference.md`, `work/hiby_adb_gui_reference.md`.
3. **Полоска A–Z** в «Жанры», «Исполнителе альбома» и на подуровнях — её нет.
4. **Транслит жанров на `É`** — 5 жанров без транслита (`tools/translit_db.py`).
5. **Чистка:** `work/_clr.db` (root) — удалить при удобном случае.
6. **Множество авторов (соавторы) для Artists и Album Artist.** Итерации 1 и 2
   сделаны (CTE-триггеры `split_ARTIST2_TABLE`/`split_ALBUM_ARTIST2_TABLE`,
   одноразовый разбор, патч слотов 143/146, пересборка `ARTIST_TABLE`/
   `ALBUM_ARTIST_TABLE`; образ `out/v3_analog_split2.upt`, бинарь `ad7e7d4f`).
   Проверено offline на копии реальной БД (3.12.2). Разбор и проект —
   `work/artist_split_design.md`. **Осталось:**
   - **kind 0x21** «треки исполнителя альбома» (4 литерала
     `0x9ba474/0x9bb874/0x9bb9e0/0x9bbb4c`): сейчас точное `album_artist = ?`,
     у соавтора вернёт «no music». Нужен component-match (перенос строк в RX +
     правка `lui/addiu`).
   - Проверка на устройстве: после повторного «Обновления медиатеки» соавторы
     не склеиваются обратно (триггер + патч слотов 143/146).
7. **Вшитый DBFIX (`exp_db_autofix`) — СДЕЛАНО и проверено на устройстве
   (2026-10-10).** Причина «не отрабатывает»: точка хука `0x71d0b0` — радио-сканер,
   при «Обновлении медиатеки» не исполняется. Хук перенесён на `0x70ecfc`
   (`commit transaction` в пересборке `FUN_0070eb00`); `make.sh build` вшивает
   `usr/share/hiby_db_fix.sql`; `verify_build` проверяет SQL на копии БД. Сборка
   `out/v3_analog_selfdb10.upt` (бинарь `4ad95aa1…`). Детали — `.opencode/NOTES.md`
   (сессия 2026-10-10 прод.). **Проверено:** после прошивки + «Обновления
   медиатеки» триггер `split_ARTIST2_TABLE` стал новым (CTE), соавторы раздельны,
   сырых букв 0, integrity ok.

### Переключение между альбомами — СДЕЛАНО (альбом→альбом)

Скрипт `tools/exp_shuffle_hierarchy.py` (в цепочке `verify_build.py` после
`exp_shuffle_guard`). Проверено на устройстве 2026-10-09: Artists→`Дэн Субботин`
→ альбом → доиграл → следующий его альбом; Album Artist — аналогично.
Разбор — `work/stock_album_step_design.md`.

Ключевые факты: сток кликал альбом с ключом `artist\<Артист>\<Альбом>` (гейт
автоперехода не срабатывал); наш `exp_album_view` даёт ключ `album\<Альбом>` →
глобальный переход. Решение: контекст автора при открытии списка альбомов
(`FUN_004a9180` @`0x4a9288`) + на автопереходе (`FUN_004eae80` @`0x4eaf2c`)
подставлять следующий альбом из списка автора через штатную `FUN_004369a0`.
Грабля: wide-слово префикса собирается как `второй символ<<16 | первый`
(`artist` = `0x0072_0061`, не `0x0061_0072`).

**Проверенная сборка:** бинарь `fde1e6c26e08a7909ceeb4b4e1b93ce9` — ровно тот
код, что лежит в `tools/exp_shuffle_hierarchy.py` (образ
`out/v3_analog_albumstep.upt`, ISO `4c11ceed5de692c4bfd2218b0449b41e`; ISO-хеш
не воспроизводим — таймстампы, значим md5 бинаря).

**Обновление (albumstep4):** повтор последнего альбома исправлен — при совпадении
целевого альбома с текущим хук уходит к следующему автору (см. п.1 «Открытых
задач»); если следующего автора нет — штатный fallback. Чтение строк — через
`FUN_0070b020` (SQL, минуя «живой вид»); `rec+0x52c` = имя без префикса. Направление
«назад» на границе автора — штатный fallback.

### Закрыто 2026-10-08

- **Разведение Artists и «Исполнитель альбома»** — Artists→`Дэн Субботин` = 5,
  «Исполнитель альбома»→`Дэн Субботин` = 2; проверено на устройстве. Детали —
  `docs/next-album-artist.md`, скрипт `tools/exp_albums_artist_album_artist.py`.
- **Переключатель треков в «Исполнителе альбома»** — теперь 2 трека (по
  `album_artist`), не 13; назад к альбомам; Artists не задет. Скрипт
  `tools/exp_toggle_album_artist.py`.

## Процесс (см. AGENTS.md)

- Один патч — одна итерация; проверки ДО флеша:
  `python3 tools/verify_build.py <bin> [--image out/x.upt] [--db <копия>]`.
- Чек-лист: Artists / «Исполнитель альбома» / Albums / All / Files; соавтор
  (`Дэн Субботин`); пустой список → «awaiting scan»; подключение USB не вешает.
- Откат: `adb push` known-good бинаря + `reboot`; образы — в `out/`.
- **Грабли:** права `hiby_player` = `775` (иначе бутлуп); `jal`/`j` из RX/пещеры —
  только `jalr`; флаги `open` на MIPS o32 (`O_CREAT=0x100`, `O_APPEND=0x8`); adb —
  по маркеру в момент загрузки.

## Артефакты

- `docs/` — `stock-baseline.md` (сток), `ui-queries.md` (карта UI→SQL нашей v7),
  `next-album-artist.md` (решение Artists/Album Artist).
- `tools/` — патчи цепочки, `verify_build.py`, `dump_sql_slots.py`,
  `make_db_fix_sql.py`, `dedupe_rootfs.py`, `exp_albums_artist_album_artist.py`
  (разведение Artists/Album Artist), `exp_toggle_album_artist.py` (переключатель
  треков в Album Artist), `diag_album_keys.py` (заготовка диагностики).
- `overlay/` — файлы, добавляемые в rootfs при сборке (`S98adb_debug`).
- `experiments/2026-10-07/` — ранние черновики.
- `backup/` — релизные образы/бинари; `out/` — собранные образы.
