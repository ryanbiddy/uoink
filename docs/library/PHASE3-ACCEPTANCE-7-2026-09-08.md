**PHASE 3 NOT ACCEPTED. AS-02b closes. C20 needs a corrected scenario 03
browser/state pair. C21's waiting-for-client pill is demonstrated, but two defects
in the new surface and the earlier evidence omissions remain. C22 still requires
Ryan's actual disposable Inno installation receipt. C22 alone will not close this
candidate.**

Run AS-7, codex independent review under the [seventh-round brief](PHASE3-ACCEPTANCE-7-BRIEF-2026-09-08.md)
and [contract phase3-v1-2026-09-07](PHASE3-CONTRACT-2026-09-07.md). Reviewed candidate:
`3c3eda964a066886d212d1b9bba41ed24204c4e2`. The dedicated worktree was initially
clean. Implementation and existing tests were not edited; no commit or merge was made.

| Item | AS-7 disposition |
|---|---|
| AS-02b, repair `d2ec84a` | **Closed.** All four AS-6 malformed-record reproductions pass, as do the other five AS-6 checks and the original 159-test strict suite. |
| C20, receipt `56c1c86` | **Open, narrowed to scenario 03's evidence.** All eight scenarios are represented. Seven receive the scoped credit below; scenario 03's screenshot and state dump disagree. |
| C21 waiting-for-client display, `867605b` | **Demonstrated for an item on the first page.** The new screenshot visibly shows the pill. The general per-item affordance remains incomplete beyond that page; accepted classification also has an incorrect label. |
| C21 earlier evidence requirements | **Open.** Executed launcher bytes, explicit exit status, seven archived artifacts, and browser-run receipt/database bindings are still missing. |
| C22 | **Open, Ryan.** Source staging and fixture tests do not establish installed Inno behavior. |

**The AS-02b repair preserves uncertainty for the reviewed damaged records.**
`_child_record_bound` now rejects a non-boolean `unresolved_launch` and calls
`_child_entry_valid` before liveness can skip an ended child. The entry validator
rejects non-positive/non-integer PIDs, boolean or textual creation markers, and
boolean, textual or negative exit markers. A valid creation marker may be null;
an absent/null exit marker still requires a liveness check. Earlier records may
omit the launch flag. Damaged records cannot pass the shared read/write validation.

The four original cases (`ended_ms=false`, a textual exit marker, an ended child
without identity, and `unresolved_launch=[]`) now yield unknown ownership and
`worker_not_stopped`; the attempt stays uncertain and retains its claim. AS-02a
and AS-03a/b/c remain closed within their previously reviewed scope. The earlier
AS-01/04/05/06 dispositions also stand. No new child-ownership failure was found.

**C20 covers the requested matrix, but does not establish a match in every row.**
I inspected all 17 supplied screenshots, their named state files, both scenario
notes, the overlay logs, and the launcher. All **33/33** S20 manifest entries
match their raw bytes. The receipt's server and dashboard hashes match the CRLF
forms of the named `d2ec84a` and `12339c3` Git blobs. The source-service hash and
repaired launcher hash match this worktree directly. Thus the historical input
hashes are reconciled; they are not hashes of every current production file.

| Scenario | Independently reviewed evidence and ruling |
|---|---|
| 01 default off | Off, 0/10, 0/25 idle and observed zero match the recorded off/revision 0/epoch 0, zero items and zero receipts. **Credit.** |
| 02 consent, pending and actual enrollment | Modal names the caps and standing ingest. Confirmed on/revision 1/epoch 1 with one receipt and zero items matches pending enrollment; the next capture shows 3 enrolled and 1/10, matching three back-catalog rows and one succeeded start. **Credit.** The short state summaries omit some fields; the production confirmed-click path corroborates the intent timing. |
| 03 refresh error | The screenshot shows `degraded: http_500: HTTP 500`, **1 consecutive failure** and **2/10** starts. Its state file says `detection error None failures None` and `starts ['succeeded']`, representing **one** start. The receipt's claim that starts remained unchanged is not demonstrated by this pair. **Rerun or supply the retained contemporaneous state.** |
| 04 exhausted allowance | Library shows 10 items; Sources shows 10/10 and 14/25 enrolled. The state summary records ten succeeded starts, ten charges and fourteen enrolled. **Credit for exhaustion and those counts.** The summary is not a retained dump of every eligible item. |
| 05 stale confirmation | Modal opens on the on state; the recorded confirm-intent request receives HTTP 409; the row is refreshed off at revision 2. **Credit.** The post-image does not retain the claimed toast, and the short note is the evidence for the HTTP result. |
| 06 off while in flight | The before/modal/after images show a started attempt and draining after off. `06c.state.txt` retains off/revision 2, two receipts and one charged `started` row; `07a.state.txt` retains that same start as succeeded and its item committed. **Credit.** |
| 07a/07b lost responses | Notes record both real requests and which responses were discarded. Single loss ends on/revision 3/three receipts; double loss ends off/revision 4/four receipts with a failed-fetch toast. Both retain the one original charge. State dumps match the final visible states. **Credit for both variants.** |
| 08 restart/reconciliation | Before: slot 1 succeeded, slot 2 started. After: the same slot 2 is uncertain, actual attempts remain one, both charges remain, and consent stays on/revision 1. Images show 2/10 and uncertain, plus the earlier committed Library item. **Credit for the browser/reconciliation state match, within the listener-restart scope below.** |

For scenario 03, retain the same source's `source_detection_cursors` row, the
public `source_status.detection` and `allowance` objects, and all its ledger rows
alongside the screenshot, with source ID and observation time. Freeze or account
for capture progress between reads. This must explain the two displayed charges
and record the real failure fields. The launcher's `/ctl?state=1` currently dumps
sources, starts, items and a receipt count, **not detection cursors**. Reading
nonexistent source-row error fields cannot supply the missing evidence. The AS-7
test reproduces this package mismatch; it does not allege that the product
persisted a false failure count.

The failed fixed-port rebind in `overlay-1-hold.log` occurred after scenarios
01–07. The repaired launcher binds port 0, updates `server.PORT`, and advances its
clock before ticking. Scenario 08's fresh instance and new dashboard port are
corroborated by the second log and state dump. That tooling failure does not
invalidate earlier observations or require a blanket rerun of 01–07.

Scenario 08 keeps the Python process, service objects and capture thread alive.
It replaces the HTTP listener and invokes `reconcile_on_startup`; it does not
demonstrate process termination/relaunch or a new incarnation. The receipt's
reference to S22 as process-restart coverage overstates the staged-tree receipt,
which explicitly did not install or run an installed helper. Keep actual process
recovery in C22. No separate rerun of 08 is needed for the credited UI state
match; Ryan's C22 must include the real-process browser/state observation.

**C21's new pill is real; its broader claims need two repairs.**
The supplied `dashboard-sources-waiting-for-client-c21.jpg` visibly shows
“S20 matrix item 2” with “Waiting for client (unfiled),” one committed item and
1/10 starts. The production renderer consumes `classification.state`, and the
extracted-function test passes for `waiting_for_client`. This closes the narrow
AS-6 observation that no browser surface rendered that state.

| Finding | Reproduction and required repair |
|---|---|
| **AS7-UI-01: captured items after page one are unreachable** | `toggleCapturedItems` requests `source_status` with `item_limit:25` once, then `renderCapturedItems` filters that page to committed items. With 25 older uncommitted rows and a newly committed 26th row, the source summary says one capture, but the disclosure says “No captured items in the first page.” There is no pager. The real-service control confirms that the waiting capture can be on page two. Add usable pagination or load the relevant committed items through a supported API path; demonstrate reaching this waiting item. |
| **AS7-UI-02: accepted classification falsely reads Filed** | Passing a committed item with `classification.state='accepted'` to the unchanged renderer produces `<span class="classification-pill accepted" title="accepted">Filed</span>`. The contract explicitly says accepted describes staging, not applied shelving. Use a label such as “Classification accepted” or “Staged”; only claim applied filing from authoritative application/membership evidence. |

These are two product failures, distinct from the six failed evidence checks.
The JavaScript reproductions execute the actual extracted functions in a Node VM
with injected `source_status` replies. They are not a new browser capture or a
live backend run. The pagination control separately uses the real service,
migrations, publication fixture and Phase 2 enqueue on an isolated database.

**The earlier C21 evidence omissions are unchanged.** All **16/16** S21 manifest
entries match raw bytes. The retained AT6 database opens read-only with
`mode=ro&immutable=1`; integrity is `ok`, with no foreign-key violations. Its hash
is `eb193f5eec1e3fb963476235f404e0f9b99b8bdd24bd1a78cb5d3f17624b1dc6`.
It still contains one succeeded charged start, one committed item, one episode
and corpus item, one citation/12.5–21.75-second clip, one outbox/run/ready work row,
zero client attempts and zero shelf memberships. The receipt records prepare
after commit, one synthetic transcript/download, zero model calls and no forbidden
attempts. Those successful historical observations retain their AS-6 credit.

| Requirement | Supplied evidence and exact remaining work |
|---|---|
| Executed launcher bytes/hash | Recorded `d17a84c65d126abc60774ccb5fe1b63f6195faca4435f6d2a8e8f116e326b3a7`; current raw file `be212fe55ff13d1475dc1d8b89dd397256e71669e1bffff7946c10cd977ba635`; candidate Git blob/current LF form `e4649df0ca1278c2ce509536e45dbcf7899481be271c789ed7e780316ec5dff5`. The recorded hash matches neither form nor retained bytes. Archive the executed file or supersede this run with matching retained bytes. |
| Exit status | The command is explicit, including `--hold-seconds 5`. The result string says automated pass; no explicit process exit status or corresponding completion log is supplied. Retain the actual exit status after completion. |
| Seven artifacts/logs | The hashes remain in the receipt without their bytes: fixture transcript, helper server log, incarnation JSON, podcast sidecar, podcast markdown, retained `.media-inputs` JSON and generated taxonomy JSON. Archive all seven with a manifest. The database is already present and credited. |
| Browser run binding | AT6 images show feed port **64703**; its archived receipt/database use **60407**. The new pill image shows feed **49557** (receipt prose names dashboard **49558**), with no corresponding retained JSON/database. Retain the receipt, database and artifacts from the actual held browser run, bound to its source/item, ports and screenshots. |

I did not follow receipt paths outside this dedicated checkout. The old item-detail
image still says transcript preview unavailable and that the markdown path lies
outside the Uoink folder; it does not prove readable transcript content. This
remains a limit of that screenshot, not a newly reproduced capture failure.

A **single replacement S21 run after the two UI repairs** can close the evidence
requirements: use the final candidate, retain the exact launcher, command and
input hashes, hold that same run for browser observation, then archive its database,
all artifacts and completion/exit status. Bind the new pill and visible unfiled
item to that run. There is no need to reconstruct every superseded historical run
if a complete replacement supplies the requested evidence. The tests in this
review audit the currently supplied files; a replacement needs an explicit
supersession record and corresponding test selectors, not fabricated additions to
old receipts.

**C22 remains the installed-build gate.** Ryan's one receipt should be produced
on the final repaired candidate and include:

- Candidate and Inno package hashes, actual install/upgrade commands and exits,
  installed paths, bundled interpreter version and dependency/import provenance
  with the checkout absent from runtime resolution.
- Migration/upgrade and replay observations on disposable empty and populated
  profiles; the shipped subscription module/migration and registry schemas.
- An unrelated one-off capture, both manual-first and standing-first capture
  orderings, identity/deduplication, charges and publication outcomes.
- Actual helper termination and relaunch through the installed production path,
  including real child lifetime, launch interruption and registration failure.
  Record incarnation/claim/lock evidence, unchanged charges, no duplicate launch,
  settlement and ownership release when termination/publication is established.
  Include the post-restart browser state paired with persisted state.
- Protected Phase 2 input/state hashes before and after, with any expected
  fixture-only handoff changes accounted for, and instrumentation establishing
  zero models/client spawns, no resident helper or port 5179 access, and no live
  index access. Use only the disposable profile and fixture data.

Once a satisfactory C22 is supplied, **AS7-UI-01/02, C20 scenario 03 and C21's
complete replacement evidence still remain unless already closed**. After those
repairs/evidence, rerun affected suites on the final integrated SHA and review the
receipts. No other Phase 3 code repair is demanded by this review. This review
does not certify the separate Phase 4–6 integrations.

**Observed verification on this candidate:**

| Group | Result | Exit |
|---|---|---|
| Supplied strict Phase 3 suite | 159 passed, 6 warnings, 45.72 s | 0 |
| New AS-7 tests, first run | 4 passed, 8 failed, 1.18 s | 1 |
| Final strict suite including AS-7 | 163 passed, 8 failed, 6 warnings, 47.71 s | 1 |
| Companions: service / dashboard / legacy | 111 / 31 / 27 passed | 0 each |
| Companions: adapter / podcast / packaging | 98 / 30 / 6 passed | 0 each |
| Companions: heartbeat / extra / phase4 | 10 / 49 / 32 passed | 0 each |
| Brief's combined dashboard/source/podcast selectors | 180 passed, 88 warnings, 14.02 s | 0 |

Companions total **394 passes**. These groups overlap the combined suite; do not
sum them as unique cases. No skips or setup/teardown errors occurred in the final
runs. Python was `C:\Python314\python.exe`, version 3.14.6; Node was v24.18.0.
The AS-7 failures are intentionally unmarked failing reproductions, not xfails.

All runs set `PYTHONDONTWRITEBYTECODE=1`, `PHASE3_REQUIRE_IMPLEMENTATION=1`,
disabled pytest plugin autoload/cache, and removed `ANTHROPIC_API_KEY` from their
process environment. Test data, profiles and logs stayed under this worktree's
`_scratch`. The existing companion runner's audit guards remained enabled.
Server-importing groups used its byte-identical server copy, SHA-256
`475a87468484df7857f8ca44856b7cd1bb59af4b42f807b703056589afc187f6`.
The guard blocked import-time process probes, WhisperX imports and podcast-test
process/DNS attempts, including a DNS request for `127.0.0.1:5179`; no connection
occurred. AS-7's pure rendering checks launched only Node. No model, resident
helper, live index, browser overlay, S20/S21 launcher or installed helper was run.

Two invocation issues were resolved without changing tracked runners. The brief's
bare companion command exits 1 with `IndexError` because it requires a group
argument; all nine declared groups were then run separately. Moving `APPDATA`
before interpreter startup initially hid user-installed pytest (`No module named
pytest`); adding the known package directory to `PYTHONPATH`, alongside this
worktree, restored it. Neither startup failure is counted as a product test failure.

Commands from this worktree, in PowerShell (the explicit repair selector is
already included in the wildcard and is run once):

```powershell
$as7Site = python -B -c "import site; print(site.getusersitepackages())"
$as7Root = Join-Path (Get-Location) '_scratch/as7'
New-Item -ItemType Directory -Force -Path $as7Root | Out-Null
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONPATH = (Get-Location).Path + [IO.Path]::PathSeparator + $as7Site
$env:PHASE3_REQUIRE_IMPLEMENTATION = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
foreach ($key in 'LOCALAPPDATA','APPDATA','XDG_DATA_HOME','TEMP','TMP',
    'UOINK_DATA_ROOT','UOINK_OUTPUT_ROOT','UOINK_OUTPUT_DIR','YOINK_OUTPUT_DIR') {
    Set-Item -Path ('Env:' + $key) -Value $as7Root
}
$phase3Tests = @(Get-ChildItem -LiteralPath 'tests/library_work_astra' `
    -Filter 'test_phase3_*.py' | Sort-Object Name | ForEach-Object FullName)
python -B -m pytest -q -ra --tb=short -p no:cacheprovider `
    --basetemp=_scratch/as7/final-strict $phase3Tests
python -B -m pytest -q -ra --tb=short -p no:cacheprovider `
    --basetemp=_scratch/as7/new-tests tests/library_work_astra/test_phase3_acceptance7.py

# Bare invocation observed exit 1; the actual companion interface takes a group.
python -B tests/library_work_astra/run_phase3_companions.py
foreach ($group in 'service','dashboard','legacy','adapter','podcast',
    'packaging','heartbeat','extra','phase4') {
    python -B tests/library_work_astra/run_phase3_companions.py $group
}
```

For the brief's combined selectors, the existing runner was evaluated with only
its podcast selector list and result directory replaced in memory. All guards and
server-copy isolation stayed intact; no existing test or runner file was edited.
The following was piped to `python -B -` under the same environment:

```python
from pathlib import Path
import sys
p = Path('tests/library_work_astra/run_phase3_companions.py').resolve()
s = p.read_text(encoding='utf-8')
s = s.replace(
    "'podcast': ['tests/test_podcast_durability.py', 'tests/test_podcast_corpus_bridge.py',\n"
    "                'tests/test_podcast_background_jobs.py', 'tests/test_podcast_workflow_truth.py',\n"
    "                'tests/test_podcast_url_validation.py'],",
    "'podcast': ['tests/test_dashboard_sources_api.py', 'tests/test_dashboard_sources_ui.py', "
    "'tests/test_dashboard_v324_ui.py', 'tests/test_source_subscriptions*.py', 'tests/test_podcast_*.py'],")
s = s.replace("'as6'", "'as7'").replace("'_scratch/as6'", "'_scratch/as7'")
assert "'tests/test_podcast_*.py'" in s
sys.argv = [str(p), 'podcast']
exec(compile(s, str(p), 'exec'), {'__name__': '__main__', '__file__': str(p)})
```

Logs are retained locally in `_scratch/as7/{strict,new-tests,final-strict,combined}.log`
and `companion-<group>.log`; the unchanged companion runner writes its JSON results
under `_scratch/as6`, and the combined run's result is `_scratch/as7/podcast-result.json`.
The reproducible evidence and UI cases are in
[test_phase3_acceptance7.py](../../tests/library_work_astra/test_phase3_acceptance7.py).

Handoff: AS-7 review complete; Phase 3 not accepted. Added this report and twelve
AS-7 cases. Evidence: original 159/159; final 163 passed/8 failed; companions
394 passed; combined suite 180 passed; 49 manifest entries and retained AT6
database verified. Open work: the two C21 UI repairs, C20 scenario 03, C21
replacement evidence and Ryan's C22. Implementation, existing tests, receipts,
contracts and protected Phase 2 inputs remain unchanged by this worker.
