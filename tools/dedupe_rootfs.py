#!/usr/bin/env python3
"""Схлопывание одинаковых файлов rootfs в hardlink'и (экономия места в образе).

Зачем: rootfs содержит побайтовые дубликаты (`libFLAC.so`+`.8`,
`libmp3lame.so`+`.0`, `sudo`+`sudoedit`, `aplay`+`arecord`, `certificate.png`×2).
UBIFS хранит hardlink'и одной копией, поэтому образ уменьшается примерно на 1.6 МБ.
Это важно: апдейтер плеера виснет, если SYSTEM.UBI вырастает до размера оригинала.

Идемпотентно. Запускается автоматически в `tools/make.sh build`.

    python3 tools/dedupe_rootfs.py <каталог rootfs>
"""
from __future__ import annotations

import hashlib
import sys
from collections import defaultdict
from pathlib import Path


def digest(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    root = Path(sys.argv[1])
    by_size: dict[int, list[Path]] = defaultdict(list)
    for p in root.rglob("*"):
        if p.is_symlink() or not p.is_file():
            continue
        st = p.stat()
        if st.st_size < 4096 or st.st_nlink > 1:
            continue
        by_size[st.st_size].append(p)

    saved = 0
    for size, files in by_size.items():
        if len(files) < 2:
            continue
        by_hash: dict[str, Path] = {}
        for f in files:
            d = digest(f)
            if d in by_hash:
                keep = by_hash[d]
                f.unlink()
                f.hardlink_to(keep)
                saved += size
                print(f"  hardlink {f} -> {keep}")
            else:
                by_hash[d] = f
    print(f"сэкономлено {saved} байт")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
