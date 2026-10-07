# 02. Рабочий цикл

Цель — минимальное число перепрошивок и нулевой риск «кирпича». Правило: сначала
офлайн (анализ/патч/сборка/verify), потом одна заливка на устройство.

## 0. Бэкапы и база

- Сохрани стоковую `.upt` и **эталонный бинарь** (`fw/SYSTEM/usr/bin/hiby_player`)
  с его md5. Все будущие патчи делать от него, не от экспериментальных сборок.
- Перед правками БД: `adb pull /data/usrlocal_media.db work/device/media.db`.
- Держи под рукой релизный образ для откатa (`out/*.upt`).

## 1. Распаковка

```
./tools/make.sh unpack     # stock.upt -> fw/unpacked (ISO) + fw/SYSTEM (UBIFS)
# или вручную, см. docs/01-overview.md
```
`make.sh` целиком (unpack/patch/build/verify/all) — `tools/generic/make.sh`; он
использует образ `hiby-fw-tools` через обёртку `docker/fw.sh`.

## 2. Идентификация

```
md5sum fw/SYSTEM/usr/bin/hiby_player      # зафиксировать в NOTES
file fw/SYSTEM/usr/bin/hiby_player        # MIPS, little-endian, stripped
```
В NOTES/CHANGELOG фиксируй md5 базы — иначе непонятно, от чего собран патч.

## 3. Статический анализ

Ghidra-обёртка (`docker/ghidra.sh`) хранит проект (анализ не повторяется) и умеет
декомпилировать по адресу:

```
BIN=fw/SYSTEM/usr/bin/hiby_player ./docker/ghidra.sh import       # один раз, долго
BIN=fw/SYSTEM/usr/bin/hiby_player ./docker/ghidra.sh list
BIN=fw/SYSTEM/usr/bin/hiby_player ./docker/ghidra.sh decompile 0x4ca500 0x4a52a0
```
> Ghidra 12 `analyzeHeadless` не запускает PyGhidra-скрипты — обёртка использует
> CLI `pyghidra` с `GHIDRA_INSTALL_DIR`. Для «тяжёлого» реверса есть `ghidra-mcp`
> (см. `docker/ghidra-mcp.md`) — 250+ инструментов, xref, декомпиляция, эмуляция.

Вспомогательные скрипты (fast paths без Ghidra):
```
./docker/fw.sh python3 tools/generic/xref.py      fw/SYSTEM/usr/bin/hiby_player "SELECT DISTINCT album"
./docker/fw.sh python3 tools/generic/disasm_range.py fw/SYSTEM/usr/bin/hiby_player 0x4ca600 0x4ca700
./docker/fw.sh python3 tools/generic/find_jal.py  fw/SYSTEM/usr/bin/hiby_player 0x4a95e0
```

## 4. Проектирование патча

Выбери наименее инвазивный вариант (по возрастанию риска):

1. **На месте, той же длиной** — поменять байты/строку/константу без сдвига.
2. **Перенос строки** в свободный хвост `.rodata` + переписать указатель в слоте
   таблицы SQL (`tools/examples/patch_sql.py` — образец).
3. **Новый код** в RX-запас / code cave + `jal`-хук из точки вызова; `$ra` при
   этом сохраняется вызывающим — проверяй по дизассемблеру.
4. **Трамплин** в прологе (`lui $at; ori $at; jr $at`) — только если хук обязан
   быть на входе функции (`jr` не трогает `$ra`).

Правила:
- каждый патч — **идемпотентный** скрипт с `--check` и ассертами исходных байт;
- адреса и исходные байты — в скрипте, а не «на память»;
- сверяй дизасм **до** и **после** патча (`disasm_range.py`).

## 5. Реализация

Образцы — `tools/examples/exp_*.py`. Типовой каркас: прочитать файл в `bytearray`,
найти исходник, ассертить, заменить, записать; `--check` печатает состояние.
Не забывай расширять program header, если пишешь в конец RX-сегмента.

## 6. Сборка образа

```
./tools/make.sh build <имя>.upt
```
Делает: `chown 1004:1004 fw/SYSTEM` → `mkfs.ubifs` → пересчёт md5 в `UPDATE.TXT`
→ `genisoimage`. **Не забывай вернуть базовый бинарь** в `fw/SYSTEM` после сборки.

## 7. Проверка

```
./tools/make.sh verify <имя>.upt
```
Распаковывает образ, сверяет md5 UBI с `UPDATE.TXT`, `diff -r` дерева и печатает
состав патчей (`patch_player.py --check`, `patch_sql.py --check`).

Полезно: собрать бинарь из стоковой базы прогоном всей цепочки скриптов и
убедиться, что md5 совпадает с ожидаемым (воспроизводимость).

## 8. Тест на устройстве

```bash
adb pull  /usr/bin/hiby_player work/device/hiby_player.release   # сохранить что было
adb push  work/device/hiby_player.new /usr/bin/hiby_player
adb shell 'chmod 755 /usr/bin/hiby_player; sync; md5sum /usr/bin/hiby_player; reboot'
# подождать ~45–60 c, при отвале: adb kill-server
```
Rootfs смонтирован rw. Убийство `hiby_player` тоже перезагружает устройство — это
нормальный способ применить бинарь. Если поймал bootloop — залей релиз обратно по
adb (канал живёт первые минуты) либо прошей релизный `.upt`.

Диагностика (без правок в RX!):
- `strace -f -e trace=openat,open -o /data/tr.txt -p $(pidof hiby_player)` — но
  трейс держать в одной adb-сессии;
- дамп памяти: `dd if=/proc/$(pidof hiby_player)/mem of=/data/h.bin bs=4096 skip=... count=...`;
- логи плеера — через его же лог-функцию из хука (RW), не `printf`.

## 9. Документирование

- `CHANGELOG.md` — «на человеческом языке», что заметит владелец.
- `NOTES.md` — адреса, слоты, грабли, md5, порядок сборки.
- Зафиксируй финальные md5 (бинарь, UBI, ISO) — иначе теряется трассируемость.
