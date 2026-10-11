#!/usr/bin/env python3
"""NFC-normalize Unicode in the TempotecMusic library.

Fixes decomposed (NFD) sequences that some players render as two glyphs,
e.g. ``и`` + U+0306 instead of ``й``, ``е`` + U+0308 instead of ``ё``,
``А`` + U+0306 instead of ``Й``.  Applies to:

  * Vorbis comments of FLAC files,
  * ID3 frames of MP3 files,
  * file and directory names.

Only NFC is applied.  NFKC is intentionally NOT used: ``.fat_stage``
legitimately contains full-width substitutes (``： ？ ＊ ＂``) for characters
that FAT32 forbids.

Default = dry-run.  ``--apply`` writes tags and renames paths.

Usage:
    python3 normalize_unicode.py                 # dry-run, library/ + .fat_stage
    python3 normalize_unicode.py --apply
    python3 normalize_unicode.py --apply library
"""

from __future__ import annotations

import argparse
import os
import sys
import unicodedata

from mutagen import MutagenError

DEFAULT_ROOTS = ("library", ".fat_stage")
AUDIO_EXT = (".flac", ".mp3")


def combining(text: str) -> list[int]:
    """Codepoints of combining marks present in *text*."""
    return [ord(c) for c in text if unicodedata.combining(c)]


def is_nfc(text: str) -> bool:
    return text == unicodedata.normalize("NFC", text)


# --------------------------------------------------------------------------
# tags
# --------------------------------------------------------------------------


def tag_changes(path: str) -> list[tuple[str, str, str]]:
    """Return ``[(field, old, new)]`` for every non-NFC tag value."""
    out: list[tuple[str, str, str]] = []
    try:
        if path.lower().endswith(".flac"):
            from mutagen.flac import FLAC

            audio = FLAC(path)
            for key, values in audio.items():
                for value in values:
                    if not is_nfc(value):
                        out.append((key, value, unicodedata.normalize("NFC", value)))
        elif path.lower().endswith(".mp3"):
            from mutagen.id3 import ID3

            for frame in ID3(path).values():
                texts = getattr(frame, "text", None)
                if not isinstance(texts, list):
                    continue
                for value in texts:
                    if isinstance(value, str) and not is_nfc(value):
                        out.append(
                            (frame.FrameID, value, unicodedata.normalize("NFC", value))
                        )
    except (OSError, MutagenError) as exc:
        print(f"  ! cannot read {path}: {exc}", file=sys.stderr)
    return out


def apply_tags(path: str) -> None:
    if path.lower().endswith(".flac"):
        from mutagen.flac import FLAC

        audio = FLAC(path)
        for key, values in list(audio.items()):
            audio[key] = [unicodedata.normalize("NFC", v) for v in values]
        audio.save()
    else:
        from mutagen.id3 import ID3

        tags = ID3(path)
        for frame in tags.values():
            texts = getattr(frame, "text", None)
            if isinstance(texts, list):
                frame.text = [
                    unicodedata.normalize("NFC", v) if isinstance(v, str) else v
                    for v in texts
                ]
        tags.save()


# --------------------------------------------------------------------------
# paths
# --------------------------------------------------------------------------


def path_plan(root: str) -> list[tuple[str, str]]:
    """Return ``[(old, new)]`` renames, deepest first (dirs after their files)."""
    plan: list[tuple[str, str]] = []
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        for name in filenames + dirnames:
            if is_nfc(name):
                continue
            old = os.path.join(dirpath, name)
            new = os.path.join(dirpath, unicodedata.normalize("NFC", name))
            plan.append((old, new))
    return plan


def apply_paths(plan: list[tuple[str, str]]) -> int:
    done = 0
    for old, new in plan:
        if os.path.exists(new):
            print(f"  ! target exists, skipped: {new}", file=sys.stderr)
            continue
        os.rename(old, new)
        done += 1
    return done


# --------------------------------------------------------------------------


def process(root: str, apply: bool) -> tuple[int, int, int]:
    """Return ``(files_with_tag_changes, tag_values, path_renames)``."""
    tag_files = 0
    tag_values = 0
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            if not name.lower().endswith(AUDIO_EXT):
                continue
            path = os.path.join(dirpath, name)
            changes = tag_changes(path)
            if not changes:
                continue
            tag_files += 1
            tag_values += len(changes)
            for field, old, new in changes:
                marks = " ".join(f"U+{c:04X}" for c in combining(old))
                print(f"  [{field}] {old!r} -> {new!r}   ({marks})")
                print(f"        {path}")
            if apply:
                apply_tags(path)

    plan = path_plan(root)
    for old, new in plan:
        print(f"  [path] {old} -> {new}")
    if apply:
        apply_paths(plan)
    return tag_files, tag_values, len(plan)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write changes")
    parser.add_argument(
        "roots", nargs="*", default=None, help="roots (default: library .fat_stage)"
    )
    args = parser.parse_args()
    roots = args.roots or list(DEFAULT_ROOTS)

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== NFC normalization ({mode}) ===")
    total_files = total_values = total_paths = 0
    for root in roots:
        if not os.path.isdir(root):
            print(f"skip missing root: {root}")
            continue
        print(f"--- {root}")
        files, values, paths = process(root, args.apply)
        print(f"    {files} file(s), {values} tag value(s), {paths} path(s)")
        total_files += files
        total_values += values
        total_paths += paths
    print(
        f"=== total: {total_files} file(s), {total_values} tag value(s), {total_paths} path(s) ==="
    )
    if not args.apply and (total_files or total_paths):
        print("dry-run: nothing written. Re-run with --apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
