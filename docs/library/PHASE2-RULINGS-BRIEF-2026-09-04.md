# Phase 2 rulings and closure (run L), 2026-09-04

Run K integrated at `91589f7`: 876 passed, 3 skipped, 1 xfailed. Gemini's 33 independent
tests pass; Claude's 20 audit tests pass; Astra's 64 checks pass. Open items are the two
rulings the auditor requested (`SERVICE-AUDIT-2026-09-04.md` OBS-2, OBS-4) and the three
deviations Astra reported (`tests/library_work_astra/RUN-K-RECONCILIATION.md`). Fable rules
as follows under ORCHESTRATION-V1 rule 1; these become contract `phase2-v1.2-2026-09-04`.

## Rulings

- **R1 (OBS-2): keep the conservative reading.** Unpin and undo invalidate every work row
  for the item in every run that contains it (work `blocked`, manifest `pinned`/`changed`,
  proposals and previews deleted, `run_revision` bumped). A user decision changes what the
  Librarian should reconsider; a refresh plus re-claim is cheap and reversible. Document it
  in the contract's invalidation row.
- **R2 (OBS-4): surface the stored recovery state.** `_ready` returns `recovery_conflict`
  when `recovery_state='conflict'` and `recovery_pending` when `'pending'`, for every
  endpoint, with the same message shape. One code per state, not per endpoint.
- **R3 (deviation 1): no mutation during pending recovery.** `expire_attempts` and
  `list_work` must not call `_expire` unless `_ready` passes. A list during pending recovery
  reports the frozen lease state plus `recovery_state`; an expiry call returns
  `recovery_pending` and changes nothing.
- **R4 (deviation 2): pin-invalidated previews name their conflicts.** A preview refused
  because a pin arrived returns `error.details.conflicts` listing each `(video_id,
  shelf_id, pin_kind)` the way stale-revision conflicts already do.
- **R5 (deviation 3): contract-version constant becomes `phase2-v1.2-2026-09-04`** and the
  `list_work` response carries it as `contract_version`.

## codex (Astra): implement R2 through R5

Allowed files: `library_work.py`, `tests/library_work_astra/**`, `docs/library/PHASE2-CONTRACT-2026-09-04.md`
(append a "v1.2 rulings" section only). One check per ruling in `tests/library_work_astra/`.
Nothing else changes. Keep the frozen `(context, args)` surface and the tool schemas as
they are.

## gemini: independent tests for R1 through R5

Allowed files: `tests/test_library_work_*.py`. Write the tests from this brief's wording,
not from Astra's diff. They will fail until Astra's fix is merged; leave them failing (no
xfail) and say so. R1 is already implemented: its test should pass on this base.

Shared rules: own worktree; commit if git allows, else leave files and say so; never merge
or push; never open the live index; no model execution. Completion packet at the end.
