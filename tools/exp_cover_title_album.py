#!/usr/bin/env python3
"""D9t: «альбомы артиста» = D9 (kind5-источник) + RX-хук тайтла строки.

Состав: релиз (make.sh patch) + exp_album_view + ЭТОТ скрипт:
  - слот kind2 0xaae114 := 0x4A9DC0 (kind5-кэш треков автора; обложки per-album,
    путь из col1 — см. notes D9);
  - хук провайдера тайтла строки: элемент-код 0x15 в FUN_004a3c80 (family0) /
    FUN_004a3fa0 (family1) возвращает rec+0x20c (col2). Хук: если вид — наш
    подменённый (view+0x40==4 И ключ view+0x3de0 = L"artist\\…" или
    L"album_artist\\…") → тайтл = rec+0x42c (col3=album kind5-шаблона);
    иначе стоковое value (delay-слот записал бы просто rec, поэтому хук
    ВСЕГДА дописывает правильный итог).

Точки патча (проверены дизасмом):
  0x4a4008: addiu $a1,$a1,0x20c → jal HOOK1  (delay `sw $a1,(v0)` остаётся)
  0x4a3d14: addiu $s0,$s0,0x20c → jal HOOK0  (delay `sw $s0,(v0)` остаётся)
jal безопасен: $ra восстанавливается из стека; хвосты веток t-регистры не
используют; хук трогает только t0..t2 и перезаписывает значение.

RX: 0xa7e400 (HOOK1), 0xa7e480 (HOOK0); phdr2 → 0x67f000.

Использование:
    python3 tools/exp_cover_title_album.py <hiby_player> [--check]
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

VTO = 0x400000
SLOT_VA = 0xAAE114
SLOT_OFF = SLOT_VA - VTO
SLOT_OLD = 0x4A95E0
SLOT_NEW = 0x4A9DC0  # kind5

HOOK1_VA = 0xA7E400
HOOK0_VA = 0xA7E48C
PATCH1_VA = 0x4A4008  # addiu a1, a1, 0x20c
PATCH0_VA = 0x4A3D14  # addiu s0, s0, 0x20c
ORIG = {HOOK1_VA: 0x24A5020C, HOOK0_VA: 0x2610020C}
PHDR_FILESZ = 0x67E370
PHDR_NEW = 0x67F000

R = {n: i for i, n in enumerate(
    "zero at v0 v1 a0 a1 a2 a3 t0 t1 t2 t3 t4 t5 t6 t7 s0 s1 s2 s3 s4 s5 s6 s7 "
    "t8 t9 k0 k1 gp sp fp ra".split())}


def iw(op: int, rs: str, rt: str, imm: int) -> int:
    assert -32768 <= imm <= 65535 or (imm & 0xFFFF) != 0
    return op << 26 | R[rs] << 21 | R[rt] << 16 | (imm & 0xFFFF)


def assemble(segment_va_base: int, lines: list[str]) -> bytes:
    """→ packed код (LE, по слову на инструкцию)."""
    out_words = _assemble_words(segment_va_base, lines)
    return b"".join(struct.pack("<I", w) for w in out_words)


def _assemble_words(segment_va_base: int, lines: list[str]) -> list[int]:
    """lines: 'label:', 'nop', 'addiu rt,rs,imm', 'lw/lbu rt,off(rs)', 'sw',
    'bne/beq rs,rt,label', 'b label', 'jr rs', 'jal label'."""
    loc, words = {}, []  # label → index слова
    norm = []
    for line in lines:
        s = line.split("#")[0].strip()
        if not s:
            continue
        if s.endswith(":"):
            assert s[:-1] not in loc
            loc[s[:-1]] = len(norm)
            continue
        norm.append(s)
    def pc(i: int) -> int:
        return segment_va_base + i * 4
    def lw_lbu_sw_val(off: str) -> int:
        return int(off, 0)
    out = []
    for i, s in enumerate(norm):
        # сначала: rt, off(rs) остаются нетронутыми для lw/lbu/sw
        op0 = s.split()[0]
        if op0 in ("lw", "lbu", "sw"):
            rt, paren = [x.strip() for x in s.split(None, 1)[1].split(",", 1)]
            off, rs = paren.strip().split("(", 1)
            rs = rs.rstrip(")")
            off = off.strip() or "0"
            opc = {"lw": 35, "lbu": 36, "sw": 43}
            out.append(opc[op0] << 26 | R[rs] << 21 | R[rt] << 16 | (int(off, 0) & 0xFFFF))
            continue
        p = [x for x in s.replace(",", " ").split() if x]
        op = p[0]
        a = p[1:]
        if op == "nop":
            out.append(0)
        elif op == ".word":
            out.append(int(a[0], 0) & 0xFFFFFFFF)
        elif op in ("bltz", "bgez"):
            rs, lbl = a
            delta = pc(loc[lbl]) - pc(i) - 4
            assert delta % 4 == 0 and -32768 <= delta // 4 <= 32767
            out.append(1 << 26 | R[rs] << 21 | (0 if op == "bltz" else 1) << 16 | (delta // 4 & 0xFFFF))
        elif op == "addiu":
            rt, rs, imm = a
            out.append(iw(9, rs, rt, int(imm, 0)))
        elif op == "lui":
            rt, imm = a
            out.append(iw(15, "zero", rt, int(imm, 0)))
        elif op == "move":
            rd, rs = a[0], a[1]
            out.append(R[rs] << 21 | R["zero"] << 16 | R[rd] << 11 | 0x25)
        elif op == "ori":
            rs, rt, imm = a
            out.append(iw(13, rs, rt, int(imm, 0)))
        elif op in ("beq", "bne"):
            rs, rt, lbl = a
            delta = pc(loc[lbl]) - pc(i) - 4
            assert delta % 4 == 0 and -32768 <= delta // 4 <= 32767
            out.append(iw(4 if op == "beq" else 5, rs, rt, delta // 4))
        elif op == "b":
            delta = pc(loc[a[0]]) - pc(i) - 4
            assert delta % 4 == 0
            out.append(iw(4, "zero", "zero", delta // 4))
        elif op == "jr":
            out.append(R[a[0]] << 21 | 8)
        elif op in ("jal", "j"):
            if op == "jal":
                target = pc(loc[a[0]]) if not a[0].startswith("0x") else int(a[0], 0)
                assert target % 4 == 0
                out.append(3 << 26 | target >> 2)
            else:
                target = pc(loc[a[0]]) if not a[0].startswith("0x") else int(a[0], 0)
                assert target % 4 == 0 and target >> 28 == (segment_va_base) >> 28
                out.append(2 << 26 | target >> 2)
        else:
            raise ValueError(s)
    return out


def hook_lines(end: str, view: str, rec: str) -> list[str]:
    yes, stk, swx = f"{end}_yes", f"{end}_stk", f"{end}_swx"
    L: list[str] = []
    A = L.append
    A(f"lw t0, 0x423c({view})")        # дискриминатор: source-объект == 0x4a9dc0
    A("lui t1, 0x4a")
    A("ori t1, t1, 0x9dc0")
    A(f"bne t0, t1, {stk}")
    A("nop")
    A(yes + ':')
    A(f"addiu t0, {rec}, 0x42c")
    A(f"b {swx}")
    A("nop")
    A(stk + ':')
    A(f"addiu t0, {rec}, 0x20c")
    A(swx + ':')
    A("sw t0, (v0)")
    A("jr ra")
    A("nop")
    return L


def find_phdr2(d: bytes) -> int:
    phoff = struct.unpack_from("<I", d, 28)[0]
    es, n = struct.unpack_from("<HH", d, 42)
    for i in range(n):
        ph = phoff + i * es
        if struct.unpack_from("<I", d, ph)[0] == 1 and \
           struct.unpack_from("<I", d, ph + 16)[0] in (PHDR_FILESZ, PHDR_NEW):
            return ph
    raise SystemExit("phdr2 не найден")


def main() -> int:
    argv = sys.argv[1:]
    check = "--check" in argv
    args = [a for a in argv if a != "--check"]
    if len(args) != 1:
        raise SystemExit(__doc__)
    path = Path(args[0])
    d = bytearray(path.read_bytes())

    slot = struct.unpack_from("<I", d, SLOT_OFF)[0]
    w1 = struct.unpack_from("<I", d, PATCH1_VA - VTO)[0]
    w0 = struct.unpack_from("<I", d, PATCH0_VA - VTO)[0]
    rx1 = d[HOOK1_VA - VTO:HOOK0_VA - VTO]
    ph = find_phdr2(d)
    phsz = struct.unpack_from("<I", d, ph + 16)[0]

    if check:
        print(f"слот {SLOT_VA:#x} = {slot:#x} ({'kind5' if slot == SLOT_NEW else 'сток/иное'})")
        print(f"patch1 {PATCH1_VA:#x} = {w1:#010x} ({'HOOK1' if w1 >> 26 == 3 and (w1 & 0x3FFFFFF) << 2 == HOOK1_VA else 'сток/иное'})")
        print(f"patch0 {PATCH0_VA:#x} = {w0:#010x} ({'HOOK0' if w0 >> 26 == 3 and (w0 & 0x3FFFFFF) << 2 == HOOK0_VA else 'сток/иное'})")
        print(f"phdr2 filesz = {phsz:#x}")
        return 0

    # RX код
    code1 = assemble(HOOK1_VA, hook_lines("hook1", "a0", "a1"))
    code0 = assemble(HOOK0_VA, hook_lines("hook0", "v1", "s0"))
    assert len(code1) <= HOOK0_VA - HOOK1_VA
    rx = bytes(code1) + bytes(code0)          # непрерывно: HOOK0 сразу после HOOK1
    rx_off = HOOK1_VA - VTO
    cur_rx = bytes(d[rx_off:rx_off + len(rx)])
    if cur_rx != bytes(len(rx)):
        if cur_rx != rx:
            raise SystemExit("RX-зона занята чем-то чужим — прерывание")
        print("RX-хуки уже записаны")
    else:
        d[rx_off:rx_off + len(rx)] = rx
        print(f"RX-хуки {HOOK1_VA:#x}..{HOOK1_VA + len(rx):#x}")

    # слот kind2 → kind5-источник
    if slot != SLOT_NEW:
        if slot != SLOT_OLD:
            raise SystemExit(f"неожиданный слот {slot:#x}")
        struct.pack_into("<I", d, SLOT_OFF, SLOT_NEW)
        print(f"слот {SLOT_VA:#x}: {SLOT_OLD:#x} → {SLOT_NEW:#x}")

    # jal-замены
    for va, origw, target in ((PATCH1_VA, ORIG[HOOK1_VA], HOOK1_VA),
                              (PATCH0_VA, ORIG[HOOK0_VA], HOOK0_VA)):
        off = va - VTO
        cur = struct.unpack_from("<I", d, off)[0]
        new = struct.pack("<I", 3 << 26 | target >> 2)
        if cur == target >> 2 and (cur >> 26) == 3:
            print(f"  [skip] jal {va:#x}")
        elif cur == origw:
            d[off:off + 4] = new
            print(f"  [ok] {va:#x}: {origw:#010x} → jal {target:#x}")
        else:
            raise SystemExit(f"{va:#x}: неожиданное слово {cur:#010x}")

    if phsz == PHDR_FILESZ:
        struct.pack_into("<I", d, ph + 16, PHDR_NEW)
        struct.pack_into("<I", d, ph + 20, PHDR_NEW)
        print("phdr2 → 0x67f000")

    path.write_bytes(bytes(d))
    import hashlib
    print(f"{path}: записано; sha256 {hashlib.sha256(bytes(d)).hexdigest()[:16]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
