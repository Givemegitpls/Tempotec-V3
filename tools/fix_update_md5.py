#!/usr/bin/env python3
"""Пересчитать md5 раздела rootfs в UPDATE.TXT образа прошивки.

UPDATE.TXT содержит два блока: kernel={...} и rootfs={...}; в каждом строка
`md5=<hex>`. После правки SYSTEM.UBI значение в rootfs нужно обновить, иначе
загрузчик/апдейтер откажется принимать прошивку.

Использование: python3 tools/fix_update_md5.py UPDATE.TXT SYSTEM.UBI
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path


def md5_of(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    update_txt, system_ubi = Path(sys.argv[1]), Path(sys.argv[2])
    text = update_txt.read_text()
    digest = md5_of(system_ubi)

    start = text.find("rootfs={")
    if start < 0:
        raise SystemExit(f"{update_txt}: не найден блок rootfs={{...}}")
    end = text.find("}", start)
    block = text[start:end]
    new_block, count = re.subn(
        r"(md5=)[0-9a-fA-F]{32}", lambda m: m.group(1) + digest, block, count=1
    )
    if count != 1:
        raise SystemExit(f"{update_txt}: в блоке rootfs не найдена строка md5=")
    update_txt.write_text(text[:start] + new_block + text[end:])
    print(f"md5 rootfs = {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
