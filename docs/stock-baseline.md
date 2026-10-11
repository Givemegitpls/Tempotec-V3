# Базовая карта СТОКОВОЙ прошивки Tempotec V3 Analog

Снято субагентом 2026-10-08. Адреса — VA (файловый офсет + `0x400000` для
RX/RO-сегмента; для RW-сегмента `>= 0xa8f000` действует VTO `0x410000`).
SQL-строки целиком — в `work/sql_slots_stock.txt` (199 слотов).
Декомпиляции — `work/ghidra_out/`.

## 0. О бинарях (ВАЖНО: в задании была неточность)

| Бинарь | md5 | Что это |
|---|---|---|
| `work/hiby_player` (= файл из `v3_analog.upt` → `SYSTEM.UBI` → `usr/bin/hiby_player`) | `3a5db0fa7d2536ae564841f24b5f8b54` | **настоящий фабричный сток** |
| `backup/hiby_player.base_4429784b` (копия — `work/test_hf5/hiby_player.device_release`) | `4429784bfb605f8743b15e4e06660d01` | **НЕ сток** — наша release-сборка `v3_analog_artists` (уже с патчами) |
| `work/test_hf5/hiby_player.artist_stock` | `edcb682f29fc38e69b7f804838ff16dd` | наша v7-сборка |

**Почему так.** `backup/hiby_player.base_4429784b` содержит наши правки:
`patch_player` (kind 8 → `?1/?2`), `patch_sql` (слот 125 берётся из
`ALBUM_ARTIST2_TABLE`, сортировки по `character`) и изменённый обработчик клика
по «Исполнителю альбома» (`0x4aa21c`). Фабричный сток отличается от него на
**1443 байта** и извлекается из оригинального `v3_analog.upt`
(проверено: md5 совпал). Поэтому baseline снят с `work/hiby_player` (3a5db0fa),
а `4429784b` приведён в разделе 4 как промежуточная «release-база».

Замечание к `work/ghidra_out/`: декомпиляции снимались с бинаря, где inline-SQL
уже пропатчен (kind 8 = `?1/?2`), т.е. фактически с `4429784b`. Адреса/структура
совпадают со стоком, но inline-строки для стока перепроверены по байтам
(раздел 3, kind 8).

## 1. SQL-слоты (`work/sql_slots_stock.txt`)

Таблица слотов: база `0x9b7730`, 199 записей по 4 байта (указатель на строку).
Строки берутся по индексу (прямых xref почти нет). Группы:

| Слоты | Тип | Назначение |
|---|---|---|
| 0–27 | CREATE TABLE (DDL) | схема: `MEDIA_TABLE`/`MEDIA2_TABLE`/`MEDIA3_TABLE`, сущности (`ALBUM_TABLE`, `ARTIST_TABLE`, `ALBUM_ARTIST_TABLE`, `GENRE_TABLE`, `FORMAT_TABLE`), `*2_TABLE`, списки (`COLLECT/HISTORY/M3U/PLAYLIST/RECENT/SEARCH/MANAGER/COUNT/SORT/CTIME/MTIME`) |
| 28, 79, 85, 106 | пусто (`0x9cb978`) | заглушки |
| 29–78 | ALTER TABLE ADD COLUMN | `ctime`/`mtime`, `mqa`, `pinyin_charater`, **`album_artist`** (слоты 71–78) |
| 80–106 | DELETE / DROP | очистка перед сканом (`DELETE FROM …`, `DROP TABLE …2_TABLE`) |
| 107–118 | INSERT (скан/запись) | наполнение `MEDIA2/3`, `*2_TABLE`, `COLLECT`, `M3U`, `PLAYLIST`, `VERSION` |
| 119–131 | INSERT (сборка списков) | `MEDIA_TABLE` из `MEDIA2_TABLE` (119–122), `ALBUM/ARTIST/ALBUM_ARTIST/GENRE_TABLE` из `*2_TABLE` (124–127), `HISTORY/RECENT/CTIME/MTIME` |
| 132–156 | DELETE (обслуживание) | точечные удаления из списков/сущностей |
| 157–193 | SELECT / UPDATE | запросы списков, count-ы, поиск, апдейты |
| 194–198 | INSERT INTO SEARCH_TABLE | наполнение поиска из `MEDIA/MEDIA2/COLLECT/ALBUM/ARTIST` |

Ключевые слоты «музыкальных» списков (сток):

| Слот | Строка | Обслуживает |
|---|---|---|
| 157 | `SELECT COUNT(id) FROM MEDIA_TABLE` | count «All» |
| 159 | `SELECT * FROM MEDIA_TABLE limit ? offset ?` | **All** (без `ORDER BY`!) |
| 160 | `SELECT * FROM MEDIA2_TABLE limit ? offset ?` | тех. список |
| 167 | `SELECT COUNT(id) FROM ARTIST_TABLE` | count Artists |
| 168 | `SELECT COUNT(id) FROM ALBUM_TABLE` | count Albums |
| 169 | `SELECT COUNT(id) FROM ALBUM_ARTIST_TABLE` | count Album Artist |
| 170 | `SELECT COUNT(id) FROM GENRE_TABLE` | count Genres |
| 172 | `SELECT * FROM ARTIST_TABLE limit ? offset ?` | **Artists** |
| 173 | `SELECT * FROM ALBUM_TABLE limit ? offset ?` | **Albums** |
| 174 | `SELECT * FROM GENRE_TABLE limit ? offset ?` | **Genres** |
| 182 | `SELECT DISTINCT album FROM MEDIA_TABLE WHERE artist like ? ORDER BY album collate pinyin` | **Albums of an artist** (kind 9) |
| 183 | `SELECT DISTINCT album FROM MEDIA_TABLE WHERE genre like ? ORDER BY album collate pinyin` | **Albums of a genre** (kind 0x14) |
| 176 | `SELECT * FROM COLLECT_TABLE limit ? offset ?` | Collect |
| 185 | `SELECT * FROM HISTORY_TABLE ORDER BY rowid DESC limit ? offset ?` | History |
| 194–198 | `INSERT INTO SEARCH_TABLE … WHERE character like ?` | наполнение Search |
| 124–127 | `INSERT INTO <ENTITY>_TABLE SELECT * FROM <ENTITY>2_TABLE ORDER BY <name> COLLATE pinyin` | сборка сущностей после скана |

Особенности стока:
- **сортировка — `COLLATE pinyin`** (слоты 119–127, 182, 183, а также inline-запросы
  kind-ов). Колонка `character` в стоке есть (в DDL), но для порядка списков НЕ
  используется — A–Z полоска опирается на `character`, а список идёт по pinyin.
- `ALBUM_TABLE` в DDL (слот 3) — только `(id, album, character, cn)`; `ctime/mtime/
  mqa/pinyin_charater` добавляются ALTER-ами 37/38/55/60. `album_artist` в
  `ALBUM_TABLE` нет — он есть только в `ALBUM_ARTIST_TABLE`/`ALBUM_ARTIST2_TABLE`
  и в `MEDIA*`/`COLLECT`/`HISTORY`/`SEARCH`/`RECENT` (ALTER 71–78).

## 2. Таблица видов `0x95e770` (109 × 0x3c)

Раскладка записи (15 слов): `[0]` имя (`VG_…`), `[1]` type (идёт в `view+0x40`),
`[2]` селектор шаблона (`0`=`@class@`, `1`=`@music@`, `2`=`@book@`),
`[4..0xc]` флаги (w4=bit0 … w12=bit10), `[0xd]`→`view+0x41e0`,
`[0xe]` строка-ключ (в `view+0x3828`).

Ключевые «музыкальные» виды:

| idx | Имя | type | sel | w4 | ключ [0xe] |
|---|---|---|---|---|---|
| 0 | `VG_LISTVIEW_ALL` | 0x00 | 1 | 0 | `all` (`0x9d842c`) |
| 1 | `VG_LISTVIEW_MAIN_EXPLORER` | 0x01 | 0 | 0 | — |
| 2 | `VG_LISTVIEW_ARTIST` | 0x03 | 0 | 0 | `artist` (`0x9695fc`) |
| 3 | `VG_LISTVIEW_ALBUM` | 0x04 | 0 | **1** | `album` (`0x9695e4`) |
| 4 | `VG_LISTVIEW_ALBUM_ARTIST` | 0x05 | 0 | 0 | `album_artist` (`0x960960`) |
| 5 | `VG_LISTVIEW_GENRE` | 0x06 | 0 | 0 | `genre` (`0x960908`) |
| 6 | `VG_LISTVIEW_MAIN_FORMAT` | 0x2c | 0 | 0 | — |
| 7 | `VG_LISTVIEW_COLLECT` | 0x07 | 1 | 0 | — |
| 8 | `VG_LISTVIEW_HISTORY` | 0x08 | 1 | 0 | — |
| 9 | `VG_LISTVIEW_M3U` | 0x09 | 0 | 0 | — |
| 10 | `VG_LISTVIEW_RECENT_ADD` | 0x41 | 1 | 0 | — |
| 11 | `VG_LISTVIEW_EXPLORER` | 0x02 | 0 | **1** | — |
| 14 | `VG_LISTVIEW_SONGS_OF_A_GENRE` | 0x0c | 1 | 0 | — |
| 15 | `VG_LISTVIEW_SONGS_OF_AN_ALBUM_AND_A_GENRE` | 0x0e | 1 | 0 | — |
| 16 | `VG_LISTVIEW_ALBUMS_OF_A_GENRE` | 0x0d | 0 | 0 | — |
| 17 | `VG_LISTVIEW_SONGS_OF_AN_ALBUM` | 0x0f | 1 | 0 | — |
| 18 | `VG_LISTVIEW_SONGS_OF_AN_ALBUM_ARTIST` | 0x63 | 1 | 0 | — |
| 19 | `VG_LISTVIEW_SONGS_OF_AN_ALBUM_AND_AN_ARTIST` | 0x10 | 1 | 0 | — |
| 20 | `VG_LISTVIEW_SONGS_OF_ARTIST_ALL` | 0x11 | 1 | 0 | — |
| 21 | `VG_LISTVIEW_ALBUMS_OF_AN_ARTIST` | 0x12 | 0 | **0** | — |
| 47 | `VG_LISTVIEW_FORMAT` | 0x2d | 0 | 0 | — |
| 71 | `VG_LISTVIEW_SEARCH_ITEM` | 0x46 | 1 | 0 | — |
| 107 | `VG_LISTVIEW_MOST_PLAYED` | 0x6c | 1 | 0 | — |

**w4=bit0** включает фоновый загрузчик обложек. Среди «альбомных» видов бит стоит
ТОЛЬКО у `VG_LISTVIEW_ALBUM` (idx 3) и у `EXPLORER`/`DOWNLOAD_ITEM`; у
`ALBUMS_OF_AN_ARTIST` (idx 21) и `ALBUMS_OF_A_GENRE` (idx 16) — 0.

### 2.1. Класс-таблица (источник данных и клик)

Параллельные массивы в `.data`:
- пути шаблонов: `0xabd3c8` (stride `0x20c`), `+0` = `z:\layout\…\<name>.listview`;
- «класс»-записи: `0xabd4cc` (stride `0x20c`):
  `+0x00` = **источник данных** (`view+0x423c`), `+0x08` = lowercase-имя вида,
  `+0x50` = **обработчик клика по строке**.

`pi` (индекс в этих массивах) ≠ индекс в таблице видов. Для «музыкальных» видов:

| pi | имя | источник (`+0`) | клик (`+0x50`) | что открывает клик |
|---|---|---|---|---|
| 1 | `vg_listview_all` | `FUN_004a73a0` | `FUN_004a8980` (thunk) | воспроизведение/меню |
| 6 | `vg_listview_album` | `FUN_004a95e0` | `FUN_004a9680` | `vg_listview_songs_of_an_album` |
| 7 | `vg_listview_genre` | `FUN_004a8ba0` | `FUN_004a8c20` | `vg_listview_albums_of_a_genre` |
| 10 | `vg_listview_artist` | `FUN_004a8a80` | `FUN_004a8b20` | `vg_listview_albums_of_an_artist` |
| 62 | `vg_listview_album_artist` | `FUN_004aa160` | `FUN_004aa1a0` | `vg_listview_songs_of_an_album_artist` |
| 81 | `vg_listview_songs_of_a_genre` | `FUN_004a9b60` | `FUN_004a8a20` | плеер |
| 84 | `vg_listview_songs_of_an_album` | `FUN_004a9700` | `FUN_004a9900` | плеер |
| 85 | `vg_listview_albums_of_a_genre` | `FUN_004a8ca0` | `FUN_004a8f00` | `vg_listview_songs_of_an_album_and_a_genre` |
| 87 | `vg_listview_songs_of_artist_all` | `FUN_004a9dc0` | `FUN_004a9fa0` | плеер |
| 88 | `vg_listview_albums_of_an_artist` | `FUN_004a9180` | `FUN_004a9360` | `vg_listview_songs_of_an_album_and_an_artist` |
| 89 | `vg_listview_songs_of_an_album_artist` | `FUN_004aa240` | `FUN_004aa420` | плеер |
| 90 | `vg_listview_songs_of_an_album_and_a_genre` | `FUN_004a8f20` | `FUN_004a8a40` | плеер |
| 91 | `vg_listview_songs_of_an_album_and_an_artist` | `FUN_004a9380` | `FUN_004a8a60` | плеер |
| 50 | `vg_listview_main_format` | `FUN_004a7de0` | `FUN_004a7e20` | — |
| 56 | `vg_listview_search_item` | `FUN_005418a0` | `FUN_00541a00` | — |
| 22 | `vg_listview_explorer` | `FUN_004a84e0` | `FUN_004a8700` | — |

## 3. Потоки по экранам (сток)

Архитектура — две ветки:
- **A. Верхние списки** (`All/Albums/Artists/Album Artist/Genres/Formats/Collect/…`):
  источник вида (`view+0x423c`) → `FUN_004a1ba0(...)` → `FUN_0070b020(rec,0,key,0,keyw)`
  → `SELECT * FROM <ENTITY_TABLE> limit ? offset ?`; count — `FUN_0070aa60(key)`.
- **B. Подсписки** («треки/альбомы X»): `FUN_0070a3a0(kind,0,rec,0)` →
  `FUN_00708d20(kind)` строит `list_tb_N` (inline-SQL) → `FUN_0070b020` →
  `FUN_007060a0(key)` → `SELECT * FROM list_tb_N …`.

Клик по строке — `FUN_004a7500`/`FUN_004a75e0` (строит ключ и открывает дочерний
вид). Полоска A–Z — `FUN_00703320` (считает позицию по `character`).

| Экран (view idx/type) | pi | kind / key | SQL (слот / inline) | Когда |
|---|---|---|---|---|
| **All** (0/0x00) | 1 | key `all` | слот **159** `SELECT * FROM MEDIA_TABLE limit ? offset ?`; count 157 | открытие; смена сортировки |
| **Albums** (3/0x04) | 6 | key `album` | слот **173** `SELECT * FROM ALBUM_TABLE limit ? offset ?`; count 168 | открытие Albums |
| **Artists** (2/0x03) | 10 | key `artist` | слот **172** `SELECT * FROM ARTIST_TABLE …`; count 167 | открытие Artists |
| **Album Artist** (4/0x05) | 62 | key `album_artist` | inline `SELECT * FROM ALBUM_ARTIST_TABLE limit ? offset ?`; count 169 | открытие |
| **Genres** (5/0x06) | 7 | key `genre` | слот **174** `SELECT * FROM GENRE_TABLE …`; count 170 | открытие |
| **Formats** (6/0x2c) | 50 | key `format` | inline `SELECT * FROM FORMAT_TABLE limit ? offset ?` | открытие |
| **Songs of an album** (17/0x0f) | 84 | kind **6** | inline case 6: `… WHERE album = ? …` (ветки `has_child_file` 0/1/2, `ck_id`) | клик по альбому (`FUN_004a9680`) |
| **Songs of an artist (all)** (20/0x11) | 87 | kind **5** | inline case 5: `… WHERE artist = ?` (+ `artist like ?` ветка) | открытие / переключатель |
| **Songs of an album_artist** (18/0x63) | 89 | kind **0x21** | inline case 0x21: `… WHERE album_artist = ? …` | **клик по автору альбома** (`FUN_004aa1a0`) |
| **Songs of a genre** (14/0x0c) | 81 | kind **7** | inline case 7: `… WHERE genre = ? …` | переключатель из «Albums of a genre» |
| **Albums of a genre** (16/0x0d) | 85 | kind **0x14** | слот **183** `SELECT DISTINCT album FROM MEDIA_TABLE WHERE genre like ? …` | клик по жанру (`FUN_004a8c20`) |
| **Albums of an artist** (21/0x12) | 88 | kind **9** | слот **182** `SELECT DISTINCT album FROM MEDIA_TABLE WHERE artist like ? …` | клик по артисту (`FUN_004a8b20`) |
| **Songs of album+artist** (19/0x10) | 91 | kind **8** | inline case 8 (сток): `… WHERE (album = ? AND artist = ? ) AND ((has_child_file = 0 …` | клик по альбому в контексте артиста (`FUN_004a9360`) |
| **Songs of album+genre** (15/0x0e) | 90 | kind **0x15** | inline case 0x15: `… WHERE album = ? AND genre = ? …` | клик по альбому в контексте жанра (`FUN_004a8f00`) |
| **Search** (71/0x46) | 56 | key `search` | чтение `SELECT * FROM SEARCH_TABLE WHERE rowid IN(SELECT rowid FROM SEARCH_TABLE limit ? offset ?)` (`0x9c3340`); наполнение — слоты **194–198** | ввод в поиске |
| **Explorer/Files** (1/0x01, 11/0x02) | 70/22 | key `data\…` | `FUN_0070b020` ветка `data\` → `FUN_006fbf40` → динамические `m3u_<n>` (`SELECT * FROM %s%d limit ? offset ?`) | открытие папки |

### (а) Стоковый источник «Albums» — подтверждено

Класс-запись `pi 6` (`0xabe114`, файл `0x6ae114`) содержит источник
`0x4a95e0` = `FUN_004a95e0`, которая вызывает
`FUN_004a1ba0(..., L"album", ...)` → `FUN_0070b020(key="album")` →
`SELECT * FROM ALBUM_TABLE limit ? offset ?` (слот 173). То есть в стоке
категория «Альбомы» показывает **все альбомы** из `ALBUM_TABLE`.

### (б) Стоковый путь «Исполнитель альбома» — подтверждено

1. Верхняя категория открывает вид `vg_listview_album_artist` (pi 62) с ключом
   `L"album_artist"` (широкая строка `0x960b30`). Источник —
   `FUN_004aa160` → `FUN_004a1ba0(key="album_artist")` → `FUN_0070b020` (ветка
   `album_artist`, строка 112) → `SELECT * FROM ALBUM_ARTIST_TABLE limit ? offset ?`.
2. **Клик по автору альбома** — `FUN_004aa1a0`. Инструкция `0x4aa21c`:
   `lui $a2,0x96` + `addiu $a2,$a2,0x948` → `0x960948` =
   `"vg_listview_songs_of_an_album_artist"`. Значит клик открывает вид
   `vg_listview_songs_of_an_album_artist` (view idx 18, type 0x63; pi 89).
3. Источник вида pi 89 — `FUN_004aa240` → `FUN_0070a3a0(0x21,...)` →
   `FUN_00708d20` **case 0x21** → inline `INSERT INTO list_tb_N … WHERE
   album_artist = ? …` (три ветки: `ck_id=0`, `has_child_file=2`, `has_child_file=1`;
   плюс четвёртая для cue-треков `path like ? AND album_artist = ?`).

Итог: в **фабричном стоке** ожидание из задания верно — клик по автору альбома
ведёт в `vg_listview_songs_of_an_album_artist`, kind `0x21`, `WHERE album_artist = ?`.
(В `4429784b` это уже переделано на `albums_of_an_artist`, см. раздел 4.)

### (в) Где используется тег `album_artist` в стоке

- **Схема:** колонка добавляется ALTER-ами 71–78 в `MEDIA_TABLE`, `MEDIA2_TABLE`,
  `MEDIA3_TABLE`, `COLLECT_TABLE`, `HISTORY_TABLE`, `COLLECT_OPERATE_TABLE`,
  `SEARCH_TABLE`, `RECENT_TABLE`. Отдельные сущности — `ALBUM_ARTIST_TABLE` (слот 5)
  и `ALBUM_ARTIST2_TABLE` (слот 14).
- **Запись при скане:** INSERT-слоты 107/108/113/114/128/131 (и 194–196) пишут
  `album_artist`; слот 111 наполняет `ALBUM_ARTIST2_TABLE`; слот 126 собирает
  `ALBUM_ARTIST_TABLE` из `ALBUM_ARTIST2_TABLE` (`ORDER BY album_artist COLLATE pinyin`).
- **Фильтрация:**
  - kind **0x21** (`songs_of_an_album_artist`): `WHERE album_artist = ?` — основной
    потребитель тега;
  - kind **8** (`songs_of_an_album_and_an_artist`) в **стоке** фильтрует только по
    `artist = ?` — `album_artist` там НЕ участвует (добавлен нашим патчем);
  - `ALBUM_ARTIST_TABLE`-ветка `FUN_0070b020` (key `album_artist`) — верхний список.
- **Обслуживание:** слоты 91/96 (`DELETE FROM ALBUM_ARTIST*_TABLE`), 137/142
  (`DELETE … WHERE album_artist like ? / = ?`), 146 (`… WHERE album_artist not in
  (SELECT DISTINCT album_artist from MEDIA2_TABLE)`), 175 (`SELECT artist,album,
  genre,album_artist FROM MEDIA_TABLE WHERE path like ? AND cue_id = ?`).
- **Позиционные (A–Z) запросы:** семейство `0x9b99xx`; у одного из них
  (VA `0x9b99f4`) баг: внешняя таблица `ALBUM_ARTIST_TABLE`, а подзапрос по
  `ALBUM_TABLE` (перепутаны).

## 4. Сток ↔ наша сборка v7 (`edcb682f`)

Сравнение по байтам/слотам (сток `3a5db0fa`, release-база `4429784b`, v7 `edcb682f`):

| Аспект | Фабричный сток `3a5db0fa` | Release-база `4429784b` | v7 `edcb682f` |
|---|---|---|---|
| Источник «Albums» `0xABE114` | `0x4a95e0` (`FUN_004a95e0` → `SELECT * FROM ALBUM_TABLE`, слот 173) | `0x4a95e0` | **`0x4a9180`** (kind 9 → слот 182, `MEDIA_TABLE WHERE artist like ?`) |
| Клик по артисту `0x4a8b84` | `-0x2d1c` → `albums_of_an_artist` | `-0x2d1c` | **`-0x2d58`** → `vg_listview_album` (категория «Albums») |
| Клик по автору альбома `0x4aa21c` | **`+0x948` → `songs_of_an_album_artist`** (kind 0x21) | `-0x2d1c` → `albums_of_an_artist` | **`-0x2d58`** → `vg_listview_album` |
| Слот 125 (сборка `ARTIST_TABLE`) | `SELECT * FROM ARTIST2_TABLE ORDER BY artist COLLATE pinyin` | `SELECT id,album_artist,… FROM ALBUM_ARTIST2_TABLE` | `SELECT id,artist,… FROM ARTIST2_TABLE` |
| Слот 159 («All») | `SELECT * FROM MEDIA_TABLE limit ? offset ?` | без изменений | **`… ORDER BY character,name limit ? offset ?`** (строка `0x93fa00`) |
| Слоты 119–127 (порядок) | `ORDER BY <name> COLLATE pinyin` | `ORDER BY character,…` + `CASE WHEN character BETWEEN 'A' AND 'Z'` | как в базе |
| kind 8 (`songs_of_album+artist`) | `WHERE (album = ? AND artist = ? ) AND ((has_child_file = 0 …` | `WHERE (album=?1 AND (artist LIKE ?2 OR album_artist LIKE ?2)) AND has_child_file IN (0,1,2)` | как в базе |
| Вид 21 (`albums_of_an_artist`) w4 | `0` | `0` | **`1`** (включает загрузчик обложек) |
| RX-хуки (`0xa7e370..`) | нет (0 ненулевых байт) | нет | есть (~334 байта: shuffle/artist-toggle/kind9-шаблон) |
| Отличий от стока (байт) | — | 1443 | 1883 |

**Следствия для UI v7 (из `docs/ui-queries.md`, сверено со стоком):**
- «Albums» и «Albums of an artist» в v7 используют ОДИН источник (kind 9, слот 182,
  `WHERE artist like ?`) — поэтому категория «Альбомы» и подсписок артиста делят вид.
- Путь «Исполнитель альбома» в v7 потерял собственный запрос по `album_artist`:
  и Artists, и Album Artist ведут в `vg_listview_album` (kind 9 по тегу `artist`).
  В стоке для этого был отдельный kind 0x21 `WHERE album_artist = ?`.
- Слот 182 (`WHERE artist like ?`) в стоке обслуживает только
  «Albums of an artist»; в v7 он же отдаёт данные для категории «Albums».
- `ORDER BY character,name` в «All» — добавка v7 (`exp_all_sort`), в стоке «All»
  вообще без `ORDER BY` (порядок по rowid/pinyin).
- Сортировки сущностей: сток — `COLLATE pinyin`; v7 — по `character` с приведением
  к `A–Z` (нужно для совпадения с прыжком по полоске).

## 5. Не подтверждено

1. **Идентичность бинаря из задания.** В задании `backup/hiby_player.base_4429784b`
   назван стоком, но это наша release-сборка (md5 не совпадает с файлом из
   `v3_analog.upt`; отличия — 1443 байта). Фабричный сток —
   `3a5db0fa` (`work/hiby_player`). Нужно подтвердить у владельца, какой именно
   бинарь считать «стоком» для дальнейших сравнений.
2. **Механика передачи ключа при клике.** `FUN_004a7500`/`FUN_004a75e0` читают
   значение выбранной строки и открывают вид по имени; точная сборка
   `list_tb_N`-запроса с этим значением не прослежена до конца (какой именно
   `?` биндится именем строки, а какой — литералом ключа).
3. **Достижимость вида pi 89 вне клика по автору альбома.** Строка-имя
   `0x960948` в стоке грузится только из обработчика `FUN_004aa1a0`; иных
   открывателей `vg_listview_songs_of_an_album_artist` не найдено. Возможны
   косвенные пути через фреймворк (открытие по индексу класса) — не проверено.
4. **Слот 159 и prepared-statement `DAT_00bc18f0[0x132]`.** Соответствие
   «слот 159 ↔ prepared statement для All» взято из `docs/ui-queries.md` и текста
   строки; прямой привязки индекса не проверял.
5. **Explorer/Files.** Точная выборка списка (динамические `m3u_<n>`,
   `FUN_0070f420`/`FUN_006fbf40`) и роль `MANAGER_TABLE` не разобраны.
6. **Search.** Полный путь подготовки statement'ов и точное время выполнения
   слотов 194–198 не локализованы (в таблице слотов прямых xref нет).
7. **Top-level dispatch** (`FUN_004a8040`, switch по `view+0x1d0` 0..5) — сопоставление
   индексов категориям (кроме case 5 = album_artist) не проверено.
8. **A–Z полоска в стоке**: механика `FUN_00703320` и наличие полоски у
   All/Albums/Artists (в Genres/Album Artist — нет) взяты из `NOTES`/`ui-queries`
   и не перепроверялись на живом стоке.
