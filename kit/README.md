# HiBy firmware modding — agent kit

Самодостаточный набор инструкций, скиллов, docker-образов и скриптов, чтобы
агент (или человек) мог распаковать прошивку HiBy OS, найти нужный код, аккуратно
пропатчить бинарь `hiby_player`, собрать `.upt` и проверить результат на устройстве.

Рабочий пример-первоисточник — **Tempotec V3 Analog** (тот же класс устройств, что
HiBy R1 / R3 II 2025 / R3 Pro II / V1: Ingenic X1600E, MIPS32 LE, `.upt`). Все
конкретные адреса в `docs/04-recipes.md` — от V3 Analog; на другом устройстве их
надо пересчитать (см. `docs/06-adapt-new-device.md`).

## Кому это

Агенту, который получил задачу «добавить/починить фичу в прошивке HiBy»: обложки
в списках, поиск/сортировка, уровни меню, кириллица, правки медиатеки.

## С чего начать

1. `docs/01-overview.md` — как устроена прошивка.
2. `docs/02-workflow.md` — полный цикл (это основной документ).
3. `docs/03-techniques.md` — приёмы реверса и патчинга.
4. `docs/04-recipes.md` — готовые рецепты: обложки в Artists, фильтр `album_artist`,
   кириллический поиск.
5. `docs/05-pitfalls.md` — обязательный чек-лист грабель (прочитать до правок).
6. `docs/06-adapt-new-device.md` — перенос на другое устройство.

## Что внутри

```
kit/
  README.md
  docs/            01..06 — методология и рецепты
  skills/          SKILL.md для opencode (общий + устройство)
  docker/          Dockerfile.tools, Dockerfile.ghidra, Dockerfile.ghidra-mcp, обёртки, ghidra-mcp
  tools/generic/   make.sh, xref.py, disasm_range.py, find_jal.py, fix_update_md5.py, ...
  tools/examples/  наши патч-скрипты (идемпотентные, --check) как образцы
  reference/       NOTES-v3.md — вся история/адреса V3 Analog
```

## Быстрый старт

```bash
# 1. образы (из корня kit/)
docker build -t hiby-fw-tools  -f docker/Dockerfile.tools  docker
docker build -t hiby-ghidra    -f docker/Dockerfile.ghidra docker

# 2. распаковать/собрать прошивку (из корня проекта, где лежит .upt)
SRC=stock.upt ./kit/tools/generic/make.sh unpack
SRC=stock.upt ./kit/tools/generic/make.sh build my.upt
SRC=stock.upt ./kit/tools/generic/make.sh verify my.upt

# 3. анализ
BIN=fw/SYSTEM/usr/bin/hiby_player ./kit/docker/ghidra.sh import
BIN=fw/SYSTEM/usr/bin/hiby_player ./kit/docker/ghidra.sh decompile 0x4ca500

# 4. патч (пример) и сборка
python3 kit/tools/examples/exp_cover_kind9id.py fw/SYSTEM/usr/bin/hiby_player --check
```
> `make.sh` — шаблон: `SRC`, `TREE`, `FW`, `FW_IMAGE`, `PATCH_*`, `FIXMD5` берутся из
> env (см. шапку скрипта). `fw.sh` монтирует текущий `$PWD` в `/work`.

## Установка скиллов (opencode)

Скиллы в `kit/skills/` — обычные SKILL.md. Чтобы агент подхватывал их
автоматически, скопируй/симлинкни в каталог скиллов:

```bash
# для этого проекта:
mkdir -p .opencode/skills
cp -r kit/skills/hiby-firmware-patching kit/skills/tempotec-v3-analog .opencode/skills/
# или глобально:
cp -r kit/skills/* ~/.config/opencode/skills/
```

## Ключевые предупреждения (полностью — в `docs/05-pitfalls.md`)

- `VA = file_offset + image_base` (у V3 `+0x400000`); табличные строки адресуются по
  индексу — «нет xref» ≠ «код мёртв».
- **Никогда не писать в RX-страницы** — плеер падает (диагностику вести через RW,
  лог-функцию, `strace` или дампы `/proc/pid/mem`).
- Кэш списков (`list_tb_*`, `MANAGER_TABLE`) в `/data` переживает прошивку — чистить
  один раз (`tools/examples/clear_list_cache.py`).
- Медиатека — **не** в образе; её правки делать отдельно и бэкапить.
- Все сборки прогонять через `verify` и сверять md5; базовый бинарь не затирать.
