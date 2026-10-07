#!/usr/bin/env bash
# Сборка/разборка прошивки HiBy OS. Шаблон: запускать ИЗ КОРНЯ ПРОЕКТА.
# Все инструменты — в docker-образе (см. kit/docker/README.md).
#
#   ./kit/tools/generic/make.sh unpack
#   ./kit/tools/generic/make.sh patch        # patch_player + patch_sql (если есть)
#   ./kit/tools/generic/make.sh build [имя]
#   ./kit/tools/generic/make.sh verify [имя]
#
# Переопределяется через env:
#   FW=kit/docker/fw.sh  FW_IMAGE=hiby-fw-tools
#   SRC=stock.upt  TREE=fw/SYSTEM  UNPACKED=fw/unpacked
#   FIXMD5=kit/tools/generic/fix_update_md5.py
#   PATCH_PLAYER=tools/patch_player.py  PATCH_SQL=tools/patch_sql.py
set -euo pipefail

FW=${FW:-kit/docker/fw.sh}
FW_IMAGE=${FW_IMAGE:-hiby-fw-tools}
export FW_IMAGE
SRC=${SRC:-stock.upt}
UNPACKED=${UNPACKED:-fw/unpacked}
TREE=${TREE:-fw/SYSTEM}
OUT="out/${2:-v3_analog_patched.upt}"
FIXMD5=${FIXMD5:-kit/tools/generic/fix_update_md5.py}
PATCH_PLAYER=${PATCH_PLAYER:-tools/patch_player.py}
PATCH_SQL=${PATCH_SQL:-tools/patch_sql.py}
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
  [ -f "$PATCH_PLAYER" ] && $FW python3 "$PATCH_PLAYER" "$@" $TREE/usr/bin/hiby_player
  [ -f "$PATCH_SQL" ] && $FW python3 "$PATCH_SQL" $TREE/usr/bin/hiby_player
  true
}

cmd_build() {
  $FW bash -c "
    set -e
    chown -R 1004:1004 $TREE
    mkfs.ubifs -x lzo -d $TREE -e 0x1F000 -c 480 -m 0x800 -o $UNPACKED/SYSTEM.UBI
    python3 $FIXMD5 $UNPACKED/UPDATE.TXT $UNPACKED/SYSTEM.UBI
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
    echo '--- различия дерева SYSTEM (ожидается пусто):'
    diff -r --no-dereference -q $TREE \$V/SYSTEM || true
    echo '--- md5 бинаря в образе:'
    md5sum \$V/SYSTEM/usr/bin/hiby_player
  "
}

case "${1:-all}" in
  unpack) cmd_unpack ;;
  patch)  shift; cmd_patch "$@" ;;
  build)  cmd_build ;;
  verify) cmd_verify ;;
  all)    cmd_unpack; cmd_patch; cmd_build; cmd_verify ;;
  *) echo "использование: $0 {unpack|patch|build|verify|all} [имя образа]" >&2; exit 1 ;;
esac
