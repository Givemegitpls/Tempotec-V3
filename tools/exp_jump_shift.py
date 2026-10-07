#!/usr/bin/env python3
"""Эксперимент: сдвиг буквы при прыжке по алфавитной полоске.

Плеер ищет позицию для прыжка по букве, которую подставляет в SQL-запрос.
Наблюдение: нажатие «A» приводит к альбомам на «B», то есть плеер уходит
на одну букву вперёд. Скрипт правит одну инструкцию в функции прыжка
(0x70340c): вместо `move $a2, $s3` (буква как есть) ставит
`addiu $a2, $s3, delta` — буква, которую реально увидит запрос.

Использование:
    python3 tools/exp_jump_shift.py <hiby_player> [delta]
delta по умолчанию -1 (на букву назад). Для проверки знака можно поставить +1.
"""

from __future__ import annotations

import sys
from pathlib import Path

OFFSET = 0x70340C - 0x400000
MOVE_A2_S3 = bytes.fromhex("21306002")  # addu a2, s3, zero (move a2, s3)


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    path = Path(sys.argv[1])
    delta = int(sys.argv[2]) if len(sys.argv) > 2 else -1
    data = bytearray(path.read_bytes())

    if data[OFFSET : OFFSET + 4] == MOVE_A2_S3:
        word = (0x09 << 26) | (19 << 21) | (6 << 16) | (delta & 0xFFFF)
        data[OFFSET : OFFSET + 4] = word.to_bytes(4, "little")
        path.write_bytes(bytes(data))
        print(f"{path}: сдвиг буквы при прыжке = {delta:+d}")
        return 0

    word = int.from_bytes(data[OFFSET : OFFSET + 4], "little")
    if (word >> 26) == 0x09 and ((word >> 21) & 31) == 19 and ((word >> 16) & 31) == 6:
        current = word & 0xFFFF
        current = current - 0x10000 if current >= 0x8000 else current
        print(f"{path}: сдвиг уже стоит: {current:+d}")
        return 0

    raise SystemExit(f"не совпала инструкция по смещению {OFFSET:#x}: {data[OFFSET:OFFSET+4].hex()}")


if __name__ == "__main__":
    raise SystemExit(main())
