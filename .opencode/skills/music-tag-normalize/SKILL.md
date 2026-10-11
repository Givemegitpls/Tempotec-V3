---
name: music-tag-normalize
description: "Use when normalizing or repairing tags or names in the TempotecMusic library (library/): Unicode NFC (decomposed 'й'/'ё' rendering as two glyphs, NFD inherited from vfat/Windows/qobuz), multi-artist separators to ';', compound names like 'Чиж & Co' / '25/17' / 'X Ambassadors', beets/tag_fix splitter bugs, alias/canon unification, auditing artist tags. Trigger words: теги артистов, разделители, album artist, п.у., feat, tag_fix, normalize tags, й в два символа, шапочка справа, NFD, NFC, Unicode normalization."
---

# Normalizing artist / album artist tags (TempotecMusic)

Project-specific workflow for `/home/alex/TempotecMusic/library` (FLAC + MP3,
tags written by beets + `tag_fix.py` + MusicBrainz Picard leftovers).

> Скрипты и скилл теперь лежат и в репозитории прошивки
> (`tempotec v3/.opencode/skills/music-tag-normalize/`) — для самодостаточности.
> Библиотека остаётся в `~/TempotecMusic/library`; при запуске из другого каталога
> указывай корни явно, напр.
> `python3 normalize_unicode.py --apply ~/TempotecMusic/library`.

Bundled script: `normalize_artist_sep.py` (same dir). Default = **dry-run**;
`--apply` writes tags.

## Core principle

**The multi-value lists `artists` / `albumartists` are the source of truth.**
Picard split them correctly. Never re-split those list elements.

`tag_fix.py` (in `/tmp/opencode`) used an aggressive regex splitter that breaks
compound names — **do NOT re-run `tag_fix.py`**, it re-introduces:
- `Чиж & Co` → `Чиж;Co`
- `25/17` → `25;17`
- `X Ambassadors` → `Ambassadors`

## Workflow

1. Snapshot current tags (before):
   ```bash
   python3 - <<'PY'
   import os, json
   from mutagen.flac import FLAC
   from mutagen.easyid3 import EasyID3
   def tags(p):
       return ({k:list(v) for k,v in FLAC(p).items()} if p.lower().endswith(".flac")
               else {k:list(v) for k,v in EasyID3(p).items()})
   out={}
   for dp,_,fs in os.walk("library"):
       for f in fs:
           if f.lower().endswith((".flac",".mp3")):
               p=os.path.join(dp,f); out[p]=tags(p)
   json.dump(out, open("/tmp/opencode/tagdump.json","w"), ensure_ascii=False)
   PY
   ```
2. Dry-run the normalizer and read the report:
   ```bash
   python3 .opencode/skills/music-tag-normalize/normalize_artist_sep.py
   ```
   Report goes to `/tmp/opencode/artist_sep_report.json`.
3. Review flagged tokens (see "Audit" below) + the `artist` / `albumartist` diffs.
4. Apply:
   ```bash
   python3 .opencode/skills/music-tag-normalize/normalize_artist_sep.py --apply
   ```
5. Verify (see "Verification").

## What the script does

- `artist`-family: `artist`, `artists`, `artist_credit`, `artists_credit`,
  `artistsort`, `artists_sort` → all set to one `;`-joined canonical string.
- `albumartist`-family: `albumartist`, `album_artist`, `album artist`,
  `albumartists`, `album_artists`, `albumartist_credit`, `albumartists_credit`,
  `albumartistsort`, `albumartists_sort` → same, derived from `albumartists`
  (so collabs become `Anacondaz;Horus`, `Brandenburg;Carlos Perón`).
- Canonicalization uses the tag_fix alias table (dir-name based) plus the extra
  alias `Чёрная речка → Chernaya Rechka` (one artist, one spelling).
- Sort tags are set to the display value (proper "Last, First" sort is
  intentionally lost).
- `title` / `album` are never touched — they legitimately contain `(feat. …)`.

## Audit — catching compound-name cases

The script flags any final token that contains a separator (`&`, `/`, `+`,
`feat`, `ft`, `w/`, ` x `) or is ≤2 chars / numeric. Eyeball that list.

Verified verdicts:
| Token | Verdict |
|---|---|
| `Чиж & Co` | ONE artist (keep) |
| `25/17` | ONE artist (keep) |
| `X Ambassadors` | ONE artist (keep) |
| `KAT x Aku P` | collab → split `KAT;Aku P` |
| `A-Sid, Maestro` | sort-inversion of ONE artist `Maestro A-Sid` |
| `ACHTZIG TAUSEND MILLIONEN` | real project (K.I.Z+Casper+Kraftklub) |
| `Ghost Creek` | real artist (Little People = remixer) |

For new ambiguous names, delegate verification to a `general` subagent (web:
MusicBrainz / Discogs / Bandcamp / Wikipedia). `websearch` may 403 here — use
`webfetch` on direct URLs or `https://html.duckduckgo.com/html/?q=...`.

## Unicode NFC normalization (decomposed `й` / `ё`)

Symptom: a player shows `й` as two glyphs, the breve sitting to the *right* of
`и` (same for `ё`, `Й`, `Ё`). Cause: the value is NFD — `и` (U+0438) +
combining breve (U+0306) instead of precomposed `й` (U+0439). Players that do
not run NFC normalization render the mark separately. Origin here: names/tags
inherited from the vfat card (created on Windows) and from qobuz downloads —
see `backup/` (16 NFD names, 17 NFD tag values; the rebuilt `library/` was
already clean except one album).

Bundled script: `normalize_unicode.py` (same dir). Default = **dry-run**;
`--apply` writes tags and renames paths. Roots default to `library .fat_stage`.

```bash
python3 .opencode/skills/music-tag-normalize/normalize_unicode.py            # dry-run
python3 .opencode/skills/music-tag-normalize/normalize_unicode.py --apply library
python3 .opencode/skills/music-tag-normalize/normalize_unicode.py --apply .fat_stage
```

What it does: NFC-normalizes every Vorbis comment (FLAC), every ID3 text frame
(MP3), and every file / directory name under each root. NFC composes all
canonically decomposable Cyrillic pairs in one pass — `е+U+0308`→`ё`,
`И+U+0306`→`Й`, `Е+U+0308`→`Ё`, `і+U+0308`→`ї`, `у+U+0306`→`ў` — so no
per-letter table is needed. NFKC is deliberately **not** used: `.fat_stage`
legitimately holds full-width substitutes (`： ？ ＊ ＂`) for FAT32-forbidden
chars. Note: a few sequences have no precomposed form (e.g. `А`+U+0301) and stay
decomposed — that is correct, not a bug.

Gotcha — `.fat_stage` is a hardlink mirror: apply to `library` **first**, then
to `.fat_stage` (mutagen can rewrite the tag block, and `make_fat_tree.py`
refuses to run while `.fat_stage` exists). After fixing, re-run
`make_fat_tree.py` (after `rm -rf .fat_stage`) if you prefer a full rebuild over
the targeted rename.

Verification:

```bash
python3 .opencode/skills/music-tag-normalize/normalize_unicode.py   # expect 0 everywhere
```

## Verification

```bash
# no п.у. / feat / ' & ' left in artist-family fields (exception: "Чиж & Co")
python3 - <<'PY'
import json, re
d=json.load(open("/tmp/opencode/tagdump_after.json"))
AF=["artist","artists","artist_credit","artists_credit","artistsort","artists_sort",
    "albumartist","album_artist","album artist","albumartists","album_artists",
    "albumartist_credit","albumartists_credit","albumartistsort","albumartists_sort"]
bad=[(p,k,s) for p,t in d.items() for k in AF for s in t.get(k,[])
     if re.search(r"п\.у\.|\bfeat\b|\bft\b|\bfeaturing\b|\bw/", s, re.I)
     or (" & " in s and "Чиж & Co" not in s)]
print("bad:", len(bad), bad[:10])
PY

# audio still decodes
flac -t "library/<Artist>/<Album>/<track>.flac"
```

## Notes / gotchas

- `_conflicts/` is excluded by the script.
- Some releases inherit odd Picard `albumartists` (e.g. `Kraftklub/Geboren weil
  du lebst` → `ACHTZIG TAUSEND MILLIONEN`, `Little People/Night Fog` →
  `Ghost Creek`). These are real credits; folder names stay unchanged.
- Rollback: restore fields from the "before" snapshot `/tmp/opencode/tagdump.json`.
