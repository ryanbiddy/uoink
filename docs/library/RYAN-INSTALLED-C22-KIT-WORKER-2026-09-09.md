# C22 installed receipt kit — Grok worker (2026-09-09)

Worker: Grok. Brief: `docs/library/RYAN-INSTALLED-C22-KIT-BRIEF-2026-09-09.md`.
AS-7 C22 list: `docs/library/PHASE3-ACCEPTANCE-7-2026-09-08.md` (“C22 remains the installed-build gate”).
Owner rules: `docs/library/ORCHESTRATION-HANDOFF-2026-09-08.md`.
Runbook (still a stop preflight, not this kit): `docs/library/INSTALL-RECEIPT-RUNBOOK-2026-09-09.md`.

No subagents. No Inno, production default helper, live index, port 5179 (including negative probes), paid API, model/client processes, commits, or pushes. `ANTHROPIC_API_KEY` unset. `librarian_apply_enabled` stays false. Phase 4 client/everyday tooling is Astra’s separate scope.

**No claimed installed pass.** Ryan has not run the sealed kit on a throwaway profile against the isolated installed helper.

Astra owns independent verification, isolation-mechanism integration, and the final runbook/package seal.

## What was built (four executable pieces)

New package only: `scripts/install_receipt/`. No production, existing tests, fixtures, assertions, or runbook edits.

### 1. Fail-closed operator runner and manifest

- `manifest.py` + `c22_operator_manifest.example.json` — schema `c22-operator-manifest-v1`. `expected_package_sha256`, `candidate_sha`, and `installer_source_sha` are null until Astra seals them. The kit **refuses to invent** those digests.
- `validation.py` — required explicit `installed_app_path`, `package_path`, `package_sha256`, `isolated_profile`, `isolated_port`, `receipt_root`. Rejects relative roots, live Uoink/Yoink data roots, volume roots, port 5179, hash mismatch, missing bundled `server.py`, production default helpers (`start_server.ps1` / `start_server.bat` / `launch.bat`), checkout-root PYTHONPATH, user-site PYTHONPATH, and `ANTHROPIC_API_KEY` in the child.
- `runner.py` — creates a fresh receipt root and **refuses overwrite**. Journals every command (argv, UTC start/end, exit, stdout/stderr hashes, child pid+creation identity). Partial logs stay on failure. `plan_inno()` records the isolated Inno argv and will not execute it from this worker or from `--synthetic`.

### 2. Deterministic fixtures and installed-helper launcher

- `fixtures.py` — loopback RSS/audio (never 5179); empty profile; **versioned** populated legacy fixture `c22-legacy-populated-v1-schema27` (schema 27, kit-side SQL 0001–0027, not installed credit). Settings force `librarian_apply_enabled=false`. Synthetic audio/transcript only.
- `launcher.py` — original installed startup path:

  `<bundled python.exe> -B -s <installed>\server.py --isolated-profile <abs> --isolated-port <non-5179>`

  Never `start_server.ps1`. Isolation flags are **consumed**; the isolation worker implements them on product entry points.
- `guards.py` — receipt `sitecustomize.py` blocks 5179, the live index, non-loopback/undeclared ports, and model/client process names; wraps acquisition/transcription and the declared launch-interrupt / registration-failure injections. Copied into the disposable `{app}\python\Lib\site-packages\` because embeddable `python._pth` ignores PYTHONPATH, so inherited bundled-python children load the same guards.
- `stub_helper.py` — **labeled synthetic instrument**, not installed credit. Implements the same isolation flags and the HTTP paths the scenarios drive.

### 3. Executable AS-7 C22 scenarios

`scenarios.py` + CLI `run`. Unexpected failure ends that scenario and preserves the outcome. Scenario IDs:

| ID | AS-7 item | Kit behavior |
|---|---|---|
| `install` | isolated Inno command and exit | Records argv; **unexecuted** until Ryan |
| `installed_provenance` | bundled interpreter, `__file__`, 0028 / schema 30 | File hashes now; runtime provenance needs the bundled interpreter |
| `empty_migration_replay` | empty migrate, stop, reopen, no invented rows | Executable |
| `populated_legacy_replay` | versioned populated legacy then replay | Executable; same-package replay is not a cross-version upgrade |
| `one_off_capture` | unrelated one-off, standing off, zero standing charges | Executable (synthetic media) |
| `manual_first` | manual then standing; identities/charges/no dup | Executable |
| `standing_first` | consent, standing, then same manual item | Executable |
| `whole_helper_relaunch` | kill owned helper by pid+creation; relaunch installed path | Executable; listener restart does not count |
| `registered_child_lifetime` | actual registered child lifetime | Executable via declared `spawn_child` injection |
| `launch_interruption` | interrupt between launch intent and child record | `C22_INJECT=launch_interrupt` |
| `registration_failure` | separate registration failure | `C22_INJECT=registration_failure` (not the interrupt case) |
| `browser_state_checkpoint` | post-restart browser + persisted state | Snapshot + observation protocol; **no synthesized screenshot** |
| `protected_phase2_state` | Phase 2 before/after hashes, allowed enqueue | Executable; apply stays false |
| `upgrade_operator_step` | real installed upgrade command | Records argv; same-version reinstall is labeled `same_version_reinstall` |

### 4. Evidence collector / verdict input

`evidence.py` — table/file snapshots, `PRAGMA integrity_check` / `foreign_key_check`, Phase 2 table hashes, explicit allowed enqueue changes, per-scenario pass/fail/unexecuted. `verdict.json` always has `installed_pass_claimed: false`.

## Exact commands

Python 3.14.6 (`C:\Python314\python.exe`) in this worktree. `ANTHROPIC_API_KEY` unset. Scratch: `_scratch/c22-kit`.

### Verification (this worker)

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
python -B -m pytest -q -ra --tb=short -p no:cacheprovider `
  --basetemp=_scratch/c22-kit/pytest tests/test_install_receipt_c22_kit.py
```

Final result: **19 passed**, 24.35 s, exit 0. Labeled synthetic instrument checks only. Inno and the production default helper were not started. Port 5179 was not probed.

```powershell
python -B scripts/install_receipt/cli.py list-scenarios
```

### After Astra seals hashes (Ryan’s throwaway profile)

Receipt root must not already exist. Package digest must match the sealed manifest. Isolated port must not be 5179. Installed dir must contain a space and bundled `python\python.exe`. Do not use `C:\Users\hello`.

```powershell
$receipt = Join-Path $env:USERPROFILE 'Documents\Uoink Install Receipt 2026-09-09'
python -B scripts/install_receipt/cli.py run `
  --installed-app '<absolute path with a space>\Uoink Installed' `
  --package '<absolute>\Uoink-Setup-3.8.0.exe' `
  --package-sha256 '<Astra-sealed digest>' `
  --isolated-profile (Join-Path $receipt 'profiles\empty') `
  --isolated-port 18081 `
  --fixture-port 18082 `
  --receipt-root $receipt `
  --manifest scripts/install_receipt/c22_operator_manifest.example.json
```

`run` prepares fixtures, launches through the installed `server.py` isolation flags, executes scenarios, and writes `evidence/verdict.json`. It will not execute Inno.

Print the isolated Inno argv (still does not start it):

```powershell
python -B scripts/install_receipt/cli.py plan-install `
  --installed-app '...' --package '...' --package-sha256 '...' `
  --isolated-profile '...' --isolated-port 18081 --receipt-root '...'
```

Template recorded (isolation worker must implement the Inno surface):

`/VERYSILENT /NORESTART /SUPPRESSMSGBOXES /DIR="{installed_app_path}" /NOICONS /TASKS=! /MERGETASKS=! /CLOSEAPPLICATIONS=no /ISOLATEDPROFILE={isolated_profile} /ISOLATEDPORT={isolated_port}`

Print the helper launch argv:

```powershell
python -B scripts/install_receipt/cli.py print-launch-argv `
  --installed-app '...' --package '...' --package-sha256 '...' `
  --isolated-profile '...' --isolated-port 18081 --receipt-root '...'
```

Re-read a preserved receipt (does not overwrite):

```powershell
python -B scripts/install_receipt/cli.py collect --receipt-root $receipt
```

`--synthetic` is only for labeled non-installed instrument checks. It skips the ordinary-user check, space/bundled-python requirements, and the sealed-hash requirement. It is **not** installed credit.

## What this tooling cannot execute (until Ryan / Astra)

| Item | Why |
|---|---|
| Inno install/upgrade | Kit records the command; this worker must not start the installer |
| Production default helper | `start_server.ps1` / autostart / 5179 path is refused |
| Real bundled Python 3.11.9 / MCP 1.27.1 `__file__` provenance | Needs the sealed installed tree; tests used a stub `server.py` |
| Isolation flags on product entry points | Declared and consumed (`--isolated-profile`, `--isolated-port`); implemented by the isolation worker |
| Browser screenshot | Protocol + DB snapshot only; no synthesized image |
| Phase 4 client/everyday session | Astra’s separate scope |
| Installed pass | Forbidden to claim until Ryan runs the sealed kit |

Synthetic scenario passes are instrument evidence for the kit, not C22 acceptance.

## Test repairs (recorded before each rerun)

Assertions in `tests/test_install_receipt_c22_kit.py` were not changed after a failing run.

### Repair 1 (before rerun 2)

First run: **16 passed, 3 failed**, 2.50 s.

| Failure | Cause | Repair |
|---|---|---|
| `test_runner_refuses_overwrite` FileExistsError | Test helper `_install` used `mkdir()` without `exist_ok` | `mkdir(exist_ok=True)`; overwrite still targets the receipt root |
| populated-legacy `IntegrityError: datatype mismatch` | `citations.citation_id` inserted as text; column is INTEGER PK | Integer id plus required `kind`/`seq`/`youtube_deep_link` |

### Repair 2 (before rerun 3)

Second run: **18 passed, 1 failed**, 24.56 s. `one_off_capture` TypeError: `record() got multiple values for argument 'status'` because the helper `/sources/status` payload was spread into `record(...)`. Attempted to pop the key inside `record()` — insufficient; Python raises at the call boundary.

### Repair 3 (before rerun 4)

Third run: **18 passed, 1 failed**, 24.49 s. Same TypeError. Renamed the parameter to `outcome_status`.

### Final run (after import cleanup)

**19 passed**, 24.35 s, exit 0.

## Files changed (new only)

- `scripts/install_receipt/` — runner, manifest, validation, fixtures, launcher, guards, stub helper, scenarios, evidence, CLI, example manifest
- `tests/test_install_receipt_c22_kit.py`
- `docs/library/RYAN-INSTALLED-C22-KIT-WORKER-2026-09-09.md`

No existing production, tests, fixtures, assertions, or runbook files were modified. Nothing was committed or pushed.

## Open questions for Astra

1. Confirm Inno `/ISOLATEDPROFILE` and `/ISOLATEDPORT` match the isolation worker’s actual surface (CLI flags on `server.py` are `--isolated-profile` / `--isolated-port` as the brief declared).
2. Confirm whether `--isolated-profile` is the data root itself or a parent that still nests `Uoink\`. The kit treats it as the data root (`index.db` there) and also looks for `token.txt` under the install dir.
3. Seal `expected_package_sha256` / candidate / installer source into the manifest; the kit will not fill them.
4. Whether copying receipt `sitecustomize.py` into the disposable bundled `Lib\site-packages` is accepted as the inherited-child guard (required because `._pth` ignores PYTHONPATH).
5. Replace the runbook stop preflight with these commands only after the isolation mechanism is integrated and a new installer is sealed.
