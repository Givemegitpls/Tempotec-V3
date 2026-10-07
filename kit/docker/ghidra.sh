#!/usr/bin/env bash
# Обёртка для Ghidra (headless, PyGhidra) в docker. Проект хранится в
# $PROJ (по умолчанию work/ghidra_project), анализ не повторяется.
#
# Важно: analyzeHeadless в Ghidra 12 не умеет PyGhidra-скрипты
# ("Ghidra was not started with PyGhidra"), поэтому используется CLI `pyghidra`
# (pip) с GHIDRA_INSTALL_DIR=/opt/ghidra.
#
# Примеры (из корня проекта):
#   BIN=fw/SYSTEM/usr/bin/hiby_player ./kit/docker/ghidra.sh import
#   BIN=fw/SYSTEM/usr/bin/hiby_player ./kit/docker/ghidra.sh list
#   BIN=fw/SYSTEM/usr/bin/hiby_player ./kit/docker/ghidra.sh decompile 0x4c7e9c 0x4eb680
set -euo pipefail

GHIDRA_IMAGE=${GHIDRA_IMAGE:-hiby-ghidra}
PROJECT_ROOT=${PROJECT_ROOT:-$PWD}
BIN=${BIN:-work/hiby_player}
PROJ=${PROJ:-work/ghidra_project}
PROJNAME=${PROJNAME:-hiby}
OUT=${OUT:-work/ghidra_out}
# скрипты монтируем из kit/docker/ghidra_scripts — образ пересобирать не нужно
SCRIPTS_HOST=$(cd "$(dirname "$0")/ghidra_scripts" && pwd)

run_pyghidra() {
  mkdir -p "$PROJECT_ROOT/$PROJ"
  docker run --rm -i \
    -v "$PROJECT_ROOT:/work" -v "$SCRIPTS_HOST:/scripts:ro" -w /work \
    -e GHIDRA_INSTALL_DIR=/opt/ghidra "$GHIDRA_IMAGE" \
    pyghidra --project-path "/work/$PROJ" --project-name "$PROJNAME" "$@"
}

cmd_import()   { run_pyghidra "$BIN" /scripts/Noop.py; }
cmd_list()     { mkdir -p "$PROJECT_ROOT/$OUT"; run_pyghidra --skip-analysis "$BIN" /scripts/ListFunctions.py "/work/$OUT"; }
cmd_decompile(){ mkdir -p "$PROJECT_ROOT/$OUT"; run_pyghidra --skip-analysis "$BIN" /scripts/DecompileAt.py "/work/$OUT" "$@"; }

case "${1:-}" in
  import)    cmd_import ;;
  list)      cmd_list ;;
  decompile) shift; cmd_decompile "$@" ;;
  raw)       shift; docker run --rm -i -v "$PROJECT_ROOT:/work" -w /work \
               -e GHIDRA_INSTALL_DIR=/opt/ghidra "$GHIDRA_IMAGE" "$@" ;;
  *)         sed -n '2,16p' "$0"; exit 1 ;;
esac
