# Service audit, first pass: `library_work.py` on the frozen surface

**Date:** 2026-09-04 (run K, Phase 2 reconciliation) · **Auditor:** Claude · **Subject:** Astra's
`library_work.py` (1,748 lines) and `migrations/0027_library_substrate.sql` at `dd2251e`, read
against `PHASE2-CONTRACT-2026-09-04.md` and the frozen Python surface in
`PHASE2-RECONCILIATION-BRIEF-2026-09-04.md` (`phase2-v1.1-2026-09-04`). Plan:
`SERVICE-AUDIT-PLAN-2026-09-04.md`. Tests: `tests/test_library_service_audit.py` (new, 20 cases).

**Status: read-through complete; tests written, not executed by the auditor.** The worker
sandbox refuses `python`/`pytest`, so every verdict below is a code-trace verdict, and the
raw-receipt directory the plan reserves (`tests/.audit-run-<sha>/`) does not exist yet. The
orchestrator runs:

```
PYTHONPATH=. python -m pytest -q tests/test_library_service_audit.py -p no:cacheprovider
```

A test that fails on that run is a candidate defect and overrides the PASS below for its row.
No PASS banner is claimed; the per-case table is the deliverable.

Scope of this pass, per the brief: transaction boundaries, the three durable boundaries,
attempt-token and apply-key semantics, pin durability through rename, stale-undo refusal.
Rows outside that scope are marked DEFERRED with what a second pass needs.

## Summary

- **No contract violation found in scope.** Every traced path matches the clause quoted
  beside it. Twenty deterministic tests pin the traces; two are cross-connection or
  cross-process and exercise the real SQLite and store locks.
- **Two rulings requested** (OBS-2, OBS-4 below): behavior the contract does not name that
  Gemini's realigned tests will otherwise encode by accident.
- **Eleven observations** with `file:line`, none blocking: lock re-entrancy on Windows, a
  double-fault window, cosmetic status/label drift, and the Windows durability substitute.

## A. Transaction boundaries, tokens and keys

| # | Case | Trace (`library_work.py`) | Verdict | Test |
|---|---|---|---|---|
| A1 | Claim is one `BEGIN IMMEDIATE` | `claim_work` 507-546: `write_transaction()` at 513 opens `BEGIN IMMEDIATE` (`index.py:501`); reap 515, run/taxonomy recheck 516-517, `ready AND attempts<3` select 521, per-row `_fresh` 526 (source, taxonomy, pin recheck 449-463), token 529, attempt insert 541, `leased`/`attempts+1` 544, all inside the one transaction. No read of ready rows precedes the lock. | PASS | `test_a1_claim_is_one_begin_immediate_across_two_connections` |
| A2 | Token quality | `secrets.token_urlsafe(32)` at 529: 256 bits, 43 chars, matches `^[A-Za-z0-9_-]{43,128}$`; `work_id` is `token_urlsafe(24)` at 437 (32 chars) so never equal; client and submission keys are client strings compared in different columns. | PASS | `test_a2_attempt_token_quality` |
| A3 | Lease clock and caps | Claim deadline 531 (`now + lease_seconds*1000`), `lease_max_ms = now + 3,600,000` at 543; renew 573 `min(now + seconds, lease_max)`; expiry inclusive: `_attempt` 551 `now >= lease_expires_ms`, reaper 466 `<= now`. Owner: `_owner` 210-212 then `_attempt` filters by `client_id` 549-550. | PASS | `test_a3_lease_clock_renewal_cap_and_owner` |
| A4 | Three-claim ceiling | `attempts` incremented only at 544. Release/cancel 576, expiry 470, invalid submit 680-681 all derive `ready`/`blocked` from `attempts < 3` and never reset it; `refresh_run_item` refuses at 712-713 when exhausted. | PASS | `test_a4_three_claim_ceiling_survives_release_expiry_and_invalid_submit` |
| A5 | Receipts before lease checks | `submit_result` 643-696: envelope check 646-649, owner 650, then inside the transaction receipt by key 653-657 (hash mismatch conflicts 656, else stored `response_json` 657), consumed-token check 658-660, and only then `_ready`/`_expire`/`_attempt` 661-666. Stale token without receipt returns `stale_attempt` at 552 before any write. | PASS | `test_a5_receipts_are_checked_before_lease_checks`, `test_a5_stale_token_without_receipt_writes_nothing` |
| A6 | Submit is one transaction, no labels | Submission insert 684, attempt `submitted` 686, work state 687, manifest 688, proposals 691-693, run revision 694, preview purge 695: one `write_transaction`. `item_shelves` is never touched on submit. A `sqlite3.Error` inside is not caught by the inner `except LibraryError` 676 and rolls back via `index.py:504-507`; the wrapper returns `storage_error` 187-191. | PASS | `test_a6_submit_is_all_or_nothing` |
| A7 | Validation writes nothing | Deferred: identity 599-602, shelf 611-612, confidence 614-615 (`< .60`, no rounding), evidence 617-627 read correctly; not tested this pass. | DEFERRED | second pass |
| A8 | Quote matching rules | 621-623: NFC + whitespace collapse, case and punctuation preserved, one excerpt only. Read-through agrees; not tested this pass. | DEFERRED | second pass |
| A9 | Response budget | 535-540: candidate response measured in UTF-8; `packet_too_large` blocks the row via `_invalidate` 538 and returns without a lease. Not tested this pass. | DEFERRED | second pass |
| A10 | Preview is pure | `preview_apply` 922-944 writes only `library_previews` 933; `_compute_preview` 847-920 is read-only. | PASS by reading | (A12/A14 tests snapshot state around previews) |
| A11 | Churn arithmetic | 893-898, 914-917. Not tested this pass. | DEFERRED | second pass |
| A12 | Apply is one transaction after the record is durable | `apply_preview` 998-1021: store lock 1003, replay 1004, `BEGIN IMMEDIATE` 1005, retry/ready/enabled/preview/approval/ceiling rechecks 1006-1019 (all reads), `_publish_operation` 1020: referenced taxonomy files verified 1227 **before** the temp record is written and fsynced 786-789, hook `before_file_publication` 790-791, atomic publish 792-801, `_pending_record` 1237, hook `after_publication_before_db_commit` 1239, DB projection 1241, commit on block exit 1005, pins checkpoint 1289, hook `after_db_commit_before_response` 1296, response 1297. No DB write precedes publication; no response precedes commit. See OBS-1. | PASS | `test_a12_apply_publishes_record_before_any_db_write` |
| A13 | Zero partial changes on conflict | `_recheck_preview` 955-966 recomputes the full binding and raises before any write; details from `_revision` 814-818 carry revisions only. | PASS by reading | second pass adds the five-cause matrix |
| A14 | Apply idempotency, no-change receipts | `_operation_retry` 990-996 (same hash returns stored receipt; different hash conflicts). Zero delta: `changed=False` 1214, `after == before` 1216, receipt only 1269, no `library_applies` row 1271, sequence advances 1284. | PASS | `test_a14_apply_key_replay_and_zero_delta_receipt` |
| A15 | Pins: semantics and inverse | `_pin_delta` 1069-1110: pin preserves others and locks 1101-1108, primary if none 1104; move clears rows and sets policy 1094-1100; pin while exclusive conflicts 1086-1087; unpin clears lock and owned policy 1080-1084; `confidence=None` on every locked row 1104, 1108. Inverse holds complete prior rows and absence (`_delta` 827-841); `_project_delta` 1246-1257 deletes then reinserts the exact list. | PASS | `test_a15_pin_move_unpin_semantics_and_exact_inverse` |
| A16 | User intent capability | `mint_user_intent` 1023-1055 binds `digest(operation)` (token excluded 1036-1037), kind, session hash and `now + 300,000`; `_intent` 1057-1067 checks all four plus consumed; `consumed_by` is written inside `_project_record` 1276-1277, the same transaction as the receipt; identical retries pass `_operation_retry` then `_retry_session` 1157-1163 (session hash from the authoritative record). | PASS | `test_a16_user_intent_binds_operation_session_and_expiry` |
| A17 | Undo rules, stale-undo refusal | `_undo_delta` 1129-1138: expected revision must be current 1130, target `after_revision` must equal current 1134-1135, already-undone target conflicts 1136-1137. Undo publishes with `undo_of` 1153 and is itself a `library_applies` row, so undo-of-undo works. A stale undo whose intent was minted before a newer pin is refused with `expected/current` revisions. | PASS | `test_a17_undo_rules_and_stale_undo_refusal` |
| P2-4 | Pin durability through rename and activation | `item_shelves` keys on stable `shelf_id`; a renamed node keeps its id (`approve_taxonomy` 305-340). Activation touches only `shelf_versions.status` and `library_meta` 1258-1262; pinned rows are untouched. A retired or absent pinned identity adds `retired_pin` 888-891 and `_recheck_preview` refuses at 964-965. | PASS | `test_p24_pin_survives_rename_and_activation_and_blocks_on_retirement` |
| A18 | Refresh invalidates, preserves history | `refresh_run_item` 698-734 and `_invalidate` 440-447: attempts invalidated, proposals removed, submissions untouched, generation +1 at 726. Not tested this pass. | DEFERRED | second pass |
| A19 | Adapter/service validation parity | `validate_arguments` 154-158 with the frozen `_SCHEMAS` 1609-1748 on every registry method; operator methods use `_fields`/`_id`. Not tested this pass. | DEFERRED | second pass with `tests/test_library_adapters.py::INVALID` |
| A20 | No raw exceptions, no paths | No `str(exc)`, `repr(exc)`, `INDEX_PATH` or `output_root` in the module (grep); the wrapper 183-191 maps `sqlite3.Error`/`OSError` to fixed messages. Fault tests assert the injected text and the temp root name are absent from responses. | PASS | asserted inside A6, B1, B3 |

## B. Durable boundaries (P2-5)

The service exposes the plan's requested fault-injection hook (`crash_hook`, constructor
221, invoked at 790, 1239, 1296) with the three contract boundary names. The in-process
cases below use it or a targeted fault; Astra's own subprocess kills
(`tests/library_work_astra/test_durable.py`, `test_edges.py`) remain the process-kill
evidence and are not duplicated here.

| # | Kill point | Trace | Verdict | Test |
|---|---|---|---|---|
| B1 | After temp flushed, before rename | `_atomic_file` 778-808: temp written with `xb`, flushed, fsynced 786-789; `before_publish` 790; on failure the `finally` 807-808 unlinks the temp; `_pending_record` is still `None`, so the wrapper returns `storage_error` and the DB transaction rolls back. Reopen ignores `*.tmp` because `_read_records` globs `*.jsonl` 1173. | PASS | `test_b1_fault_before_publication_leaves_nothing_committed` |
| B2 | After rename, before `BEGIN IMMEDIATE` | The transaction is already open (OBS-1), so this boundary is "after publication, before any DB write": `__init__` 232-235 and `_recover_locked` 1353-1398 replay records past the DB checkpoint 1369-1374; the retry hits `_operation_retry`. Covered by Astra's parametrized kill tests at this boundary name. | PASS by reading | Astra `test_external_process_kill`, `test_forced_crash` |
| B3 | Inside the DB transaction after writes | `_project_record` 1264-1285 raising after `_project_delta` wrote rows: caught at 1242-1243 as `recovery_pending`, rollback, wrapper `_mark_pending` 184-185. Replay projects the committed record exactly once; the retry returns the record's receipt; one `library_applies` row; intent consumed on replay 1276-1277. | PASS | `test_b3_fault_inside_db_transaction_after_partial_writes` |
| B4 | After commit, before response | `_project_published` 1287-1297: pins checkpoint, `_pending_record=None`, hook, receipt. A failure in the response path yields `storage_error` (retryable) with the DB and record already in agreement; the retry returns the stored receipt. See OBS-3. | PASS | `test_b4_fault_after_commit_before_response` |
| B5 | Corrupt committed record | `_read_records` 1165-1202 verifies hash, sequence, previous hash, filename and revision chain; any failure sets `recovery_state='conflict'` 1395-1398. Covered by Astra `test_corrupt_record_stops`. See OBS-4 on the error code seen by lease calls. | PASS by reading | Astra |
| B6 | Missing committed record (middle and last) | Middle: sequence check 1181. Last: pins checkpoint 1195-1199 and DB checkpoint 1359-1360 both stop. Mutations refuse; `list_work` still answers. | PASS | `test_b6_missing_committed_record_stops_visibly` |
| B7 | Complete DB loss | `_recover_locked(rebuild=True)` 1375-1380 reprojects the folded stream for live items only; orphans counted 1385-1387. Covered by Astra `test_complete_db_loss`, `test_rebuild_and_orphan`. | PASS by reading | Astra |
| B8 | Two processes | `_locked_store` 736-776: exclusive-create once, byte lock via `msvcrt.locking` (Windows) or `flock`; never unlinked. The loser replays 1004/1116/1144 then fails `_revision` under the lock. | PASS | `test_b8_two_processes_pin_serialise_through_the_store_lock` |

## C. Migration and index hooks

DEFERRED to the second pass except what the reading confirmed: `Index.write_transaction()`
is `BEGIN IMMEDIATE` and refuses to nest (`index.py:486-507`); `upsert_yoink`/`delete_yoink`
call `_invalidate_library_sources` **after** their commit (`index.py:600`, `608`); the
migration in `migrations/` matches the contract draft's sixteen tables with the idempotent
DDL and checkpoint insert Astra listed (`0027_library_substrate.sql:1-5`).

## D. Reading items

| # | Item | Result |
|---|---|---|
| D1 | Model, network, process execution | None. Imports are stdlib plus `library_cards` (25); `msvcrt`/`fcntl`/`ctypes` are lock and rename primitives (752-766, 794). `library_cards` imports only `urllib.parse.urlsplit` (pure parsing). Test `test_d1_service_has_no_model_network_or_process_imports`. |
| D2 | Response before durability | None. Traced in A12; the only early returns are stored receipts (995, 657). |
| D3 | Client fields granting authority | None. `actor`, `max_churn`, `approved`, `force` are rejected by `additionalProperties:false` or `_fields`; `approved_churn_percent` is operator plus local confirmation only (969-977); authority comes from `RequestContext` alone. |
| D4 | Silent coercion | None found. `_check` uses `type(value) is` (123, 125, 127) so booleans never pass as integers; `.get` defaults are schema defaults only (524, 531, 925). |
| D5 | Deletion of history | None. No statement deletes or updates `library_submissions`, `library_attempts`, `library_applies`, `library_operation_receipts`, `library_manifest`, `library_work` or `library_runs` (grep; test `test_d5_service_never_deletes_or_rewrites_history_tables`). Proposals and previews are the only rows removed, as the contract requires on invalidation. |
| D6 | Windows specifics | Rename via `MoveFileExW` with `MOVEFILE_WRITE_THROUGH`, and `REPLACE_EXISTING` only for the mutable pins checkpoint (792-799); file handle closed before rename (786-789); no directory fsync on Windows (see OBS-9); lock file never recreated, kernel lock is the only authority (738-741). |

## Observations and requested rulings

None of these is a contract violation. OBS-2 and OBS-4 need a ruling because Gemini's
realigned tests will otherwise fix the current behavior as the specification.

**OBS-1. `BEGIN IMMEDIATE` is held across the file publish** (`apply_preview` 1005 →
`_publish_operation` 1233). The plan expected lock → publish → `BEGIN IMMEDIATE`. Astra's
order keeps the revalidation and the projection in one SQLite write lock, which is stronger
for correctness (nothing can slip between recheck and projection) at the cost of holding the
DB write lock through an fsync and a rename. Accepted as satisfying "one database transaction
after the authoritative record is durable": no DB write precedes publication.

**OBS-2 (ruling requested). Undo and unpin invalidate every work row for the item.**
`_project_record` 1278-1283 calls `_invalidate` (440-447) for each item in a pin/undo forward
delta, marking work `blocked`, the manifest `pinned` or `changed`, deleting proposals and
previews and bumping `run_revision`, in every run that contains the item. After an unpin, or
an undo of an apply, the source and taxonomy are unchanged, yet the run must be refreshed and
re-claimed (attempt budget permitting) before it can be previewed again; redo remains
available through undo-of-undo because the record carries the full delta. The contract's
invalidation row names only "source/taxonomy changed or item deleted". Ask: is this the
intended conservative reading ("permits a later reviewed assignment to reconsider it"), or
should unpin/undo leave accepted proposals in place and let the next preview recompute?

**OBS-3. Post-commit failures are reported as errors for a durable operation.** A failure
after commit in the response path returns `storage_error` (B4), and a failure writing the
pins checkpoint returns `recovery_pending` and marks the store pending (1290-1294). Both are
safe (the retry returns the receipt, replay is a no-op) and honor "do not acknowledge success
before file publication and DB commit"; the client sees a retryable error for work that
succeeded. Note for the client/adapter docs: always retry with the same key after a
retryable error.

**OBS-4 (ruling requested). Error code during a recovery conflict.** After a corrupt or
missing record sets `recovery_state='conflict'`, lease and submit calls fail through `_ready`
(262-264) with code `recovery_pending` and the message "Recover authoritative records before
mutation", while apply/pin/undo/mint fail with `recovery_conflict` from `_recover_locked`.
The plan accepted "the service's documented equivalent"; the split should be documented or
`_ready` should surface the stored state. Gemini's B5 test needs to know which to assert.

**OBS-5. Store lock is not re-entrant on Windows.** `_locked_store` (736-776) guards with a
re-entrant `RLock` but opens a new handle and calls `msvcrt.locking` each time; Windows
refuses a second handle in the same process for a region it already holds, so a nested
`_locked_store` would spin for ten seconds and fail with `store_busy`. No path nests today
(`recover_operations`, `export_library_state`, `apply_preview`, `pin_shelf`, `undo_apply`,
`mint_user_intent`, `approve_taxonomy` each take it once and call the unlocked
`_recover_locked`). Fragility only; a comment or an assertion would prevent a future nest.

**OBS-6. Double-fault window.** If a projection fault (1242-1243) is followed by a failure
inside `_mark_pending` (1299-1301), the second `sqlite3.Error` escapes the wrapper (the
`except` clauses at 183 and 187 are siblings) and `recovery_state` stays `ready`. Lease and
submit calls then run against a projection missing the published record until the next
apply/pin/undo/mint replays it (1004, 1116, 1144, 1042). Projection cannot be overwritten
(apply rechecks the revision after replay), but a claim could lease an item whose pin is
published and not yet projected. Low severity; two consecutive storage failures required.

**OBS-7. "Newest approved" tiebreak compares `created_at` as text** (`_pin_delta` 1090,
`ORDER BY ... v.created_at DESC`). `_stamp()` stores millisecond epochs as strings; the order
is correct while digit counts are equal (thirteen digits until 2286) and wrong across a
digit-length change, which only test clocks reach. Cosmetic.

**OBS-8. Submission and operation keys are global namespaces** (`library_submissions`
PK, `library_operation_receipts` PK). Two clients choosing the same literal key collide with a
permanent `idempotency_conflict` for the second. Contract-consistent (keys are client-chosen
hashes of the request by intent); the client docs should require UUID-strength keys.

**OBS-9. Windows durability substitute.** Directory fsync is unavailable on Windows; the
service relies on `MOVEFILE_WRITE_THROUGH` for the rename (792-799) and fsyncs the temp file
data before it (789). The contract accepts that the crash tests "do not by themselves certify
power-loss durability"; this is the documented substitute and should be named in the client
and packaging docs.

**OBS-10. Stale temp files after a kill are ignored, never removed.** Cleanup at 807-808 runs
only in the process that created the temp. Cosmetic; a startup sweep of `journal/*.tmp` older
than the newest committed record would be safe.

**OBS-11. Third release leaves the manifest `waiting` while the work is `blocked`**
(`_lease_action` 576-580 writes `waiting` on release regardless of exhaustion; `_expire`
465-471 does not touch the manifest). Activation is still blocked (`incomplete_manifest` on
`waiting`), and `list_work` shows `blocked`; only the manifest label understates the state.

**OBS-12. Undoing an activation leaves the version `superseded`, not `approved`** (1259).
`_taxonomy` accepts `superseded`, so nothing breaks; the status no longer says whether the
version was ever active.

**OBS-13. Pinning an existing agent row keeps its `evidence_json` on the user row** (1108).
The schema permits it, the inverse restores it exactly, and `confidence` is nulled. Note only,
in case a later export treats user rows as evidence-free.

## The FK failure Gemini hit (for codex's section, from this reading)

No service path reached in this audit can violate a foreign key: every insert into
`item_shelves`, `library_item_policy`, `library_proposals`, `library_applies` and
`library_user_intents.consumed_by` is preceded in the same transaction by the row it
references, and `_project_delta` skips items that are not live (1249-1250, 1256). Gemini's
apply/undo file seeds the substrate with raw SQL against an in-memory copy of the draft
migration; a fabricated `item_shelves` or `library_applies` row is the likeliest source.
Codex owns the verdict.

## What the second pass needs

1. A7, A8, A9, A11, A13 (five-cause matrix), A18, A19 against the frozen surface.
2. Section C on the disposable copy `uoink-index-copy-2026-09-04-upgraded.db` (sha256
   `2765cc35…4dfc`, verified before open), plus the injected-failure rollback of 0027.
3. Process-kill runs of B1-B4 through `tests/library_crash_runner.py` once Gemini's runner is
   realigned, recording receipts in `tests/.audit-run-<sha>/`.
4. Rulings on OBS-2 and OBS-4 folded into the contract addendum.
