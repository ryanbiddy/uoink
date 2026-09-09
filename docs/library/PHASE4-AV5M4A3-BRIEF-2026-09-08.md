# AV-5m4a3: retain ownership through immediate temp cleanup

Engine: Grok. Read AV-5m4a2's brief and report, AW-4 and the new AW-6 case.
AV-5m4a2 is integrated after independent **219 passed, nine failed** in
both roots (76.01 seconds worker, 72.05 seconds checkout). Its seven new
tests and all four AW-4 cases pass. Nine frozen interceptor/setup failures
remain for Ryan. This is intermediate implementation, not Phase 4 acceptance.

New frozen `tests/library_work_astra/test_phase4_aw6_acceptance.py` failed
in 0.69 seconds, worker scratch `aw6-finally`. It changes ownership of the
allocated temp name at `_io_replace`, then raises a publication error.
The `_atomic_vault` finally path calls `_io_unlink(tmp)` without the known
file identity or hash and deletes the independent replacement. The original
allocated file was moved aside and still exists. Recorded cleanup's handle
checks do not protect this immediate cleanup path.

Carry the creating handle's file/volume identity and content authority through
every cleanup of that allocation, including immediate finally cleanup and
write-error paths in the child. Never delete a pathname whose current identity
is unknown. Preserve unresolved intent for retry. Keep the one-argument
`_io_unlink` seam if necessary for unchanged injectors, but bind authority to
the original operation, not mutable instance-global state that a later resync
can replace. AV-5m4b2 owns session lifetime/exclusion concurrently; preserve
its thread-local operation context when integrating. List any overlapping
methods in your report.

Inspect the child's write-error cleanup and temp-to-destination publication
for the same identity gap. A failed write must not unlink a replacement after
closing its original handle. A replaced temp must not be adopted as our own
publication source. Add focused coverage for the actual bound I/O. On platforms
where deletion exclusion cannot be proven, refuse and retain cleanup. The
POSIX rename/check/restore sequence in AV-5m4a2 is not general exclusion from
independent writers; do not claim otherwise or overwrite a new pathname during
restoration. This is a Windows release; a fail-closed unsupported fallback is
acceptable where an equivalent safe primitive is unavailable.

Run all AV-5m4a2 named suites, its seven implementation tests, the unchanged
AW-6 case and your new tests. All existing tests/helpers are frozen. Do not
restore direct binding writes, fixture inspection or unlink bypasses. Write
`docs/library/PHASE4-AV5M4A3-GROK-2026-09-08.md` early, with exact commands,
counts, boundary proof and limitations. No report means incomplete work.

No live index, port 5179, models, API key, paid API, commits, pushes or
subagents. Apply stays false. Use disposable roots and resolved dependencies.
Astra verifies both roots and reviews the merged lifetime/identity behavior.
