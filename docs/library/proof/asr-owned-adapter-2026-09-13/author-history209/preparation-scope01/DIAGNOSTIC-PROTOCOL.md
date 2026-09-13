2026-09-13. Proposed first action after root reviews the exact diagnostic source and admits it: run diagnose_scope01.ps1 once from the checkout. It refuses the existing runs/scope01 label and checks the unchanged inert child hash before starting Python.

The diagnostic uses C:\Python314\python.exe with -I -S -B, a fixed reviewed stdlib child that intentionally exits 1, provider credentials removed without printing, IG_FORBIDDEN_LIVE bound lexically, and TORCH_DEVICE_BACKEND_AUTOLOAD=0. Only generated text outputs and the inert child source are involved. No adapter, resolver, D1, model/package or network activity occurs.

Four observations run in order: original unqualified reset/capture at script scope, the same inside a function, explicit global reset/capture at script scope, then inside a function. The two original observations initialize the global variable to the distinct sentinel 314159 before executing the original local reset/capture statements. This makes a stale global value recognizable; it is diagnostic setup, not a repair of prior evidence.

Each observation immediately captures the chosen and global values, then records whether a local variable exists and its value. Preserve its stdout/stderr and flushed observation JSON. The diagnostic reports both the original and explicit-global outcomes. It does not require the original captures to succeed and does not rewrite the first failed receipt. Its own exit is 0 only if all four global observations show the intended child exit and both proposed captures agree, with empty stderr.

Root must inspect the actual result and tool exit before admitting either repaired wrapper. If explicit-global capture is not confirmed, stop without running the candidate. Even a successful diagnostic is only evidence for this observed PowerShell/interpreter invocation; the two repaired wrapper checks still need separate admission. The old missing01 measurement remains failed with native_exit=null.

Proposed direct command, with the checkout as working directory:

    & '.\_scratch\asr-native-exit-scope-repair01\diagnose_scope01.ps1'

The script sets startup bindings before its Python calls. Root should also retain the actual tool result and source hashes. No diagnostic or repaired wrapper was executed during preparation.
