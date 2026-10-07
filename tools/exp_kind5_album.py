#!/usr/bin/env python3
"""D12: «альбомы артиста» = kind5-кэш с альбомным наполнением.

Штатный источник (слот 0xaae114 = FUN_004a9dc0, kind5=songs) работает:
фильтр по артисту, обложки по path. НО title-колонка показывает трек-имя.
Правка: шаблон INSERT кэша (VA 0x9ba000) заменить на вариант
  ... SELECT id,path,album,album,... WHERE rowid in (select min(rowid) ...
  WHERE artist like ?1 ... group by album) ORDER BY character,name
(name=колонка-тайтла -> имя альбома; одна строка на альбом).
Строка переносится в RX-зазор (0xa7e800), ссылки lui/addiu в .text (0x708dfc,
0x708e08) переписываются. phdr2 расширяется.

Быстро:
  python3 tools/exp_kind5_album.py <hiby_player> [--check]
"""
from __future__ import annotations
import hashlib, struct, sys
from pathlib import Path

VTO = 0x400000
STR_VA = 0x9BA000          # старый шаблон (kind5, artist-like)
STR_OFF = STR_VA - VTO     # 0x5ba000
LUI_VA  = 0x708DFC         # lui $a1, 0x9c
LUI_OFF = LUI_VA - VTO
ADDIU_VA = 0x708E08        # addiu $a1, $a1, -0x6000
ADDIU_OFF = ADDIU_VA - VTO
RX_VA = 0xA7E800           # свободный RX-зазор
RX_OFF = RX_VA - VTO
PHDR_FILESZ = 0x67E370; PHDR_NEW = 0x67F000

NEW = ("INSERT INTO %s%d SELECT id,path,album,album,artist,genre,year,dis_id,"
       "ck_id,has_child_file,begin_time,end_time,cue_id,character,size,"
       "sample_rate,bit_rate,bit,channel,format,quality,album_pic_path,"
       "lrc_path,track_gain,track_peak,ctime,mtime FROM MEDIA_TABLE WHERE"
       " rowid in(select min(rowid) from MEDIA_TABLE WHERE artist like ?1"
       " AND has_child_file = 0 group by album) ORDER BY character,name")

def find_phdr2(d):
    phoff=struct.unpack_from("<I",d,28)[0]; es=struct.unpack_from("<H",d,42)[0]; n=struct.unpack_from("<H",d,44)[0]
    for i in range(n):
        ph=phoff+i*es
        if struct.unpack_from("<I",d,ph)[0]==1 and struct.unpack_from("<I",d,ph+4)[0]<=4 and struct.unpack_from("<I",d,ph+16)[0] in (PHDR_FILESZ,PHDR_NEW):
            return ph
    raise SystemExit("phdr2 нет")

def main() -> int:
    check="--check" in sys.argv
    path=Path(sys.argv[-1]); d=bytearray(path.read_bytes())
    old=bytes(d[STR_OFF:STR_OFF+len(NEW.split("SELECT")[0])])
    lui=struct.unpack_from("<I",d,LUI_OFF)[0]
    addiu=struct.unpack_from("<I",d,ADDIU_OFF)[0]
    new_first=bytes(d[RX_OFF:RX_OFF+12])
    if check:
        hi=(lui>>16)&0xFFFF if (lui>>26)==15 else None
        if (addiu>>26)==9 and ((addiu>>21)&31)==((lui>>16)&31):
            cur=(hi<<16)+(addiu&0xFFFF if (addiu&0xFFFF)<0x8000 else (addiu&0xFFFF)-0x10000)
        print(f"ref addiu {ADDIU_VA:#x}: {addiu:#010x} -> строка {cur:#x} ({'патч' if cur==RX_VA else 'сток/иное'})")
        print("RX-начало:", new_first[:20])
        print("phdr2:", hex(struct.unpack_from("<I",d,find_phdr2(d)+16)[0]))
        return 0
    # сток?
    stock_lui  = struct.unpack_from("<I",d,LUI_OFF)[0] & 0xFFFF == 0x9C
    stock_addiu= (struct.unpack_from("<I",d,ADDIU_OFF)[0] & 0xFFFF) == 0xA000
    if not (stock_lui and stock_addiu or new_first.startswith(b"INSERT INTO %s%d SELECT id,path,album")):
        raise SystemExit("не сток и не D12")
    if new_first.startswith(b"INSERT INTO %s%d SELECT id,path,album"):
        print("уже пропатчено"); return 0
    if any(d[RX_OFF:RX_OFF+len(NEW)+2]):
        raise SystemExit("RX-зазор не пуст")
    data=NEW.encode()+b"\0"
    d[RX_OFF:RX_OFF+len(data)] = data
    # lui $a1, 0x9c -> 0xa8 ; addiu -0x6000 -> -0x1800 (0xa8_0000 - 0x1800 = 0xa7e800)
    assert (lui>>26)==15 and (lui&0xFFFF)==0x9C
    struct.pack_into("<I",d,LUI_OFF,(lui & 0xFFFF0000) | 0xA8)
    assert (addiu>>26)==9 and (addiu&0xFFFF)==0xA000
    struct.pack_into("<I",d,ADDIU_OFF,(addiu & 0xFFFF0000) | 0xE800)
    ph=find_phdr2(d); sz=struct.unpack_from("<I",d,ph+16)[0]
    if sz==PHDR_FILESZ:
        struct.pack_into("<I",d,ph+16,PHDR_NEW); struct.pack_into("<I",d,ph+20,PHDR_NEW)
        print("phdr2 -> 0x67f000")
    else:
        print("phdr2 ок")
    path.write_bytes(bytes(d)); print("записано", hashlib.sha256(bytes(d)).hexdigest()[:16])
    return 0
if __name__=="__main__": raise SystemExit(main())
