#!/usr/bin/env python3
"""Проверки ДО флеша: патчи бинаря, (опц.) образ, (опц.) offline-симуляция БД.

Смысл — ловить регрессии/бутлупы без устройства (см. AGENTS.md).

    python3 tools/verify_build.py <hiby_player> [--image out/x.upt] [--db work/device/media.db]

* без флагов  — прогон `--check` по всей цепочке патчей бинаря;
* `--image`   — плюс `tools/make.sh verify` (дерево/хеши/патчи) через docker;
* `--db`      — плюс прогон ВШИТОГО `fw/SYSTEM/usr/share/hiby_db_fix.sql`
                (тот же, что выполняет бинарь) на КОПИИ базы и проверка
                инвариантов (триггеров >= 18, склеек 0, «сырых» букв 0,
                integrity ok).
"""
from __future__ import annotations

import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

import re

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent

# цепочка патчей бинаря (порядок важен)
CHAIN = [
    "patch_player", "patch_sql", "exp_album_view", "exp_flags_view21",
    "exp_coverpath_combo", "exp_cover_kind9col", "exp_cover_kind9id",
    "exp_shuffle_linear", "exp_shuffle_guard", "exp_shuffle_hierarchy",
    "exp_artist_toggle", "exp_toggle_album_artist", "exp_all_sort",
    "exp_albums_artist_album_artist", "exp_artist_tracks_component", "exp_db_autofix",
    "patch_artist_cleanup", "exp_az_bar", "exp_usb_mode_adb",
]
BAD = ("неожиданн", "не найдено", "занято", "не влезает", "Traceback")


def run(cmd: list[str]) -> tuple[int, str]:
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


def check_binary(binary: Path) -> bool:
    ok = True
    for name in CHAIN:
        rc, out = run([sys.executable, str(TOOLS / f"{name}.py"), str(binary), "--check"])
        first = out.splitlines()[0] if out else ""
        bad = rc != 0 or any(b in out for b in BAD)
        print(f"  {'FAIL' if bad else 'ok  '} {name:26} {first[:90]}")
        ok &= not bad
    return ok


def check_image(image: Path) -> bool:
    rc, out = run([str(TOOLS / "make.sh"), "verify", image.name])
    diff_empty = "различия дерева SYSTEM" in out and not any(
        l.startswith("<") or l.startswith(">") for l in out.splitlines()
    )
    print(f"  {'ok  ' if rc == 0 and diff_empty else 'FAIL'} make.sh verify")
    return rc == 0 and diff_empty


def check_db(db: Path) -> bool:
    """Прогон ВШИТОГО SQL (fw/SYSTEM/usr/share/hiby_db_fix.sql) на копии базы:
    именно этот файл выполняет бинарь после «обновления медиатеки»."""
    sql_path = ROOT / "fw/SYSTEM/usr/share/hiby_db_fix.sql"
    if not sql_path.exists():
        print(f"  FAIL нет {sql_path}")
        return False
    with tempfile.TemporaryDirectory() as td:
        copy = Path(td) / "media.db"
        shutil.copy(db, copy)
        con = sqlite3.connect(copy)
        con.isolation_level = None
        try:
            con.executescript(sql_path.read_text(encoding="utf-8"))
        except sqlite3.Error as e:
            print(f"  FAIL SQL: {e}")
            con.close()
            return False
        trig = con.execute("SELECT count(*) FROM sqlite_master WHERE type='trigger'").fetchone()[0]
        comb = con.execute("SELECT count(*) FROM ARTIST_TABLE WHERE instr(artist,';')>0").fetchone()[0]
        comb_aa = con.execute(
            "SELECT count(*) FROM ALBUM_ARTIST_TABLE WHERE instr(album_artist,';')>0").fetchone()[0]
        raw = con.execute(
            "SELECT count(*) FROM MEDIA_TABLE WHERE NOT (character BETWEEN 'A' AND 'Z') "
            "AND character!='~'").fetchone()[0]
        integ = con.execute("PRAGMA integrity_check").fetchone()[0]
        con.close()
        ok = trig >= 18 and comb == 0 and comb_aa == 0 and raw == 0 and integ == "ok"
        print(f"  {'ok  ' if ok else 'FAIL'} БД (вшитый SQL): триггеров={trig} склеек={comb} "
              f"склеек_AA={comb_aa} сырых_букв={raw} integrity={integ}")
        return ok


def check_tree(tree: Path) -> bool:
    """Права в дереве rootfs: бинарь и init-скрипты обязаны быть исполняемыми
    (иначе образ соберётся, но плеер не запустится — бутлуп на заставке)."""
    ok = True
    binp = tree / "usr/bin/hiby_player"
    if binp.exists():
        mode = binp.stat().st_mode & 0o777
        exec_ok = bool(mode & 0o111)
        print(f"  {'ok  ' if exec_ok else 'FAIL'} {binp}: режим {oct(mode)}")
        ok &= exec_ok
    initd = tree / "etc/init.d"
    if initd.is_dir():
        for p in initd.iterdir():
            if p.is_file() and not (p.stat().st_mode & 0o111):
                print(f"  FAIL init-скрипт не исполняемый: {p} ({oct(p.stat().st_mode & 0o777)})")
                ok = False
    dbfix = tree / "usr/share/hiby_db_fix.sql"
    if dbfix.is_file() and dbfix.stat().st_size > 0:
        print(f"  ok   {dbfix.relative_to(tree)} ({dbfix.stat().st_size} байт)")
    else:
        print(f"  FAIL нет {dbfix.relative_to(tree)} (вшить в образ: make.sh build)")
        ok = False
    strdir = tree / "usr/resource/str"
    if strdir.is_dir():
        bad = []
        for f in sorted(strdir.glob("*/sys_set.ini")):
            raw = f.read_bytes()
            enc = ("utf-16-le" if raw[:2] == b"\xff\xfe"
                   else "utf-16-be" if raw[:2] == b"\xfe\xff" else "utf-8")
            text = (raw[2:] if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw).decode(enc)
            m = re.search(r"<adb>(.*?)</adb>", text)
            if m and m.group(1) != "ADB":
                bad.append(f"{f.parent.name}:{m.group(1)}")
        print(f"  {'ok  ' if not bad else 'FAIL'} метка USB-режима adb = ADB"
              + (f" (не ADB: {bad})" if bad else ""))
        ok &= not bad
    return ok


def main() -> int:
    args = sys.argv[1:]
    if not args:
        raise SystemExit(__doc__)
    binary = Path(args[0])
    image = Path(args[args.index("--image") + 1]) if "--image" in args else None
    db = Path(args[args.index("--db") + 1]) if "--db" in args else None

    ok = check_tree(ROOT / "fw/SYSTEM")
    ok &= check_binary(binary)
    if image:
        ok &= check_image(image)
    if db:
        ok &= check_db(db)
    print("ИТОГ:", "OK" if ok else "ЕСТЬ ПРОБЛЕМЫ")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
