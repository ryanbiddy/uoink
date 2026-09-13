2026-09-13. The first admitted wrapper check failed its native-exit receipt
requirement. Do not continue the old subset or grant the 58-case ASR admission.

Actual wrapper tool d3d1b0 exited 1 in 0.2731948 seconds. The expected late
Get-FileHash error occurred on the deliberately absent instrument.txt. However,
native-exit.json recorded child_returned=true and native_exit=null, rather than
the required numeric exit 1. The pinned inert child printed its expected
failure message and stderr was empty. Its actual numeric native exit was not
captured in this receipt and must not be reconstructed as measured evidence.

Root receipt-check tool d9d929 exited 1 in 0.1297871 seconds at the first
native-receipt assertion. Read-only tool 68b58c then confirmed the null field,
the child message, empty stderr and inherited_native_error_preference=true.
Only the missing01 wrapper ran. Success01 and all four guard checks remain
unexecuted, as do all 58 ASR behavior cases.

The suspected cause is the locally assigned LASTEXITCODE shadowing the native
command's global exit variable inside the wrapper function. This remains a
diagnostic hypothesis until checked with fresh inert source under a repair
brief. The original source review did not catch this behavior; acceptance of
the native-exit block is withdrawn. Preserve the original 26-payload seal,
exact code, actual wrapper tool result and all produced files unchanged.

Prepare a fresh scope-aware exit capture and diagnostic, keep all ASR behavior
assertions and adapter/resolver source unchanged, and obtain root source review
before execution. No model, real D1, package runtime, network or installation
was involved.
