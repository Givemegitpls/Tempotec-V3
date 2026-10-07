---
name: tempotec-v3-analog
description: "Use for Tempotec V3 Analog firmware work specifically: known base binary md5, patch chain for album covers in Artists, album_artist filter, Cyrillic alphabet search, media DB scripts, ADB iteration. Trigger keywords: v3_analog.upt, Tempotec V3, hiby_player 4429784b, v3_analog_coverid, exp_cover_kind9id, exp_albums_by_album_artist, list_tb_, clear_list_cache."
---

# Tempotec V3 Analog — конкретика

Общий метод — скилл `hiby-firmware-patching`; глубина — `reference/NOTES-v3.md`.

## Базы и адреса

- Эталонный бинарь (база всех патчей): md5 `4429784bfb605f8743b15e4e06660d01`
  (`/usr/bin/hiby_player`, MIPS32 LE, `VA = file_offset + 0x400000`).
- RX-запас: `0x67e370..0x67f000` (VA `0xa7e370..0xa80000`); phdr2 `filesz/memsz → 0x67f000`.
- Свободный хвост `.rodata`: `0x93f610..0x93fce0`.
- Таблица SQL-строк: база `0x9b7730`, шаг 4. Таблица видов: `0x95e770`, запись `0x3c`.
- Слот источника вида: `0xABE114` (file `0x6ae114`).

## Релиз с фичами

- Бинарь md5 `0c8d1ef10c1d84219f50418df6226ad7`.
- Образ `out/v3_analog_shuffle.upt` (ISO `115d304bd4a223d008ad49aba96c11f3`,
  UBI `92121788547445030a6e2097406a3159`).
- Предыдущий релиз (без shuffle): бинарь `60df95e4e16f978a0f3b8e1958c87810`,
  `out/v3_analog_coverid.upt`.

## Порядок патчей (важно)

```
база 4429784b
+ patch_player.py + patch_sql.py
+ exp_album_view.py            # вид-21 -> vg_listview_album
+ exp_flags_view21.py          # w4=1,w5=1 (поток обложек)
+ exp_coverpath_combo.py       # RX-шаблон INSERT + path, phdr2, источник пути
+ exp_cover_kind9col.py        # слот 0xABE114 := 0x4A9180, col3=?2
+ exp_cover_kind9id.py         # col0 = MEDIA_TABLE.id (обложка своего альбома)
+ exp_albums_by_album_artist.py # фильтр списка по album_artist (VA 0x9c284c)
+ exp_shuffle_linear.py        # обратимый shuffle (nop @ 0x42dd8c)
+ exp_shuffle_guard.py         # сброс состояния шафла при смене списка (хук @0xa7e370)
```

## Медиатека (не в образе)

```
adb pull /data/usrlocal_media.db work/device/media.db
python3 tools/examples/translit_db.py     work/device/media.db   # буквы + триггеры
python3 tools/examples/reorder_db.py      work/device/media.db   # порядок по character
python3 tools/examples/album_artist_db.py work/device/media.db   # Артисты = авторы альбомов
adb push work/device/media.db /data/usrlocal_media.db && adb shell 'sync; reboot'
```

Порядок `translit → reorder → translit` (reorder пересоздаёт таблицы и сносит триггеры).

Кэш списков после смены логики сбрасывать один раз:
`python3 tools/examples/clear_list_cache.py <db>` (чистит `list_tb_*` и `MANAGER_TABLE`,
медиатеку не трогает).

## Итерации на устройстве

```
adb push work/test/hiby_player.new /usr/bin/hiby_player
adb shell 'chmod 755 /usr/bin/hiby_player; sync; md5sum /usr/bin/hiby_player; reboot'
```
Канал adb живёт первые минуты после включения; при отвале `adb kill-server`.
Откат — релизный образ или ранее сохранённый `hiby_player.release`.

## Известные ограничения

- Артист, указанный только как feat. (не автор альбома), может иметь пустой список —
  источник фильтрует по `album_artist`; если появится пустой `album_artist`
  (сборники), вернуть `artist like ? OR album_artist like ?`.
- Кириллица в самой полоске не делается (стоковая `a_z.png` A–Z + `#`); поиск
  работает через транслит в колонке `character`.
