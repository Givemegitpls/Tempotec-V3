#!/usr/bin/env python3
"""Обложки в «Artists → артист»: SQL кладёт реальный путь + источник пути из записи.

Механика (проверено разбором Ghidra + экспериментами):
 - Шаблон `INSERT INTO %s%d VALUES (?,?,?,0,...)` (литерал `0x9bc698`, единый для
   case 9 и case 0x14 `FUN_00708d20`) кладёт в колонку `path` записи списка
   ИМЯ альбома (bind 2), не путь — поэтому парсер обложек не находит папку.
 - Путь в запись обложки (контрол `+0x524`) копирует `FUN_004a52a0`
   (`0x4a5528 addiu $a1,$s0,0x3de0`) — источник буфер пути вида. Хак
   `exp_cover_artist_path.py` меняет источник на `local_ec0+4` (колонку `path`
   медиа-записи) — но.path с именем альбома не работает, нужен реальный путь.
 - Бит `view+0x74 & 1` (таблица видов, байт `0x55ec6c`) запускает
   `FUN_004a13c0 -> FUN_004a52a0` и создание потока обложек.

Комбо (без него тупик):
 1. Шаблон переносится в RX-запас (`0xa7e800, файл 0x67e800`), col `path` =
    подзапрос `(SELECT path FROM MEDIA_TABLE WHERE album=?2 LIMIT 1)`;
    оба места вызова (`0x7091c8/0x7091d4` и `0x709520/0x70952c`):
    `lui a1,0x9c -> 0xa8`, `addiu a1,-0x3968 -> -0x1800`.
 2. RX program header #2: filesz/memsz `0x67e370 -> 0x67f000`.
 3. `0x55ec6c` (w4 вида 21): 0 -> 1.
 4. `0x4a5528`: источник `view+0x3de0` -> `local_ec0+4` ($sp+0x24).

Использование:
    python3 tools/exp_coverpath_combo.py <hiby_player-player-path> [--check]
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

VADDR_TO_OFFSET = 0x400000

NEW_TEMPLATE = (
    b"INSERT INTO %s%d VALUES (?1,(SELECT path FROM MEDIA_TABLE WHERE album=?2 LIMIT 1),"
    b"?2,0,0,0,0,0,?3,0,0,0,?4,0,?5,0,?6,0,0,0,0,0,0,0,0,0,0)"
)

OLD_TEMPLATE = b"INSERT INTO %s%d VALUES (?,?,?,0,0,0,0,0,?,0,0,0,?,0,0,0,?,0,0,0,0,0,0,0,0,0,0)"

STR_VA = 0x9BC698
STR_OFF = STR_VA - VADDR_TO_OFFSET
NEW_STR_VA = 0xA7E800
NEW_STR_OFF = NEW_STR_VA - VADDR_TO_OFFSET

# (vaddr lui, vaddr addiu)
REFS = [(0x7091C8, 0x7091D4), (0x709520, 0x70952C)]
NEW_LUI_HI = 0xA8          # 0xa7e800: hi=0xa8, lo=-0x1800
NEW_ADDIU_IMM = 0xE800
OLD_LUI_HI = 0x9C
OLD_ADDIU_IMM = 0xC698

W4_VA = 0x55EC6C - VADDR_TO_OFFSET + 0x400000  # просто держим VA рядом
# запись вида 21: база 0x95e770 + 21*0x3c = 0x95EC5C (файл 0x55EC5C)
#   w2 @+8  = 0x55EC64 — селектор шаблона (0=@class@) — держать 0
#   w4 @+16 = 0x55EC6C — bit0: запуск парсера обложек -> 1
#   w5 @+20 = 0x55EC70 — bit1 (как у Albums) -> 1
TPL_SEL_OFF = 0x55EC64
W4_OFF = 0x55EC6C
W5_OFF = 0x55EC70

PATH_SRC_VA = 0x4A5528
PATH_SRC_OFF = PATH_SRC_VA - VADDR_TO_OFFSET
PATH_SRC_OLD = bytes.fromhex("e03d0526")  # addiu a1, s0, 0x3de0
PATH_SRC_NEW = bytes.fromhex("2400a527")  # addiu a1, sp, 0x24

PHDR_FILESZ = 0x67E370
PHDR_NEW = 0x67F000


def find_phdr2(data: bytes) -> int:
    # RX-сегмент размечен по filesz (0x67e370 / 0x67f000 после расширения)
    e_phoff = struct.unpack_from("<I", data, 28)[0]
    phentsize = struct.unpack_from("<H", data, 42)[0]
    e_phnum = struct.unpack_from("<H", data, 44)[0]
    for i in range(e_phnum):
        ph = e_phoff + i * phentsize
        p_type = struct.unpack_from("<I", data, ph)[0]
        off = struct.unpack_from("<I", data, ph + 4)[0]
        fsz = struct.unpack_from("<I", data, ph + 16)[0]
        if p_type == 1 and off <= 4 and fsz in (0x67E370, 0x67F000):
            return ph
    raise SystemExit("RX-заголовок не найден")


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    check = "--check" in sys.argv
    if len(args) != 1:
        raise SystemExit(__doc__)
    path = Path(args[0])
    data = bytearray(path.read_bytes())

    cur = bytes(data[NEW_STR_OFF : NEW_STR_OFF + len(NEW_TEMPLATE)])
    state = "unknown"
    if cur == NEW_TEMPLATE:
        state = "done"
    else:
        cur = bytes(data[STR_OFF : STR_OFF + len(OLD_TEMPLATE)])
        if cur == OLD_TEMPLATE:
            state = "stock"
    if check:
        print(f"шаблон: {state}")
        print(f"phdr2 filesz: {hex(struct.unpack_from('<I', data, find_phdr2(data) + 16)[0])}")
        print(f"селектор шаблона вида 21: {data[TPL_SEL_OFF]}")
        print(f"w4 (парсер обложек): {data[W4_OFF]}")
        print(f"w5: {data[W5_OFF]}")
        print(f"источник пути: {'patched' if bytes(data[PATH_SRC_OFF:PATH_SRC_OFF+4]) == PATH_SRC_NEW else 'stock'}")
        return 0
    if state == "done":
        print("уже пропатчено")
        return 0
    if state != "stock":
        raise SystemExit(f"шаблон не узнаётся: {cur[:60]!r}")

    # 1. новая строка шаблона
    if len(NEW_TEMPLATE) + 1 > NEW_STR_VA and False:  # мест всегда хватает
        pass
    assert NEW_STR_OFF < 0x67F000
    nm = NEW_STR_OFF
    if bytes(data[nm : nm + len(NEW_TEMPLATE)]) != NEW_TEMPLATE:
        end = data.find(b"\0", nm)
        assert end == -1 or all(b == 0 for b in data[nm : end]), "место занято"
        data[nm : nm + len(NEW_TEMPLATE) + 1] = NEW_TEMPLATE + b"\0"

    # 2. ссылки на шаблон
    for lui_va, addiu_va in REFS:
        lui_off = lui_va - VADDR_TO_OFFSET
        addiu_off = addiu_va - VADDR_TO_OFFSET
        wl = struct.unpack_from("<I", data, lui_off)[0]
        wa = struct.unpack_from("<I", data, addiu_off)[0]
        if (wl & 0xFFFF) == NEW_LUI_HI and (wa & 0xFFFF) == NEW_ADDIU_IMM:
            print(f"  [skip] ссылка {lui_va:#x}/{addiu_va:#x}: уже на {NEW_STR_VA:#x}")
            continue
        assert (wl & 0xFFFF) == OLD_LUI_HI, f"lui по {lui_va:#x}: {wl:#x}"
        assert (wa & 0xFFFF) == OLD_ADDIU_IMM, f"addiu по {addiu_va:#x}: {wa:#x}"
        # immediate — МЛАДШИЕ 2 байта инструкции (little endian)
        data[addiu_off] = NEW_ADDIU_IMM & 0xFF
        data[addiu_off + 1] = (NEW_ADDIU_IMM >> 8) & 0xFF
        data[lui_off] = NEW_LUI_HI & 0xFF
        data[lui_off + 1] = (NEW_LUI_HI >> 8) & 0xFF
        print(f"  [ok] ссылка {lui_va:#x}/{addiu_va:#x} -> {NEW_STR_VA:#x}")

    # 3. phdr filesz/memsz
    ph = find_phdr2(data)
    cur_sz = struct.unpack_from("<I", data, ph + 16)[0]
    if cur_sz == PHDR_FILESZ:
        struct.pack_into("<I", data, ph + 16, PHDR_NEW)
        struct.pack_into("<I", data, ph + 20, PHDR_NEW)
        print(f"  [ok] phdr2 filesz/memsz -> {PHDR_NEW:#x}")
    elif cur_sz >= PHDR_NEW:
        print("  [skip] phdr2 уже расширен")

    # 4. флаги вида 21 (селектор шаблона вернуть в @class@)
    if data[TPL_SEL_OFF] != 0:
        data[TPL_SEL_OFF] = 0
        print("  [ok] селектор шаблона вида 21 -> 0 (@class@)")
    else:
        print("  [skip] селектор шаблона вида 21 = 0")
    if data[W4_OFF] == 0:
        data[W4_OFF] = 1
        print("  [ok] w4 (bit0, парсер обложек) -> 1")
    else:
        print(f"  [skip] w4 = {hex(data[W4_OFF])}")
    if data[W5_OFF] == 0:
        data[W5_OFF] = 1
        print("  [ok] w5 (bit1, как у Albums) -> 1")
    else:
        print(f"  [skip] w5 = {hex(data[W5_OFF])}")

    # 5. источник пути
    if bytes(data[PATH_SRC_OFF : PATH_SRC_OFF + 4]) == PATH_SRC_OLD:
        data[PATH_SRC_OFF : PATH_SRC_OFF + 4] = PATH_SRC_NEW
        print(f"  [ok] источник пути {PATH_SRC_VA:#x} -> local_ec0+4")
    elif bytes(data[PATH_SRC_OFF : PATH_SRC_OFF + 4]) == PATH_SRC_NEW:
        print("  [skip] источник пути уже правед")

    path.write_bytes(bytes(data))
    print(f"{path}: записано")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
