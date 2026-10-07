#!/usr/bin/env python3
"""Хук-фильтр альбомов по артисту (маршрут A).

Поверх exp_album_view.py (0x4a8b84: вид «альбомы артиста» -> vg_listview_album)
и exp_coverpath_combo.py: подменённый вид получает источник данных «Albums»
(FUN_004a95e0), который тянет ВСЕ альбомы. Этот патчер ставит в слот источника
вида (данные 0xaae114, файл 0x6ae114, сейчас 0x004a95e0) указатель на хук в
RX-зазоре (0xa7e370). Хук:

  * view = *(a0+0x7c)  (эквивалент FUN_004627e0);
  * если view+0x3de0 начинается с wide L"artist\\" (литерал 0x93e8f4) —
    фильтрованный филиал: свой count + свой SQL с pre-bind ?3 = имя артиста
    (хвост после '\\', FUN_0049d760), заполнение через FUN_007005e0
    (он сам биндит ?1=LIMIT, ?2=OFFSET и не трогает ?3);
  * иначе — fallback: jal 0x4a95e0 (оригинал не тронут) с сохранёнными аргументами.

Оригинальное поведение FUN_004a1ba0 воспроизведено вызов-в-вызов
(work/design_artist_filter.md, §3/§5).

Использование:
    python3 tools/exp_artist_filter.py <hiby_player> [--check]
"""

from __future__ import annotations

import ast
import hashlib
import re
import struct
import sys
from pathlib import Path

VADDR_TO_OFFSET = 0x400000

SLOT_VA = 0xAAE114          # слово-источник вида vg_listview_album
SLOT_OFF = SLOT_VA - VADDR_TO_OFFSET
SLOT_OLD = 0x004A95E0       # FUN_004a95e0
HOOK_VA = 0xA7E370          # RX-зазор, код хука

PHDR_FILESZ = 0x67E370      # исходный filesz/memsz RX-сегмента
PHDR_NEW = 0x67F000

PREFIX_VA = 0x93E8F4        # wide L"artist\" (ассерт)
PREFIX_W = "artist\\"

SQL_CNT_VA = 0xA7EC00       # строки SQL — после кода хука (шаблон combo в 0xa7e800)
SQL_LIST_VA = 0xA7ECC8

SQL_CNT = (
    "SELECT count(*) FROM ALBUM_TABLE WHERE album IN "
    "(SELECT DISTINCT album FROM MEDIA_TABLE "
    "WHERE artist LIKE ?1 OR album_artist LIKE ?1)"
)
SQL_LIST = (
    "SELECT * FROM ALBUM_TABLE WHERE album IN "
    "(SELECT DISTINCT album FROM MEDIA_TABLE "
    "WHERE artist LIKE ?3 OR album_artist LIKE ?3) "
    "ORDER BY character, album LIMIT ?1 OFFSET ?2"
)
assert len(SQL_CNT.encode()) + 1 <= SQL_LIST_VA - SQL_CNT_VA
assert len(SQL_LIST.encode()) + 1 <= 0xA7F000 - SQL_LIST_VA

R = {n: i for i, n in enumerate(
    "zero at v0 v1 a0 a1 a2 a3 t0 t1 t2 t3 t4 t5 t6 t7 "
    "s0 s1 s2 s3 s4 s5 s6 s7 t8 t9 k0 k1 gp sp fp ra".split())}


def assemble(source: str, base: int) -> tuple[bytes, dict[str, int]]:
    """Мини-ассемблер MIPS32 LE (шаблон work/patch.py, blaze-mod, MIT).
    Поддержка: li, nop, move, slt, sll, jr, jalr, j, jal, beq/bne, beqz/bnez,
    b, lw/sw/lbu, lui, addiu, .org, .asciiz. Переходы не переупорядочиваются —
    delay slots обязаны быть явными nop/присваиваниями."""
    labels: dict[str, int] = {}
    lines: list[str] = []
    pc = base
    for raw in source.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith(".org "):
            vn = line[5:].strip()
            pc = int(vn, 16) if vn.startswith("0x") else int(vn, 10)
            lines.append(line)
            continue
        if line.startswith(".asciiz "):
            lines.append(line)
            pc += len(ast.literal_eval(line[8:])) + 1
            continue
        if line.endswith(":"):
            labels[line[:-1]] = pc
            continue
        lines.append(line)
        # li эмитит lui+ori (2 слова 8 байт); остальное по 4
        pc += 8 if line.startswith("li") else 4

    def val(s: str) -> int:
        if s in labels:
            return labels[s]
        return int(s, 16) if s.startswith("0x") or s.startswith("-0x") else int(s, 10)

    def iw(op, rs, rt, imm):
        return op << 26 | rs << 21 | rt << 16 | (imm & 65535)

    out = bytearray()
    cursor = base
    for line in lines:
        if line.startswith(".org "):
            vn = line[5:].strip()
            newpc = int(vn, 16) if vn.startswith("0x") else int(vn, 10)
            assert newpc >= cursor, line
            out.extend(b"\0" * (newpc - cursor))
            cursor = newpc
            continue
        if line.startswith(".asciiz "):
            value = ast.literal_eval(line[8:]).encode() + b"\0"
            out.extend(value)
            cursor += len(value)
            continue
        p = [x for x in re.split(r"[\s,()]+", line) if x]
        op, a = p[0], p[1:]
        if op == "li":
            v = val(a[1])
            # lui+ori (2 слова): li строго 8 байт, согласовано с проходом 1
            words = [iw(15, R["zero"], R[a[0]], (v >> 16) & 0xFFFF),
                     iw(13, R[a[0]], R[a[0]], v & 65535)]
        elif op == "nop":
            words = [0]
        elif op == "move":
            words = [R[a[1]] << 21 | R["zero"] << 16 | R[a[0]] << 11 | 0x25]
        elif op == "slt":
            words = [R[a[1]] << 21 | R[a[2]] << 16 | R[a[0]] << 11 | 0x2A]
        elif op == "sltu":
            words = [R[a[1]] << 21 | R[a[2]] << 16 | R[a[0]] << 11 | 0x2B]
        elif op == "sll":
            words = [R["zero"] << 21 | R[a[1]] << 16 | R[a[0]] << 11 | int(a[2], 0) << 6]
        elif op == "jr":
            words = [R[a[0]] << 21 | 8]
        elif op == "jalr":
            words = [R[a[0]] << 21 | R["ra"] << 11 | 0x09]
        elif op in ("j", "jal"):
            target = val(a[0])
            assert target % 4 == 0 and target >> 28 == (cursor + 4) >> 28, line
            words = [(2 if op == "j" else 3) << 26 | target >> 2]
        elif op in ("beq", "bne"):
            rs, rt, target = a
            delta = val(target) - cursor - 4
            assert delta % 4 == 0, line
            assert -32768 <= delta // 4 <= 32767, line
            words = [iw(4 if op == "beq" else 5, R[rs], R[rt], delta // 4)]
        elif op in ("beqz", "bnez"):
            delta = val(a[1]) - cursor - 4
            assert delta % 4 == 0, line
            assert -32768 <= delta // 4 <= 32767, line
            opc = 4 if op == "beqz" else 5
            words = [iw(opc, R[a[0]], R["zero"], delta // 4)]
        elif op == "b":
            delta = val(a[0]) - cursor - 4
            assert delta % 4 == 0, line
            assert -32768 <= delta // 4 <= 32767, line
            words = [iw(4, R["zero"], R["zero"], delta // 4)]
        elif op in ("lw", "sw", "lbu"):
            rt, imm, rs = a
            words = [iw({"lw": 35, "sw": 43, "lbu": 36}[op], R[rs], R[rt], int(imm, 0))]
        elif op == "lui":
            words = [iw(15, R["zero"], R[a[0]], val(a[1]))]
        elif op == "addiu":
            words = [iw(9, R[a[1]], R[a[0]], val(a[2]))]
        else:
            raise SystemExit(f"неизвестная инструкция: {line}")
        for w in words:
            out.extend(struct.pack("<I", w))
        cursor += 4 * len(words)
    return bytes(out), labels


# Раскладка кадра (frame -0x170 = 368):
#   16(sp)      5-й аргумент вызовов (stack5)
#   32(sp)      artist_buf wide, 0x100 байт ((disposing FUN_0049d760 с n=0x80)
#   296(sp)     lstmt
#   300(sp)     cstmt
#   304(sp)     cnt
#   308(sp)     n (длина имени)
#   312(sp)     fstate (FUN_0049cc40)
#   316..328    a0..a3
#   332..360    s0..s6
#   364(sp)     ra

VIEW_KEY_OFF = 0x3DE0

HOOK_SOURCE = f"""
hook_albums_src:
  addiu sp, sp, -368
  sw ra, 364(sp)
  sw s6, 360(sp)
  sw s5, 356(sp)
  sw s4, 352(sp)
  sw s3, 348(sp)
  sw s2, 344(sp)
  sw s1, 340(sp)
  sw s0, 336(sp)
  sw a3, 328(sp)
  sw a2, 324(sp)
  sw a1, 320(sp)
  sw a0, 316(sp)
  move s0, a0
  move s1, a1
  move s2, a2
  move s3, a3
  # view = *(s0+0x7c)
  lw s4, 124(s0)
  beqz s4, fallback
  nop
  # FUN_00421080(view+0x3de0, L"artist\\", 7) == 0 ?
  addiu a0, s4, {VIEW_KEY_OFF}
  lui a1, 0x93
  addiu a1, a1, 59636         # 0x93e8f4 (lo 0xe8f4)
  addiu a2, zero, 7
  jal 0x421080
  nop
  bnez v0, fallback
  nop

  # --- prologue FUN_004a95e0 (без правки) ---------------------------------
  addiu a0, zero, 2
  jal 0x49cc40
  nop
  sw v0, 312(sp)
  bnez v0, st_ok
  nop
  move a0, s0
  addiu a1, zero, 1
  jal 0x49cca0
  nop
st_ok:
  addiu a0, zero, 2
  lw a1, 312(sp)
  jal 0x49cb80
  nop

  # --- list alloc ---------------------------------------------------------
  addiu a0, zero, 16
  addiu a1, zero, 2696        # 0xa88
  addiu a2, zero, 16
  jal 0x45fe00
  nop
  beqz v0, fail
  nop
  move s5, v0                 # s5 = list
  sw v0, 0(s1)                # *param_2 = list

  # --- artist_buf: хвост после '\\' ---------------------------------------
  addiu a0, sp, 32
  addiu a1, s4, {VIEW_KEY_OFF}
  addiu a2, zero, 128
  jal 0x49d760
  nop

  # --- длина --------------------------------------------------------------
  jal 0x4211a0
  addiu a0, sp, 32
  nop
  sw v0, 308(sp)
  sll a3, v0, 1
  addiu a3, a3, 2             # (n+1)*2

  # --- count stmt ---------------------------------------------------------
  lui t0, 0xbc
  lw a0, 6384(t0)             # db = *(0xbc18f0)
  lui a1, 0xa7
  addiu a1, a1, {SQL_CNT_VA & 0xFFFF}
  addiu a2, zero, -1
  addiu a3, sp, 300
  sw zero, 16(sp)
  jal 0x606140                # prepare
  nop
  sw zero, 304(sp)
  lw t1, 300(sp)
  beqz t1, cnt_done
  nop
  move a0, t1                 # bind ?1 = artist
  addiu a1, zero, 1
  addiu a2, sp, 32
  lw t2, 308(sp)
  sll a3, t2, 1
  addiu a3, a3, 2
  sw zero, 16(sp)
  jal 0x5b2fa0
  nop
  move a0, t1
  jal 0x5efe80                # step: 100 = строка
  nop
  bnez v0, cnt_col
  nop
  b cnt_fin
  nop
cnt_col:
  move a0, t1
  move a1, zero
  jal 0x5a1240                # column 0
  nop
  sw v0, 304(sp)
cnt_fin:
  move a0, t1
  sw zero, 16(sp)
  jal 0x5d35c0                # reset
  nop
  move a0, t1
  jal 0x5d34e0                # finalize
  nop
cnt_done:
  lw t1, 304(sp)              # cnt

  # --- setters (как FUN_004a1ba0) -----------------------------------------
  sw t1, 0(s3)                # *param_4 = cnt
  lw t0, 1032(s0)             # (s0+0x408)(s0, cnt)
  lw t9, 0(t0)
  move a0, s0
  move a1, t1
  jalr t9
  nop
  lw t0, 1036(s0)             # (s0+0x40c)(s0, 0)
  lw t9, 0(t0)
  move a0, s0
  move a1, zero
  jalr t9
  nop
  lw t0, 1040(s0)             # (s0+0x410)(s0, s2)
  lw t9, 0(t0)
  move a0, s0
  move a1, s2
  jalr t9
  nop
  lw t0, 1044(s0)             # (s0+0x414)(s0, s2)
  lw t9, 0(t0)
  move a0, s0
  move a1, s2
  jalr t9
  nop

  # --- list stmt ----------------------------------------------------------
  lui t0, 0xbc
  lw a0, 6384(t0)
  lui a1, 0xa7
  addiu a1, a1, {SQL_LIST_VA & 0xFFFF}
  addiu a2, zero, -1
  addiu a3, sp, 296
  sw zero, 16(sp)
  jal 0x606140
  nop
  lw t1, 296(sp)
  beqz t1, end_ret
  nop
  # pre-bind ?3 = artist
  move a0, t1
  addiu a1, zero, 3
  addiu a2, sp, 32
  lw t2, 308(sp)
  sll a3, t2, 1
  addiu a3, a3, 2
  sw zero, 16(sp)
  jal 0x5b2fa0
  nop
  # FUN_007005e0(lstmt, list, offset=0, limit=s2): ?1=s2(limit), ?2=0(offset)
  move a0, t1
  move a1, s5
  addiu a2, zero, 0
  move a3, s2
  jal 0x7005e0
  sw zero, 16(sp)             # 5-й аргумент в delay slot (a0..a3 уже выставлены)
  move a0, t1
  jal 0x5d34e0                # finalize
  nop

  # --- count-fix (как FUN_004a1ba0) -----------------------------------------
  lw t0, 12(s5)
  lw t1, 304(sp)
  slt t2, t1, t0
  beqz t2, end_ret
  nop
  sw t0, 304(sp)
  sw t0, 0(s3)
  lw t0, 1032(s0)
  lw t9, 0(t0)
  move a0, s0
  jalr t9                     # (s0+0x408)(s0) — только a0, как в оригинале
  nop

end_ret:
  lw v0, 12(s5)
  b epilogue
  nop

fail:
  addiu v0, zero, -1
  b epilogue
  nop

fallback:
  lw a0, 316(sp)
  lw a1, 320(sp)
  lw a2, 324(sp)
  lw a3, 328(sp)
  jal 0x4a95e0                # оригинал не правлен: строго как до патча
  nop

epilogue:
  lw s0, 336(sp)
  lw s1, 340(sp)
  lw s2, 344(sp)
  lw s3, 348(sp)
  lw s4, 352(sp)
  lw s5, 356(sp)
  lw s6, 360(sp)
  lw ra, 364(sp)
  jr ra
  addiu sp, sp, 368

.org 0x{SQL_CNT_VA:x}
sql_cnt:
  .asciiz "{SQL_CNT}"
.org 0x{SQL_LIST_VA:x}
sql_list:
  .asciiz "{SQL_LIST}"
""" + ""

if "stack_slot" in HOOK_SOURCE:  # защита от редакционного артефакта
    raise SystemExit("артефакт в HOOK_SOURCE")


def find_phdr2(data: bytes) -> int:
    e_phoff = struct.unpack_from("<I", data, 28)[0]
    phentsize = struct.unpack_from("<H", data, 42)[0]
    phnum = struct.unpack_from("<H", data, 44)[0]
    for i in range(phnum):
        ph = e_phoff + i * phentsize
        p_type = struct.unpack_from("<I", data, ph)[0]
        off = struct.unpack_from("<I", data, ph + 4)[0]
        fsz = struct.unpack_from("<I", data, ph + 16)[0]
        if p_type == 1 and off <= 4 and fsz in (PHDR_FILESZ, PHDR_NEW):
            return ph
    raise SystemExit("RX-заголовок не найден")


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    check = "--check" in sys.argv
    if len(args) != 1:
        raise SystemExit(__doc__)
    path = Path(args[0])
    data = bytearray(path.read_bytes())

    cur = struct.unpack_from("<I", data, SLOT_OFF)[0]
    prefix = data[PREFIX_VA - VADDR_TO_OFFSET:PREFIX_VA - VADDR_TO_OFFSET + 16]
    expect = b"".join(c.encode() + b"\0" for c in PREFIX_W)[:16]
    prefix_ok = prefix.startswith(expect)
    if check:
        state = "применён" if cur == HOOK_VA else ("сток" if cur == SLOT_OLD else "НЕИЗВ")
        print(f"слот {SLOT_OFF:#x}: {cur:#010x} ({state})")
        print(f"wide 'artist\\' {PREFIX_VA:#x}: {'ок' if prefix_ok else 'НЕ СОВПАЛ'}")
        ph = find_phdr2(data)
        print(f"phdr2 filesz: {struct.unpack_from('<I', data, ph + 16)[0]:#x}")
        return 0
    if cur not in (SLOT_OLD, HOOK_VA):
        raise SystemExit(f"слот {SLOT_OFF:#x} = {cur:#010x} — не тот бинарь")
    if not prefix_ok:
        raise SystemExit("литерал artist\\ не совпал")
    if cur == HOOK_VA:
        print("уже пропатчено")
        return 0

    code_start = HOOK_VA - VADDR_TO_OFFSET
    if any(data[code_start:code_start + 0x400]):
        raise SystemExit("RX-зазор 0xa7e370+ не пуст")
    if any(data[SQL_CNT_VA - VADDR_TO_OFFSET:0xA7F000 - VADDR_TO_OFFSET]):
        raise SystemExit("SQL-запас не пуст (лимит RX: файл-офсет 0x67f000)")

    code, labels = assemble(HOOK_SOURCE, HOOK_VA)
    print(f"собрано байт: {len(code)}, labels: "
          + ", ".join(f"{k}={v:#x}" for k, v in sorted(labels.items(), key=lambda kv: kv[1])))

    data[code_start:code_start + len(code)] = code
    struct.pack_into("<I", data, SLOT_OFF, HOOK_VA)
    ph = find_phdr2(data)
    cur_sz = struct.unpack_from("<I", data, ph + 16)[0]
    if cur_sz == PHDR_FILESZ:
        struct.pack_into("<I", data, ph + 16, PHDR_NEW)
        struct.pack_into("<I", data, ph + 20, PHDR_NEW)
        print(f"phdr2: filesz/memsz -> {PHDR_NEW:#x}")
    elif cur_sz >= PHDR_NEW:
        print("phdr2 уже расширен")

    path.write_bytes(bytes(data))
    print(f"{path}: записано, sha256 {hashlib.sha256(bytes(data)).hexdigest()[:16]}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
