# Phase 3 S21 receipt: controlled end-to-end capture (2026-09-08)

Fable executed Astra's S21 procedure (`tests/library_work_astra/test_phase3_s21.py`, specified
in [PHASE3-ACCEPTANCE-2026-09-08.md](PHASE3-ACCEPTANCE-2026-09-08.md)) on the integrated
candidate at `61eeb07` (AT-2 repairs, `_backend_call`, legacy alignment; before Astra's AS-2
verdict landed). It is evidence for the gate S21 row, not an acceptance ruling; Astra rules.
Nothing here touched the resident helper, port 5179, the live index, a model, or a network
address other than the two ephemeral loopback ports the launcher opened.

## Result

**Automated: PASS. Browser observation: done.** One podcast episode from the local fixture
feed landed once with provenance and clips, was visible unfiled in the dashboard, produced
exactly one Phase 2 work row after commit, and a repeated detection and reconciliation made
no second charge, capture or run. Zero model calls, zero forbidden attempts.

| Observation (Astra's expected list) | Observed |
|---|---|
| Item lands once | `yoinks` 1 row, `source_capture_starts` 1, ledger `committed`/`succeeded`, allowance charged 1 of 10 |
| Provenance | `source_type=episode`, `platform=podcast`, metadata URL = fixture episode URL; feed URL, GUID and capture key persisted (AT-2) |
| Clips | one clip 12.5 to 21.75 s, deep link `.../episode#t=12`, from the synthetic cue |
| Unfiled visible state | dashboard Library: "1 uoinks", card under **Uncategorized**, "needs attention" |
| One Phase 2 work row after commit | `library_work` 1 row `ready`, `prepare_observations[0].after_commit = true`, outbox `enqueued` bound to `taxonomy-v3-2026-09-07` and the frozen prompt hash; dashboard item `classification.state = waiting_for_client` |
| Zero model calls | `model_calls = 0`, `forbidden_attempts = []`, one fixture download, one fixture transcript |
| Repeat detection | after +15 min and `reconcile_on_startup` + scheduler tick: still 1 start, no new run |
| Dashboard Sources | one healthy Podcast RSS source, "On (Standing capture)", 1/10 daily starts, back-catalog 0/25 |

Receipt directory `docs/library/proof/s21-2026-09-08/` (hashed in its `SHA256SUMS`):
`receipt.json` (held run, evidence database SHA-256 `ff073f54…`), `dashboard-library-unfiled.jpg`,
`dashboard-sources.jpg`, `receipt-first-diagnostic-run.json`, `receipt-original-launcher-FAIL.json`,
`launcher-diagnostic.diff`. Pinned inputs matched the procedure: taxonomy v3 `c3fdb4fb…`,
`assign.md` `cd22a3c1…`. Scratch roots retained under `_scratch/s21-*`.

## A defect in the launcher, for Astra

The unmodified launcher fails its own `model_calls == 0` assertion with `model_calls = 1`
(`receipt-original-launcher-FAIL.json`), after every product observation had already
passed. Cause: `server.py` imports `whisper_runner`, whose module-level `_probe_whisperx()`
attempts `import whisperx` once to record availability; the launcher's `NoModels`
meta-path guard counts that import attempt as a model call. WhisperX is not installed on
this machine (`ModuleNotFoundError` when the probe runs unguarded), and no transcription
engine ran: the transcript came from the launcher's synthetic injection.

The two passing runs used a diagnostic copy of the launcher whose only change is a
pre-import of `whisper_runner` before the guard is installed (`launcher-diagnostic.diff`,
three added lines; the trailing hunk is the 200-line window boundary, not a change). The
guard stays active for the whole run. Astra owns the launcher and should rule whether to
adopt that pre-import, count only imports that occur after helper start, or distinguish the
availability probe some other way; Fable did not edit the committed file.

## Rerun on the round-2 candidate (`d479899`, after AT-3)

Astra repaired the launcher in run AV-1r (the import-time WhisperX availability probe is
exempted from model-call accounting; every other guard stays). With that unmodified
launcher, S21 on `d479899` reports `AUTOMATED PASS; browser observation still required`
with `model_calls = 0`, `forbidden_attempts = []`, one fixture download, one fixture
transcript, one item committed once, one work row after commit, and no second charge.
Receipt: `receipt-at3-candidate-d479899.json` (evidence database SHA-256 `735b9879…`;
`server.py` `aad3d6eb…`, `source_subscriptions.py` `25cba538…` as pinned by the launcher).
The browser observation from the first run stands for the unchanged dashboard surfaces;
it was not repeated.

## Rerun on the round-3 candidate (`0bb97c8`, after AT-4)

Same launcher, same procedure: `AUTOMATED PASS`, `model_calls = 0`, `forbidden_attempts = []`,
one item once, one work row after commit, no second charge. Receipt
`receipt-at4-candidate-0bb97c8.json` (evidence database SHA-256 `4237cee4…`). Astra's AS-3
request for the real incarnation, capture-lock assertions and full provenance fields inside
the launcher is Astra's own file to extend; Fable did not edit it.

## Process-recovery receipt (AS-02)

`tests/library_work_astra/process_recovery_receipt.py --execute` (Fable-only launcher; not
collected by pytest) on `0bb97c8`: a real parent process took the persisted execution claim
for a start, spawned a real child and recorded it under `DATA_ROOT/source_children`, and was
killed while the child survived. The production `_ServerCaptureBackend.probe` (compiled from
this checkout's `server.py` as Astra's integration harness does) reported `running` with the
parent alive, `running` with the parent dead and the child alive (children `alive`, executing
incarnation `dead`), and `stopped` only after the child was killed. Receipt
`docs/library/proof/procrec-2026-09-08/receipt.json` (pids, claim record, per-step
observations, assertions, result PASS).

## Round-6 candidate `1830b7a` (after AT-6): receipts and C21 browser observation

- S21 with Astra's extended launcher: `AUTOMATED PASS`, 0 model calls, candidate SHA recorded,
  ownership observed at download, transcription, publication, publication_returned and
  settled (`receipt-at6-candidate-1830b7a.json`, evidence database alongside). Launcher file
  SHA-256 at execution `d17a84c6…` (committed bytes); command
  `python -B tests/library_work_astra/test_phase3_s21.py --execute-s21 --hold-seconds N` with
  `S21_CANDIDATE_SHA` set; interpreter `C:\Python314\python.exe`.
- Process recovery (`procrec-2026-09-08/receipt-at6-candidate-1830b7a.json`): PASS.
- Astra's real-child launch-interruption probe
  (`procrec-2026-09-08/real-launch-interrupt-at6-candidate-1830b7a.json`): the real child
  survived the injected interruption, child status `unknown`, probe `unknown` (no false stop),
  all created children reaped.
- Browser observation on the same candidate (Chrome on the held overlay, screenshots
  `dashboard-library-at6-1830b7a.jpg`, `dashboard-item-detail-at6-1830b7a.jpg`,
  `dashboard-sources-at6-1830b7a.jpg`): Library shows the single item unfiled
  (Uncategorized, "needs attention"); the item detail shows identity (podcast episode,
  "Untitled podcast", topic Uncategorized), the episode source link on the fixture port
  (`http://127.0.0.1:64703/episode`), speakers "not labeled yet", transcript checker and
  re-transcription state; Sources shows the standing subscription healthy, on, 1 of 10 daily
  starts, 0 of 25 back-catalog. **The per-item `waiting_for_client` classification state is
  not rendered by the dashboard source row**; it is visible only in the API response the
  launcher records (`source_status.items[0].classification.state`). That is a dashboard
  affordance gap for Astra to name, not a capture defect.

## Status

S21 is established on `61eeb07`, `d479899`, `0bb97c8` and `1830b7a` with ownership,
incarnation and provenance observations; AS-02 has real-process receipts. Astra rules in
run AS-6. C20 (the full consent browser matrix) and C22 (installed Inno, Ryan) remain.
