# Ghidra headless: список функций программы в текстовый файл.
# Запуск: ./docker/ghidra.sh list
# Результат: work/ghidra_out/functions.txt (адрес, имя, размер)
# @category tempotec
# @runtime PyGhidra

import os

from ghidra.program.model.listing import FunctionIterator

args = getScriptArgs()
outdir = args[0] if args else "/work/work/ghidra_out"
if not os.path.isdir(outdir):
    os.makedirs(outdir)
path = os.path.join(outdir, "functions.txt")

fm = currentProgram.getFunctionManager()
count = 0
with open(path, "w") as fh:
    it = fm.getFunctions(True)
    while it.hasNext():
        func = it.next()
        fh.write("%s\t%s\t%d\n" % (
            func.getEntryPoint(), func.getName(), func.getBody().getNumAddresses()))
        count += 1

print("written %d functions to %s" % (count, path))
