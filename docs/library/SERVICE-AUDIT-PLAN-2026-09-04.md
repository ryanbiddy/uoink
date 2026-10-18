# Service audit plan: `library_work.py` transactions and forced crashes

**Date:** 2026-09-04 (run J, Phase 2 stage 1) · **Auditor:** Claude (service reviewer per
`PHASE2-BRIEF-2026-09-04.md` reservation 5 and the contract's ownership table) · **Subject:**
Astra's `library_work.py`, migration `0027_library_substrate.sql`, and the narrow `index.py`
hooks, on the integrated SHA Fable names for the next stage. **Status:** plan only. Nothing
below has been run; the module did not exist in this worktree when this was written.

Contract: `PHASE2-CONTRACT-2026-09-04.md` (`phase2-v1-2026-09-04`). This audit is the
independent verification the contract requires ("Astra cannot certify its own implementation
solely with its own tests"). It complements, and does not replace, Gemini's independent
`tests/test_library_work_*.py`, which are the acceptance evidence for gates P2-1 through P2-5.
Where Gemini's tests and this audit both cover a case, both must pass; where they disagree,
the reproduction goes to Fable per protocol rule 1.

## Ground rules

1. **Never the live index.** Every case runs on a fresh copy of
   `uoink-index-copy-2026-09-04-upgraded.db` (sha256
   `2765cc359805fb12f7a90aecd3dd0b34d884aa8cb3015785011bf400da3b4dfc`, verified before
   SQLite opens it) or on an empty schema-26 database created in a temp root, upgraded to 27.
   The authoritative record root is a temp directory, never `%LOCALAPPDATA%\Uoink\library\`.
2. **No model execution, no network.** Every "client" is a Python function that calls the
   service directly or through `uoink_mcp_tools.call_tool`. Results are fixtures.
3. **Observed versus expected, per case.** Each case records the SQL state before and after
   (`library_work`, `library_attempts`, `library_submissions`, `library_proposals`,
   `item_shelves`, `library_item_policy`, `library_previews`, `library_operation_receipts`,
   `library_applies`, `library_user_intents`, `library_meta`), the authoritative record
   directory listing with hashes, and the exact response. A case passes only if all three
   match the contract text quoted beside it.
4. **Injectable clock and injectable crash points.** The audit relies on the contract's
   required injectable clock (`now_ms` in the request context) and asks Astra for a
   documented fault-injection hook at the three durable boundaries (a callable the service
   invokes with a boundary name; tests raise or `os._exit` inside it). If the hook is absent,
   the crash cases run through Gemini's `tests/library_crash_runner.py` subprocess kills only
   and this plan records which cases were reached.
5. **I read the code, not only the tests.** Each transaction case below names the invariant
   and the code path I will trace by hand (`BEGIN IMMEDIATE` placement, what is inside versus
   outside the transaction, where the authoritative record is fsynced and renamed relative to
   the commit).

## A. Transaction boundaries (read-through plus tests)

| # | Case | Contract text | What I check |
|---|---|---|---|
| A1 | Claim is one `BEGIN IMMEDIATE` | "Claim uses `Index.write_transaction()` / `BEGIN IMMEDIATE`, reaps expired attempts, and selects `ready` rows" | Reap, recheck of source/taxonomy revision, row update to `leased`, attempt insert and `attempts` increment all inside one transaction; no read of `ready` rows before the lock. Two threads on two connections each call `claim_work` for a one-row run: exactly one token is current (`library_one_current_attempt`), the other gets zero packets, `attempts` is 1. |
| A2 | Attempt token quality | "cryptographically random, at least 256-bit attempt token distinct from work ID, client ID and submission key" | Token source is `secrets`; decoded length >= 32 bytes; 10,000 tokens from one process are unique; a token never equals `work_id`, `client_id`, or a later `submission_key`; the schema's `^[A-Za-z0-9_-]{43,128}$` is met. |
| A3 | Lease clock and caps | "Leases default to 900 seconds, range 60-900; renewal extends from server time but never past 3,600 seconds after the initial claim ... `now >= lease_expires_ms` is expired" | With the injected clock: claim at t0 with 900 s, renew at t0+800 with 900 s yields t0+1700; renew repeatedly until the cap: expiry never exceeds t0+3600; at exactly `now == lease_expires_ms` the attempt is expired (boundary inclusive); a renew by a different `client_id` on the same token is refused without changing expiry. |
| A4 | Three-claim ceiling is not resettable | "Do not reset the three-claim ceiling through `release`, invalid output, cancellation or arbitrary client fields" | Claim, release, claim, release, claim, release: `attempts` is 3 and the row is `blocked`, visible in `list_work`, and a fourth claim returns zero packets. Repeat with expire and with invalid submit in place of release. A refresh (`refresh_run_item`) on an exhausted row leaves it exhausted; only a new run frees the item. |
| A5 | Submit: receipts before lease checks | "Check recorded receipts before current-lease checks, after authentication" | Submit a valid result; expire the lease with the clock; resubmit the identical request: the exact stored `response_json` bytes come back and no second submission/proposal row appears. Change one byte under the same key: `idempotency_conflict`, no write. Submit a second, different result under the consumed token with a new key: `idempotency_conflict`. A stale token with no receipt: `stale_attempt`, zero proposals. |
| A6 | Submit is one transaction, no current labels | "store immutable submission and proposed memberships; no current labels written" | After an accepted submit, `library_proposals` has 1-3 rows with exactly one `is_primary=1` and `item_shelves` is unchanged (row count and content hash before/after). The submission insert, attempt state change, work state change and proposals are inside one transaction: a fault injected after the submission insert leaves nothing (all-or-nothing). |
| A7 | Validation writes nothing | P2-2 list: "Wrong/missing/extra/duplicate IDs, malformed nested output, NaN/Infinity, foreign shelf, joined-clip quote and stale revisions write zero current labels; rejects remain visible" | Each malformed case yields a stored rejection (`outcome='rejected'` with reasons), the attempt is retired, the row is `ready` (attempts < 3) or `blocked`, and `item_shelves` plus `library_proposals` are unchanged. Cases: `video_id` not matching the row; `source_revision` mismatch; `taxonomy_revision` mismatch; `packet_hash` mismatch; duplicate `shelf_id` in memberships; `shelf_id` from a non-active version; a quote spanning two excerpts; a quote absent from the named excerpt after NFC and whitespace normalisation but present in another; `confidence` 0.59 (must be unmapped or rejected, never accepted by rounding); `basis=fetched_full` whose reconstructed full card hash differs. |
| A8 | Quote matching rules | "Normalize Unicode to NFC and collapse whitespace for matching; preserve case and punctuation. A quote must be a substring of one specified excerpt" | Accepted: NFD input against NFC excerpt; runs of spaces/newlines collapsed. Rejected: case change; punctuation change; a quote equal to the concatenation of the ends of two adjacent excerpts. |
| A9 | Response budget | "A claim response is at most 122,880 serialized UTF-8 bytes ... taxonomy alone is at most 16,384 bytes ... `packet_too_large` ... block that row" | A run with 12 ready items whose cards are near 8,192 bytes returns fewer than 12 complete packets with no lease issued for omitted rows; a run whose single card cannot fit returns `packet_too_large` and the row becomes `blocked` with a visible reason. |
| A10 | Preview is pure | "Preview creation changes no current assignment, pin, activation or projection revision" | Snapshot `item_shelves`, `library_item_policy`, `library_meta.projection_revision`, `shelf_versions.status` before and after `preview_apply`; identical. `library_previews` gains one row whose `delta_hash` recomputes from its `forward_json`/`binding_json`. |
| A11 | Churn arithmetic | "Churn numerator is the number of distinct such items whose membership or primary changes ... Denominator is ... previously assigned, nondeleted items ... If the denominator is zero, churn is `0/0`, presented as `0.0` with `initial_filing=true`" | Baseline of 20 assigned items: change primary on 2, add a secondary on 1, rename a shelf only on 1 -> numerator 3, denominator 20. Empty baseline -> `0.0`, `initial_filing=true`, `can_apply=false` without approval. 100*changed > 15*baseline refuses apply; a client-supplied `max_churn` field is a schema rejection (adapter) and, called directly, ignored by the service. |
| A12 | Apply is one transaction after the record is durable | "Successful apply writes the forward delta, inverse delta, activation and membership changes, one journal receipt, and `projection_revision + 1` as one database transaction after the authoritative record is durable" | Trace the order in code: lock, recheck bindings, taxonomy record persisted, temp operation record written and flushed, atomic publish, then `BEGIN IMMEDIATE`, then commit, then response. Fault inside the DB transaction leaves the file published and the DB unchanged and `recovery_state='pending'`. |
| A13 | Zero partial changes on conflict | "A stale revision, changed source, new pin, changed taxonomy or altered delta returns a conflict with zero partial changes" | For each of the five staleness causes, apply returns a conflict whose details name expected/current revisions and affected IDs, and the full table snapshot is identical to before. Confirm the details carry no source paths. |
| A14 | Apply idempotency and no-change receipts | "Replaying the same operation key/request returns its original receipt without changing the revision; changed content under that key is a conflict. A zero-delta apply returns a no-change receipt and does not create a fictitious revision" | Replay: identical receipt bytes, revision unchanged, no new `library_applies` row. Changed content, same key: conflict. Zero delta: a `library_operation_receipts` row exists, `library_applies` has no new row, `projection_revision` unchanged, `last_operation_sequence` advanced by one. |
| A15 | Pins: semantics and inverse | "`pin` adds/locks that membership ... `move` replaces all memberships with one primary locked membership and sets an item-level exclusive-move policy ... `unpin` leaves the membership in place, clears its lock" | Pin onto an item with two agent memberships keeps both and locks one; if no primary existed it becomes primary. Move leaves exactly one locked primary and `exclusive_move=1`; an agent apply that would add a membership to that item is excluded and reported. Pin to another shelf while exclusive: conflict. Unpin: row stays, `locked=0`, policy cleared. Every pin/move/unpin has an inverse in its receipt that, replayed, restores the exact prior rows (including absence). `confidence IS NULL` on every locked row (the `item_shelves` CHECK). |
| A16 | User intent capability | "binds the canonical operation (excluding the token), expected revision, user session and a 5-minute expiry. It is consumed atomically with the operation, with identical retries allowed" | A token minted for `pin video A shelf X rev 7` is refused for `move`, for shelf Y, for rev 8, for another session hash, and after t+300 s. A pin with a valid token consumed once; the identical retry (same operation key) returns the stored receipt; a different operation key with the same token is refused. `library_user_intents.consumed_by` is set in the same transaction as the receipt. A token supplied to a registry adapter without the dashboard route (fabricated, 43 chars) is refused. |
| A17 | Undo rules | "Initially allow only a target whose `after_revision` is the current revision ... Repeating the undo key returns its stored receipt; attempting a second undo of the same target with a different key conflicts. The newer undo operation may itself be undone" | Apply (rev 7->8), pin (8->9), undo of the apply: conflict (a newer pin exists). Undo of the pin: succeeds (9->10) and restores membership, primary, lock and policy exactly. Repeat with the same key: same receipt, revision 10. Second undo of the pin with a new key: conflict. Undo of the undo: succeeds (10->11) and the pin is back. |
| A18 | Refresh invalidates, preserves history | "Refreshing changed input increments packet generation and run revision, invalidates previews and accepted proposals, and preserves old attempt/submission records" | After an accepted submit and a preview, change the item's source (reindex on the disposable copy) and `refresh_run_item`: `packet_generation` 2, `run_revision` +1, the preview is unusable (apply returns conflict), proposals for that item are invalidated, old attempt and submission rows remain byte-identical, manifest disposition `changed`. |
| A19 | Adapter/service parity of validation | "recursive service validation remains mandatory on every transport" | Every malformed request in `tests/test_library_adapters.py::INVALID` is also sent straight to the service function, bypassing the adapter validator, and is rejected with a validation error rather than executed. Anything the service accepts that the frozen schema rejects is a finding. |
| A20 | No raw exceptions, no paths | "Return no raw database exceptions or paths" | Grep every error path in the module for `str(exc)`, `repr(exc)`, `INDEX_PATH`, `output_root` reaching a response; force a `sqlite3.OperationalError` (locked database from a second connection) during claim and submit and confirm the response contains neither the SQL text nor a path. |

## B. Forced-crash cases (P2-5)

Each case runs in a subprocess against a disposable copy plus a temp authoritative root,
is killed (SIGKILL / `TerminateProcess`, not a Python exception) at the named boundary, then
the store is reopened once and `recover_operations` runs. The three boundaries are the
contract's: (1) before file publication, (2) after publication / before DB commit, (3) after
commit / before response. Operation kinds: apply, pin, undo (nine kills), plus the two
misuse cases.

| # | Kill point | Expected after reopen and one replay |
|---|---|---|
| B1 | After the temp record is written and flushed, before the atomic rename | No committed record; the temp file is ignored (and may be removed); DB unchanged; `recovery_state='ready'`; the same request with the same key succeeds fresh; revision advances exactly once overall. |
| B2 | After the atomic rename, before `BEGIN IMMEDIATE` | The record is committed; replay projects it: DB matches the forward delta, `projection_revision` is the record's `after_revision`, `library_operation_receipts` has the record's receipt; the retried request returns that original receipt without a second record or a second revision. |
| B3 | Inside the DB transaction (after some writes, before commit) | Same outcome as B2: SQLite rolls back the partial transaction, replay projects the committed record exactly once. Verify no duplicate `item_shelves` rows and exactly one `library_applies` row for the sequence. |
| B4 | After commit, before the response is sent | DB and record agree; `recovery_state='ready'`; the retried request returns the stored receipt; revision unchanged by the retry. |
| B5 | Corrupt committed record (flip one byte in the middle of the sequence) | Startup stops visibly: `recovery_state='conflict'` (or the service's documented equivalent), every mutating call returns `recovery_pending`, read calls still work, and the log names the sequence number. Recovery does not skip the record and continue. |
| B6 | Missing committed record (delete one file from the middle) | Same as B5. Deleting the last record only is also a stop, not a silent truncation. |
| B7 | Complete DB loss | Delete the disposable DB (verify by hash that it is the disposable), rebuild corpus identities and clips, reload `taxonomies/<hash>.json`, replay operations: pins, exclusive policy, activation and revision match the pre-loss snapshot; a pin on an item absent from the rebuilt corpus is retained as an orphan and counted, not resurrected and not dropped. |
| B8 | Two processes | Two subprocesses attempt `pin_shelf` on the same item concurrently: the cross-process lock serialises them; exactly one wins at the expected revision, the other gets a conflict, and the record sequence has no gap or duplicate. |

Success criteria for section B are exact: receipt bytes equal, `projection_revision` equal,
record sequence contiguous, and the set of `item_shelves` rows equal to the expected forward
projection. "Roughly right" is a failure.

## C. Migration and index hooks (P2-0, with Astra's packet)

- Fresh schema-26 DB and the populated copy both upgrade to 27; reopening applies nothing
  further; `PRAGMA foreign_key_check` and `PRAGMA integrity_check` are clean; FTS tables are
  untouched; `library_work`, `item_shelves`, `library_proposals` are empty after upgrade.
- An injected failure inside 0027 (a duplicated `CREATE TABLE` appended in a copy of the
  migration) rolls back to 26 with no partial tables.
- `index.py` hooks: `write_transaction()` is `BEGIN IMMEDIATE`; the rebuild path
  (`rebuild_all_clips`, `--rebuild-index`) preserves `item_shelves`, `library_item_policy`
  and pins, and invalidates affected work/previews after the source commit, not before.
- The migration copied into `migrations/` is byte-identical to
  `docs/library/phase2-contract/0027_library_substrate.sql` except for changes Astra lists in
  the completion packet; each listed change is checked against the contract.

## D. What I will read for, beyond the tests

1. Anything that calls a model, imports `urllib`, `requests`, `httpx`, `anthropic` or
   `openai`, or spawns a process. There must be none (D-17).
2. Any path where a response is sent before the authoritative record is durable, or before
   the DB commit, or where the record is fsynced but the directory is not.
3. Any place a client-supplied field (`actor`, `max_churn`, `approved`, `force`) influences
   authority or thresholds.
4. Any silent coercion: `int()` on a bool, `float()` on a string, rounding of confidence,
   `.get(..., default)` that turns a missing identity into a valid one.
5. Any deletion of rejection or attempt history, or any UPDATE of `library_submissions`.
6. Windows specifics: `os.replace` onto an existing name, file handles held open across the
   rename, `fsync` on the directory (not available on Windows; document the substitute), and
   the exclusive-create lock file's stale-lock handling after a kill.

## E. Outputs

`docs/library/SERVICE-AUDIT-2026-09-04.md` with one row per case above: observed, expected,
PASS/FAIL, and for every FAIL a minimal reproduction (SQL state and the exact call) that Fable
can hand to Astra. Raw receipts and record listings in
`tests/.audit-run-<sha>/` (disposable, hashed, not committed). No PASS banner without the
per-case table.

## Open items for Astra before the audit can run

1. Signature convention. The adapters call `library_work.<method>(arguments: dict,
   context: dict)` with `context` carrying `index`, `now_ms`, `apply_enabled`, `transport`,
   `actor`, `contract_version`, `schema_version` (and, for the intent route, `session_hash`
   and `intent_ttl_ms`). If the module's signatures differ, `uoink_mcp_tools._library_invoke`
   is the single place to adapt; say so in the packet and I will change it there.
2. `mint_user_intent(arguments, context)` is expected by the dashboard route
   (`POST /library/intent`), returning `{ok, schema_version, user_intent_token, expires_ms,
   kind, request_hash}` and writing `library_user_intents`. It is not in the contract's
   function table because the table predates the route reservation; if Astra prefers another
   name, `uoink_mcp_tools.LIBRARY_INTENT_METHOD` is the one constant to change.
3. A fault-injection hook at the three durable boundaries (rule 4 above).
4. The `counts` shape returned by `list_work` (flat by state, or nested under `work` and
   `manifest`); `uoink_mcp_tools.library_status` accepts both, and `/health` reports
   `waiting_for_client` from the `waiting_for_client` field, so only the counts matter here.
