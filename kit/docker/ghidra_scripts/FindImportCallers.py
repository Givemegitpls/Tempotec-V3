# Ghidra headless: найти функции, вызывающие импортируемый символ (напр. rand/srand).
# Запуск:
#   ./docker/ghidra.sh raw pyghidra --skip-analysis \
#     --project-path /work/work/ghidra_project --project-name tempotec \
#     /work/work/hiby_player /work/docker/ghidra_scripts/FindImportCallers.py rand /work/work/ghidra_out/rand_callers.txt
# @category tempotec
# @runtime PyGhidra

import os

args = getScriptArgs()
name = args[0] if args else "rand"
out = args[1] if len(args) > 1 else "/work/work/ghidra_out/import_callers.txt"

st = currentProgram.getSymbolTable()
fm = currentProgram.getFunctionManager()

lines = []
seen = set()


def note(from_addr):
    f = fm.getFunctionContaining(from_addr)
    key = str(f.getEntryPoint()) if f is not None else str(from_addr)
    if key in seen:
        return
    seen.add(key)
    lines.append("%s  %s  from %s" % (key, f.getName() if f is not None else "?", from_addr))


# 1) символы с этим именем (thunk/внешний символ) и их ссылки
for s in st.getSymbols(name):
    for r in s.getReferences():
        note(r.getFromAddress())

# 2) внешние локации с этим именем (на случай, если ссылаются напрямую)
try:
    extmgr = currentProgram.getExternalManager()
    for loc in extmgr.getExternalLocations():
        if loc.getLabel() == name:
            for r in loc.getReferences():
                note(r.getFromAddress())
except Exception as exc:  # noqa: BLE001
    print("external scan: %s" % exc)

d = os.path.dirname(out)
if d and not os.path.isdir(d):
    os.makedirs(d)
with open(out, "w") as fh:
    fh.write("\n".join(sorted(lines)) + "\n")
print("=== callers of %s: %d ===" % (name, len(lines)))
print("\n".join(sorted(lines)))
