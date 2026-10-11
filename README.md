**English** | [Русский](README.ru.md)

# Tempotec V3 Analog — modified firmware

Unofficial firmware for the **Tempotec V3 Analog** player: fixes the annoyances of
the stock interface and adds missing features.

## What the mod does

Comparison of the current version against the stock image.

**Sections and appearance**

- **The "Album Artist" tab now has an album level.** Previously the category showed
  a flat track list right away; now, like in "Artists": artist → their albums → tracks.
- **Album covers in the "Artists" and "Album Artist" tabs.** Previously there were no
  covers in these lists at all.
- **"Album list ⇄ track list" toggle.** In the "Artists" and "Album Artists" tabs, a
  button in the top bar switches the list view between "tracks" and "albums" modes.
- **An "ADB" item in the "USB device mode" menu.** A third connection mode besides
  Audio and Storage: brings up ADB on the player.

**Search**

- **Russian names are searchable with the strip.** The first letter of a name is
  transliterated to Latin (Кино → `K`, Дайте танк → `D`, Вольный Путь → `V`); the
  strip itself is unchanged from stock (A–Z and "#").

**Library and content**

- **Collaborative artists are split apart.** The tag `X;Y` is split by `;` into any
  number of artists — each co-artist appears separately in the list, and the
  collaborative album appears under each of them. Applies to both the artist and the
  album artist tag.
- **An album opened via an artist shows all tracks**, including collaborative
  recordings (`X feat. Y`) — previously part of an album could be missing.

**Playback**

- **Reversible shuffle.** "Back → forward" returns exactly the same track, with no
  repeats until the end of the list. The "in order", "repeat list" and "repeat track"
  modes are unchanged.

## Installation

1. Copy the firmware image to the **root of the SD card**, strictly under the name
   **`v3_analog.upt`** (the player looks for a file with exactly this name; the
   ready-made image is at `out/v3_analog.upt`).
2. Insert the card into the player.
3. On the player: **Settings → "Software update"** → select the firmware file.
4. After flashing, run **"Update library"** once — the firmware will set the letters,
   split collaborative artists and rebuild the lists by itself (no computer needed).

**Rollback:** flash the stock `v3_analog.upt` (or a known-good build from `backup/`)
the same way.

## Building

**Requirements:** Linux, `docker` installed, and the stock `v3_analog.upt` firmware
version `1.3` in the project root. Nothing else needs to be installed on the system —
all the tools live in the docker image.

```
docker build -t tempotec-fw-tools docker      # once
./tools/build_all.sh                          # build "from scratch" from stock
```

The resulting image will appear at `out/v3_analog.upt`. The script unpacks the stock
image, applies the whole chain of binary patches, runs the checks and builds the image.

Verification before flashing:

```
python3 tools/verify_build.py fw/SYSTEM/usr/bin/hiby_player --image out/v3_analog.upt
```

## Technical details

This is a vibe-coded project. Clone the repo and point an LLM at it.
