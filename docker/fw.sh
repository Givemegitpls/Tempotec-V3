#!/usr/bin/env bash
# Обёртка для распаковки/упаковки прошивки Tempotec V3 Analog.
# Все инструменты (7z, ubireader, mkfs.ubifs, genisoimage) живут в docker-образе
# tempotec-fw-tools, в систему ничего не ставится.
#
# Использование: ./docker/fw.sh <команда> [args...]
# Каталог проекта монтируется в /work (это и есть рабочая директория контейнера).
#
# Запуск от root нужен, чтобы ubireader мог создать в дереве симлинки и
# device-ноды, а mkfs.ubifs — записать uid/gid 1004:1004 как в оригинале.
set -euo pipefail
cd "$(dirname "$0")/.."
exec docker run --rm -i \
  -v "$PWD:/work" -w /work \
  tempotec-fw-tools "$@"
