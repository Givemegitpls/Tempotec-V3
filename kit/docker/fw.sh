#!/usr/bin/env bash
# Обёртка для инструментов прошивки HiBy OS (7z, ubireader, mkfs.ubifs,
# genisoimage) внутри docker-образа. В систему ничего не ставится.
#
# Использование (из корня проекта, где лежат .upt/tools):
#   FW_IMAGE=hiby-fw-tools ./kit/docker/fw.sh <команда> [args...]
# Каталог проекта (текущий $PWD или $PROJECT_ROOT) монтируется в /work.
#
# Root в контейнере нужен: ubireader создаёт симлинки/device-ноды, mkfs.ubifs
# пишет uid/gid 1004:1004 как в оригинале.
set -euo pipefail

FW_IMAGE=${FW_IMAGE:-hiby-fw-tools}
PROJECT_ROOT=${PROJECT_ROOT:-$PWD}

exec docker run --rm -i \
  -v "$PROJECT_ROOT:/work" -w /work \
  "$FW_IMAGE" "$@"
