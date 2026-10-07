#!/usr/bin/env bash
# Обёртка для запуска инструментов Ghidra (headless, PyGhidra) в докере.
# Проект Ghidra хранится в work/ghidra_project, чтобы анализ не повторялся.
#
# Важно: analyzeHeadless из Ghidra 12 не умеет PyGhidra-скрипты ("Ghidra was not
# started with PyGhidra"), поэтому используется CLI `pyghidra` (pip) с
# GHIDRA_INSTALL_DIR=/opt/ghidra.
#
# Примеры:
#   ./docker/ghidra.sh import                       # импорт+анализ hiby_player
#   ./docker/ghidra.sh list                          # список функций в файл
#   ./docker/ghidra.sh decompile 0x4c7e9c 0x4eb680   # декомпилировать функции
#   ./docker/ghidra.sh raw pyghidra --help           # произвольная команда
set -euo pipefail
cd "$(dirname "$0")/.."

BIN=${BIN:-work/hiby_player}
PROJ=${PROJ:-work/ghidra_project}
PROJNAME=${PROJNAME:-tempotec}
OUT=${OUT:-work/ghidra_out}
# скрипты берём из смонтированного каталога проекта — образ пересобирать не нужно
SCRIPTS=/work/docker/ghidra_scripts

run_pyghidra() {
  mkdir -p "$PROJ"
  docker run --rm -i -v "$PWD:/work" -w /work \
    -e GHIDRA_INSTALL_DIR=/opt/ghidra tempotec-ghidra \
    pyghidra --project-path "/work/$PROJ" --project-name "$PROJNAME" "$@"
}

cmd_import() {
  # импорт и анализ бинаря (один раз; результат остаётся в проекте)
  run_pyghidra "$BIN" "$SCRIPTS/Noop.py"
}

cmd_list() {
  mkdir -p "$OUT"
  run_pyghidra --skip-analysis "$BIN" "$SCRIPTS/ListFunctions.py" "/work/$OUT"
}

cmd_decompile() {
  mkdir -p "$OUT"
  run_pyghidra --skip-analysis "$BIN" "$SCRIPTS/DecompileAt.py" "/work/$OUT" "$@"
}

case "${1:-}" in
  import)    cmd_import ;;
  list)      cmd_list ;;
  decompile) shift; cmd_decompile "$@" ;;
  raw)       shift; docker run --rm -i -v "$PWD:/work" -w /work \
               -e GHIDRA_INSTALL_DIR=/opt/ghidra tempotec-ghidra "$@" ;;
  *)         sed -n '2,16p' "$0"; exit 1 ;;
esac
