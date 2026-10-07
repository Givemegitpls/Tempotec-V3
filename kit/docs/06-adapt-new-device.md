# 06. Перенос на другое устройство HiBy OS

Устройства семейства (R1, R3 II 2025, R3 Pro II, Tempotec V1/V3) делят формат `.upt`
и SoC Ingenic X1600E, но у каждого свой `hiby_player` и свои адреса. Переносить
патчи можно только с пересчётом; логика («что чинить») переносится, байты — нет.

## Шаг 1. Разведка

```
7z x -y stock.upt -o unpacked
ubireader_extract_files -k -o SYSTEM unpacked/SYSTEM.UBI
md5sum SYSTEM/usr/bin/hiby_player            # зафиксировать базу
file SYSTEM/usr/bin/hiby_player             # подтвердить MIPS32 LE
readelf -l SYSTEM/usr/bin/hiby_player       # program headers, RX-сегмент, image base
readelf -S SYSTEM/usr/bin/hiby_player       # секции .text/.rodata
```
Определи:
- **image base / формулу** `VA = file_offset + base`;
- **RX-запас**: конец RX `p_filesz` → начало следующего сегмента;
- **code cave** в `.text` (нулевые прогоны) — `grep -c`/скриптом.

## Шаг 2. Найти аналоги ключевых объектов

Ищи по тексту, а не по адресам:

| объект | как найти |
|---|---|
| таблица SQL-строк | substring `INSERT INTO %s%d` и рядом `list_tb_`; база = VA минус индекс*4 |
| таблица видов | ищи имена `vg_listview_album`, `vg_listview_albums_of_an_artist` — по ним восстанавливается база/шаг записей |
| парсер обложек | строки `cover_parser`, `front`/`cover`/`folder`; функция с папками/расширениями |
| обложки строк | функции около `cover_parser`, ищи `qobuz_`/`tidal_` (признак стриминга) |
| полоска букв | картинка `a_z.png`; функцию `%c`/`'#'` рядом с буквами |
| алфавитный счёт | запрос `SELECT count(id) FROM %s WHERE rowid < (SELECT rowid FROM %s WHERE ... like ?)` |

Полезно: у hiby-mods в `binaries/*/README.md` (R3 Pro II) описаны code cave и
патчи — как образец методологии (адреса чужие).

## Шаг 3. Пересчитать адреса

Каждый наш скрипт из `tools/examples/` содержит константы (`VA`, offset, исходные
байты). Для нового устройства:
1. найди те же функции/строки по сигнатурам/строкам;
2. пересчитай `file_offset = VA - base`;
3. **ассерть исходные байты** — если не совпало, скрипт должен падать, а не портить.

## Шаг 4. Проверка гипотез

- Для любого UI-вопроса сначала сними дамп живого состояния (`/proc/pid/mem`) при
  открытом экране и сопоставь с БД (`list_tb_*`) — это снимает 80% неопределённости.
- Меняй по одному изменению за итерацию, строй образ, сверяй `verify`.
- Держи стоковый образ для откатa.

## Что переносится как есть

- `tools/generic/*` (make.sh, xref, disasm, find_jal, fix_update_md5) — только
  image base в конфиге.
- docker-образы и обёртки.
- Методология БД (translit/reorder/album_artist) — но схема таблиц и значения
  колонок у разных поколений отличаются; проверяй `pragma table_info` и триггеры.
