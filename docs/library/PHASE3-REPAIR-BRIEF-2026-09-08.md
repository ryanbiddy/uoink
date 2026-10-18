# Phase 3 repair brief (run AT, 2026-09-08)

Fable's dispatch under `ORCHESTRATION-V1-2026-09-04.md`. Astra's acceptance
([PHASE3-ACCEPTANCE-2026-09-08.md](PHASE3-ACCEPTANCE-2026-09-08.md)) is NOT ACCEPTED on six
defects, each with an exact repair and a reproducing test in
`tests/library_work_astra/test_phase3_*.py` (integrated at `f9bee3d`: 90 pass, 13 fail).
Base: the commit this brief lands in. No worker runs a model, the resident helper, or
touches port 5179 or the live index. Do not commit; Fable integrates and runs every test.

## claude (Fable 5.1 worker): repair AS-01 to AS-06

Read the six findings in the acceptance report and implement exactly the repairs Astra
names, in `source_subscriptions.py`, `server.py` (the `_ServerCaptureBackend` and tick),
`podcasts.py` and `mobile_playlists.py` as needed:

- AS-01: a durable publication-inspection/recovery contract on the production backend, used
  by both completion and restart; the outbox is inserted only after verified publication;
  the same completeness rule when linking an existing corpus row.
- AS-02: persist a process identity per incarnation; require verified terminal execution
  (or an explicit, checked completion proof carried by the callback) before releasing
  active ownership; unknown or surviving execution stays in flight; fence replacement owners
  and stale callbacks through acquisition and publication.
- AS-03: manual and standing dispatchers share a cross-process lock keyed by canonical
  capture identity (a file lock is acceptable), acquired before the standing started
  transition, with a recheck of corpus and consent/owner, held through publication; a busy
  manual owner leaves the observation eligible without charge; a manual completion links
  without a standing outbox.
- AS-04: bounded poll-lease reconciliation on every tick before due selection.
- AS-05: acquire each poll lease immediately before its fetch (or claim only a bounded
  group that can start within its lease); deadlines from the actual claim time.
- AS-06: persist the full normalized feed URL plus entry id (or the capture key) in
  publication provenance and check it before linking, resuming or overwriting a shortened
  corpus id; a mismatch is a visible blocked identity conflict.

Astra's tests are the acceptance target; do not edit them. Keep the existing 39 service
tests, the 31 dashboard tests and the 38 aligned legacy tests green (adjust only those whose
assumptions the repairs legitimately change, and say which). You cannot run a shell: list
the exact pytest commands Fable must run. Cite the finding id in a comment at each repair.
