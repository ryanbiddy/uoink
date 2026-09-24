# AV-5m4b3: isolate lease mutations and prove operation lifetime

Engine: Grok. Read AW-4, AV-5m4b2's brief and its retained report. AV-5m4b2
`3ddbb5ef` is rejected. Its complete original diff, reports and proposed tests
are retained in `patches/av5m4b2-grok-rejected-2026-09-08.patch`. Independent
verification: **226 passed, twelve failed**, 71.70 seconds, worker scratch
`av5m4b2-wi`. The failures are the eight old parent interceptors and four
AW-4 cases; the latter are already repaired by AV-5m4a2 in the checkout.
Three AW-5 cases pass, but the next review exposes a remaining late write.

Start from current `cc/living-library`. Three-way apply the retained patch
as a starting point, preserving integrated binding, recorded-temp identity,
staging and transport changes. AV-5m4a3 separately owns temp allocation,
publication and immediate cleanup. Keep its changes on overlap.

## Required repair

New frozen `tests/library_work_astra/test_phase4_aw7_acceptance.py` failed
in 3.65 seconds (worker scratch `aw7-late-lease`). It pauses the real
`_write_dest_lease`, lets resync return its timeout, then releases the call.
The old parent creates the destination lease after return. This contradicts
the requirement that all destination mutations be killable. Checking for a
newer live lease just before os.replace cannot stop the late syscall.

Route destination lease writes, replacement and cleanup through isolated I/O,
with the original session, token and operation bound before the call. A late
parent must refuse through its dead bound session before touching a destination.
Audit lease reads/clear operations and startup/termination for unbounded caller
I/O too. Keep exclusion stable across TEMP/profile roots and held until every
old mutator is unable to write. Unknown liveness stays fail-closed. Do not use
a Python-thread timeout plus another distant check. Preserve ordinary fixture
seeding without callback/name inspection; that helper may use an explicit
bounded isolated operation when no resync owns it.

The local intent generation check also precedes `_atomic_local` and unlink.
Prove a late operation cannot finish either mutation after a later resync
owns the intent. Hold exclusion at the mutation itself or use an isolated,
generation-bound operation; add an interleaving test at that boundary.

## Exclusion and evidence quality

The proposed BriefStore repair reads CPython object memory at slot 2, then
calls a separately loaded SQLite library. That is not a demonstrated safe
fallback for an unknown object/interpreter/library layout; catching a Python
exception cannot certify an arbitrary native pointer. Use an explicit ownership
marker established by the authoritative Index write-transaction context and
bound to its connection/thread, or another supported proof. Refuse an unproven
inherited transaction without rolling back caller work. Preserve the active
Index write-transaction case. A third connection's busy result is not proof.

The proposed timeout tests replace `session.call` with a parent wait after
NtSuspendProcess. That exercises a different blocking boundary and does not
diagnose why the original actual-child cases returned success. The claimed
ctypes/warm-run explanation lacks a retained decisive observation. Preserve
both original versions in the retained patches. Unintegrated implementation
tests may now be repaired with a demonstrated real child stall, retaining
child-death, time bounds and independent user-edit assertions. A parent-stub
case may be a separate new test. Never edit a committed test/helper or acceptance
assertion, including AW-5 and AW-7.

Run every AV-5m4b2 named suite, current AV-5m4a2's seven tests, AW-7 and
new implementation cases. Include AW-6 if present in the base and identify
its AV-5m4a3 assignment if still failing. Report the combined union. Preserve
the nine current frozen Phase 4 setup failures for Ryan. Implementation
defects in this brief remain our work.

Write `docs/library/PHASE4-AV5M4B3-GROK-2026-09-08.md` early with commands,
counts, process/operation lifetime and overlap notes. No report means incomplete
work. No live index, port 5179, model, API key, paid API, commits, pushes or
subagents. Apply remains false. Use disposable roots and resolved dependencies,
including pywin32; do not restore the user's APPDATA to bypass missing imports.
Astra verifies and integrates before AW-4 closes.
