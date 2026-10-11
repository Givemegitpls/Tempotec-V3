#!/usr/bin/env python3
"""Normalize artist / album-artist separators to ';' across TempotecMusic library.

Method:
  * Source of truth = multi-value lists `artists` / `albumartists` (correctly split
    by Picard). The old tag_fix.py regex-splitter is used only as a fallback and
    is guarded against known compound names (e.g. "Чиж & Co", "25/17").
  * Every canonical token is mapped through the tag_fix alias table so casing and
    known aliases stay stable; "Чёрная речка" is unified to "Chernaya Rechka".
  * All artist-family tags are set to the same `;`-joined canonical string.

Default = dry-run (report only). Pass --apply to write tags.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from mutagen.easyid3 import EasyID3
from mutagen.flac import FLAC

LIB = Path("/home/alex/TempotecMusic/library")
REPORT = Path("/tmp/opencode/artist_sep_report.json")

# ---- field families --------------------------------------------------------
FAM_ARTIST = ["artist", "artists", "artist_credit", "artists_credit", "artistsort", "artists_sort"]
FAM_ALBUM = [
    "albumartist", "album_artist", "album artist", "albumartists", "album_artists",
    "albumartist_credit", "albumartists_credit", "albumartistsort", "albumartists_sort",
]

# ---- canonicalization ------------------------------------------------------
ALIASES = {
    "SOFT PLAY": {"soft play", "slaves"},
    "Rain City Drive": {"rain city drive", "slaves"},
    "Slaves": {"slaves"},
    "Insane": {"insane", "slaves"},
    "Yabai The Maid": {"yabai the maid", "unfeeling"},
    "Yakui The Maid": {"yakui the maid"},
    "WOODJU": {"woodju"},
    "масло черного тмина": {"масло черного тмина", "maslo chernogo tmina"},
    # unify the two spellings of Чёрная речка into one
    "Chernaya Rechka": {"chernaya rechka", "чёрная речка", "черная речка"},
}
CANON = {"Woodju": "WOODJU", "Unfeeling": "Yabai The Maid", "DECO_27": "DECO*27"}

# fallback splitter (only used when a file lacks the multi-value list)
_KNOWN_COMPOUND = {"чиж & co", "25/17"}
SEP = re.compile(
    r"\s*(?:;|/|\bw/|&|\band\b|\bx\b|\bvs\.?\b|\bwith\b|\bfeat\.?\b|\bft\.?\b|,|\bп\.у\.)\s*",
    re.IGNORECASE,
)


def split_fallback(value) -> list[str]:
    if isinstance(value, list):
        value = ";".join(str(x) for x in value)
    s = str(value).strip()
    if s.lower() in _KNOWN_COMPOUND:
        return [s]
    out = []
    for p in SEP.split(s):
        p = p.strip(" \t.;:,-")
        p = re.sub(r"\s+(?:w|ft|feat|with)$", "", p, flags=re.IGNORECASE)
        if p and p.lower() not in ("w", "ft", "feat", "with"):
            out.append(p)
    return out


def canon_tokens(dirname: str, tokens: list[str]) -> list[str]:
    alias = ALIASES.get(dirname, set())
    low = dirname.lower()
    out = []
    for t in tokens:
        t = t.strip()
        if not t:
            continue
        tl = t.lower()
        if dirname == "Dave Ruda" and tl == "slaves":
            out.append("Insane")
        elif tl in alias or tl == low:
            out.append(dirname)
        else:
            out.append(t)
    seen = set()
    res = []
    for t in out:
        if t.lower() not in seen:
            seen.add(t.lower())
            res.append(t)
    return res


def tokens_from(tags: dict, listkey: str, fallbackkey: str) -> list[str]:
    v = tags.get(listkey)
    if v:
        return [str(x).strip() for x in v if str(x).strip()]
    raw = tags.get(fallbackkey)
    if raw:
        return split_fallback(raw[0] if isinstance(raw, list) else raw)
    return []


def read_tags(p: Path) -> dict:
    if p.suffix.lower() == ".flac":
        return {k: list(v) for k, v in FLAC(p).items()}
    return {k: list(v) for k, v in EasyID3(p).items()}


def load(p: Path):
    return FLAC(p) if p.suffix.lower() == ".flac" else EasyID3(p)


# ---- flags -----------------------------------------------------------------
FLAG_RE = re.compile(r"[&/+]|\bfeat\b|\bft\b|\bw/\b|\bx\b|\bband\b|\bvs\b", re.IGNORECASE)


def flag_tokens(tokens: list[str]) -> list[str]:
    out = []
    for t in tokens:
        if FLAG_RE.search(t) or len(t) <= 2 or t.isdigit():
            out.append(t)
    return out


def main() -> None:
    apply = "--apply" in sys.argv
    report = {}
    changed_files = 0
    field_counter = Counter()
    flagged = Counter()
    artist_before_after = []
    album_before_after = defaultdict(set)  # folder -> {(before),(after)}

    for p in sorted(LIB.rglob("*")):
        if p.suffix.lower() not in (".flac", ".mp3") or "_conflicts" in p.parts:
            continue
        rel = p.relative_to(LIB)
        if len(rel.parts) < 2:
            continue
        dirname = rel.parts[0]
        try:
            tags = read_tags(p)
        except Exception as exc:  # noqa: BLE001
            print("ERR", p, exc)
            continue

        a_tokens = canon_tokens(dirname, tokens_from(tags, "artists", "artist"))
        al_tokens = canon_tokens(dirname, tokens_from(tags, "albumartists", "albumartist"))
        ja = ";".join(a_tokens)
        ja_album = ";".join(al_tokens)

        changes = {}
        for k in FAM_ARTIST:
            if k in tags or k == "artist":
                cur = ";".join(tags[k]) if isinstance(tags.get(k), list) else tags.get(k)
                if cur != ja:
                    changes[k] = {"before": cur, "after": ja}
        for k in FAM_ALBUM:
            if k in tags or k == "albumartist":
                cur = ";".join(tags[k]) if isinstance(tags.get(k), list) else tags.get(k)
                if cur != ja_album:
                    changes[k] = {"before": cur, "after": ja_album}

        if not changes:
            continue
        changed_files += 1
        for k in changes:
            field_counter[k] += 1
        if "artist" in changes or "artists" in changes:
            artist_before_after.append((str(rel), changes.get("artists", changes.get("artist"))))
        album_before_after[dirname].add((ja_album,))
        for t in flag_tokens(a_tokens + al_tokens):
            flagged[t] += 1
        report[str(rel)] = changes

        if apply:
            obj = load(p)
            for k, ch in changes.items():
                obj[k] = ch["after"]
            obj.save()

    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(f"files changed: {changed_files}")
    print("fields changed:", dict(field_counter))
    print("report:", REPORT)
    print("---- flagged canonical tokens (manual review; expected legit compounds) ----")
    for t, n in flagged.most_common():
        print(f"  {n:4d}  {t!r}")
    if apply:
        print("APPLIED")


if __name__ == "__main__":
    main()
