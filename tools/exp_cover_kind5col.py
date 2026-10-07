#!/usr/bin/env python3
"""Эксперимент covR5: источник kind5 (0xaae114 := 0x4a9dc0) + RX-шаблон
kind5-кэша с col2 (name) = album.

Обоснование (2026-10-04):
- канон по живым тестам: tv_title строки читает rec+0x20c = col2;
  путь поиска обложки — cover+0x114 = col1 (путь).
  kind5 (D9): col1=путь трека (обложки ✔), col2=название трека (тайтлы ✗).
  kind9: col2=имя альбома (тайтлы ✔), но kind9-поток cover-парсер не
  активирует (cовR4: одна обложка на список).
- решение: kind5-шаблон с заменой name → album в SELECT:
    SELECT id,path,album,album,artist,… ORDER BY character,name
  → тайтлы = имя альбома, обложки = per-row путь (kind5-механика ✔).
- kind9 не используется (медленный/виснущий по D10/D11-опытам).

Ссылки на kind5-шаблон (сток): lui 0x708dfc (hi 0x9c), addiu 0x708e08
(imm -0x6000) → на RX 0xa7e800 (hi 0xa8, imm -0x1800). Слот kind2
0xaae114 := 0x4a9dc0 (штатный kind5-кэш треков автора).

Состав до применения: release (4429784b) + exp_album_view + exp_flags_view21
(w4=1,w5=1; w13 НЕ трогать). Пач_player/patch_sql уже входят в релиз.

Использование:
    python3 tools/exp_cover_kind5col.py <hiby_player> [--check]
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

VTO = 0x400000
SLOT_VA = 0xAAE114
SLOT_OFF = SLOT_VA - VTO
KIND5 = 0x4A9DC0
TPL_VA = 0xA7E800
TPL_OFF = TPL_VA - VTO

OLD_TPL = (
    "INSERT INTO %s%d SELECT id,path,name,album,artist,genre,year,dis_id,ck_id,"
    "has_child_file,begin_time,end_time,cue_id,character,size,sample_rate,"
    "bit_rate,bit,channel,format,quality,album_pic_path,lrc_path,track_gain,"
    "track_peak,ctime,mtime FROM MEDIA_TABLE WHERE rowid in(select rowid from "
    "MEDIA_TABLE WHERE artist like ? AND has_child_file = 0) ORDER BY character,name"
)
NEW_TPL = (
    "INSERT INTO %s%d SELECT id,path,album,album,artist,genre,year,dis_id,ck_id,"
    "has_child_file,begin_time,end_time,cue_id,character,size,sample_rate,"
    "bit_rate,bit,channel,format,quality,album_pic_path,lrc_path,track_gain,"
    "track_peak,ctime,mtime FROM MEDIA_TABLE WHERE rowid in(SELECT min(rowid) "
    "FROM MEDIA_TABLE WHERE artist like ? AND has_child_file = 0 GROUP BY album) "
    "ORDER BY character,name"
)

REFS = [(0x708DFC, 0x708E08)]
OLD_LUI_HI = 0x9C
OLD_ADDIU_IMM = 0xA000
# imm -0x6000 = 0xA000 в младших 16 бит
NEW_LUI_HI = 0xA8
NEW_ADDIU_IMM = 0xE800  # -0x1800


def main() -> int:
    argv = sys.argv[1:]
    check = "--check" in argv
    args = [a for a in argv if a != "--check"]
    if len(args) != 1:
        raise SystemExit(__doc__)
    path = Path(args[0])
    data = bytearray(path.read_bytes())

    slot = struct.unpack_from("<I", data, SLOT_OFF)[0]
    end = data.find(b"\x00", TPL_OFF)
    tpl = data[TPL_OFF:end].decode("utf-8", "replace")

    if check:
        st = "kind5" if slot == KIND5 else hex(slot)
        t = "col2=album" if tpl == NEW_TPL else (tpl[:44] + "…" if tpl else "нет шаблона")
        lui = struct.unpack_from("<I", data, REFS[0][0] - VTO)[0]
        adi = struct.unpack_from("<I", data, REFS[0][1] - VTO)[0]
        print(f"статус: слот={st}; шаблон={t}; ref lui={lui & 0xFFFF:#06x} imm={adi & 0xFFFF:#06x}")
        return 0

    changed = False
    if slot != KIND5:
        if slot != 0x4A95E0:
            raise SystemExit(f"неожиданный слот {slot:#x} — прерывание")
        struct.pack_into("<I", data, SLOT_OFF, KIND5)
        changed = True
        print(f"слот kind2 {SLOT_VA:#x}:={KIND5:#x}")

    # шаблон в RX: если пусто — пишем с нуля; иначе требуем OLD
    if not data.startswith(NEW_TPL.encode(), TPL_OFF):
        if tpl not in ("", OLD_TPL):
            raise SystemExit(f"неожиданный шаблон в RX: {tpl[:64]!r}")
        # точная длина: NEW + ноль. Требуем, чтобы зона [конец OLD … конец NEW]
        # была нулями — тогда замена не сдвигает ни одного байта файла.
        need = len(NEW_TPL) + 1
        if tpl:
            tail = data[TPL_OFF + len(OLD_TPL) + 1 : TPL_OFF + need]
        else:
            tail = data[TPL_OFF : TPL_OFF + need]
        if not all(b == 0 for b in tail):
            raise SystemExit(f"запас не нулевой: {tail[:16].hex()}")
        data[TPL_OFF : TPL_OFF + need] = NEW_TPL.encode() + b"\x00"
        print(f"RX-шаблон {TPL_VA:#x}: записан ({len(NEW_TPL)} б, kind5+GROUP-BY, col2=album)")
        changed = True

    for lui_va, adi_va in REFS:
        lui_off = lui_va - VTO
        adi_off = adi_va - VTO
        wl = struct.unpack_from("<I", data, lui_off)[0]
        wa = struct.unpack_from("<I", data, adi_off)[0]
        if (wl & 0xFFFF) == NEW_LUI_HI and (wa & 0xFFFF) == NEW_ADDIU_IMM:
            print(f"  [skip] ref {lui_va:#x}: уже на RX")
            continue
        assert (wl & 0xFFFF) == OLD_LUI_HI, f"lui {lui_va:#x}: {wl & 0xFFFF:#x}"
        assert (wa & 0xFFFF) == OLD_ADDIU_IMM, f"addiu {adi_va:#x}: {wa & 0xFFFF:#x}"
        data[adi_off] = NEW_ADDIU_IMM & 0xFF
        data[adi_off + 1] = (NEW_ADDIU_IMM >> 8) & 0xFF
        data[lui_off] = NEW_LUI_HI & 0xFF
        data[lui_off + 1] = (NEW_LUI_HI >> 8) & 0xFF
        print(f"  [ok] ref {lui_va:#x}/{adi_va:#x} → {TPL_VA:#x}")
        changed = True

    if not changed:
        print("всё уже пропатчено")
        return 0
    path.write_bytes(bytes(data))
    print(f"{path}: записано")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
