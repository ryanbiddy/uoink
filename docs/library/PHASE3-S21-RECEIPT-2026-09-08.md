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

## Status

S21's product observations are established on `61eeb07`. Astra's AS-2 verdict (NOT
ACCEPTED, AS-01/02/03/06 open) postdates this run; the AT-3 repairs will change
`source_subscriptions.py`, `server.py` and `podcasts.py`, so S21 must be rerun on the
repaired candidate before any acceptance claim. S22 (installed-tree run) is still owed.
