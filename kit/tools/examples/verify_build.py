#!/usr/bin/env python3
"""Проверки ДО флеша: патчи бинаря, (опц.) образ, (опц.) offline-симуляция БД.

Смысл — ловить регрессии/бутлупы без устройства (см. AGENTS.md).

    python3 tools/verify_build.py <hiby_player> [--image out/x.upt] [--db work/device/media.db]

* без флагов  — прогон `--check` по всей цепочке патчей бинаря;
* `--image`   — плюс `tools/make.sh verify` (дерево/хеши/патчи) через docker;
* `--db`      — плюс offline-симуляция конвейера БД на КОПИИ базы:
                translit → reorder → translit → split, затем инварианты
                (триггеров >= 14, склеек 0, «сырых» букв 0, integrity ok).
"""
from __future__ import annotations

import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent

# цепочка патчей бинаря (порядок важен)
CHAIN = [
    "patch_player", "patch_sql", "exp_album_view", "exp_flags_view21",
    "exp_coverpath_combo", "exp_cover_kind9col", "exp_cover_kind9id",
    "exp_shuffle_linear", "exp_shuffle_guard", "exp_artist_toggle",
    "exp_all_sort", "exp_albums_by_component", "exp_artist_tracks_component",
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
    with tempfile.TemporaryDirectory() as td:
        copy = Path(td) / "media.db"
        shutil.copy(db, copy)
        for script in ("translit_db", "reorder_db", "translit_db", "split_artists_db"):
            rc, out = run([sys.executable, str(TOOLS / f"{script}.py"), str(copy)])
            if rc != 0:
                print(f"  FAIL {script}: {out[:120]}")
                return False
        con = sqlite3.connect(copy)
        trig = con.execute("SELECT count(*) FROM sqlite_master WHERE type='trigger'").fetchone()[0]
        comb = con.execute("SELECT count(*) FROM ARTIST_TABLE WHERE instr(artist,';')>0").fetchone()[0]
        raw = con.execute(
            "SELECT count(*) FROM MEDIA_TABLE WHERE NOT (character BETWEEN 'A' AND 'Z') "
            "AND character!='~'").fetchone()[0]
        integ = con.execute("PRAGMA integrity_check").fetchone()[0]
        con.close()
        ok = trig >= 14 and comb == 0 and raw == 0 and integ == "ok"
        print(f"  {'ok  ' if ok else 'FAIL'} БД: триггеров={trig} склеек={comb} "
              f"сырых_букв={raw} integrity={integ}")
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
