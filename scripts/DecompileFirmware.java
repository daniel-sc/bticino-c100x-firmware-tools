// Offline research helper for Ghidra's headless analyzer.
// Writes into the ignored research directory; never connects to a device.
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.decompiler.DecompileOptions;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import java.io.PrintWriter;

public class DecompileFirmware extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException("Expected output file path");
        }
        DecompInterface decompiler = new DecompInterface();
        DecompileOptions options = new DecompileOptions();
        options.grabFromProgram(currentProgram);
        options.setRespectReadOnly(true);
        decompiler.setOptions(options);
        decompiler.openProgram(currentProgram);
        try (PrintWriter out = new PrintWriter(args[0])) {
            FunctionIterator functions = currentProgram.getFunctionManager().getFunctions(true);
            while (functions.hasNext() && !monitor.isCancelled()) {
                Function function = functions.next();
                if (function.isExternal() || function.isThunk()) continue;
                DecompileResults result = decompiler.decompileFunction(function, 60, monitor);
                out.println("\n/* " + function.getEntryPoint() + " " + function.getName() + " */");
                if (result.decompileCompleted()) {
                    out.println(result.getDecompiledFunction().getC());
                } else {
                    out.println("/* Decompilation failed */");
                }
            }
        } finally {
            decompiler.dispose();
        }
    }
}
