# Phase 6 refusal integration review — 2026-09-09

Verdict: accept the bounded production repair. The two stale-publication
failures from corrected tree `4a35316` pass in the complete named union:
**71 passed, zero failed** independently in the worker (208.89 seconds)
and checkout (203.59 seconds). Both runs report 20 warnings. No existing
test, fixture, assertion, skip or parameter changed.

Worker `d4d402e8-2461-436f-b9c6-9fed61a1605d` started from `a74385c`.
Its raw diff was retained and applied with `git apply --3way` on checkout
parent `0ad33d4`, without a conflict. The proof metadata's `checkout_before`
field records the earlier capture-time HEAD `1063843`, not the application
parent. The applied source in both roots matches after normalizing line endings.

`library_media.py` validates the complete media block before classifying
an omitted ticket under the existing immediate transaction. A validated
snapshot already in committed history receives `revision_unavailable` /
`superseded_snapshot`. Other omitted tickets still receive
`invalid_request` / `publication_ticket_required`. Foreign and malformed
tickets remain invalid. This path neither mints a ticket nor writes without
one. `index.py` delegates that classification instead of raising too early;
its active-transaction refusal and successful-publication invalidation remain.

The named union includes BC-2, evaluation, BC-3f, BC-3a3, BC-3e and the
complete BD, BD-2, BD-3 and BD-4 acceptance files. The original worker's
71-pass run and six-pass line-ending confirmation are preserved separately.
Commands, raw logs, XML, guard, patch and source hashes are sealed in
`proof/ryan-phase6-integration-2026-09-09/SHA256.json` (17 files).

This is a focused integration result, not a replacement for the failed
full tree on `4a35316`. A new full tree and package are still owed after
the remaining source integrations. Phase 6 ships chapters and cited ranges;
speaker attribution remains blocked and no diarization was run.
