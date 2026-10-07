#!/usr/bin/env python3
"""Эксперимент: заставить индикатор A-Z показывать другой алфавит.

Что правится — одна и та же пара инструкций в классе списка с алфавитным
указателем (соответствие "позиция прокрутки -> буква"):

    0x4c9278  addiu $s3, $s3, 0x41      ; letter = 'A' + index
    0x4c927c  slti  $v1, $s3, 0x5b      ; index >= 26 -> '#'

Скрипт меняет базовую букву и границу диапазона. Значения — коды Unicode,
поэтому для кириллицы: base=0x410 ('А'), limit=0x430 ('Я'+1).

Использование:
    python3 tools/exp_letters.py <hiby_player> <base-hex> <limit-hex>
например:
    python3 tools/exp_letters.py hiby_player 0x410 0x430
"""

from __future__ import annotations

import sys
from pathlib import Path

ADD_BASE_OFFSET = 0x4C9278 - 0x400000
SLTI_OFFSET = 0x4C927C - 0x400000
ADD_BASE_OLD = bytes.fromhex("41007326")  # addiu s3, s3, 0x41
SLTI_OLD = bytes.fromhex("5b00632a")  # slti  v1, s3, 0x5b


def encode_addiu(rt: int, rs: int, imm: int) -> bytes:
    return (
        (0x09 << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)
    ).to_bytes(4, "little")


def encode_slti(rt: int, rs: int, imm: int) -> bytes:
    return (
        (0x0A << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)
    ).to_bytes(4, "little")


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    path = Path(sys.argv[1])
    base = int(sys.argv[2], 0)
    limit = int(sys.argv[3], 0)
    data = path.read_bytes()

    if data[ADD_BASE_OFFSET : ADD_BASE_OFFSET + 4] != ADD_BASE_OLD:
        raise SystemExit("не совпала инструкция базовой буквы — бинарь не тот")
    if data[SLTI_OFFSET : SLTI_OFFSET + 4] != SLTI_OLD:
        raise SystemExit("не совпала инструкция предела — бинарь не тот")

    # s3 = rt = rs = 19, v1 = rt = 3, rs = s3 = 19
    data = bytearray(data)
    data[ADD_BASE_OFFSET : ADD_BASE_OFFSET + 4] = encode_addiu(19, 19, base)
    data[SLTI_OFFSET : SLTI_OFFSET + 4] = encode_slti(3, 19, limit)
    path.write_bytes(bytes(data))
    print(f"{path}: базовая буква {base:#x}, предел {limit:#x} — записано")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
