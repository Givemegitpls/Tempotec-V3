#!/usr/bin/env python3
"""D11: источник «альбомы артиста» = копия FUN_004a9dc0 (SONGS-вариант) с kind 5→9
(ALBUMS-вариант кэша), размещённая в RX-зазоре; слот 0xaae114 := копия.
Предназначен поверх release + patch_player + patch_sql + combo + album_view
(как exp_artist_filter, но вместо хука — скопированная функция)."""
from __future__ import annotations
import struct, sys, hashlib
from pathlib import Path

VTO=0x400000
SRC=0x4A9DC0; SRC_LEN=464
KIND_OFF=0x4A9EBC-SRC            # смещение `addiu $a0,$zero,5` внутри тела
DST=0xA7E370
SLOT_VA=0xAAE114; SLOT_OFF=SLOT_VA-VTO
PHDR_FILESZ=0x67E370; PHDR_NEW=0x67F000

def find_phdr2(d: bytes) -> int:
    phoff=struct.unpack_from("<I",d,28)[0]; entsz=struct.unpack_from("<H",d,42)[0]; n=struct.unpack_from("<H",d,44)[0]
    for i in range(n):
        ph=phoff+i*entsz
        if struct.unpack_from("<I",d,ph)[0]==1 and struct.unpack_from("<I",d,ph+4)[0]<=4 and struct.unpack_from("<I",d,ph+16)[0] in (PHDR_FILESZ,PHDR_NEW):
            return ph
    raise SystemExit("phdr2 не найден")

def main() -> int:
    check="--check" in sys.argv
    path=Path(sys.argv[-1])
    d=bytearray(path.read_bytes())
    slot=struct.unpack_from("<I",d,SLOT_OFF)[0]
    body_off=DST-VTO
    dst_word=struct.unpack_from("<I",d,body_off+KIND_OFF)[0]
    if check:
        print("слот:",hex(slot),"(stock 0x4a95e0 / D9 0x4a9dc0 / D11 копия)")
        print("kind-слово в копии:",hex(dst_word))
        print("phdr2:",hex(struct.unpack_from("<I",d,find_phdr2(d)+16)[0]))
        return 0
    if any(d[body_off:body_off+SRC_LEN]):
        if slot==DST and dst_word==0x24040009:
            print("уже пропатчено"); return 0
        raise SystemExit("RX-зазор не пуст")
    code=bytearray(d[SRC-VTO:SRC-VTO+SRC_LEN])
    off_k=KIND_OFF
    kind=struct.unpack_from("<I",code,off_k)[0]
    assert kind==0x24040005, hex(kind)
    struct.pack_into("<I",code,off_k,0x24040009)
    d[body_off:body_off+SRC_LEN]=code
    struct.pack_into("<I",d,SLOT_OFF,DST)
    ph=find_phdr2(d); sz=struct.unpack_from("<I",d,ph+16)[0]
    if sz==PHDR_FILESZ:
        struct.pack_into("<I",d,ph+16,PHDR_NEW); struct.pack_into("<I",d,ph+20,PHDR_NEW)
        print("phdr2 → 0x67f000")
    else:
        print("phdr2 уже расширен")
    path.write_bytes(bytes(d))
    print("записано, sha256",hashlib.sha256(bytes(d)).hexdigest()[:16])
    return 0

if __name__=="__main__":
    raise SystemExit(main())
