# Installed Phase 4 probe repair verdict

Approve the bounded receipt-tool repair. The first installed prepare attempt
remains failed: the embedded interpreter could not import six application
modules. Setup and reinstall had each exited zero, and all 32,054 installed
files matched the sealed package. This was a receipt bootstrap defect.

The probe now receives the validated absolute app directory as an explicit
argument and inserts it before importing the original seven modules. Its actual
module paths and sys.path remain recorded. Missing and relative arguments fail
before imports. Checkout and user-site rejection, guards, ownership cleanup,
package bindings and fixture behavior are unchanged. No interpreter ._pth edit
is part of this repair. The normal server and MCP entry points already establish
their own installed import path.

Four new regressions execute isolated no-site subprocesses against disposable
fake modules. They demonstrate the original bare-import failure, successful
bound imports, two invalid-argument refusals and retained checkout rejection.
No existing test or assertion changed. The original five receipt suites plus
these regressions pass: **63/63** in the detached worker (27.02 seconds), then
**63/63** in the checkout (25.74 seconds), after raw diff and three-way apply.

Exact patch and outputs are sealed under
`proof/ryan-p4-embedded-probe-2026-09-10/SHA256.json`. The first installed failure
and restored guard/interpreter state remain in the Agent Install 05 receipt root.
Retry in a fresh P4 directory after this integration; do not overwrite it.

A fresh complete tree is required for this receipt-source change. The installer
payload is unchanged, so rebuilding its identical bytes is not required. This
verdict is not an installed Phase 4 pass, a real-client receipt or a waiver of
the historical AT6 failure.
