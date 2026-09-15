# Codex run K completion packet, 2026-09-04

Status: codex reconciliation complete against `dd2251e`. The reported FK failure
is a fixture defect. No production or migration change is warranted for it.

## FK verdict and replacement evidence

`tests/test_library_work_apply_undo.py:130` inserts an `item_shelves` row for
`tax_v1/shelf_alpha` before `seed_substrate_manifest_and_proposals` creates that
taxonomy. SQLite rejects the missing `(version_id,shelf_id)` parent. No service
method has run when it fails.

The frozen SQL requires that parent in `shelf_nodes`. The fixture also bypasses
the approval/publication order in PHASE2-CONTRACT, “Identity and frozen input,”
clause 2: the authoritative taxonomy must exist before a run or pin references
it. Gemini should establish the baseline through an approved taxonomy and apply
using Fable's frozen `method(context, args)` surface.

`test_reconciliation.py` exercises the intended case through that surface:
ten baseline assignments, three replacements, exactly 30% churn, refusal at
the default 15% and at 29%, then successful apply at a trusted 30% approval.
Refused apply changes neither assignments nor the operation sequence. Exact
retry returns the original receipt. Final FK and integrity checks pass.

## Known deviations for independent tests

These remain unchanged. The two behavior findings were reproduced on disposable
fixtures; they are not inferred from the passing churn test.

1. **Lease mutations continue while recovery is pending.**
   `library_work.py:474` (`expire_attempts`) and `:481` (`list_work`) call
   `_expire` without `_ready`. PHASE2-CONTRACT “Pins and authoritative recovery,”
   paragraph at line 78, requires later mutations to wait for replay after a
   durable operation fails DB projection.

   Reproduction for each endpoint separately: claim the fixture row; mint a pin
   intent; inject `OSError` in `_project_record`; call `pin_shelf` and observe
   `recovery_pending`; advance the clock to the lease deadline; call the endpoint.
   Both returned `ok:true` and changed the row from `leased` to `ready`, while
   `(projection_revision,last_operation_sequence,recovery_state)` stayed
   `(0,0,"pending")`. Test that pending expiry cannot mutate the lease; a list
   response may still expose status without reaping.

2. **A new pin invalidates an apply without the required conflict details.**
   `library_work.py:946` (`_preview`) returns `preview_conflict` with `details:{}`
   when the pin has deleted the preview. Reproduction: accept work, create and
   approve its preview at revision 0, pin that item at revision 0, enable apply
   in the disposable fixture, then submit the original apply request. The result
   lacks expected/current revisions and affected item IDs, which
   PHASE2-CONTRACT “Service surface and adapter returns,” line 100, requires.
   The conflict itself correctly prevents application.

3. **Contract metadata is stale.** `library_work.py:27` still declares
   `phase2-v1-2026-09-04`; the reconciliation addendum at line 31 declares
   `phase2-v1.1-2026-09-04`. This is a metadata discrepancy; the service already
   uses the frozen Python calling convention and the JSON schemas are unchanged.

The `journal/*.jsonl` store layout differs from the original contract's
`operations/*.json` layout, but Fable's run J reservation 8 explicitly authorizes
it. It is not an unresolved service defect. This packet is not the independent
service audit assigned to Claude.

## Validation and handoff

- Original FK reproduction: one failure at test line 130, before a service call.
- Existing Astra suite before additions: **63 passed**.
- Added churn case alone: **1 passed**.
- Final Astra suite: **64 passed**, including the existing process-kill,
  concurrency, migration rollback and DB-reconstruction checks.

Final command, from the dedicated worktree in PowerShell:

```powershell
$env:PYTHONPATH='.'
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest -q tests/library_work_astra -p no:cacheprovider --basetemp=tests/library_work_astra/_work/pytest-run-k-final
```

Files added: `tests/library_work_astra/test_reconciliation.py` and this packet.
Commit unavailable: `git add` could not create the worktree metadata's
`index.lock` (permission denied). Both files remain untracked and uncommitted.
Production files, the migration, and Gemini's independent tests are unchanged.
Tests and probes used disposable roots under `tests/library_work_astra/_work`.
No live index, model execution, merge, or push was used.

Open work: Gemini realigns the independent fixture and tests the reported gaps;
Fable assigns any follow-up service repairs and metadata reconciliation. No
additional user input is needed for this codex section.
