# Repair the Phase 4 verification path budget

The first broader worker run remains FAIL: 174 passed, 59 failed, zero skipped
in 100.51 seconds; actual pytest/verifier exit 1. Source SHA256 remains
67432bf13905b8c28c2048ce51bbebd74490d463f8b1a4e08fdd3ce4e53a0a23.
No source or fixture change followed that observation.

Read-only inspection found a concrete verifier setup error. The descriptive
label astra-authority-repair03-worker-phase4-01 becomes part of --basetemp.
For the first failed export, a0/v/Uoink/Library/<64-character hash>.md is
227 characters. Production _atomic_vault adds a dot, 24 hex characters and
.tmp: 256 characters total. Its existing _path_too_long rejects anything above
240. The frozen AW fixture already uses short names for this documented cap.
The resulting ledger contains only the short Library.md as synced; item:a and
item:b remain pending with written_generation zero. The actual test assertion
observes the missing item file despite a successfully written short index.

Repair only the fresh run labels to a3w02 (worker) and a3c01 (checkout).
The first temporary path becomes 220 characters with a3w02. Keep the identical
verifier, guard, selectors, source, assertions, fixtures and path-limit behavior.
This is verification setup correction, not product acceptance or a claim that
every failure has been explained. A new complete Phase 4 observation must show
the result. Retain the first raw log/XML/results and this diagnosis in the seal.
If failures remain, stop and diagnose them before another attempt. No models,
new fetch, live index, port 5179, website, marketing or installation.
