#!/usr/bin/env python3
"""Эксперимент covR4: kind9-источник (слот 0xaae114 := 0x4a9180) + полный
RX-шаблон INSERT с col3 (album) = ?2, чтобы image-кэш lookup (FUN_004ca2e0,
вторая ветка: сравнение album rec+0x42c с entry+0x220) находил per-row запись.

Шаблон кладётся в RX 0xa7e800 ПОЛНОСТЬЮ (в covR3 был порезан хвост — причина
bootloop): полная строка с двойным нулем-терминатором.

Ожидаемый состав до применения: release + patch_player + patch_sql +
exp_album_view + exp_flags_view21 (w4=1,w5=1) — строго в этом порядке.

Использование:
    python3 tools/exp_cover_kind9col.py <hiby_player> [--check]
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

VTO = 0x400000
SLOT_VA = 0xAAE114
SLOT_OFF = SLOT_VA - VTO
KIND9 = 0x4A9180  # штатный источник «альбомы артиста» (kind9)
TPL_VA = 0xA7E800
TPL_OFF = TPL_VA - VTO
OLD_TPL = (
    "INSERT INTO %s%d VALUES (?1,(SELECT path FROM MEDIA_TABLE WHERE album=?2 LIMIT 1),"
    "?2,0,0,0,0,0,?3,0,0,0,?4,0,?5,0,?6,0,0,0,0,0,0,0,0,0,0)"
)
NEW_TPL = (
    "INSERT INTO %s%d VALUES (?1,(SELECT path FROM MEDIA_TABLE WHERE album=?2 LIMIT 1),"
    "?2,?2,0,0,0,0,?3,0,0,0,?4,0,?5,0,?6,0,0,0,0,0,0,0,0,0,0)"
)


def slot_target(d: bytes) -> int:
    return struct.unpack_from("<I", d, SLOT_OFF)[0]


def main() -> int:
    argv = sys.argv[1:]
    check = "--check" in argv
    args = [a for a in argv if a != "--check"]
    if len(args) != 1:
        raise SystemExit(__doc__)
    path = Path(args[0])
    data = bytearray(path.read_bytes())

    slot = slot_target(data)
    end = data.find(b"\x00", TPL_OFF)
    tpl = data[TPL_OFF:end].decode("utf-8", "replace")
    status = (
        f"слот kind2 = {slot:#x} (нужно {KIND9:#x}); "
        f"шаблон {'col3=?2' if tpl == NEW_TPL else tpl[:40] + '…'}"
    )
    if check:
        print("статус:", status)
        tail = data[end + 1 : end + 4]
        print("хвост после шаблона (штатно нули):", tail.hex())
        return 0

    changed = False
    if slot != KIND9:
        st = struct.unpack_from("<I", data, SLOT_OFF)[0]
        if st not in (0x4A95E0,):  # разрешаем только со стокового значения
            raise SystemExit(f"неожиданный слот {st:#x} — прерывание")
        struct.pack_into("<I", data, SLOT_OFF, KIND9)
        changed = True

    if data.find(NEW_TPL.encode(), TPL_OFF, TPL_OFF + len(NEW_TPL)) != TPL_OFF:
        if tpl != OLD_TPL:
            raise SystemExit(f"неожиданный шаблон в RX: {tpl[:64]!r}")
        # замена точной длины: NEW на 2 байта длиннее OLD, терминирующий ноль
        # остаётся, плюс съедаем два следующих нуля — байты после НЕ сдвигаются.
        need = len(NEW_TPL) + 3  # NEW + ноль + 2 нуля запаса
        tail = data[TPL_OFF + len(OLD_TPL) + 1 : TPL_OFF + need]
        if tail != b"\x00" * (need - len(OLD_TPL) - 1):
            raise SystemExit(f"за шаблоном не нули: {tail.hex()}")
        data[TPL_OFF : TPL_OFF + need] = NEW_TPL.encode() + b"\x00\x00\x00"
        changed = True

    if not changed:
        print("всё уже пропатчено (слот kind9, шаблон col3=?2)")
        return 0
    path.write_bytes(bytes(data))
    print(f"{path}: слот kind2:={KIND9:#x}, RX-шаблон col3=?2 ({TPL_VA:#x})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
