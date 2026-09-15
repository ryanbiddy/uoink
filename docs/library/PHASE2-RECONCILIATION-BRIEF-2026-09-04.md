# Phase 2 reconciliation (run K), 2026-09-04: tests versus service

Run J integrated at `8f43313` (Astra substrate `7893034`, Claude adapters `34871ed`, Gemini
tests `6c5a2ae`). Full suite: **859 collected, 29 failing, all in Gemini's independent
`tests/test_library_work_*.py`**, plus one HTTP-bridge fixture failure already fixed.

## Fable's ruling (ORCHESTRATION-V1 rule 1)

The contract named the service functions but never froze their Python signatures. Gemini's
tests assumed keyword arguments and a `connection.library_service` attribute; Astra's service
takes `(context, args)` with `args` shaped exactly like the frozen tool-schema requests. Both
readings were defensible. The frozen Python surface from now on is Astra's, because it exists,
mirrors `tool-schemas.json` one-to-one, and carries 63 passing checks:

```python
from library_work import LibraryWorkService, RequestContext, LibraryError

svc = LibraryWorkService(index, store_root, clock=lambda: ms, librarian_apply_enabled=False)
ctx = RequestContext(authenticated=True, client_id="c1", session_id="s1",
                     operator=False, local_user_confirmed=False)
result = svc.claim_work(ctx, {"action": "claim", "run_id": "r1", "client_id": "c1", ...})
```

Every method is `method(context, args: dict) -> dict` with the `ok`/`schema_version`
envelope from the contract; errors raise or return `{ok: false, error: {...}}` per the
contract. Methods: `approve_taxonomy`, `prepare_run`, `refresh_run_item`, `list_work`,
`claim_work`, `renew_attempt`, `release_attempt`, `cancel_attempt`, `expire_attempts`,
`validate_result`, `submit_result`, `preview_apply`, `approve_preview`, `apply_preview`,
`pin_shelf`, `undo_apply`, `recover_operations`, `export_library_state`,
`rebuild_library_state`. `store_root` is the authoritative-records directory (reservation 8).
This addendum is contract version `phase2-v1.1-2026-09-04`; the JSON tool schemas are unchanged.

## gemini: realign the independent tests

Allowed files: `tests/test_library_work_*.py`, `tests/library_crash_runner.py`. Rewrite the
29 failing tests to the frozen surface above. Keep them independent: derive expected
behavior from the contract text and the tool schemas, not from reading Astra's code. Every
test that still fails after realignment is a candidate defect: leave it failing (no xfail),
and list each with the contract clause it enforces in your packet. Baseline to beat:
`PYTHONPATH=. python -m pytest -q tests/test_library_work_*.py -p no:cacheprovider`.

## codex (Astra): the one substantive failure, and any survivors

Allowed files: `library_work.py`, `migrations/0027_library_substrate.sql`,
`tests/library_work_astra/**`. One Gemini test failed with
`sqlite3.IntegrityError: FOREIGN KEY constraint failed` (in
`tests/test_library_work_apply_undo.py` at run J integration). Reproduce it against the
contract semantics regardless of the test's call shape; if it is a service defect, fix it
with a check in `tests/library_work_astra/`; if the test violated the contract, say exactly
which clause. Then wait for nothing else: your packet lists the defect verdict and any
behavior in the service you know deviates from `PHASE2-CONTRACT` clauses so Gemini's
realigned tests can target them.

## claude: service audit, first pass

Allowed files: `tests/test_library_service_audit.py` (new), `docs/library/SERVICE-AUDIT-2026-09-04.md`.
Execute the plan in your `SERVICE-AUDIT-PLAN-2026-09-04.md` against Astra's `library_work.py`
as a reader: transaction boundaries, the three durable boundaries, the attempt-token and
apply-key semantics, pin durability through rename, stale-undo refusal. Write the audit
findings with `file:line` and a small deterministic test per finding (you cannot run
shell; the orchestrator runs them). No production edits.

Shared rules: own worktree; commit if git allows, else leave files and say so; never merge
or push; never open the live index; no model execution. Completion packet at the end.
