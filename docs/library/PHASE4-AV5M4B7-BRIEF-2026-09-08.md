# AV-5m4b7: finish cancellation and helper ownership

Engine: grok. Work only in the Control Room worktree. Read this brief and
`docs/library/PHASE4-AW11-2026-09-08.md` completely. Apply the complete retained
`docs/library/patches/av5m4b6-grok-rejected-2026-09-08.patch` with three-way
application. Write `docs/library/PHASE4-AV5M4B7-GROK-2026-09-08.md` early.
Target only the two observed defects below. A run without its report and
decisive executable evidence is incomplete.

## Repair

1. A prepared session cancelled before launch must not later create an
   untracked child. Distinguish prepared, actual launch in progress, running
   and cancelled states. A short state lock can protect transitions; do not
   hold a lock through a potentially blocking Popen or pipe read. If Popen is
   already in progress, retain session and owner until it returns or fails;
   cancellation returns boundedly without claiming physical death. Its
   eventual result must be registered and cleaned up through the original
   session. A cancelled launch that has not entered Popen should refuse
   before process creation and release once no launch can follow. Prevent
   concurrent cancellation from closing a job handle that launch still uses.
   Preserve unknown-liveness retention and proven-death eventual release.
2. Unbound `_atomic_local` / `_unlink_intent_file` must not adopt the current
   Mirror writer from a foreign thread. Reuse only the original admitted
   operation's session or an explicit originating-helper binding. Preserve
   the unchanged same-thread helper tests in AW-4 and AV-5m3. A bound dead or
   cancelled session must refuse, never fall back to a later one. Propagated
   operation context for `_run_cancellable` remains supported. Do not restore
   process-global owner lookup or use only the shared kernel-gate name as
   destination/token/operation identity. Validate the requested destination
   when reusing an operation session for a lease helper.

The shared Windows gate and its serialization tradeoff are already accepted
as the bounded alias approach. Preserve all AW-9/AW-10 behavior, identity-bound
Windows mutation, isolated final local mutation, Index transaction ownership,
and F/H2/BC-3f media binding. No broad redesign or unrelated cleanup is needed.

## Verification

The frozen new acceptance files are
`tests/library_work_astra/test_phase4_aw11_start_cancel_acceptance.py` and
`tests/library_work_astra/test_phase4_aw11_foreign_helper_acceptance.py`.
Do not edit them or any other committed acceptance tests/helpers.

Add `tests/test_phase4_av5m4b7_lifetime.py` with decisive observations for
cancellation during a controlled actual Popen handoff, launch failure after
cancellation, eventual cleanup/gate release, and successful original helper
use with foreign helper refusal. Use actual task-owned child processes and
preserve separate startup, cancellation return and termination timings. Do
not describe an idle cancelled child as post-timeout publication. Cover exact
destination reuse/refusal without synchronous parent realpath.

Run the full named union from
`docs/library/PHASE4-AV5M4B6-BRIEF-2026-09-08.md`, including all B5/B6 files,
unchanged AW-9/AW-10 and both new AW-11 files, plus B7 tests. Use short
disposable roots and a task-specific selector variable, never PowerShell's
automatic `$args`. Retain the original B6 failed unions and AW-11 failures as
failed observations. Document any repair before a rerun and keep its original
output. The nine frozen Phase 4 failures remain failed for Ryan's ruling;
any other regression remains implementation work.

No model/API calls, ANTHROPIC_API_KEY, paid API, live index, port 5179, commits,
pushes, subagents, acceptance/helper edits, broad process kills, wrapper
introspection or async Python exceptions. Apply stays false. Only terminate
exact task-created processes. Astra independently verifies both roots before
integration, then finishes AW-4 and the real-client receipt.
