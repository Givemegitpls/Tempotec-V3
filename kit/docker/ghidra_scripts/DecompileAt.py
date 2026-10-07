# Ghidra headless: декомпилировать функции по адресам.
# Запуск: ./docker/ghidra.sh decompile 0x4c7e9c 0x4eb680
# Если анализатор не создал функцию (код достижим только косвенно) —
# принудительно дизассемблируем окно и создаём функцию.
# @category tempotec
# @runtime PyGhidra

import os

from ghidra.app.cmd.disassemble import DisassembleCommand
from ghidra.app.cmd.function import CreateFunctionCmd
from ghidra.app.decompiler import DecompInterface
from ghidra.program.model.address import AddressSet
from ghidra.util.task import ConsoleTaskMonitor

args = getScriptArgs()
outdir = args[0] if args else "/work/work/ghidra_out"
addrs = args[1:]
if not os.path.isdir(outdir):
    os.makedirs(outdir)

decomp = DecompInterface()
decomp.openProgram(currentProgram)
monitor = ConsoleTaskMonitor()
fm = currentProgram.getFunctionManager()


def ensure_function(addr):
    func = fm.getFunctionContaining(addr) or fm.getFunctionAt(addr)
    if func is not None and func.getBody().getNumAddresses() > 4:
        return func
    # принудительный дизассемблер окна 0x1000 байт
    start = addr
    end = addr.add(0x1000)
    DisassembleCommand(AddressSet(start, end), None, True).applyTo(
        currentProgram, monitor
    )
    CreateFunctionCmd(addr).applyTo(currentProgram, monitor)
    func = fm.getFunctionAt(addr) or fm.getFunctionContaining(addr)
    return func


for spec in addrs:
    addr = toAddr(spec)
    func = ensure_function(addr)
    if func is None:
        print("нет функции по адресу %s" % spec)
        continue
    res = decomp.decompileFunction(func, 120, monitor)
    if not res.decompileCompleted():
        print("не удалось декомпилировать %s (%s)" % (spec, res.getErrorMessage()))
        continue
    name = func.getName()
    out = os.path.join(outdir, "%s_%s.c" % (func.getEntryPoint(), name))
    with open(out, "w") as fh:
        fh.write("// %s  %s  size=%d\n" % (
            func.getEntryPoint(), name, func.getBody().getNumAddresses()))
        fh.write(res.getDecompiledFunction().getC())
    print("ok %s %s (size=%d) -> %s" % (
        spec, name, func.getBody().getNumAddresses(), out))
