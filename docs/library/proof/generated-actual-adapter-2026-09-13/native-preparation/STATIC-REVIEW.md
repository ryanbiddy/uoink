# Static preparation review, 2026-09-13

Source reread `f44d84` confirmed the lifecycle and inherited port contract. The adapter's exact lease key is `(fixed generated run, large-v3-turbo, pinned immutable revision)`; the generated port validates that key and the superclass retains the same object. Admission occurs only after protection is acquired. Binding occurs after the permit is reserved and before the factory installs its owner. Startup sees the installed owner but remains reserved through inherited adoption and the new policy acknowledgement. The factory assigns the worker and marks running only after that call returns. Cleanup confirms actual stopped/closed state before releasing the lease. No source correction was needed.

The data-only preparer checked exact existing source hashes and Python syntax. It compared the original/new audit functions, fixed dispatcher, native monitor, source finder/loader and finalizer ASTs; they match. The global native-exit block is unchanged. The only guard addition is the final independent adapter-state check, also recorded in both receipts.

Source-only PowerShell parsing in tool `4f6ab3` returned zero parse errors and exit 0. It did not invoke the launcher or compile/import any candidate Python module. Full bootstrap diff and final receipt checks were reread in that same call. There is no candidate or native result for this preparation.

The expected policy digest is calculated from source literals and the fixed generated filename/size/SHA recipe. The real resolver source is parsed as text to obtain the immutable revision; it is never imported by the preparer. Native support hashes are retained metadata at this stage, not new binary observations. Their before/after revalidation remains part of the later admitted launcher.
