# Docker: образы для патчинга прошивок

Два основных образа + опциональный ghidra-mcp.

## Сборка

```bash
# из корня kit/ (build context = docker/, т.к. Dockerfile.ghidra копирует ghidra_scripts)
docker build -t hiby-fw-tools -f docker/Dockerfile.tools docker
docker build -t hiby-ghidra   -f docker/Dockerfile.ghidra docker
```

- **hiby-fw-tools** (Ubuntu 24.04): `mtd-utils`, `genisoimage`, `radare2`,
  `p7zip-full`, `squashfs-tools`, `python3-pyelftools`, `python3-capstone`,
  `ubi_reader` (pip). Для распаковки/сборки `.upt` и быстрого дизасма.
- **hiby-ghidra** (Ubuntu 24.04 + OpenJDK 21 + Ghidra 12.1.4 + `pyghidra`):
  headless-анализ и декомпиляция.

## Обёртки

```bash
FW_IMAGE=hiby-fw-tools ./kit/docker/fw.sh <команда>       # каталог проекта -> /work
BIN=fw/SYSTEM/usr/bin/hiby_player ./kit/docker/ghidra.sh import
BIN=fw/SYSTEM/usr/bin/hiby_player ./kit/docker/ghidra.sh decompile 0x4ca500
```
`fw.sh` монтирует текущий `$PWD` (или `$PROJECT_ROOT`) в `/work`.
`ghidra.sh` дополнительно монтирует `ghidra_scripts/` в `/scripts` (образ
пересобирать при смене скриптов не нужно).

## Ghidra-скрипты

`ghidra_scripts/`:
- `Noop.py` — заголовок-обёртка для импорта+анализа;
- `ListFunctions.py` — список функций в файл;
- `DecompileAt.py` — декомпиляция по адресам (при необходимости дизассемблирует
  окно `0x1000` и создаёт функцию — для косвенных вызовов).

Все скрипты — PyGhidra (`# @runtime PyGhidra`), т.к. в Ghidra 12 Jython убран из
базовой поставки.

## ghidra-mcp (опционально)

См. `ghidra-mcp.md`. Образ: `docker build -t hiby-ghidra-mcp -f docker/Dockerfile.ghidra-mcp docker`
(экспериментальный, версия ghidra-mcp чувствительна).
