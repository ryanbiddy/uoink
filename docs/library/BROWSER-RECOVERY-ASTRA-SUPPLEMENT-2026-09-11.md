# Capture display review and bounded repair

The original worker diff has 220 passes and one historical AT6 failure in
Astra's independent worktree run browser-recovery-astra-before-01. It is not
accepted yet. The implementation can describe an uncertain start as running,
interpret any blocked reason as a settled failure, and associate a missing
start's reason with a different fallback item. The UI can also infer completion
from an older captured item. These are product defects in the proposed change.

Use explicit ledger states for outcomes, prefer an active start when one exists,
keep each displayed reason attached to its own item, and render unknown/waiting
states without claiming success or failure. Retain consent off/draining and
archived states. Use deterministic ordering. Keep the existing worker's tests
unchanged and add separate regressions that exercise the real rendering code,
including hostile text. No existing acceptance test, fixture or marker edits.

Rerun the original named UI/API/strict Phase 3 union plus the new regressions in
the worktree under a new label, then in the checkout after raw diff integration.
The original 220/1 and deleted worker-attempt evidence stay historical. No source
charges, scheduling, consent, retries, schema or write paths may change.

Installation observation and a new full tree remain required after integration.

The real renderer also read isExhausted before its const declaration; the static
worker tests missed that JavaScript runtime error. Move allowance calculation
ahead of outcome selection. An Astra edit script initially omitted UTF-8 decoding
and stopped on the HTML file; the source encoding was restored before testing.

Astra render-01: 11 passed / 1 failed. The new blocked-item fixture called a
nonexistent connection helper. Change only that new setup to service.store.write;
all assertions stay unchanged. Run render-02 under a fresh label.

The final worktree union includes all original named suites, 12 executed-renderer
regressions and the existing source registry/ledger tests. Result: 316 passed,
one historical AT6 failure, six existing warnings, 47.60 seconds. Labels and
raw results remain under _scratch/browser-recovery-astra-final-01. The original
worker report describes its earlier revision and is retained unchanged.
