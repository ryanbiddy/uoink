# Phase 3 original evidence recovery

Astra recovered 33 archive files from the original disposable fixtures on
2026-09-09, under the companion recovery brief. No capture, helper, browser,
model or source request was run. Existing test files and historical receipt
bytes are unchanged. Independent verification on `239dbbd` has 22 passed and
one failed in AS-7/8/9, and 181 passed and one failed in the strict Phase 3
suite. The earlier 20-failure full tree remains failed.

AT6's original `s21-0w_h99w2` fixture retains all eight artifacts with exactly
the hashes recorded in `receipt-at6-candidate-1830b7a.json`. This includes the
four missing log/incarnation/sidecar/markdown entries. Their original bytes are
now in `proof/s21-2026-09-08/recovery-2026-09-09/at6`, with an appended archive
manifest. No missing byte was reconstructed from a different run.

The held browser run on feed 64703 is `s21-5o8tsqk7`. Its original receipt
records candidate **`6d9a819`**, not the `1830b7a` embedded in the historical
image names. The recovered receipt/database and all eight artifacts match
their original recorded hashes. Its dashboard is 64704; the retained launcher
log records browser health requests during the hold. The existing image names
remain historical names. This recovery corrects their source association; it
does not make the two distinct runs identical.

The C21 pill image uses feed 49557 and dashboard 49558. Its original
`s21-5h_s7v0y` fixture retains the database, WAL, shared memory, incarnation
and launcher log. The recorded PID 67056 was absent at recovery. Original
file bytes and timestamps remained unchanged across copying and analysis.
SQLite opened only a separate working copy; a new closed backup is explicitly
labeled as derived on 2026-09-09. Integrity is `ok`, with no foreign-key
violations. Original database/WAL/shared-memory bytes are retained separately.

The recovered state matches these visible screenshot facts: the same feed is
on at revision/consent epoch 1, two items are enrolled, one capture succeeded
in daily slot 1, and “S20 matrix item 2” is committed as
`episode_cf538072f1d`. That item has one `ready` work row and a collecting run,
zero client attempts and zero applies. Production maps ready work to
`waiting_for_client`; the archived image displays that pill. This is a
comparison with retained state, not a new contemporaneous browser receipt.

**AT6's Python process exit status remains unrecorded.** The retained Claude
launch/result pair binds tool ID `toolu_01KnGtXmf35uPGZKWC9HgYM7` to the
correct original receipt path. Its command piped S21 output through grep,
then ran other probes after semicolons. The outer tool's successful completion
cannot establish the S21 child's status. The archive contains a narrowly
selected projection and source-record hashes, not unrelated conversation.
A read-only Security event 4689 query for PID 59556 in the exact launch window
was denied by Windows permissions; no event or exit code was recovered. No
inferred zero was added to the receipt.

Review verdict: the recovery is suitable for the unchanged AS-7/8/9 archive
checks. Preserve the outstanding exit-status failure unless actual original
process-exit evidence becomes available. AS-8/AS-9's complete replacement
observation remains separate and does not retroactively supply that value.
This review grants no installed C22/Phase 4 or release approval.

The wider verification also has 11 confirmation passes, 35 dashboard passes,
and 377 companion passes with 17 failures. Those 17 are from the historical
Phase 4 companion driver, whose subprocess prohibition prevents the current
isolated mirror writer from starting. Its audit records the blocked Popen
calls. The result stays failed; see
`PHASE3-COMPANION-DRIVER-NOTE-2026-09-09.md` for the reviewed future invocation
after the Phase 4 product repair. Groups overlap and are not unique totals.
The full outputs, commands, runner and guard are sealed in
`proof/p3-original-checks-2026-09-09/SHA256.json` (23 files).
