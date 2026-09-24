# AV-5m4b6: close destination-alias admission

Engine: grok. Work only in the Control Room worktree. Read this brief,
`docs/library/PHASE4-AW10-2026-09-08.md` and
`docs/library/PHASE4-AV5M4B5-BRIEF-2026-09-08.md` completely. Apply the
complete retained `docs/library/patches/av5m4b5-grok-rejected-2026-09-08.patch`
with three-way application. Write
`docs/library/PHASE4-AV5M4B6-GROK-2026-09-08.md` early. No report or no
decisive executable proof means an incomplete run.

## Required repair

B5's final independent union is 267 passed / nine frozen failures. All three
AW-9 lifetime defects are closed by those bytes. AW-10 adds one actual
failure: a verified junction alias admits a second live writer before the
first writer has a lease. Lexical hashing cannot establish physical directory
identity. Repair this boundary before writer launch, with bounded admission
or refusal, preserving B5's dedicated lifetime owner and unknown-liveness
retention. Do not resolve destination filesystems synchronously in the parent.

A conservative shared Windows kernel admission gate across all mirror
destinations is acceptable and preferred for this bounded repair. It must
apply before every writer can start and retain ownership until death is
proven. It may serialize unrelated destinations; document that concurrency
tradeoff. Same-thread non-recursion must use the actual kernel gate identity,
even if the request carries a different lexical destination. Preserve exact
destination/token/operation binding independently of that gate's key. Do not
make every request share a mutable session or let a foreign operation adopt
an existing owner. Context propagation within the same admitted operation is
allowed. An abandoned gate is not proof of writer death.

Audit helper-created sessions as well as Mirror entry. Reusing an owner must
be tied to the same admitted operation, not just a process-global lookup.
Do not permit a replacement mutator while an earlier session has unknown
liveness or a launch in progress. Cover normal and junction-alias callers
from another process and another thread in the same process. Keep eventual
proven-death release; gate leakage is not an acceptable repair.

An alternative bounded alias refusal may be used only with equally decisive
evidence and no destination-resolution race. Do not add unbounded parent
`realpath`, a TEMP/profile-dependent lock, SQLite pointer introspection,
parent final-write fallback, or post-timeout destination rollback.

Existing committed acceptance tests/helpers are frozen. B/B2/B3/B4/B5 test
files in the rejected patch are unintegrated: correct only demonstrated setup
defects and explain each change. For example, the B4 late-parent test can
terminate the original process before starting its later session while
retaining the stale original plan and all no-adoption assertions. It need
not manufacture two admitted live writers. Kernel-key metadata assertions
must describe the actual new gate; do not weaken ownership behavior tests.

## Verification and retention

Run one final combined union with every selector in the B5 brief, B5's new
`tests/test_phase4_av5m4b5_lifetime.py`, the unchanged
`tests/library_work_astra/test_phase4_aw10_acceptance.py`, and new B6 tests.
Use short disposable roots and a task-specific selector variable, never
PowerShell's automatic `$args`. The 240-character destination cap is real;
retain the old long-path failed output. Document setup/source repairs before
any rerun. Keep all original failed outputs as failed observations.

New tests must observe actual competitor processes through an owned junction,
same-process foreign-thread admission, unknown/dead lifecycle, and release
after confirmed death. Show the unrelated-destination serialization tradeoff
if using the shared gate. Retain separate startup, operation, termination and
caller-return timings where already measured. Preserve A3 identity, F/H2 and
BC-3f media bindings, isolated local mutation and Index transaction ownership.

No model/API calls, ANTHROPIC_API_KEY, paid API, live index, port 5179,
commits, pushes, subagents, acceptance/helper edits, broad process kills,
wrapper introspection or async Python exceptions. Apply remains false.
Terminate only exact task-created processes. Astra independently verifies
both roots before integration, then finishes AW-4 and the real-client receipt.
