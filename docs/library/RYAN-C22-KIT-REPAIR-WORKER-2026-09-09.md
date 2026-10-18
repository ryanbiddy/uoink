# C22 kit repair — Grok worker (2026-09-09)

Worker: grok. Brief: `docs/library/RYAN-C22-KIT-REPAIR-BRIEF-2026-09-09.md`.
Original kit patch applied: `docs/library/patches/ryan-c22-kit-original-2026-09-09.patch`.
AS-7: `docs/library/PHASE3-ACCEPTANCE-7-2026-09-08.md`. Original kit brief:
`docs/library/RYAN-INSTALLED-C22-KIT-BRIEF-2026-09-09.md`.

No subagents, Inno, port 5179 (including negative probes), live index, paid
API, API keys, client/model execution, new fetch, commits, push, or merge.
`ANTHROPIC_API_KEY` unset. `librarian_apply_enabled` stays false.

**Kit `9c866bb0` is rejected as an installed verification instrument.** Its
19-pass claim is stub-only. No installed credit. No full unsafe process suite
is inferred. The original patch is preserved in the worktree; original test
assertions were not edited.

**No claimed installed pass.** Ryan has not run the sealed kit on a throwaway
profile against the isolated installed helper. Astra owns final bundled
verification after integration.

## Five repairs

### 1. Actual helper API (no stub-only routes)

Removed all scenario dependence on `GET /c22/snapshot` (stub-only). Scenarios
now drive production routes:

- `GET /health`, `GET /sources`, `GET /sources/status`
- `POST /sources` (`register_source`)
- `POST /sources/consent-intent`, `POST /sources/consent`
- `POST /podcasts/feeds`, `GET /podcasts/feeds`, `POST /podcasts/feeds/poll`
- `GET /podcasts/episodes`
- `POST /podcasts/episodes/download`, `/transcribe`, `/to-corpus`
- `POST /helper/quit`

`POST /extract` on an RSS URL is recorded and explicitly **not** counted as
podcast publication. Stub `stub_helper.py` remains for instrument mechanics
and original tests; it is not the final integration check.

### 2. Outcomes from measured persisted state

- `collect_snapshot` reads `yoinks.video_id`; it does not invent
  `c22legacytimed000` / `c22legacytext00000`.
- Empty replay requires schema **30**, matching start counts, no invented
  yoinks, integrity `ok`.
- Populated replay requires preserved timed/text identities, original
  markdown/sidecar bytes, idempotent yoink counts, schema 30.
- Protected Phase 2 compares before/after hashes; unaccounted enqueue
  deltas fail.
- Browser protocol without an image is **unexecuted in all modes**, including
  synthetic.
- Missing evidence fails or stays unexecuted. No `or True`.

### 3. Owned stop

Stop holds the `Popen` handle. Identity is pid + exact creation time +
executable on that live object. Missing creation/executable is unknown, not
dead. No `taskkill`, no 2s tolerance on the kill path. HTTP `/helper/quit`
is attempted first; the handle is then terminated and waited. Exit codes are
recorded. Cleanup runs on missing token, failed health, exceptions, and
relaunch. Surviving unregistered children from registration-failure are
preserved in evidence and not treated as the helper.

### 4. Agreed isolation interface

Inno argv (recorded, not executed):

`/VERYSILENT /NORESTART /SUPPRESSMSGBOXES /DIR="<app>" /ISOLATED=1 /PROFILE="<root>" /PORT=<non-5179>`

Runtime: `--isolated-profile`, `--isolated-port`, optional
`--isolated-from-install-dir` when `uoink_install_isolation.py` and
`isolated-install.json` are present. Token at `<profile>/token.txt`. Marker
`isolated-install.json`. Declared profile is the data root (`index.db` there).
`LOCALAPPDATA` is pointed at a canary, not the profile and not the live
library. Live `index.db` mtime/hash is snapshotted before env changes.

Source-runtime synthetic verification provisions the archived first isolation
source (`docs/library/proof/ryan-install-review-2026-09-09/original.patch`)
into a disposable scratch copy of current `server.main`. Rejected
`--isolated-stop` is not run. No Inno.

### 5. Full `server.main` and original child methods

Source-runtime launches original `server.py` `main()` with production
reconciliation enabled. Only acquisition/transcription wraps and declared
`C22_INJECT` hooks are permitted. Guard sitecustomize is hashed; bundled
site-packages install is restored when present.

Child launch / interrupt / registration-failure run against original
`source_subscriptions.record_child_launch_intent` /
`record_child_start` (product module from the scratch tree), not a stub
`c22_children` table.

## Source-runtime synthetic results (not installed credit)

Receipt: `_scratch/c22-kit/r-una8_nq9/receipt`. Helper
`GET /health` returned `migration_version: 30`, `apply_enabled: false`,
declared profile was the data root, canary was not used as data root, live
index unchanged.

| ID | Status | Evidence |
|---|---|---|
| `install` | unexecuted | Inno argv recorded; `/ISOLATED=1 /PROFILE= /PORT= /DIR=` present |
| `installed_provenance` | unexecuted | Provenance command ran (`nousersite 1`, scratch `server.py`); no bundled `python.exe` so not installed credit. Schema 30 measured. |
| `empty_migration_replay` | pass | Schema 30 both opens; no invented rows |
| `populated_legacy_replay` | pass | Timed/text identities retained; markdown/sidecar bytes retained; idempotent |
| `one_off_capture` | pass | One publication; zero standing charges; `/extract` not counted as publication |
| `manual_first` | **fail** | `POST /sources` `unsupported_source`: loopback/private targets refused. Feed add succeeded with `source_id` null. Product failure preserved. |
| `standing_first` | **fail** | Same loopback refusal; 0 standing charges. Product failure preserved. |
| `whole_helper_relaunch` | pass | Held-handle stop; new pid/creation; no `taskkill` |
| `registered_child_lifetime` | pass | Product `source_subscriptions` child record; child liveness `alive` |
| `launch_interruption` | pass | `unresolved_launch: true` after intent, no spawn |
| `registration_failure` | pass | Unresolved launch plus surviving unregistered sleeper |
| `browser_state_checkpoint` | unexecuted | Protocol + snapshot ready; screenshot null in all modes |
| `protected_phase2_state` | pass | Before/after hashes accounted; apply false |
| `upgrade_operator_step` | unexecuted | Same-version reinstall labeled `same_version_reinstall` |

## Verification counts

Python 3.14.6 (`C:\Python314\python.exe`). `ANTHROPIC_API_KEY` unset.
Scratch: `_scratch/c22-kit`.

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
python -B -m pytest -q -ra --tb=line -p no:cacheprovider `
  --basetemp=_scratch/c22-kit/pytest-final `
  tests/test_install_receipt_c22_kit.py `
  tests/test_install_receipt_c22_kit_repair.py
```

**Combined: 26 passed, 2 failed, 72.99 s, exit 1.**

| File | Result |
|---|---|
| `tests/test_install_receipt_c22_kit.py` (original assertions unchanged) | **17 passed, 2 failed** |
| `tests/test_install_receipt_c22_kit_repair.py` (new) | **9 passed** |

Original failures kept (assertions not edited after the run):

1. `test_plan_inno_does_not_execute` — still asserts `/ISOLATEDPROFILE=`; kit now records agreed `/ISOLATED=1 /PROFILE= /PORT= /DIR=`.
2. `test_synthetic_helper_scenarios_and_verdict` — stub helper cannot satisfy production podcast routes / measured oracles (`manual_first` fail; `/podcasts/episodes` 404 on stub). Stub-only 19-pass is rejected.

Separate original-only run after the `--isolated-from-install-dir` guard:
**17 passed, 2 failed, 18.32 s.**

Repair unit subset (no full helper): **8 passed, 1 deselected, 1.66 s.**
Source-runtime helper/oracles test: **1 passed, 41.50 s.**

```powershell
python -B scripts/install_receipt/cli.py list-scenarios
```

Exit 0. Fourteen scenarios listed.

## Exact safe operator commands (still unexecuted here)

Do not run Inno or port 5179. Receipt root must not already exist. Isolated
port must not be 5179. Token is `<profile>\token.txt`.

```powershell
$receipt = Join-Path $env:USERPROFILE 'Documents\Uoink Install Receipt 2026-09-09'
python -B scripts/install_receipt/cli.py plan-install `
  --installed-app '<absolute path with a space>\Uoink Installed' `
  --package '<absolute>\Uoink-Setup-3.8.0.exe' `
  --package-sha256 '<Astra-sealed digest>' `
  --isolated-profile (Join-Path $receipt 'profiles\empty') `
  --isolated-port 18081 `
  --receipt-root $receipt
```

Recorded Inno shape (this worker must not execute it):

```text
Uoink-Setup-<version>.exe /VERYSILENT /NORESTART /SUPPRESSMSGBOXES /DIR="<app>" /ISOLATED=1 /PROFILE="<profile>" /PORT=<non-5179>
```

Start (after Astra isolation integration and sealed install):

```text
"<app>\python\python.exe" -B -s "<app>\server.py" --isolated-profile "<profile>" --isolated-port <non-5179>
```

Stop is the kit-owned Popen handle / `/helper/quit` path in this repair, not
the rejected isolation `--isolated-stop` implementation.

## Remaining unexecuted / operator-owned

| Item | Why |
|---|---|
| Inno install / reinstall / upgrade | Recorded only; this worker must not start Setup |
| Installed bundled Python 3.11.9 provenance | Source-runtime used `C:\Python314\python.exe`; no bundled `python\python.exe` |
| Browser screenshot | Protocol without an image is unexecuted in all modes |
| Standing capture against loopback RSS | Production `register_source` refuses loopback/private URLs (`unsupported_source`). Reported, not hidden. |
| Installed pass | Forbidden until Ryan runs the sealed kit |
| Isolation `--isolated-stop` | Rejected first-worker stop; not run |
| Control Room `3a3bd6cb` ownership repair | Read-only; not edited |

## Files changed (new kit files only)

- `scripts/install_receipt/` — original kit plus repairs: oracles, owned stop,
  source-runtime provisioner, child instrument, scenarios/launcher/guards/
  evidence/manifest/constants/fixtures
- `tests/test_install_receipt_c22_kit.py` — original file from the archived
  patch; **assertions unchanged**
- `tests/test_install_receipt_c22_kit_repair.py` — new review tests
- `docs/library/RYAN-INSTALLED-C22-KIT-WORKER-2026-09-09.md` — original worker
  notes from the patch
- `docs/library/RYAN-C22-KIT-REPAIR-WORKER-2026-09-09.md` — this report

No production, existing tests, fixtures, assertions, or runbook files were
modified. Nothing was committed or pushed.

## Open questions

1. Standing C22 capture against a loopback fixture cannot register a Phase 3
   source until product URL policy allows the declared fixture ports, or Ryan
   uses a non-loopback fixture that still stays on the helper/fixture
   allowlist. Do not paper over this with a custom route.
2. Confirm Astra's sealed Inno surface matches `/ISOLATED=1 /PROFILE= /PORT=
   /DIR=` (the first kit's `/ISOLATEDPROFILE` `/ISOLATEDPORT` is rejected).
3. Seal package hashes; this kit will not invent them.
4. Final bundled interpreter / Inno execution remains Astra + Ryan.
