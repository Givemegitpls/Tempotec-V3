#!/usr/bin/env bash
# Сборка прошивки «с нуля»: чистый сток -> вся цепочка патчей -> проверки -> образ.
#
#   ./tools/build_all.sh [имя_образа.upt] [копия_базы_медиатеки.db]
#
# Имя образа по умолчанию — v3_analog.upt (готовый образ: out/v3_analog.upt).
# Другое имя задаётся первым аргументом или переменной окружения IMAGE=...
# (например: IMAGE=v3_analog_test.upt ./tools/build_all.sh).
#
# Всё, что попадает в образ, видно до сборки: ./tools/make.sh audit
# (дифф fw/SYSTEM против свежераспакованного стока).
#
# Инструменты (7z, ubireader, mkfs.ubifs, genisoimage) — только в docker-образе
# tempotec-fw-tools (docker/Dockerfile). Правки бинаря идут через ./docker/fw.sh.
set -euo pipefail
cd "$(dirname "$0")/.."

BIN=fw/SYSTEM/usr/bin/hiby_player
IMAGE="${IMAGE:-${1:-v3_analog.upt}}"
DB="${DB:-${2:-}}"

# Порядок важен и должен совпадать с tools/verify_build.py:CHAIN.
CHAIN=(
  exp_album_view
  exp_flags_view21
  exp_coverpath_combo
  exp_cover_kind9col
  exp_cover_kind9id
  exp_shuffle_linear
  exp_shuffle_guard
  exp_shuffle_hierarchy
  exp_artist_toggle
  exp_toggle_album_artist
  exp_all_sort
  exp_albums_artist_album_artist
  exp_artist_tracks_component
  exp_db_autofix
  patch_artist_cleanup
  exp_az_bar
  exp_usb_mode_adb
)

echo "== 1/5 распаковка стока (v3_analog.upt -> fw/SYSTEM)"
./tools/make.sh unpack

echo "== 2/5 базовые патчи: patch_player --album-level + patch_sql"
./docker/fw.sh python3 tools/patch_player.py --album-level "$BIN"
./docker/fw.sh python3 tools/patch_sql.py "$BIN"

echo "== 3/5 цепочка патчей"
for s in "${CHAIN[@]}"; do
  echo "   -- $s"
  ./docker/fw.sh python3 "tools/$s.py" "$BIN"
done
./docker/fw.sh chmod 775 "$BIN"

echo "== 4/5 проверки до флеша (--check по всей цепочке)"
# check_tree ругается на артефакты, которые создаёт шаг 5 (вшитый hiby_db_fix.sql
# и метки ADB в str/*/sys_set.ini) — это ожидаемо; строгая проверка образа ниже.
python3 tools/verify_build.py "$BIN" \
  || echo "   (ожидаемо: hiby_db_fix.sql и метки USB-режима появляются на шаге 5)"

echo "== 5/5 сборка образа out/$IMAGE"
./tools/make.sh build "$IMAGE"
if [ -n "$DB" ]; then
  python3 tools/verify_build.py "$BIN" --image "out/$IMAGE" --db "$DB"
else
  python3 tools/verify_build.py "$BIN" --image "out/$IMAGE"
fi

echo "== готово: out/$IMAGE"
