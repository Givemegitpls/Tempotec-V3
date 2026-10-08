# TODO — Tempotec V3 Analog (мод прошивки)

Обновлено: 2026-10-08.

## Рабочее состояние

- **Свежая сборка:** `out/v3_analog_aa_split.upt` (ISO md5 `b4d377d2…`, UBI
  `cb027352…`, бинарь `1029d446…`) — Artists и «Исполнитель альбома» разведены
  (5 vs 2), всё из версий 1–8. **Проверено на устройстве 2026-10-08** (сейчас
  залито на плеер).
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
  exp_artist_toggle → exp_all_sort → exp_albums_artist_album_artist →
  exp_artist_tracks_component → exp_db_autofix` (+ `overlay/`, SQL-файл).
  (`exp_albums_by_component` заменён новым; `exp_albums_by_section` и
  `exp_albums_album_artist` удалены как проваленные.)

## Открытые задачи

1. **Полоска A–Z** в «Жанры», «Исполнителе альбома» и на подуровнях — её нет.
2. **Транслит жанров на `É`** — 5 жанров без транслита (`tools/translit_db.py`).
3. **Чистка:** `work/_clr.db` (root) — удалить при удобном случае.

### Закрыто 2026-10-08

- **Разведение Artists и «Исполнитель альбома»** — Artists→`Дэн Субботин` = 5,
  «Исполнитель альбома»→`Дэн Субботин` = 2; проверено на устройстве. Детали —
  `docs/next-album-artist.md`, скрипт `tools/exp_albums_artist_album_artist.py`.

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
  (разведение Artists/Album Artist), `diag_album_keys.py` (заготовка диагностики).
- `overlay/` — файлы, добавляемые в rootfs при сборке (`S98adb_debug`).
- `experiments/2026-10-07/` — ранние черновики.
- `backup/` — релизные образы/бинари; `out/` — собранные образы.
