#!/usr/bin/env python3
"""Метка USB-режима adb: `<adb>…</adb>` → `<adb>ADB</adb>` во всех языках.

Режим `FUN_00476bc0(mode>=2)` — чисто adb-гаджет (idVendor 18D1, idProduct 0D02,
`functions=adb`), стоковая метка «Dock» вводит в заблуждение. Метка лежит в
`usr/resource/str/<lang>/sys_set.ini` (UTF-16) по ключу `<adb>`. Правка ресурса,
не бинаря; выполняется на этапе `make.sh build` (иначе `unpack` откатит).

Идемпотентно, `--check`.

    python3 tools/patch_usb_label.py [--tree fw/SYSTEM] [--check]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

LABEL = "ADB"
RE_ADB = re.compile(r"<adb>(.*?)</adb>", re.S)


def decode(raw: bytes) -> tuple[str, bytes]:
    """Возвращает (текст, BOM). Поддерживает utf-16 LE/BE и utf-8."""
    if raw[:2] == b"\xff\xfe":
        return raw[2:].decode("utf-16-le"), b"\xff\xfe"
    if raw[:2] == b"\xfe\xff":
        return raw[2:].decode("utf-16-be"), b"\xfe\xff"
    return raw.decode("utf-8"), b""


def main() -> int:
    argv = sys.argv[1:]
    check = "--check" in argv
    tree = Path("fw/SYSTEM")
    if "--tree" in argv:
        tree = Path(argv[argv.index("--tree") + 1])

    files = sorted((tree / "usr/resource/str").glob("*/sys_set.ini"))
    if not files:
        raise SystemExit(f"не найдено sys_set.ini в {tree}/usr/resource/str")

    changed = 0
    for f in files:
        raw = f.read_bytes()
        text, bom = decode(raw)
        new = RE_ADB.sub(f"<adb>{LABEL}</adb>", text)
        if new == text:
            continue
        changed += 1
        if check:
            cur = RE_ADB.search(text)
            print(f"{f.parent.name}: <adb>={cur.group(1) if cur else '?'} -> {LABEL}")
            continue
        f.write_bytes(bom + new.encode("utf-16-le" if bom == b"\xff\xfe"
                                       else "utf-16-be" if bom == b"\xfe\xff" else "utf-8"))

    if check:
        print(f"{'нужна правка' if changed else 'ok'}: {changed} файл(ов) из {len(files)}")
        return 0
    print(f"метка USB-режима adb -> '{LABEL}': обновлено {changed} из {len(files)} файлов")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
