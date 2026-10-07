#!/usr/bin/env python3
"""D12-lite: kind5-шаблон кэша (VA 0x9ba000) с col2=name → album, БЕЗ GROUP BY.
Изолирует причину ломки diag8: смена колонок против GROUP BY-подзапроса.
Строка короче стока (select rowid -> select min(rowid) убран) — в файле не трогаем
сток (padding остаётся), ссылка lui/addiu переводится на RX-копию.
    python3 tools/exp_kind5_album_lite.py <hiby_player> [--check]
"""
from __future__ import annotations
import hashlib, struct, sys
from pathlib import Path

VTO = 0x400000
STR_VA = 0x9BA000
STR_OFF = STR_VA - VTO
LUI_VA  = 0x708DFC
ADDIU_VA = 0x708E08
RX_VA = 0xA7E800
RX_OFF = RX_VA - VTO
PHDR_FILESZ = 0x67E370; PHDR_NEW = 0x67F000

NEW = ("INSERT INTO %s%d SELECT id,path,album,album,artist,genre,year,dis_id,"
       "ck_id,has_child_file,begin_time,end_time,cue_id,character,size,"
       "sample_rate,bit_rate,bit,channel,format,quality,album_pic_path,"
       "lrc_path,track_gain,track_peak,ctime,mtime FROM MEDIA_TABLE WHERE"
       " rowid in(select rowid from MEDIA_TABLE WHERE artist like ?1"
       " AND has_child_file = 0) ORDER BY character,name")

def find_phdr2(d):
    phoff=struct.unpack_from("<I",d,28)[0]; es=struct.unpack_from("<H",d,42)[0]; n=struct.unpack_from("<H",d,44)[0]
    for i in range(n):
        ph=phoff+i*es
        if struct.unpack_from("<I",d,ph)[0]==1 and struct.unpack_from("<I",d,ph+16)[0] in (PHDR_FILESZ,PHDR_NEW):
            return ph
    raise SystemExit("phdr2 нет")

def main()->int:
    check="--check" in sys.argv
    path=Path([a for a in sys.argv[1:] if a!="--check"][0]); d=bytearray(path.read_bytes())
    lui=struct.unpack_from("<I",d,LUI_VA-VTO)[0]; adi=struct.unpack_from("<I",d,ADDIU_VA-VTO)[0]
    rx=d[RX_OFF:RX_OFF+len(NEW)+2]
    if check:
        cur=None
        if (lui>>26)==15 and (adi>>26)==9:
            hi=lui&0xFFFF; lo=adi&0xFFFF
            lo=lo-0x10000 if lo>=0x8000 else lo
            cur=(hi<<16)+lo
        print(f"ref: lui imm={hi if (lui>>26)==15 else '?'} addiu imm={lo if (adi>>26)==9 else '?'} → {cur:#x} ({'RX' if cur==RX_VA else 'сток/иное' if cur==STR_VA else '?'})")
        print("RX-начало:",rx[:30])
        return 0
    stock=(lui&0xFFFF)==0x9C and (adi>>26)==9 and (adi&0xFFFF)==0xA000 and rx[:9]!=b"INSERT IN"
    if rx[:9]==b"INSERT IN":
        if not rx.startswith(NEW.encode(),"latin1" if False else 0):
            raise SystemExit("RX шаблон уже есть, но другой")
        print("уже пропатчено"); return 0
    if not stock: raise SystemExit("не сток")
    if any(rx): raise SystemExit("RX-зона не пуста")
    data=NEW.encode()+b"\0"
    d[RX_OFF:RX_OFF+len(data)]=data
    struct.pack_into("<I",d,LUI_VA-VTO,(lui&0xFFFF0000)|0xA8)
    struct.pack_into("<I",d,ADDIU_VA-VTO,(adi&0xFFFF0000)|0xE800)
    ph=find_phdr2(d); sz=struct.unpack_from("<I",d,ph+16)[0]
    if sz==PHDR_FILESZ:
        struct.pack_into("<I",d,ph+16,PHDR_NEW); struct.pack_into("<I",d,ph+20,PHDR_NEW)
        print("phdr2 → 0x67f000")
    path.write_bytes(bytes(d))
    print("записано",hashlib.sha256(bytes(d)).hexdigest()[:16])
    return 0
if __name__=="__main__": raise SystemExit(main())
