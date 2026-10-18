**PHASE 3 NOT ACCEPTED. AS7-UI-01 and AS7-UI-02 close. C20 receives the full
matrix credit scoped in AS-7. C21's affordance, launcher bytes, exit status and
browser-run binding close, but its artifact archive is missing the recorded
`helper/server.log`. C22 remains Ryan's installed-build gate. Phase 3 is not yet
accepted subject to C22 only.**

Run AS-8, codex independent review under the
[eighth-round brief](PHASE3-ACCEPTANCE-8-BRIEF-2026-09-08.md) and
[contract phase3-v1](PHASE3-CONTRACT-2026-09-07.md). Reviewed candidate:
`08644bf0e96242e70ea74e47e0bf57395f671669`. The dedicated worktree was initially
clean. This review adds only this report and
[test_phase3_acceptance8.py](../../tests/library_work_astra/test_phase3_acceptance8.py).
Implementation, existing tests and retained proof were not edited. No commit or
merge was made.

| Requested ruling | AS-8 disposition |
|---|---|
| AS7-UI-01, capture pagination | **Closed.** Actual dashboard functions reach a waiting capture on page two automatically and on page nine through the returned cursor after “Load more items.” |
| AS7-UI-02, accepted classification | **Closed.** The renderer says “Classification accepted (staged).” It no longer claims applied filing. |
| C20, scenario 03 and matrix | **Closed within AS-7's stated scope.** The replacement image and complete frozen state agree. Other rows keep their AS-7 credit, including scenario 08's listener/reconciliation limitation. |
| C21, affordance | **Closed.** The retained at7 Sources image displays “Waiting for client (unfiled),” and pagination exposes later captures. |
| C21, executed launcher | **Closed.** Retained raw bytes match the receipt and run record. |
| C21, exit status | **Closed.** The corresponding run record retains integer `exit_code: 0`, command, interpreter, environment and start/finish times; stdout ends with the receipt path. |
| C21, seven artifacts | **Open, narrowed to one file.** Eight of nine receipt-hashed artifacts are present and match. The missing server log is one of the seven previously requested artifacts. |
| C21, browser-run binding | **Closed with the timestamp correction below.** Feed/source/item identities and screenshot epochs bind the observed waiting item to at7 and its retained database. |
| C22 | **Open, Ryan.** The single installed-build receipt requested in AS-7 is unchanged. |

**The UI repairs hold on this candidate.** I reviewed `1d9e438` and executed the
current production rendering/loading functions in AS-7's Node VM runner. The new
cases check both the automatic page walk and the eight-page boundary: page nine
is fetched using `item_cursor='page-9'` when loading more, and the waiting pill
appears. The existing AS-7 page-two service control and classification checks
also pass. These are fixture API replies and extracted JavaScript, with no new
browser or helper run. The later dashboard changes since `1d9e438` concern the
Phase 5 activity surface; the reviewed Phase 3 repairs remain present.

**Scenario 03 now explains the visible allowance.** I inspected
[03-refresh-error.jpg](proof/s20-2026-09-08/03-refresh-error.jpg), both full JSON
state files, the summary and `overlay-4-hold.log`. The image shows feed `57992`,
On, `http_500: HTTP 500`, one consecutive failure, 1/10 starts today, two captured
items, 3/25 enrolled and three observed items. The persisted detection cursor and
public `source_status.detection` agree on the error, count and last successful
versus failed poll timestamps.

The two JSON packages differ only in `observed_at_ms`: `1788905506617` before and
`1788905619478` after. Source, cursor, consent receipt, items, starts, injected
clock and public status are identical. The ledger contains two succeeded starts:
one charged on `2026-09-08`, one on `2026-09-09`. The injected service clock and
allowance both select `2026-09-09`, so the displayed charge is **one**, with nine
remaining. The failed-poll tick also captured previously eligible work. It did
not erase that work or charge both starts to the same day.

AS-7's short-summary test happens to pass because it counts two ledger rows;
its “2/10” image transcription belongs to the superseded screenshot. The new
AS-8 case pins the replacement image hash and checks its daily allowance against
the full package. All **37/37** S20 manifest entries match. This closes the final
C20 evidence gap. Scenario 08 still demonstrates listener replacement and
reconciliation while the Python process survives; actual installed helper
termination/relaunch and its paired browser/state observation remain in C22.

**At7 replaces the earlier C21 evidence, but its archive is incomplete.** I used
[SUPERSESSION-at7.md](proof/s21-2026-09-08/SUPERSESSION-at7.md),
`receipt-at7-candidate-1d9e438.json`, `run-record-at7-candidate-1d9e438.json`, the
retained launcher, database, artifact tree and three at7 images. Historical
absolute paths were treated as recorded identifiers; none was followed into
another checkout.

The executed launcher's raw SHA-256 is
`d17a84c65d126abc60774ccb5fe1b63f6195faca4435f6d2a8e8f116e326b3a7`, matching both
records. Its LF-normalized bytes equal the current launcher, hash
`e4649df0ca1278c2ce509536e45dbcf7899481be271c789ed7e780316ec5dff5`.
The other eleven recorded input hashes reconcile with this candidate's raw or
LF bytes. The production Python files named in the receipt are unchanged since
the run's candidate `1d9e438`.

The run record reports **exit 0**, a 560-second hold and 561.76 seconds elapsed,
from `2026-09-08T22:15:59.681417+00:00` to
`2026-09-08T22:25:21.434963+00:00`. Its command matches the receipt. The archived
stdout and stderr are present and match the top-level manifest.

The new finding is **AS8-EV-01: the at7 helper server log is absent**:

```text
docs/library/proof/s21-2026-09-08/artifacts-at7-candidate-1d9e438/helper/server.log
Expected bytes: 5331
Expected SHA-256: 75c70e5a1c8bf3ec396e233098f3180ec0af8879b71f547263dd0a596c963bdd
```

The receipt, run record and `SHA256SUMS` all name it, but the file is absent from
both the worktree and the candidate's Git tree. No other retained S21 file has
that hash. `git check-ignore -v` identifies `.gitignore:4:server.log`; that rule
is a plausible explanation for the omission, not evidence of the missing bytes.
Thus S21 verifies **35/36** top-level manifest entries and **8/9** receipt-hashed
artifacts. The run record's `all_artifacts_match: true` does not establish that
every artifact reached this candidate. The retained eight include all six other
previously missing artifacts, the evidence database and `publication.json`.

Fable can close AS8-EV-01 by supplying the original 5,331-byte at7 log at the
recorded path with the recorded hash. A new S21 run is unnecessary if those
original bytes remain available. If they are unavailable, supply an explicitly
superseding complete run; do not reconstruct a log or alter the old receipt to
claim it was retained. No new implementation repair follows from this finding.

**The at7 browser and database agree on the waiting capture.** The Sources image
visibly shows feed `59403`, “S21 controlled capture,” one committed item, 1/10 and
“Waiting for client (unfiled).” Library shows one Uncategorized item; detail
shows the same title and source episode on `59403`. Dashboard port `59404` comes
from the browser observation and matching process records; these tab screenshots
do not include an address bar.

The browser note's approximate `23:37:00Z` is inconsistent with its own precise
screenshot epochs. Those epochs convert to **22:17:08.769, 22:17:26.076 and
22:17:49.279 UTC**, all during the recorded hold. I credit that precise timing,
the visible feed URL and the matching source/item identities, and treat the
approximate timestamp as a transcription error. The S20 summary's approximate
“16:12 PDT” likewise disagrees with its observation epochs (15:11:46.617 to
15:13:39.478 PDT); the complete pair and overlay log provide the comparison basis.
Neither approximate timestamp creates an additional acceptance condition.

The at7 database hash is
`09a24ef0c3ed0f93b33219b6ff826344b77793543412f2dec29605213ef60d97`, equal to the
receipt, run record and archived database copy. Opened with
`mode=ro&immutable=1`, it reports integrity `ok` and no foreign-key violations.
It contains one succeeded charged start, committed source item, episode, corpus
item, citation and 12.5–21.75-second clip; one classification outbox, run and
ready work row; zero client attempts and zero shelf memberships. Work/run IDs
match the receipt's `waiting_for_client` item. The receipt records prepare after
commit, one synthetic download/transcript, zero model calls and no forbidden
attempts. The detail screenshot still reports transcript preview unavailable
because the isolated markdown path is outside the Uoink folder; it is not proof
of readable transcript content, as already scoped in AS-7.

**C22's requested receipt is unchanged.** Use the complete list under “C22
remains the installed-build gate” in
[AS-7](PHASE3-ACCEPTANCE-7-2026-09-08.md): actual disposable Inno install/upgrade,
bundled runtime provenance, empty/populated migration and replay, capture
orderings and deduplication, real child/helper recovery with paired browser and
persisted state, protected Phase 2 hashes and isolation instrumentation. Produce
it on the final candidate. The staged-tree S22 receipt remains insufficient.
AS-02b and the earlier reviewed repair dispositions stand. This review does not
certify the separate Phase 4–6 integrations.

**Observed verification:**

| Group | Result | Exit |
|---|---|---|
| Strict Phase 3 wildcard, including AS-7 and AS-8 | 174 passed, 7 failed, 6 warnings; 67.83 s | 1 |
| AS-8 subset of that run | 8 passed, 2 failed | Included above |
| Companions: service / dashboard / legacy | 111 / 31 / 27 passed | 0 each |
| Companions: adapter / podcast / packaging | 98 / 30 / 6 passed | 0 each |
| Companions: heartbeat / extra / phase4 | 10 / 49 / 32 passed | 0 each |
| Brief's three dashboard selectors | 35 passed; 0.30 s | 0 |

Companions total **394 passes**; groups overlap other suites and should not be
summed as unique cases. All 159 pre-AS-7 Phase 3 cases pass. Of the seven strict
failures, four are unchanged historical AS-7 selectors for AT6 exit/artifacts
and ports `64703`/`49557`. They do not count against the replacement run. The
other three are the old S21 manifest audit plus AS-8's manifest and archive
audits, all failing on AS8-EV-01. No additional product defect, skip or final
setup/teardown error occurred. The failures remain ordinary assertions, not
xfails.

Python was `C:\Python314\python.exe`, version 3.14.6; Node was v24.18.0. All suites
set `PYTHONDONTWRITEBYTECODE=1`, `PHASE3_REQUIRE_IMPLEMENTATION=1`, disabled pytest
plugin autoload/cache and removed `ANTHROPIC_API_KEY`. Profiles and test writes
stayed under this worktree's `_scratch`. The existing companion guards remained
enabled, using a byte-identical server copy with SHA-256
`475a87468484df7857f8ca44856b7cd1bb59af4b42f807b703056589afc187f6`.
They blocked import-time process/model probes and podcast-test process/DNS
attempts, including a lookup for `127.0.0.1:5179` before connection. No model,
resident helper, port 5179 connection, live index, S20/S21 launcher or installed
helper was run by this review. The UI reproductions launched only Node.

Two invocation issues were resolved without editing existing runners. The
brief's bare companion command exits 1 with `IndexError` because it requires a
group argument; all nine declared groups were then run. The first adapter run
ended at collection with exit 3 because moving `APPDATA` hid pywin32's `.pth`
paths. Preserving those existing user-site subdirectories in `PYTHONPATH`
restored `pywintypes`; the unchanged adapter group then passed 98/98. No package
installation or stub was used.

Reproduction in PowerShell from this worktree (the repair file is included once
by the expanded wildcard):

```powershell
$as8Root = Join-Path (Get-Location) '_scratch/as8'
New-Item -ItemType Directory -Force -Path $as8Root | Out-Null
$as8SitePaths = python -B -c "import site,sys,os; s=site.getusersitepackages(); print(os.pathsep.join(p for p in sys.path if p.lower().startswith(s.lower())))"
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONPATH = (Get-Location).Path + [IO.Path]::PathSeparator + $as8SitePaths
$env:PHASE3_REQUIRE_IMPLEMENTATION = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
foreach ($key in 'LOCALAPPDATA','APPDATA','XDG_DATA_HOME','TEMP','TMP',
    'UOINK_DATA_ROOT','UOINK_OUTPUT_ROOT','UOINK_OUTPUT_DIR','YOINK_OUTPUT_DIR') {
    Set-Item -Path ('Env:' + $key) -Value $as8Root
}
$phase3Tests = @(Get-ChildItem -LiteralPath 'tests/library_work_astra' `
    -Filter 'test_phase3_*.py' | Sort-Object Name | ForEach-Object FullName)
python -B -m pytest -q -ra --tb=short -p no:cacheprovider `
    --basetemp=_scratch/as8/strict $phase3Tests
python -B tests/library_work_astra/run_phase3_companions.py
foreach ($group in 'service','dashboard','legacy','adapter','podcast',
    'packaging','heartbeat','extra','phase4') {
    python -B tests/library_work_astra/run_phase3_companions.py $group
}
python -B -m pytest -q -ra --tb=short -p no:cacheprovider `
    --basetemp=_scratch/as8/dashboard tests/test_dashboard_sources_api.py `
    tests/test_dashboard_sources_ui.py tests/test_dashboard_v324_ui.py
```

Local logs and exit records are under `_scratch/as8`: `strict.log`,
`strict-exit.txt`, `dashboard.log`, `companion-*.log`, `companion-exits.json` and
`companion-adapter-retry-exit.txt`. The unchanged companion runner writes its
per-group guard/exit records under `_scratch/as6`; the adapter record reflects
the successful retry.

Handoff: AS-8 review complete; Phase 3 acceptance withheld. Added this report
and ten AS-8 cases. Evidence: strict 174 passed/7 failed, companions 394 passed,
dashboard 35 passed; S20 37/37 and S21 35/36 manifest entries verified. Open work:
Fable supplies the original at7 server log for AS8-EV-01; Ryan supplies C22.
Only those two conditions remain within this review's Phase 3 scope.
