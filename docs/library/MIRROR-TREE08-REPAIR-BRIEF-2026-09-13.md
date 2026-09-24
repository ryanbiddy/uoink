# Diagnose the combined mirror failures before rebuilding

The complete 9dd0cfb tree08 result is 2,675 passed, 51 failed and three skipped
across 2,729 cases. Main exits one; the two media cases exit zero. All cases
occur exactly once and only S21 is excluded. Fifty failures concern mirror
operations; the other is the historical AT6 receipt. The immutable record is
proof/ryan-final-partitioned-08-2026-09-13/SHA256.json. Package09 is not built.

The first new failure is test_live_worker_lease_blocks_a_second_mirror in
tests/test_phase4_av5m3_isolation.py, at its initial export, before the dummy
lease owner launches. Its preceding real-worker startup and cancellation/user-
edit cases passed. Later failures repeatedly reach WaitForSingleObject and
destination exclusion unavailable. Preserve these results. A fresh guarded
seven-case AV5m3 diagnostic with passive owner/thread snapshots passes in 5.35 s;
it is a narrower observation and does not clear the combined failure.

Astra will investigate cancellation and owner lifetime. Control Room Gemini has
one independent, bounded security/lifecycle assignment: inspect the authority
used by owned_pids, physical_liveness and termination. In particular, Windows
Toolhelp parent PIDs can outlive a parent's identity. Determine whether a recycled
or orphan parent PID can cause a foreign child to be adopted, retained or killed,
and whether a confirmed process exit can be forgotten on a later failed query.
These are source-review hypotheses, not the established cause of tree08.

Work in the assigned worktree. Read library_mirror.py and existing tests covering
AW-8 through AW-12, AV5m4b4 through b7 and Phase 4 lifecycle. No existing tests,
fixtures, marks, timeouts, application source or installed state may change in
this diagnostic assignment. Write new synthetic regression probes only if they
test a concrete authority boundary. Use fake kernel/process observations and
inert PID values; do not open, assign, suspend or terminate any real process,
acquire the shared Windows gate, run Inno or launch the product. No models,
network/source fetch, live index, port 5179, paid API, credentials or publication.

Write docs/library/MIRROR-PROCESS-AUTHORITY-GEMINI-2026-09-13.md early. Include
exact source lines, actual probe outcomes and an explicit distinction between
confirmed defects and plausible explanations of the full-tree failure. If a
probe fails, retain its original bytes, output, command and result. Do not delete
attempts or retry without a documented correction. A proposed fix belongs in the
report; do not modify production in this first assignment. A report without its
claimed evidence is incomplete. No commits, pushes or subagents.

For any synthetic probes use the existing guarded native verifier with fresh
labels, PYTHONDONTWRITEBYTECODE=1, PHASE3_REQUIRE_IMPLEMENTATION=1 and all provider
variables unset. The shared read-only verifier is
E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\integrator_verify.py and
its native interpreter is the same checkout's _scratch\ig-native\Scripts\python.exe.
Set IG_FORBIDDEN_LIVE to C:\Users\hello\AppData\Local\Uoink\index.db before invoking
that interpreter; the guard must refuse that path, never read it. Set --root to
your worktree and name only your new probe file. Do not run the real mirror suites
while Astra performs the separate lifetime investigation.

After diagnosis, a reviewed product repair must retain unknown-child exclusion,
late-write refusal, destination-alias safety and independent user bytes. It must
also release admission after known death. Verify required suites in worker and
checkout around raw git diff / git apply --3way. Run a fresh full committed tree
only after the repair is documented. Do not edit frozen fixtures to regain green.

Ryan's latest instruction pauses all website and marketing work until Astra and
the council agree the product is ready for market. Local website drafts remain
unpublished; no website council or marketing agent has started. Complete product
repairs, replacement package, installed/native/client checks and readiness review
first. Existing certificate, Desktop-isolation, model/test and historical gates
remain explicit; this diagnostic grants no release approval.
