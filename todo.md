# TODO — Tempotec V3 Analog (мод прошивки)

Обновлено: 2026-10-07.

## Текущее состояние

**Последний релиз:** `out/v3_analog_artist_stock.upt`
- ISO md5 `d8b8c4e4b9034acdd91a4bfd4bfdd5aa`, SYSTEM.UBI md5 `5bf92ec1c52044d685874475e88cfb9e`
- бинарь md5 `edcb682f29fc38e69b7f804838ff16dd`
- состав: всё из v1–v6 + Artists = тег `artist` (слот 125 → `ARTIST2_TABLE`; фильтр альбомов, слот 182 → стоковый `artist`) + постоянный фикс сортировки «All» (`tools/exp_all_sort.py`).
- **на устройстве залит этот бинарь**, проверен пользователем.

**Отладочный образ:** `out/v3_analog_artist_stock_adb.upt`
- ISO `3851f6c64d82500fc9bc0a76ff9e02b5`, UBI `1381a479c7f1168088741d81e6f659ac`
- бинарь `edcb682f…`, `etc/init.d/S98adb_debug` `86de3452…` (гаджет `adb` без `mass_storage`).
- На устройстве скрипт `S98adb_debug` уже поправлен: `for f in "adb";` → карта не отваливается от USB.

**Важно про SD:** отладочный гаджет `functions=mass_storage,adb` с LUN на весь `/dev/mmcblk0`
«забирал» карту у плеера (плеер считал, что карты нет; пропадали обложки). Лечится
`adb`-only (см. выше). Детали — `.opencode/NOTES.md`.

## В работе: разбор тега `artist` по `;`

Цель: совместный трек (`artist` = `Noize MC;Anacondaz`) должен быть виден у **каждого**
соавтора отдельно. `album_artist` **не** разбивать; альбомы собираются по `album_artist`
и должны быть полными. Раздел «Исполнитель альбома» не ломать.

Что выяснено:
- 78 трековых артистов, из них 6 склеек `X;Y` (все по 2 составляющих).
- `ARTIST2_TABLE` наполняет сканер: `INSERT INTO ARTIST2_TABLE(artist,id,character,cn,ctime,mtime,pinyin_charater) VALUES (?,…)`.
- `ARTIST_TABLE` собирается из `ARTIST2_TABLE` (слот 125).
- Список альбомов артиста: `SELECT DISTINCT album FROM MEDIA_TABLE WHERE artist like ?` (слот 182).
- Значения в БД хранятся с хвостовым `\x00` (C-строка) — в MEDIA и в ARTIST.
- Транслит буквы (`character`) — триггер `fix_char_ARTIST2_TABLE` (AFTER INSERT).

Написаны скрипты (в репо):
- `tools/split_artists_db.py` — создаёт `ARTIST_SPLIT_NUM` + триггер `split_ARTIST2_TABLE`
  (AFTER INSERT, разбор по `;`), разбирает существующие склейки, пересобирает `ARTIST_TABLE`.
- `tools/exp_albums_by_component.py` — правит слот 182: фильтр списка альбомов по
  составляющей `(';'||replace(artist,char(0),'')||';') LIKE '%;'||replace(?,char(0),'')||';%'`.

**Блокер / что чинить:**
- Триггер с recursive CTE **зацикливается** (и в БД, и в памяти) — НЕ использовать.
- Рабочий вариант триггера (проверен в памяти): обрабатывает **первую** `;`
  (вторая часть вставляется, первая остаётся в строке через UPDATE). Но из-за
  `PRAGMA recursive_triggers=OFF` (по умолчанию) вложенные `;` (3+ компонента) не
  разбираются — для текущих данных (все по 2) этого достаточно, но зафиксировать ограничение.
- В `split_artists_db.py` в `TRIGGER_SQL` сейчас стоит именно зацикливающийся CTE-вариант —
  **заменить** на 2-компонентный:
  ```sql
  CREATE TRIGGER IF NOT EXISTS split_ARTIST2_TABLE AFTER INSERT ON ARTIST2_TABLE
  WHEN instr(replace(NEW.artist,char(0),''),';')>0
  BEGIN
    INSERT OR IGNORE INTO ARTIST2_TABLE(id,artist,character,cn,ctime,mtime,pinyin_charater)
    SELECT NEW.id,
           substr(replace(NEW.artist,char(0),''), instr(replace(NEW.artist,char(0),''),';')+1)||char(0),
           NEW.character, NEW.cn, NEW.ctime, NEW.mtime, NEW.pinyin_charater;
    UPDATE ARTIST2_TABLE SET artist =
           substr(replace(NEW.artist,char(0),''),1,instr(replace(NEW.artist,char(0),''),';')-1)||char(0)
    WHERE rowid=NEW.rowid;
  END
  ```
- Проверено на копии БД: `split_artists_db.py` (с null-осознанным разбором) даёт
  ARTIST_TABLE 77 записей, склеек 0, дублей нет. Фильтр по составляющей матчится
  (напр. «Дэн Субботин» → 11 альбомов).

Шаги для завершения:
1. Поправить `TRIGGER_SQL` в `split_artists_db.py` на 2-компонентный (выше), перепроверить на копии БД.
2. Прогнать `exp_albums_by_component.py` на текущем бинаре (проверить, что влезает в `.rodata`).
3. Собрать образ (цепочка + `exp_albums_by_component`), залить бинарь, прогнать
   `split_artists_db.py` на живой БД (pull → скрипт → push → reboot), очистить кэш списков
   (`tools/clear_list_cache.py`).
4. Проверить на устройстве: у каждого соавтора — свои альбомы; Album Artists не сломан;
   Artists/Albums/All/Files целы.
5. Обновить `CHANGELOG.md`, `readme.md`, `.opencode/NOTES.md`, скилл.

## Остальные задачи

1. **Полоска A-Z в «Жанры», «Исполнитель альбома» и на подуровнях** — её там нет.
   Нужно найти, где выставляется `view->0x10` и поле `[view->0x258][0x3b6c][0x1fc]`
   (прямых `sw` в `+0x1fc` в коде нет — вероятно, структура копируется из `.rodata`).
2. **Транслит жанров на `É`** — 5 жанров без транслита, падают в «#»; добавить в карту
   `tools/translit_db.py` при следующей правке БД.
3. **Повтор DB-постпроцессинга при обнулении `/data`:**
   `translit_db` → `reorder_db` → `translit_db` (reorder сносит триггеры) → `album_artist_db`
   (последний — только если снова понадобится группировка по авторам альбомов).
4. **Чистка:** удалить `work/_clr.db` (создан root’ом из docker) — при удобном случае с sudo.
5. **Опционально:** «следующий альбом того же автора» при `album_skip` —
   попытка `tools/exp_albums_by_author.py` падала/перезагружала плеер (слепой хук в
   `FUN_004eae80`); если возвращаться — реимплементация функции целиком с отладкой по шагам.
