# TODO — Tempotec V3 Analog (мод прошивки)

Обновлено: 2026-10-08.

## Рабочее состояние

- **Свежая сборка:** `out/v3_analog_albumstep.upt` (ISO `fa9ce8fe…`, бинарь
  `fde1e6c2…`) — плюс переход «альбом → следующий альбом того же автора».
  Проверено на устройстве 2026-10-09 (Artists и Album Artist). Предыдущая —
  `out/v3_analog_aa_toggle.upt` (`c77cc270…`).
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
  exp_albums_artist_album_artist → exp_artist_tracks_component → exp_db_autofix`
  (+ `overlay/`, SQL-файл). (`exp_albums_by_component` заменён новым;
  `exp_albums_by_section` и `exp_albums_album_artist` удалены.)

## Открытые задачи

1. **Последний альбом автора → следующий автор.** Сейчас: если доиграл
   ПОСЛЕДНИЙ альбом автора — этот же альбом начинается заново (не «глобальный
   список» и не следующий автор). Продолжение задачи «переключение между
   альбомами» (само «альбом→альбом» сделано — см. ниже).
2. **adb: довести GUI-переключатель** (пасхалка About ×10 восстановлена правкой
   `set_functions.json` `"about":1`; в бинаре `fcn.0050b8e0` порог `slti v0,0xa`
   @`0x50b910`, зовёт `fcn.00476800` → `system("/etc/init.d/K90adb start|stop")`).
   - Закрепить `about:1` в сборке (положить `set_functions.json` в `overlay/` или
     сделать патч-скрипт — при `unpack` правка откатится).
   - Снизить число тапов (порог `0xa` @`0x50b910` → напр. 3).
   - Перенести триггер на «пианино» (логотип на About; сейчас тап по нему = титры
     с авторами) — по желанию.
   - Вернуть пункт USB-режима **Dock/adb** ИЛИ композитный `mass_storage,adb`
     (карта и adb одновременно) — предпочтительнее «пианинки».
   - Инфраструктура GUI есть: `about_dev`, `adb.dlg`, `menu/adb.png`,
     `vg_listview_usb_mode`. Референс: `work/hiby_adb_reference.md`,
     `work/hiby_adb_gui_reference.md`.
3. **Полоска A–Z** в «Жанры», «Исполнителе альбома» и на подуровнях — её нет.
4. **Транслит жанров на `É`** — 5 жанров без транслита (`tools/translit_db.py`).
5. **Чистка:** `work/_clr.db` (root) — удалить при удобном случае.

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

**Известное поведение (так и оставлено):** если доиграл ПОСЛЕДНИЙ альбом автора —
этот же альбом начинается заново (`FUN_004369a0(ключ, count)` возвращает ту же
строку, и хук копирует её обратно). В коде фикса НЕТ. План на будущее: после
выбора целевой записи сравнить её имя с текущим (`rec+0x20c`) и при совпадении
уйти в штатный fallback; затем — переход к следующему автору (тип раздела уже
хранится в `0xb02bf0`).

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
