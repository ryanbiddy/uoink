# C22 scenario and operator-path repair — Grok worker (2026-09-09)

Worker: grok. Brief: `docs/library/RYAN-C22-SCENARIO-TRUTH-REPAIR-BRIEF-2026-09-09.md`.
Second-kit archive applied: `docs/library/proof/ryan-c22-review-02-2026-09-09/original.patch`.
AS-7: `docs/library/PHASE3-ACCEPTANCE-7-2026-09-08.md` C22 list (lines 127–145).
Original kit brief: `docs/library/RYAN-INSTALLED-C22-KIT-BRIEF-2026-09-09.md`.
Kit repair brief: `docs/library/RYAN-C22-KIT-REPAIR-BRIEF-2026-09-09.md`.

No subagents, Inno, port 5179 (including negative probes), live index open/hash,
paid API, API keys, client/model execution, external fetch, commits, push, or
merge. `ANTHROPIC_API_KEY` unset. `librarian_apply_enabled` stays false.
Source-runtime mode remains explicitly synthetic. No installed credit.

**Kit `6accc421` is rejected as an instrument.** Its worker reports 26 passes
and two failed original checks; the source-runtime receipt itself had two
failed capture scenarios and several unexecuted boundaries. Those original
assertions and failed results are preserved. Both original kit test files
remain frozen:

- `tests/test_install_receipt_c22_kit.py`
- `tests/test_install_receipt_c22_kit_repair.py`

Owned scope: non-p4 files under `scripts/install_receipt`, new regressions, and
this report. Production code, old acceptance fixtures, and original kit
assertions were not edited.

## AS-7 C22 receipt (Ryan, still open)

Ryan's one receipt on the final repaired candidate must include candidate/Inno
hashes, empty and populated replay, one-off plus both capture orderings,
helper termination/relaunch with real child lifetime, launch interruption and
registration failure, post-restart browser state, and protected Phase 2
before/after hashes. This worker delivers executable measured **source-runtime**
scenarios for the instrument defects. It does not execute Inno, contact 5179,
or claim installed credit.

## Repairs

### 1. Live index, guards, port, IG_FORBIDDEN_LIVE

- Removed every live-index open/hash. `live_index_guard` stores the forbidden
  path as a string only (`IG_FORBIDDEN_LIVE` if set, else the conventional
  `C:\Users\hello\AppData\Local\Uoink\index.db`).
- Guard activity is proved with a disposable canary file, never the live path.
- Child env retains `IG_FORBIDDEN_LIVE` after `LOCALAPPDATA`/`APPDATA`/
  `USERPROFILE` are pointed at a canary. Sitecustomize honors both
  `C22_FORBIDDEN_LIVE` and `IG_FORBIDDEN_LIVE`.
- Bundled guard install/restore runs only while owned children have stopped;
  conflicting sitecustomize bytes are refused. Original restore state is kept
  as hashes, not raw bytes in JSON. Relaunch does not dump `previous_bytes`.
- `validate_port` runs before any `port_is_open` probe.
- Isolated marker is not rewritten to switch profiles. A different profile
  uses CLI `--isolated-profile`/`--isolated-port` and leaves installer
  ownership of `isolated-install.json` intact.

### 2. Synthetic acquisition, not loopback standing sources

- Product `register_source` still refuses loopback/private URLs. That policy
  is not repaired.
- Capture URLs use hostname `c22-fixture.invalid`. Acquisition wrappers
  rewrite only that exact host to the declared loopback fixture
  (`C22_FIXTURE_LOOPBACK`) and never resolve/fetch the synthetic host.
- One-off, manual-first and standing-first use separate profiles and episode
  identities. Standing-first waits for a `started_at_ms` charge before the
  later manual action and does not count that manual publication as the
  standing result.

### 3. Charge schema and protected Phase 2

- `source_capture_starts` has no origin/authority/kind. Rows with
  `started_at_ms` are standing charges. Reserved-only rows are not charges.
- Phase 2 baseline is recorded in `prepare_profiles` **before** any scenario.
- `phase2_compare` requires exact `new_rows` and unchanged prior rows. Naming
  a table in `allowed_deltas` is not permission for any mutation.

### 4. Helper child lifetime

- Child scenarios drive original helper capture (`register` + consent +
  refresh + standing `capture_pass`) with `C22_INJECT` hooks on
  `_run_subprocess` / `record_child_start`.
- Exact pid/creation/executable identity is required. Unknown stays unknown.
- Surviving unregistered children are recorded until they exit. Helper
  provenance uses the helper's `sys.executable` (bundled interpreter when
  installed).
- `child_instrument.py` remains in the kit but is not the lifetime oracle.

### 5. Operator flow and Inno switches

- `prepare-before-install` records package/profile/port and an intended app
  path that need not exist yet.
- `run --continue-existing-receipt` reuses that receipt with strict
  source/package/profile bindings and refuses overwrite of completed
  scenarios.
- Isolated Inno argv requires `/NOCLOSEAPPLICATIONS` `/NORESTARTAPPLICATIONS`
  and refuses `/CLOSEAPPLICATIONS`, `/FORCECLOSEAPPLICATIONS`,
  `/RESTARTAPPLICATIONS`.
- Provenance prints module `__file__` paths and SHA-256, interpreter version,
  `nousersite`, and user-site-on-path. A printed cwd/`server.py` path is not
  treated as installed credit. Unsealed Astra hashes stay unsealed.

## Measured results

Python 3.14.6 (`C:\Python314\python.exe`). Sealed integrator guard
(`sitecustomize` + `ig_paths`), `IG_FORBIDDEN_LIVE` retained, disposable
`LOCALAPPDATA`/`APPDATA`/`TEMP` under `_scratch/<label>`.
`ANTHROPIC_API_KEY` unset.

### Union (original two files + new regressions)

Scratch: `_scratch/c22u1`. **41 passed, 2 failed, 666.25 s, exit 1.**

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
# IG_FORBIDDEN_LIVE set to the conventional live path string; LOCALAPPDATA redirected
python -B -m pytest -q -ra --tb=line -p no:cacheprovider -p ig_paths `
  tests/test_install_receipt_c22_kit.py `
  tests/test_install_receipt_c22_kit_repair.py `
  tests/test_install_receipt_c22_scenario_truth.py `
  --basetemp=_scratch/c22u1-0
```

| File | Result |
|---|---|
| `tests/test_install_receipt_c22_kit.py` (frozen) | **17 passed, 2 failed** |
| `tests/test_install_receipt_c22_kit_repair.py` (frozen) | **9 passed** |
| `tests/test_install_receipt_c22_scenario_truth.py` (new) | **15 passed** |

Original failures kept (assertions not edited):

1. `test_plan_inno_does_not_execute` — still asserts `/ISOLATEDPROFILE=`; kit
   records `/ISOLATED=1 /PROFILE= /PORT= /DIR= /NOCLOSEAPPLICATIONS /NORESTARTAPPLICATIONS`.
2. `test_synthetic_helper_scenarios_and_verdict` — stub helper cannot satisfy
   production podcast routes / measured oracles (`manual_first` fail;
   `/podcasts/episodes` 404 on stub). Stub-only 19-pass remains rejected.

Separate original-only confirmation after the one-off oracle alignment:
**17 passed, 2 failed, 320.86 s.** Same two tests, `manual_first` still the
stub production-route failure.

New truth file alone: **15 passed, 171.69 s.**

### Source-runtime measured scenario statuses (not installed credit)

From `test_truth_source_runtime_measured_scenarios` (synthetic helper against
current `server.main` + archived isolation module in scratch):

| ID | Status |
|---|---|
| `install` | unexecuted (Inno argv recorded; `/NOCLOSEAPPLICATIONS` `/NORESTARTAPPLICATIONS` present) |
| `installed_provenance` | unexecuted for installed credit (no bundled `python.exe`; command ran) |
| `empty_migration_replay` | pass |
| `populated_legacy_replay` | pass |
| `one_off_capture` | pass (zero `started_at_ms` charges; synthetic host) |
| `manual_first` | pass (register/consent on `c22-fixture.invalid`; scoped deltas) |
| `standing_first` | pass (standing charge before later manual; not counted as standing result) |
| `whole_helper_relaunch` | pass (held-handle stop; new identity) |
| `registered_child_lifetime` | pass (helper `_run_subprocess` sleeper; exact identity) |
| `launch_interruption` | pass (unresolved launch after intent) |
| `registration_failure` | pass (unresolved + surviving unregistered child until exit) |
| `browser_state_checkpoint` | unexecuted (protocol without image) |
| `protected_phase2_state` | pass (pre-scenario baselines; exact new rows / unchanged prior) |
| `upgrade_operator_step` | unexecuted (same-version reinstall labeled) |

## Exact safe operator commands (still unexecuted here)

Do not run Inno or port 5179. Isolated port must not be 5179.

Prepare before install (receipt must not already exist):

```powershell
$receipt = Join-Path $env:USERPROFILE 'Documents\Uoink Install Receipt 2026-09-09'
python -B scripts/install_receipt/cli.py prepare-before-install `
  --intended-app '<absolute path with a space>\Uoink Installed' `
  --package '<absolute>\Uoink-Setup-3.8.0.exe' `
  --package-sha256 '<Astra-sealed digest>' `
  --isolated-profile (Join-Path $receipt 'profiles\empty') `
  --isolated-port 18081 `
  --receipt-root $receipt
```

Recorded Inno shape (this worker must not execute it):

```text
Uoink-Setup-<version>.exe /VERYSILENT /NORESTART /SUPPRESSMSGBOXES /DIR="<app>" /ISOLATED=1 /PROFILE="<profile>" /PORT=<non-5179> /NOCLOSEAPPLICATIONS /NORESTARTAPPLICATIONS
```

Continue the same receipt after Ryan installs:

```powershell
python -B scripts/install_receipt/cli.py run --continue-existing-receipt `
  --installed-app '<absolute path with a space>\Uoink Installed' `
  --package '<absolute>\Uoink-Setup-3.8.0.exe' `
  --package-sha256 '<Astra-sealed digest>' `
  --isolated-profile (Join-Path $receipt 'profiles\empty') `
  --isolated-port 18081 `
  --receipt-root $receipt
```

Start (after Astra isolation integration and sealed install):

```text
"<app>\python\python.exe" -B -s "<app>\server.py" --isolated-profile "<profile>" --isolated-port <non-5179>
```

Stop is the kit-owned Popen handle / `/helper/quit` path, not the rejected
isolation `--isolated-stop` implementation.

## Remaining unexecuted / operator-owned

| Item | Why |
|---|---|
| Inno install / reinstall / upgrade | Recorded only; this worker must not start Setup |
| Installed bundled Python 3.11.9 provenance | Source-runtime used `C:\Python314\python.exe`; no bundled `python\python.exe` |
| Browser screenshot | Protocol without an image is unexecuted in all modes |
| Astra package/candidate/installer_source seals | Unsealed; this kit does not invent them |

## Files changed

New/owned:

- `docs/library/RYAN-C22-SCENARIO-TRUTH-WORKER-2026-09-09.md`
- `tests/test_install_receipt_c22_scenario_truth.py`
- non-p4 files under `scripts/install_receipt/` (from the archived second-kit
  patch, then repaired)

Frozen unchanged:

- `tests/test_install_receipt_c22_kit.py`
- `tests/test_install_receipt_c22_kit_repair.py`

Also present from the archived patch (not edited for this repair's
assertions): `docs/library/RYAN-C22-KIT-REPAIR-WORKER-2026-09-09.md`,
`docs/library/RYAN-INSTALLED-C22-KIT-WORKER-2026-09-09.md`.

No production source edits, no commits, no push, no merge.
