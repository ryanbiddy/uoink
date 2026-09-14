# Source preparation review — 2026-09-13

Before any execution, the new stale-confirmation control exposed a missing fresh check in the proposed probe: bind_service_attempt compared raw/head/revision but did not recheck the journal's confirmation cache and poison state. A newly stale cache could be replaced by the successful recovery append before the later close observer checked it. Add those checks before clear I/O. The manager and all existing source/test assertions stay unchanged.

The new observer test also expected KernelUnconfirmed where GeneratedJournalSetup.require explicitly raises RuntimeError. Correct that single new, unexecuted expectation to RuntimeError. This is a proposed-test setup correction, not a change to any accepted fixture or previously measured behavior assertion.

Both original draft files are preserved under before/prequalification-review01-*. No cases or native operations have run; no failure is recast as a pass.
