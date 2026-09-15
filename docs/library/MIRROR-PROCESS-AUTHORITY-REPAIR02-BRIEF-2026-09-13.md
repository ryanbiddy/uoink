# Close process identity gaps in the reviewed proposal

Read ASTRA-AUTHORITY-C1008-REVIEW-2026-09-13.md first. Gemini c1008e0b is a
rejected proposal: its eleven cases pass, but Astra's ten identity boundaries
all fail. The checkout already contains accepted owner repair ff67b84. Preserve
that repair and every committed test. Ryan authorizes this product repair.

Grok owns a bounded continuation in its isolated worktree. Write the patch and
docs/library/MIRROR-AUTHORITY-REPAIR02-GROK-2026-09-13.md early. A report without
a concrete tested patch is incomplete. No subagents, commits or pushes.
Apply the retained proposal as a starting draft from
docs/library/proof/astra-authority-c1008-review-2026-09-13/proposed-product-and-tests.diff
with git apply --3way; preserve the accepted owner changes if context differs.
That draft brings both the eleven worker tests and ten failed Astra boundaries.
Do not claim it is accepted. The prior source and all located attempts remain
under the same proof directory.

Repair these four groups in library_mirror.py only:

1. Remove tolerance from ownership and mutation authority. A different process
   creation identity cannot authorize kill or job assignment, even one millisecond
   apart. A child older than its parent is not that parent's child. Preserve
   unrelated legacy lease wire formats; do not weaken assertions or globally
   rewrite external timestamps to make them match.
2. Establish parent and child identity across discovery and action, including
   the writer fallback. A Toolhelp PID plus a later timestamp query cannot prove
   the snapshot still describes that process. Prefer retained original process
   handles or an equally strong verified identity: hold identities stable while
   revalidating the parent/child relationship and while acting. Never register a
   foreign replacement merely because its own new timestamp can be queried.
   Keep already proved children tracked after parent exit. Review handle closure
   and concurrency; a handle cannot close while another thread uses it. Do not
   hold the cancellation state lock across blocking discovery or termination.
3. Refuse adoption from an unknown recorded parent identity. Recovery may use
   the original retained Popen/owned handle; a fresh arbitrary PID query is not
   authority. Treat unknown or mismatched child/parent identity conservatively,
   and retain genuinely unresolved owned children until proven dead.
4. Canonicalize a writer that is proved to be the Popen launcher. A failed second
   timestamp query must not erase the launcher's definitive handle-based death.
   Do not merge arbitrary epochs just because their numeric PIDs are equal.

Microsoft's PROCESS_INFORMATION documentation explains the lifetime protection
provided by retained process handles:
https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/ns-processthreadsapi-process_information
Read the already recorded finding; no network access is needed for this worker.

Add explicit synthetic positive/negative controls for the strong identity and
handle lifetime mechanism you choose. Keep all ten Astra behavior assertions
and eleven worker behavior assertions unchanged. These new proposal tests are
not committed acceptance fixtures: if a new native mechanism requires new inert
handle setup, preserve the exact previous fixtures, record their diff/reason,
and change setup only. A fake kernel must fail closed for unmocked operations;
never open, assign, suspend, wait on or terminate real processes in these tests.
Effect recorders must prove mutation refusal and legitimate success. Preserve
unknown-child retention, cancellation behavior and the accepted owner repair.

Run only the two new synthetic files plus your new synthetic controls via the
existing guarded native verifier. Record actual counts, commands and exits.
No real mirror suite or shared Windows gate in this assignment. Astra reviews
the final diff and runs real Phase 4 suites sequentially in both roots. Archive
every draft before modification, exact diffs, failed outputs and a documented
repair reason before each fresh run label. Do not rerun a failed baseline
without a repair, suppress a failure, relax a behavior assertion or change an
existing committed test. If a boundary cannot be repaired safely, write the
specific remaining defect and preserve the partial patch.

Use E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\ig-native\Scripts\python.exe
and E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\integrator_verify.py by absolute path, --root your
worktree, fresh --label, --runxfail. Before native Python starts set
IG_FORBIDDEN_LIVE=C:\Users\hello\AppData\Local\Uoink\index.db,
PYTHONDONTWRITEBYTECODE=1, PHASE3_REQUIRE_IMPLEMENTATION=1 and scrub all provider
keys, tokens and endpoint overrides. No live index, 5179, models, new fetch,
paid API, credentials, Inno, installed state, website or marketing. No complete
tree or release-readiness claim from these focused probes.

Dispatch preflight01 from db9423053600e88589e795cea47ec83af079313f exited one
before any worker started: the abbreviated verifier reference was interpreted
as a required file absent from the frozen Git base. This revision gives the
existing external verifier's full absolute path. Its original brief bytes remain
in Git and in Astra's preserved preflight draft. No test or product attempt ran.
