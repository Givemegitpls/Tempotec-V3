#!/usr/bin/env python3
"""Shuffle (режим random): сделать «вперёд»/«назад» обратимыми.

Причина (разбор — work/shuffle_design.md): в FUN_0042da00 ветка random для
«вперёд» пропускает записи с флагом «сыграно»
(`0x42dd8c: bne $v1,$zero,0x42dc3c`), а «назад» просто уменьшает курсор. Из-за
этого после «назад» кнопка «вперёд» уходит мимо только что прослушанного трека.

Фикс: заменить эту инструкцию на nop. Тогда «вперёд» = курсор+1, «назад» =
курсор−1 по одной и той же перестановке → «назад → вперёд» возвращает тот же
трек; порядок остаётся случайным, без повторов до конца списка; при полном
проходе таблица пересобирается. Режимы order/loop/single не затрагиваются.

Использование:
    python3 tools/exp_shuffle_linear.py <hiby_player> [--check]
"""
from __future__ import annotations

import sys
from pathlib import Path

VTO = 0x400000
PATCH_VA = 0x42DD8C
PATCH_OFF = PATCH_VA - VTO
OLD = bytes.fromhex("abff6014")  # bne $v1,$zero,0x42dc3c
NEW = bytes.fromhex("00000000")  # nop


def main() -> int:
    argv = sys.argv[1:]
    check = "--check" in argv
    args = [a for a in argv if a != "--check"]
    if len(args) != 1:
        raise SystemExit(__doc__)
    path = Path(args[0])
    data = bytearray(path.read_bytes())

    cur = bytes(data[PATCH_OFF : PATCH_OFF + 4])
    if cur == NEW:
        state = "done"
    elif cur == OLD:
        state = "stock"
    else:
        state = "unknown"

    if check:
        print(f"shuffle-пропуск ({PATCH_VA:#x}): {state} (байты {cur.hex()})")
        return 0

    if state == "done":
        print("уже пропатчено (shuffle linear)")
        return 0
    if state != "stock":
        raise SystemExit(f"неожиданные байты по {PATCH_VA:#x}: {cur.hex()}")

    data[PATCH_OFF : PATCH_OFF + 4] = NEW
    path.write_bytes(bytes(data))
    print(f"{path}: shuffle -> линейный (nop @ {PATCH_VA:#x})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
