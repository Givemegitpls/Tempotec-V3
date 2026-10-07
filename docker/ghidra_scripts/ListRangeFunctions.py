# Ghidra headless: перечислить функции в диапазоне (напр. .MIPS.stubs) с именами.
# Запуск:
#   ./docker/ghidra.sh raw pyghidra --skip-analysis \
#     --project-path /work/work/ghidra_project --project-name tempotec \
#     /work/work/hiby_player /work/docker/ghidra_scripts/ListRangeFunctions.py 0x93a2a0 0x93a7b0
# @category tempotec
# @runtime PyGhidra

args = getScriptArgs()
lo = int(args[0], 16) if args else 0x93A2A0
hi = int(args[1], 16) if len(args) > 1 else 0x93A7B0

fm = currentProgram.getFunctionManager()
for f in fm.getFunctions(True):
    off = f.getEntryPoint().getOffset()
    if lo <= off < hi:
        print("%#x  %s  size=%d" % (off, f.getName(), f.getBody().getNumAddresses()))
