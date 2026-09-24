# Phase 4 lifecycle integration review

The reviewed lifecycle repair has **163 passed, eight failed** in both roots:
176.98 seconds in worker `cc391d36`, 174.21 seconds in the checkout. All five
corrected-tree lifetime failures pass. The eight parent-interception failures
remain; `RYAN-PHASE4-INTERRUPTED-IO-CONTRACT-REVIEW-2026-09-09.md` explains
their unchanged setup. This result does not accept the full tree or Phase 4.

The worker clears an originating standalone helper's thread-local binding
after confirmed termination or abandoned startup. It retains unresolved launch,
actual Thread identity and physical exclusion. That fixes the B7 helper left
bound after its direct termination. No existing test or fixture changed.

Astra rejected one extra worker change. Its unreadable-lease exception returned
false after an old bound child died, even while a separately held actual helper
and lease were alive. The independent case failed in 0.90 seconds. Removing
that exception restores conservative refusal for an unreadable lease. The old
process's death cannot prove a different owner absent. The cancelled-plan probe
passed before this correction; it is a control, not a reproduced failure.

The corrected focus has 13 passes, including B7 followed by the original
lifetime file. The original independent worker union had 161 passes / eight
failures in 180.44 seconds. Its complete original patch and the failed owner
probe remain separate from the applied patch and corrected results in
`proof/ryan-phase4-integration-2026-09-09/SHA256.json` (24 files). The worker's
own original diagnostics and failed unions are retained in
`proof/ryan-phase4-lifecycle-2026-09-09`.

The worker's long-label runs reported two extra brief failures and, in another
order experiment, 13 extra mirror failures. Those remain failed observations.
Their temporary-root names also changed, so that experiment does not isolate
test order. For example, its retained t12 item path is 212 characters; adding
the 29-character unique temporary suffix yields 241, above the product's 240
character cap. The corresponding independent-run path plus suffix is 232.
This is a source/path calculation, not a rerun or a blanket explanation of
every extra failure. The independent named union retains every case.

Three-way application changed product source cleanly. The only merge conflict
was two added raw-proof rules in `.gitattributes`; both were kept. Three new
proof scripts were restored to the worker's raw bytes after automatic checkout
line-ending conversion. Product normalized hashes match the verified worker.
No existing acceptance file, behavior assertion, skip or parameter changed.
The final full tree and rebuilt installed package remain required.
