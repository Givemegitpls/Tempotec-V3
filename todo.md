# TODO — Tempotec V3 Analog (мод прошивки)

Обновлено: 2026-10-08.

## Рабочее состояние

**Selfdb5** — бинарь `c7de2e50…`, образ `out/v3_analog_selfdb5.upt` (ISO/UBI
см. манифест). Проверено на устройстве:
- после «обновления медиатеки» БД собирается **самим плеером**: 17 триггеров,
  `ARTIST_TABLE` 77 без склеек, `MEDIA_TABLE` 3798 без «сырых» букв, порядок по
  `character`, integrity ok — **внешние скрипты не нужны**;
- подключение USB не вешает (adb опционален, по маркеру `/mnt/sd_0/enable_adb`).

Состав: `4429784b` (база) + `patch_player --album-level` + `patch_sql` +
`exp_album_view` + `exp_flags_view21` + `exp_coverpath_combo` +
`exp_cover_kind9col` + `exp_cover_kind9id` + `exp_shuffle_linear` +
`exp_shuffle_guard` + `exp_artist_toggle` + `exp_all_sort` +
`exp_albums_by_component` + `exp_artist_tracks_component` +
**`exp_db_autofix`** (хук `0x71D0B0`, выполняет `/usr/share/hiby_db_fix.sql`).

## Открытые задачи

1. **Развести Artists и «Исполнитель альбома».** Сейчас оба показывают одно и то
   же (у Дэна 5). Ожидаемо: Album Artist — по `album_artist` (у Дэна 2).
   Черновик — `experiments/2026-10-07/exp_album_list_context.py` (не сработал:
   `jal` из RX кодируется с чужим верхним нибблом — нужен `jalr`). Учесть: место
   в RX-зазоре уже занято авто-фиксом (0xa7ed00..0xa7ef9c) — потребуется больше
   места (расширить RX-сегмент) или иная схема.
2. **Полоска A–Z** в «Жанры», «Исполнитель альбома» и на подуровнях — её нет.
3. **Транслит жанров на `É`** — 5 жанров без транслита (в `tools/translit_db.py`).
4. **Чистка:** `work/_clr.db` (root) — удалить при удобном случае.

## Процесс (см. AGENTS.md)

- Один патч — одна итерация; после каждого — проверки и только потом следующий.
- **До флеша:** `python3 tools/verify_build.py <bin> [--image out/x.upt] [--db <копия>]`
  (права дерева, все `--check`, целостность образа, offline-симуляция БД).
- **Чек-лист регрессий:** Artists / «Исполнитель альбома» / Albums / All / Files;
  соавтор (`Дэн Субботин`); пустой список → «awaiting scan»; подключение USB не
  вешает.
- **Откат:** `adb push` known-good бинаря + `reboot`.
- **Грабли:** права `hiby_player` = `775` (иначе бутлуп); `jal`/`j` из RX уходят
  не туда — только `jalr`; маркер adb `/mnt/sd_0/enable_adb`.

## Артефакты

- `overlay/` — файлы, добавляемые в rootfs при сборке (`etc/init.d/S98adb_debug`).
- `experiments/2026-10-07/` — черновики (хук разведения разделов).
- `tools/exp_db_autofix.py`, `tools/make_db_fix_sql.py`, `tools/verify_build.py`,
  `tools/dedupe_rootfs.py` — инструменты самодостаточной БД и сборки.
- `backup/` — копии релизных образов/бинарей; `out/` — собранные образы.
