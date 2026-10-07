---
name: hiby-firmware-patching
description: "Use when unpacking, patching, rebuilding or testing HiBy OS firmware (.upt, SYSTEM.UBI, hiby_player) on Ingenic X1600E devices (HiBy R1/R3 II 2025/R3 Pro II, Tempotec V1/V3): string/SQL patches, code caves, RX spare, UI lists, album covers, alphabet/Cyrillic search, media DB, shuffle/random playback. Trigger keywords: hiby firmware, hiby_player, .upt, SYSTEM.UBI, ubireader, mkfs.ubifs, genisoimage, adb push hiby_player, MIPS patch, code cave, list_tb_, MANAGER_TABLE, album cover, translit, shuffle, random order, next prev."
---

# Патчинг прошивок HiBy OS (агентный скилл)

Полная методология — в `kit/docs/` (см. `docs/02-workflow.md`). Здесь — краткая
карта действий.

## Когда применять

Задача звучит как «добавь/почини фичу в прошивке HiBy/Tempotec»: обложки в списках,
поиск/сортировка, уровни меню, кириллица, правки медиатеки, смена поведения плеера.

## Инварианты

- `VA = file_offset + image_base` (у V3 `+0x400000`) — конвертируй через ELF headers.
- Строки и запросы чаще берутся из **таблиц по индексу** — «нет xref» ≠ «не используется».
- **RX-запись = краш.** Новый код — в RX-запас/code cave; данные и логи — в RW/стек.
- **Non-main-thread view** не трогать.
- Кэш списков (`list_tb_*`, `MANAGER_TABLE`) в `/data` переживает прошивку — чистить.
- Медиатека не в образе; отдельно и с бэкапом.
- Каждый патч — идемпотентный скрипт с `--check` и ассертами исходных байт.

## Мини-цикл

```
# docker-образы
docker build -t hiby-fw-tools -f docker/Dockerfile.tools docker
docker build -t hiby-ghidra   -f docker/Dockerfile.ghidra docker

# 1) распаковка
./tools/make.sh unpack
# 2) анализ
BIN=fw/SYSTEM/usr/bin/hiby_player ./docker/ghidra.sh import
./docker/fw.sh python3 tools/generic/xref.py fw/SYSTEM/usr/bin/hiby_player "<строка>"
./docker/fw.sh python3 tools/generic/disasm_range.py fw/SYSTEM/usr/bin/hiby_player 0x... 0x...
# 3) патч (пример) + check
python3 tools/examples/<exp_*.py> fw/SYSTEM/usr/bin/hiby_player --check
# 4) сборка + проверка
./tools/make.sh build <имя>.upt && ./tools/make.sh verify <имя>.upt
# 5) тест
adb push work/device/hiby_player.new /usr/bin/hiby_player
adb shell 'chmod 755 /usr/bin/hiby_player; sync; reboot'
```

## Куда смотреть за деталями

- `kit/docs/03-techniques.md` — приёмы (xref, code cave, SQL-слоты, списки, обложки).
- `kit/docs/04-recipes.md` — готовые рецепты фич (обложки в Artists, `album_artist`, кириллица).
- `kit/docs/05-pitfalls.md` — обязательный чек-лист грабель.
- `kit/docs/06-adapt-new-device.md` — перенос на другое устройство.
- `kit/reference/NOTES-v3.md` — детальный разбор V3 (адреса, функции, история).

## Проверка гипотез (без падений)

Живое состояние — дамп `/proc/<pid>/mem` при открытом экране + сопоставление с
`list_tb_*` в `/data/usrlocal_media.db`; `strace -f -e trace=openat,open`.
Ghidra: `pyghidra` (headless analyze не умеет PyGhidra) или `ghidra-mcp`.
