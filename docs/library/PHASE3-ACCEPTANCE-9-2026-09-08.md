**Phase 3 is accepted subject to C22 only. AS8-EV-01 closes.** The original
at7 `helper/server.log` is retained with the required bytes, and every S20/S21
manifest entry verifies. Ryan's installed Inno receipt remains the sole open
Phase 3 acceptance condition, with the requirements listed in
[AS-7](PHASE3-ACCEPTANCE-7-2026-09-08.md).

Run AS-9, codex confirmation, 2026-09-08. Reviewed candidate:
`5affb085f2443cc186ba7b9e56382d34160c0f4b`. The dedicated worktree was initially
clean. Compared with AS-8's reviewed candidate `08644bf`, the intervening changes
affect documentation, retained proof and the AS-8 test file; implementation is
unchanged. The [AS-8 dispositions](PHASE3-ACCEPTANCE-8-2026-09-08.md) for AS7-UI-01/02,
C20, C21's affordance, launcher, exit status and browser-run binding stand.

The archived [server log](proof/s21-2026-09-08/artifacts-at7-candidate-1d9e438/helper/server.log)
is **5,331 bytes**, with SHA-256:

```text
75c70e5a1c8bf3ec396e233098f3180ec0af8879b71f547263dd0a596c963bdd
```

That digest equals `artifact_hashes['helper\\server.log']` in the
[at7 receipt](proof/s21-2026-09-08/receipt-at7-candidate-1d9e438.json), the
[run record](proof/s21-2026-09-08/run-record-at7-candidate-1d9e438.json) entry and
the S21 `SHA256SUMS` entry. Its raw worktree bytes also equal the committed Git
blob. All **9/9** receipt-hashed artifacts match their archived bytes and recorded
sizes, including all seven artifacts originally requested. The new
[AS-9 check](../../tests/library_work_astra/test_phase3_acceptance9.py) pins this
log's original hash and size and requires exactly one matching manifest entry.

| Retained proof | Verified manifest entries | Missing or mismatched |
|---|---|---|
| S20, `proof/s20-2026-09-08/SHA256SUMS` | 37/37 | 0 |
| S21, `proof/s21-2026-09-08/SHA256SUMS` | 36/36 | 0 |

Both timestamp corrections agree with their epochs. The at7 browser note now
gives `22:17:08.769`, `22:17:26.076` and `22:17:49.279 UTC` on September 8, matching
epochs `1788905828769`, `1788905846076` and `1788905869279`. All fall within the
recorded hold, `22:15:59.681417` through `22:25:21.434963 UTC`. S20 scenario 03's
header now says approximately `15:12 PDT`; its two JSON observation epochs,
`1788905506617` and `1788905619478`, convert to `15:11:46.617` and `15:13:39.478 PDT`.
The approximate header falls within that interval. Neither correction changes
the capture state or AS-8's evidence scope.

Every suite below ran with `PHASE3_REQUIRE_IMPLEMENTATION=1`:

| Group | Observed result | Exit |
|---|---|---|
| AS-8 plus AS-9 confirmation | 11 passed: AS-8 10/10, AS-9 1/1; 0.36 s | 0 |
| Full `test_phase3_*.py` suite | 178 passed, 4 failed, 6 warnings; 46.67 s | 1 |
| Companions: service / dashboard / legacy | 111 / 31 / 27 passed | 0 each |
| Companions: adapter / podcast / packaging | 98 / 30 / 6 passed | 0 each |
| Companions: heartbeat / extra / phase4 | 10 / 49 / 32 passed | 0 each |
| Three dashboard selectors from AS-8 | 35 passed; 0.21 s | 0 |

The full wildcard remains red because four unchanged AS-7 assertions inspect
superseded evidence:

- `test_as7_c21_at6_receipt_records_process_exit_status` reads the old AT6 receipt.
- `test_as7_c21_all_at6_artifact_bytes_are_archived` requires the old AT6 artifacts.
- `test_as7_c21_browser_run_has_retained_receipt_and_database[at6-browser]` requires
  the old browser run on feed port `64703`.
- The same test's `[c21-pill-browser]` case requires the earlier feed port `49557`.

The retained [at7 supersession record](proof/s21-2026-09-08/SUPERSESSION-at7.md)
explicitly replaces those evidence packages. AS-8's corresponding at7 checks now
all pass, including its manifest and complete archive audits. These four failures
remain ordinary assertions; no existing test was edited, deselected or marked
xfail. All 159 pre-AS-7 Phase 3 cases pass. The companion groups total 394 passes;
their overlap with other suites means these counts are not unique test totals.
No skips or setup/teardown errors occurred in the test runs.

Tests used `C:\Python314\python.exe` 3.14.6 and Node v24.18.0. Test processes had
`ANTHROPIC_API_KEY` removed, bytecode and pytest plugin autoload/cache disabled,
and profile/output/temp roots redirected into this worktree's `_scratch`.
Existing Phase 3 isolation fixtures and companion audit guards stayed enabled.
The server copy used by companions was byte-identical, SHA-256
`475a87468484df7857f8ca44856b7cd1bb59af4b42f807b703056589afc187f6`.
Guards blocked process/model probes and the podcast group's DNS attempt for
`127.0.0.1:5179` before connection. The legacy log's bind-error message comes from
the injected `BindFailure` in `test_main_exits_nonzero_when_bind_fails`.
No model, resident helper, port 5179 access or live index was used. The dashboard
cases executed extracted functions in Node; no browser or S20/S21 launcher ran.
Historical absolute receipt paths were treated only as identifiers.

Reproduction commands, entered inline in PowerShell from this worktree:

```powershell
$as9Root = Join-Path (Get-Location) '_scratch/as9'
New-Item -ItemType Directory -Force -Path $as9Root | Out-Null
$as9SitePaths = python -B -c "import site,sys,os; s=site.getusersitepackages(); print(os.pathsep.join(p for p in sys.path if p.lower().startswith(s.lower())))"
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONPATH = (Get-Location).Path + [IO.Path]::PathSeparator + $as9SitePaths
$env:PHASE3_REQUIRE_IMPLEMENTATION = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
foreach ($key in 'LOCALAPPDATA','APPDATA','XDG_DATA_HOME','TEMP','TMP',
    'UOINK_DATA_ROOT','UOINK_OUTPUT_ROOT','UOINK_OUTPUT_DIR','YOINK_OUTPUT_DIR') {
    Set-Item -Path ('Env:' + $key) -Value $as9Root
}
python -B -m pytest -q -ra --tb=short -p no:cacheprovider `
    --basetemp=_scratch/as9/confirmation `
    tests/library_work_astra/test_phase3_acceptance8.py `
    tests/library_work_astra/test_phase3_acceptance9.py
$phase3Tests = @(Get-ChildItem -LiteralPath 'tests/library_work_astra' `
    -Filter 'test_phase3_*.py' | Sort-Object Name | ForEach-Object FullName)
python -B -m pytest -q -ra --tb=short -p no:cacheprovider `
    --basetemp=_scratch/as9/strict $phase3Tests
foreach ($group in 'service','dashboard','legacy','adapter','podcast',
    'packaging','heartbeat','extra','phase4') {
    python -B tests/library_work_astra/run_phase3_companions.py $group
}
python -B -m pytest -q -ra --tb=short -p no:cacheprovider `
    --basetemp=_scratch/as9/dashboard tests/test_dashboard_sources_api.py `
    tests/test_dashboard_sources_ui.py tests/test_dashboard_v324_ui.py
```

Local evidence is under `_scratch/as9`: `proof-audit.json`, `confirmation.log`,
`strict.log`, `dashboard.log`, `companion-*.log` and `exits.json`. The unchanged
companion runner writes its guard/exit records under `_scratch/as6`. An initial
attempt to invoke the scratch `.ps1` was refused by the local execution policy
before any test ran; the commands above were then entered inline without changing
that policy.

C22 must still supply the single receipt specified under "C22 remains the
installed-build gate" in AS-7, on the final candidate: actual disposable Inno
install/upgrade with package and runtime provenance; empty/populated migration
and replay; one-off and both manual/standing capture orderings with deduplication,
charges and publication; installed helper/child termination and relaunch,
interruption and registration failure with ownership evidence and paired browser
and persisted state; protected Phase 2 hashes and isolation instrumentation.
AS-8's C20 scenario 08 listener/reconciliation limitation remains part of that
installed-process requirement. The staged-tree S22 receipt does not satisfy C22.
This confirmation does not certify the separate Phase 4-6 integrations.

Handoff: AS-9 complete; Phase 3 accepted subject to C22 only. Added this report
and one regression check. Evidence: 73/73 manifest entries, 9/9 artifacts, AS-8
10/10 and AS-9 1/1; strict 178 passed with four superseded-evidence failures;
companions 394 passed; dashboard 35 passed. Implementation, existing tests and
retained proof were not edited. No commit or merge was made. Open work: Ryan's C22
installed Inno receipt; no other Phase 3 condition remains.
