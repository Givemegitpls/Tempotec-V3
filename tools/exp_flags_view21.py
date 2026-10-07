#!/usr/bin/env python3
"""Флаги записи вида 21 (VG_LISTVIEW_ALBUMS_OF_AN_ARTIST) в таблице видов.

Запись вида: база 0x95E770 + 21*0x3C = 0x95EC5C (в файле 0x55EC5C),
15 слов:
  w0 имя, w1 type (0x12), w2 селектор шаблона (0), w3 ?
  w4..w12 = биты флага view+0x74 (w4=bit0, w5=bit1, ...),
  w13 -> view+0x41e0, w14 указатель строки-ключа.

Шток:       w4..w12 = 0,0,0,1,0,1,1,1,0   w13=1
Albums(w3): w4..w12 = 1,1,0,1,0,1,1,1,0   w13=0

В этой версии скрипта правится ТОЛЬКО w5 (bit1) -> 1 (как у Albums),
w13 не трогаем.

    python3 tools/exp_flags_view21.py <hiby_player> [--check]
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

ENTRY_VA = 0x95EC5C  # запись вида 21
DELTA = 0x400000
BASE_OFF = ENTRY_VA - DELTA

W4, W5, W6, W7, W8, W9, W10, W11, W12, W13 = range(4, 14)
# цель: как у «Albums» (idx 3), но только нужные нам флаги;
# w13 у Albums=0, у подуровней=1 — не трогаем, чтобы не сломать поведение.
DEST = {W4: 1, W5: 1, W6: 0}
# ВАЖНО: w13 НЕ трогать — w13=0 (как у Albums) ЛОМАЕТ сценарий подуровня
# (см. секцию «Сессия 2026-10-03/04» в .opencode/NOTES.md).


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    check = "--check" in sys.argv
    if len(args) != 1:
        raise SystemExit(__doc__)
    path = Path(args[0])
    data = bytearray(path.read_bytes())

    if check:
        words = struct.unpack_from("<15I", data, BASE_OFF)
        print("w4..w13:", [words[i] for i in range(4, 15)])
        return 0

    changed = False
    for wi, val in DEST.items():
        off = BASE_OFF + 4 * wi
        cur = struct.unpack_from("<I", data, off)[0]
        if cur == val:
            print(f"  [skip] w{wi}: уже {val:#x}")
        else:
            struct.pack_into("<I", data, off, val)
            print(f"  [ok]   w{wi}: {cur:#x} -> {val:#x}")
            changed = True

    if changed:
        path.write_bytes(bytes(data))
        print(f"{path}: записано")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
