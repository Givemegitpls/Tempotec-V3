# UI → SQL: какие запросы уходят из интерфейса и когда

Карта для бинаря `edcb682f…` (`work/test_hf5/hiby_player.artist_stock`), снята
субагентом 2026-10-08; адреса — VA (файл + 0x400000). Все SQL-строки выгружены в
`work/sql_slots.txt` (`tools/dump_sql_slots.py`). Часть выводов помечена
«не подтверждено» — их надо проверить на живом плеере.

## Архитектура (две ветки)

- **A. Верхние списки** (All/Albums/Artists/Album Artist/Genres/Formats/Collect/
  History/M3U/Recent). Источник данных вида — `view+0x423c` из таблицы `0xabd4cc`
  (по индексу шаблона). Далее `FUN_004a1ba0(...)` или сразу
  `FUN_0070b020(rec,0,idx,0,key)` → `SELECT * FROM <ENTITY_TABLE> limit ? offset ?`;
  счёт — `FUN_0070aa60(key)`.
- **B. Подсписки** («треки/альбомы X»). `FUN_0070a3a0(kind,0,rec,0)` →
  `FUN_00708d20(kind)` строит `list_tb_N` (SQL-литералы inline) →
  `FUN_0070b020(...)` → `FUN_007060a0(key)` возвращает номер `list_tb_N` →
  `SELECT * FROM list_tb_N …`.

**Триггеры:** открытие вида = вызов data-source; клик по строке = `FUN_004a7500`
строит ключ `<prefix>\<col2>` и открывает дочерний вид; полоска A–Z = `FUN_00703320`
(count/позиция по `character`); «обновление медиатеки» = слоты 119–130, 143–156
(+ `exp_db_autofix` выполняет `/usr/share/hiby_db_fix.sql`).

## Экраны

| Экран (view, type) | kind / key | SQL (слот / VA) | Когда |
|---|---|---|---|
| **All** `VG_LISTVIEW_ALL` (0) | key `all` | **слот 159** `0x93fa00` = `SELECT * FROM MEDIA_TABLE ORDER BY character,name limit ? offset ?` | открытие; сортировка; полоска |
| **Albums** `VG_LISTVIEW_ALBUM` (4) | сток: key `album`; здесь источник подменён на kind 9 | сток: **слот 173** `SELECT * FROM ALBUM_TABLE …`; здесь: **слот 182** `SELECT DISTINCT album FROM MEDIA_TABLE WHERE artist like ? …` | открытие Albums |
| **Artists** `VG_LISTVIEW_ARTIST` (3) | key `artist` | **слот 172** `SELECT * FROM ARTIST_TABLE …`; count 167 | открытие Artists |
| **Album Artist** `VG_LISTVIEW_ALBUM_ARTIST` (5) | key `album_artist` | `SELECT * FROM ALBUM_ARTIST_TABLE …` (inline); count 169 | открытие |
| **Genres** `VG_LISTVIEW_GENRE` (6) | key `genre` | **слот 174** `SELECT * FROM GENRE_TABLE …`; count 170 | открытие |
| **Formats** `VG_LISTVIEW_MAIN_FORMAT` (0x2c) | key `format` | `SELECT * FROM FORMAT_TABLE …` (inline) | открытие |
| **Songs of an album** (0x0f) | kind 6 | case 6 (inline): `… album = ? …` (ветки has_child_file) | клик по альбому (ключ `album\<имя>`) |
| **Songs of an artist (all)** (0x11) | kind 5 | case 5: `… WHERE artist = ?` и `artist like ?` (строки `0x9ba000`/`0x9bb000`) | открытие / кнопка-переключатель |
| **Songs of an album_artist** (0x63) | kind 0x21 | case 0x21: `… WHERE album_artist = ? …` | клик по автору альбома |
| **Songs of a genre** (0x0c) | kind 7 | case 7: `… WHERE genre = ? …` | клик по жанру |
| **Albums of a genre** (0x0d) | kind 0x14 | **слот 183** `SELECT DISTINCT album FROM MEDIA_TABLE WHERE genre like ? …` | открытие / клик по жанру |
| **Albums of an artist** (0x12) | kind 9 | **слот 182** `SELECT DISTINCT album FROM MEDIA_TABLE WHERE artist like ? …` | клик по артисту |
| **Songs of album+artist** (0x10) | kind 8 | case 8 (патч): `WHERE (album = ?1 AND (artist LIKE ?2 OR album_artist LIKE ?2)) AND has_child_file IN (0,1,2) …` | клик по альбому в контексте артиста |
| **Songs of album+genre** (0x0e) | kind 0x15 | case 0x15: `… album = ? AND genre = ? …` | клик |
| **Collect** (7) | key `collect` | **слот 176** `SELECT * FROM COLLECT_TABLE …`; count 184 | открытие |
| **History** (8) | key `history` | **слот 185** `SELECT * FROM HISTORY_TABLE ORDER BY rowid DESC …` | открытие |
| **M3U / M3ULIST** (9/0x0a) | key `playlist` | **слоты 178/180** (`M3U_TABLE`/`PLAYLIST_TABLE`); вставки 116/117 | открытие; добавление в плейлист |
| **Recent** (0x41) | key `recent` | `SELECT * FROM RECENT_TABLE` (VA `0x9c4758`); вставка 131 | открытие; добавление трека |
| **Most played** (0x6c) | key `most_played` | custom-источник `FUN_0042c4a0` → `FUN_0070b020` | открытие |
| **Explorer/Files** (2/1) | key `data\…` | `FUN_0070f420` → `FUN_0070b020` ветка `data\` → `FUN_00707ac0` = `SELECT COUNT(id) FROM m3u_%d` (динамич. таблицы) | открытие папки |
| **Search** (0x46) | key `search` | чтение `SELECT * FROM SEARCH_TABLE WHERE rowid IN(…)` (VA `0x9c3340`); наполнение — **слоты 194–198** `INSERT INTO SEARCH_TABLE … WHERE character like ?` | ввод в поиске |

## Аномалии / что «делает не то»

1. **Artists и «Исполнитель альбома» показывают одно и то же.** `exp_artist_toggle`
   ведёт оба раздела в один вид `vg_listview_album`, у которого источник (kind 9) =
   **слот 182** `WHERE artist like ?`. Отдельного запроса «альбомы album_artist» нет.
   Нужно развести (Artists — по составляющей `artist`, Album Artist — по `album_artist`).
2. **Верхняя категория «Albums»** использует тот же источник (kind 9), что и
   «альбомы артиста». **Проверено на плеере (2026-10-08): список НЕ пуст** —
   ветвь ключа `album` в `FUN_0070b020` обрабатывает это корректно. Осталось
   подтвердить, что показаны именно ВСЕ альбомы (а не подмножество).
3. **Баг в позиционном запросе (VA `0x9b99f4`):**
   `SELECT count(id) FROM ALBUM_ARTIST_TABLE WHERE rowid < (SELECT rowid FROM ALBUM_TABLE WHERE album_artist like ?)`
   — внешняя таблица `ALBUM_ARTIST_TABLE`, а подзапрос по `ALBUM_TABLE` (перепутаны).
   Соседние семейства (`0x9b9928/0x9b998c/0x9b9a68/0x9b9acc`) консистентны.
4. **«Songs of format» недостижим:** `vg_listview_songs_of_format` (kind 0x1c →
   `… WHERE path like ?`) — нет имени вида `VG_LISTVIEW_SONGS_OF_FORMAT` и шаблона
   `vg_listview_format.listview`; запрос для формата фильтрует `path`, а не `format`.
5. **`kind 0x1c` перегружен:** обслуживает и Files/Explorer (`path like ?`), и
   (недостижимый) формат; при пустом `rec+0x20c` биндится пустая строка.
6. **Слот 162 смешивает таблицы:** `SELECT * FROM MEDIA2_TABLE WHERE rowid IN(SELECT rowid FROM MEDIA_TABLE …)`.
7. **Полоска A–Z** есть только у All/Albums/Artists; в Genres/Album Artist/подуровнях
   запросы позиции (`0x9b93f4…`) существуют, но UI их не вызывает.

## Не подтверждено (проверить)

- Что лежит в `view+0x3de0` для верхней категории «Albums» (пуст ли список kind 9).
- Точные слоты M3U/Playlist/Search-вставок (194–198) и подготовка statement'ов —
  строки в таблице `0x9b7730`, прямых ссылок нет; локализовать слой подготовки не удалось.
- Explorer/Files: точная выборка списка (динамические `m3u_<n>`).

## Разбор соавторов (`;`) и связанные слоты

- **Слоты чистки скана 143/146** (`0x9c2090` / `0x9c219c`):
  `DELETE FROM ARTIST2_TABLE|ALBUM_ARTIST2_TABLE WHERE … not in (SELECT DISTINCT
  … FROM MEDIA2_TABLE)`. `MEDIA2_TABLE` хранит склейку `A;B`, поэтому составляющие
  удаляются. Патч `tools/patch_artist_cleanup.py` → component-match `NOT EXISTS`
  (строки в `.rodata 0x93f90c` и RX `0xa7ee1c`), иначе разбор соавторов не
  переживает обновление медиатеки. См. `docs/artist-split.md`.
- **`kind 0x21` «Songs of an album_artist»** (`0x63`) — строки-литералы
  `0x9ba474/0x9bb874/0x9bb9e0/0x9bbb4c` с точным `album_artist = ?`. После разбора
  соавторов у составляющей вернёт 0 строк («no music»); нужен component-match
  (перенос в RX + правка `lui/addiu`) — `.opencode/todo.md`, п.6.
- **`slot 182`** (список альбомов автора) уже матчит составляющую
  (`exp_albums_artist_album_artist.py`, строка `0x93fb00`) — работает для соавторов.
