# Разбор соавторов (`artist` / `album_artist` по `;`)

Совместные треки хранят склейку вида `Noize MC;Anacondaz` в теге `artist` (и в
`album_artist`). Плеер считает её одним автором, поэтому в Artists / «Исполнителе
альбома» склейка — одна строка, и совместный трек не виден у каждого соавтора.

Решение: разбирать тег по `;` на отдельных авторов — **без ограничения на число
составляющих** — и переживать «Обновление медиатеки».

## Где что

- `tools/split_artists_db.py` — офлайн-скрипт (по локальной копии БД):
  создаёт/пересоздаёт триггеры `split_ARTIST2_TABLE` и `split_ALBUM_ARTIST2_TABLE`,
  одноразово разбирает существующие склейки, пересобирает `ARTIST_TABLE` и
  `ALBUM_ARTIST_TABLE`. Идемпотентно, `--check`.
- `tools/make_db_fix_sql.py` — генератор вшитого SQL-фикса;
  `fw/SYSTEM/usr/share/hiby_db_fix.sql` — результат (кладётся в образ, плеер
  выполняет его сам через `tools/exp_db_autofix.py` при завершении скана).
- `tools/patch_artist_cleanup.py` — патч бинаря: слоты 143/146 (чистка скана) →
  component-match (см. ниже).
- `tools/verify_build.py` — патч в цепочке; инварианты БД: триггеров `>=18`,
  склеек в `ARTIST_TABLE`/`ALBUM_ARTIST_TABLE` = 0.
- Дизайн/разбор — `work/artist_split_design.md`.

## Механика разбора (SQL)

Триггер разбирает **все** составляющие за один проход — рекурсивный CTE внутри
одного `INSERT … SELECT` (это НЕ рекурсия триггера, `recursive_triggers` OFF не
мешает):

```sql
DROP TRIGGER IF EXISTS split_ARTIST2_TABLE;      -- IF NOT EXISTS не заменит старый!
CREATE TRIGGER split_ARTIST2_TABLE AFTER INSERT ON ARTIST2_TABLE
WHEN instr(substr(NEW.artist,1,length(NEW.artist)),';')>0
BEGIN
  INSERT OR IGNORE INTO ARTIST2_TABLE(id,artist,character,cn,ctime,mtime,pinyin_charater)
  WITH RECURSIVE parts(rest,part) AS (
    SELECT substr(NEW.artist,1,length(NEW.artist))||';',''
    UNION ALL
    SELECT substr(rest,instr(rest,';')+1), substr(rest,1,instr(rest,';')-1)
    FROM parts WHERE rest<>''
  )
  SELECT NEW.id, part||char(0), NEW.character, NEW.cn, NEW.ctime, NEW.mtime,
         NEW.pinyin_charater
  FROM parts WHERE part<>'';
  DELETE FROM ARTIST2_TABLE WHERE rowid=NEW.rowid;
END;
```

Для `album_artist` — то же (`split_ALBUM_ARTIST2_TABLE`, колонки с `mqa`).

Грабли:
- `substr(x,1,length(x))` снимает хвостовой NUL (строки в БД — C-строки).
  `replace(x,char(0),'')` NUL **не вырезает** (проверено на вшитом SQLite 3.12.2).
- `CREATE TRIGGER IF NOT EXISTS` старый триггер не заменяет → нужен `DROP` перед.
- `recursive_triggers` менять не нужно и нельзя (connection-level).

## Почему нужен патч слотов 143/146

При скане слоты чистки удаляют записи, которых нет как отдельного тега в
`MEDIA2_TABLE`:

```
slot 143: DELETE FROM ARTIST2_TABLE WHERE artist not in (SELECT DISTINCT artist FROM MEDIA2_TABLE)
slot 146: ... то же для ALBUM_ARTIST2_TABLE ...
```

`MEDIA2_TABLE` хранит **склейку** (`A;B`), поэтому составляющие удаляются →
разбор «самоубивается» на следующем обновлении. На реальной БД stock-143 удаляет
184 из 244 артистов.

Патч заменяет условие на component-match:

```sql
DELETE FROM ARTIST2_TABLE WHERE NOT EXISTS (
  SELECT 1 FROM MEDIA2_TABLE m
  WHERE (';'||substr(m.artist,1,length(m.artist))||';')
        LIKE '%;'||substr(ARTIST2_TABLE.artist,1,length(ARTIST2_TABLE.artist))||';%'
);
```

Строки длиннее стоковых → переносятся: слот 143 → `.rodata` `0x93f90c`,
слот 146 → RX-зазор `0xa7ee1c` (`tools/patch_artist_cleanup.py`).

## Сборка

```
python3 tools/make_db_fix_sql.py                      # регенерация SQL-фикса
python3 tools/verify_build.py <bin> [--image out/x.upt] [--db <копия БД>]
./tools/make.sh build <имя>
```

Цепочка бинаря (`tools/verify_build.py`): `… exp_db_autofix → patch_artist_cleanup`.
Права `usr/bin/hiby_player` = 775 (иначе бутлуп).

## Как применить на устройстве

- **Триггер создаётся вшитым DBFIX** при «Обновлении медиатеки». Если DBFIX не
  отрабатывает (см. `todo.md`, п.7) — применить офлайн:
  `adb pull /data/usrlocal_media.db`, `python3 tools/split_artists_db.py <db>`,
  `adb push`, `reboot`. Триггер остаётся в БД и на будущих сканах делит сам.
- **Проверка переживания рескана:** после разбора сделать «Обновление медиатеки»
  ещё раз — соавторы должны остаться раздельными (триггер + патч 143/146).

## Известное ограничение

- **kind 0x21 «треки исполнителя альбома»** — 4 литерала `0x9ba474/0x9bb874/
  0x9bb9e0/0x9bbb4c` с точным `album_artist = ?`; у соавтора вернёт «no music».
  Нужен component-match (перенос строк в RX + правка `lui/addiu`). Список альбомов
  соавтора (slot 182) уже component-match — работает.
- `ALBUM_TABLE`/обложки не затрагиваются: альбомы ключуются по имени альбома,
  дубликатов не будет (кросс-листинг у соавторов — целевое поведение).

## Проверено

- SQL/триггеры — на вшитом SQLite 3.12.2 (сборка `/tmp/opencode/artsplit/sqlite312`).
- Офлайн на копии реальной БД: 28+29 склеек → 0, `ARTIST_TABLE` 244,
  `ALBUM_ARTIST_TABLE` 81, триггеров 18, integrity ok, идемпотентно.
- На устройстве: Artists и Album Artist — соавторы раздельны.
