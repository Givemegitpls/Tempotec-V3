#!/usr/bin/env bash
# Сборка/разборка прошивки Tempotec V3 Analog. Всё внутри docker-образа
# tempotec-fw-tools (см. docker/Dockerfile), в систему ничего не ставится.
#
#   ./tools/make.sh unpack   # v3_analog.upt -> fw/unpacked + fw/SYSTEM
#   ./tools/make.sh patch    # правки бинарей в fw/SYSTEM
#   ./tools/make.sh build    # fw/SYSTEM -> SYSTEM.UBI -> md5 -> out/*.upt
#   ./tools/make.sh verify   # распаковать собранный образ и сверить с fw/SYSTEM
#   ./tools/make.sh all      # unpack + patch + build + verify
#
# Готовый образ: out/v3_analog.upt (имя — первый аргумент build/verify или IMAGE=...)
set -euo pipefail
cd "$(dirname "$0")/.."

FW=docker/fw.sh
SRC="${SRC:-v3_analog.upt}"
UNPACKED=fw/unpacked
TREE=fw/SYSTEM
OUT="out/${IMAGE:-${2:-v3_analog.upt}}"
HOST_UID=$(id -u)
HOST_GID=$(id -g)

cmd_unpack() {
  $FW bash -c "
    set -e
    rm -rf $UNPACKED $TREE
    mkdir -p $UNPACKED
    7z x -y $SRC -o$UNPACKED >/dev/null
    ubireader_extract_files -k -o $TREE $UNPACKED/SYSTEM.UBI
    chown -R $HOST_UID:$HOST_GID fw
    echo '--- ISO:'; ls -l $UNPACKED
    echo '--- дерево SYSTEM:'; du -sh $TREE
  "
}

cmd_patch() {
  $FW python3 tools/patch_player.py "$@" $TREE/usr/bin/hiby_player
  $FW python3 tools/patch_sql.py $TREE/usr/bin/hiby_player
}

cmd_build() {
  $FW bash -c "
    set -e
    if [ -d overlay ]; then cp -a overlay/. $TREE/; fi
    python3 tools/dedupe_rootfs.py $TREE
    chown -R 1004:1004 $TREE
    chmod 775 $TREE/usr/bin/hiby_player
    mkfs.ubifs -x lzo -d $TREE -e 0x1F000 -c 480 -m 0x800 -o $UNPACKED/SYSTEM.UBI
    python3 tools/fix_update_md5.py $UNPACKED/UPDATE.TXT $UNPACKED/SYSTEM.UBI
    mkdir -p out
    genisoimage -l -o $OUT \
      $UNPACKED/SYSTEM.UBI $UNPACKED/UIMAGE.BIN $UNPACKED/UBOOT.BIN \
      $UNPACKED/UPDATE.TXT $UNPACKED/VERSION.TXT $UNPACKED/_GITIGNO
    chown -R $HOST_UID:$HOST_GID fw out
    echo '--- образ:'; ls -l $OUT
    echo '--- UPDATE.TXT:'; cat $UNPACKED/UPDATE.TXT
  "
}

cmd_verify() {
  $FW bash -c "
    set -e
    V=/tmp/verify
    rm -rf \$V; mkdir -p \$V/iso
    7z x -y $OUT -o\$V/iso >/dev/null
    echo '--- md5 в UPDATE.TXT и на диске:'
    grep -A3 'rootfs=' \$V/iso/UPDATE.TXT | sed -n 's/.*md5=/UPDATE.TXT: /p'
    md5sum \$V/iso/SYSTEM.UBI | sed 's/^/файл:      /'
    ubireader_extract_files -k -o \$V/SYSTEM \$V/iso/SYSTEM.UBI
    echo '--- различия дерева SYSTEM после пересборки (ожидается пусто):'
    diff -r --no-dereference -q $TREE \$V/SYSTEM || true
    echo '--- патчи в собранном образе:'
    python3 tools/patch_player.py --check \$V/SYSTEM/usr/bin/hiby_player
    python3 tools/patch_sql.py --check \$V/SYSTEM/usr/bin/hiby_player
  "
}

case "${1:-all}" in
  unpack) cmd_unpack ;;
  patch)  shift; cmd_patch "$@" ;;
  build)  cmd_build ;;
  verify) cmd_verify ;;
  all)    cmd_unpack; cmd_patch; cmd_build; cmd_verify ;;
  *)      echo "использование: $0 {unpack|patch|build|verify|all} [имя образа для build/verify]" >&2; exit 1 ;;
esac
