# Startup backfill transaction ownership, 2026-09-09

Worker: Grok. Read the current handoff and this brief completely. Work only in
your Control Room worktree. Write source early. No subagents or paid API.

The original bundled C22 observation at 6632f33 exposes two real startup errors:
the one-off helper logs `sqlite3.OperationalError: cannot commit - no transaction
is active` in source_subscriptions._Store.read, and child-life logs `cannot start
a write transaction while another transaction is active`. Both arise during
the first source-watch tick. The successful scenario status does not erase them.
Original logs are retained at the checkout's _scratch/c22-bundled-01/receipt/
commands/20260909T200249Z-helper-one-off.stdout.log and
20260909T200350Z-helper-child-life.stdout.log, and in the sealed bundled proof.

server._run_phase2_author_backfill_once directly selects/inserts/commits through
idx._conn without idx._lock, while the source service shares that same connection
and lock. Investigate this concrete owner conflict. Repair shared-connection
access and completion-flag persistence through the existing Index lock/transaction
boundary. Preserve once-per-install/idempotent behavior and retry after failed
persistence. Do not suppress the exception, swallow an active transaction,
weaken source-store transactions, remove the watcher or serialize all unrelated
application work merely to make a test pass.

Own server.py and a NEW tests/test_startup_backfill_transaction_ownership.py.
Only extend ownership if diagnosis proves another production file necessary,
and explain it before editing. No existing test/fixture/assertion edits.
Reproduce the conflict deterministically with real SQLite and interleaved
threads: a held source read/write must not be committed or entered by backfill;
backfill's flag commit must be owned, and a failed flag write must leave no
foreign transaction or false completion. Check ordinary author correction and
repeat invocation. Use disposable profiles only.

Named suites: the new test file, tests/test_startup_anchor_transaction.py,
tests/test_cat_p2_taxonomy.py, tests/test_v3_2_3_anchors_lens.py and
tests/test_existing_index_read_open.py.
Also run the strict Phase 3
tests excluding only library_work_astra/test_phase3_s21.py with
PHASE3_REQUIRE_IMPLEMENTATION=1 and report retained original AT6 failure.
Use the checkout's guarded native verifier with a fresh short label, never the
ordinary interpreter's unguarded test tree. Its exact path is
E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/ig-native/Scripts/python.exe;
use the committed integrator_verify.py from proof/ryan-corrected-01-2026-09-09.
Unset API keys; preserve IG_FORBIDDEN_LIVE as a string, never inspect its file.

Retain the original failure/reproduction and complete logs/XML with counts,
source diff and a concise worker review. No commits, pushes, installer, real
client/model, live index, port 5179 (including probes), fetch, labels or speakers.
Apply remains false. Astra independently verifies the named suites, integrates
with a raw three-way patch, rebuilds the changed product and repeats the original
bundled observation plus final complete tree. You do not rebuild or run Setup.
