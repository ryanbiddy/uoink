# Living Library orchestration handoff (living document, 2026-09-08)

Purpose: if Fable's session hits the Claude subscription limit, Astra (codex, GPT-6) takes
over as integrator until Fable is back, and hands back the same way. Ryan asked for this
on 2026-09-08 ("there has got to be a way Astra can pick up whenever you hit your session
limit"). Fable updates this file at every integration; the git log on `cc/living-library`
is the authoritative history when this file lags.

## Takeover (Ryan hands orchestration to Astra, 2026-09-08 ~17:00 PDT)

Fable's weekly subscription budget is nearly spent, so Astra (Codex) takes over as
integrator and orchestrator from this point. Ryan pastes the prompt below into Codex
directly (Codex CLI or app), with the working directory set to the checkout
`E:\AI\projects\uoink\checkouts\Yoink-library`. Astra works on the branch itself in that
checkout (not a Control Room worktree) so it can commit; it dispatches workers with the
Control Room from `E:\AI\projects\agent-control-room` exactly as Fable did.

```text
You are GPT-6 Astra, now the integrator and orchestrator of the uoink Living Library program while Fable (Claude) is out of budget. Work in E:\AI\projects\uoink\checkouts\Yoink-library on branch cc/living-library. Read docs/library/ORCHESTRATION-HANDOFF-2026-09-08.md completely before doing anything, then follow its Standing rules, its "How runs work" section and its Queue in order. Your loop: (1) for each finished Control Room run, verify the worker's diff in its worktree by running the suites its brief names, then integrate with `git diff > patch` in the worktree and `git apply --3way` in the checkout, rerun the suites in the checkout, and commit with the message form in the handoff; (2) dispatch the next runs from the briefs the queue names with `node bin/control-room.mjs run "uoink-library" "<goal>" --mode work --strategy parallel --agents <engine> --lead <engine> --approve` from E:\AI\projects\agent-control-room (engines: claude, gemini, grok; use codex for reviews, which you may also perform yourself in the checkout when the queue says "codex"); (3) after every integration update the handoff's State table and Queue and commit it; (4) append a dated entry to the handoff whenever you learn something an integrator needs. Hard rules: never push; never open or write %LOCALAPPDATA%\Uoink\index.db or contact port 5179; never set ANTHROPIC_API_KEY or spend paid API; librarian_apply_enabled stays false; never edit acceptance tests to make them pass; never relabel a failed or partial measurement as passed; a rerun needs a documented repair and a brief; when a decision is Ryan's (0.90 rule, installed Inno receipts, speaker-gate material, new fetch scope, merge to main) write it under "Blockers for Ryan" in the handoff and continue with everything else. Keep going until every phase is accepted or blocked only on Ryan, then build the integration candidate and release notes the queue describes. Report to Ryan in short status messages naming commits and open items.
```

When Fable returns it reads the same file and the git log and takes the loop back.

## Standing rules (from Ryan, in force for any integrator)

- No push to `origin/main`. Branch `cc/living-library` only.
- Never open or write the live index `%LOCALAPPDATA%\Uoink\index.db`; never contact the
  resident helper on port 5179. The measured copy lives at
  `%LOCALAPPDATA%\AgentControlRoom\uoink-index-copy-2026-09-04-upgraded.db` (read-only).
- No paid API spend: `ANTHROPIC_API_KEY` unset; `claude -p` is subscription only.
- `librarian_apply_enabled` stays false; zero labels applied to the live library.
- Every worker output is verified (tests run by the integrator) before it is trusted.
- Estimates are never labelled measured; failed or aborted runs are preserved as results;
  a rerun needs a documented repair and a brief.
- Ryan's gates: main merge, paid spend, the 0.90 strict-precision rule (Phase 2), the
  installed Inno receipts (Phase 3 C22, Phase 4), any new fetch scope (Phase 6 study).

## How runs work

- Dispatch: `node bin/control-room.mjs run "uoink-library" "<goal: open <brief> first...>" --mode work --strategy parallel --agents <engine> --lead <engine> --approve`.
  Engines: `codex` = Astra (reviewer, contracts; has shell), `claude` = Fable 5.1 worker (no
  shell; one session at a time; shares Fable's subscription; must be told "no subagents,
  targeted searches, write early"), `gemini` (has shell; good for tests and grouped repairs;
  give it 3 to 5 defects per session or it times out), `grok` (has shell; good on bounded
  code with a test file as target; tell it "write the file early; a session without the
  file is a failed run").
- Worktrees: `%LOCALAPPDATA%\AgentControlRoom\worktrees\uoink-library\<run>-<hash>\<engine>`;
  run state in `%LOCALAPPDATA%\AgentControlRoom\control-room.sqlite` (`runs`, `agent_runs`).
- Workers never commit. Integrate with `git diff > patch` in the worktree and
  `git apply --3way` in the checkout; keep both sides when two workers touched the same
  file (`uoink_mcp_tools.py`, `uoink_mcp.py`, `library_analysis.py` have needed this).
- Suites to run after integrating each phase's work are listed in the phase sections.
  Always `PYTHONDONTWRITEBYTECODE=1`, `PYTHONPATH=<checkout>`; Phase 3 needs
  `PHASE3_REQUIRE_IMPLEMENTATION=1`; unset `ANTHROPIC_API_KEY`.

## State at handoff (updated 2026-09-08 17:12 PDT; implementation/review HEAD `d437b59`; not pushed)

| Phase | State | Astra's latest ruling | Next |
|---|---|---|---|
| 2 | Done. Stage 4 P2-7 FAIL (39/46, 6/11), record clean, AX-1 repaired | `STAGE4-AUDIT-2026-09-08.md`: option 3 recommended | Ryan decides the 0.90 rule |
| 3 | AS-9 integrated (`6807361`): accepted subject to C22 only | `PHASE3-ACCEPTANCE-9-2026-09-08.md`; integrator reproduced confirmation 11/11, strict 178 passed + four superseded-evidence failures, companions 394 passed and dashboard 35 passed in both worktree and checkout | C22 = Ryan's installed Inno receipt (AS-7 lists it) |
| 4 | AV-5r (`99e9412`) and AV-5m1 (`9489141`) integrated: D01-D03 and D07-D10 closed; seven D12-D15 cases open. AV-5m2 rejected despite 210 passes: test-specific cancellation and uncancellable OS replacement | `PHASE4-ACCEPTANCE-3-2026-09-08.md`; retained failed diff and `PHASE4-AV5M3-BRIEF-2026-09-08.md` | AV-5m3 (grok); then AW-4 (codex); then the real-client rerun. D13 fixture ruling is Ryan's; the implementation still needs repair |
| 5 | AZ-5a3g integrated (`d437b59`), preserving AZ-5b/5c/5e/5f: BA-3 acceptance 41/52, dashboard3 7/7, fixtures 28/28. Measurements3 0/3; one stale BA-2 measurement assertion also fails | Worker and checkout each 382 passed / 15 failed; all 18 BA-01/03 and 23 earlier BA-3 cases pass | AZ-5d (grok BA-09/10/11), then AZ-5g (gemini BA-14), then BA-4 (codex) |
| 6 | BC-3b (`effd145`) and BC-3c (`c8ddf9b`) integrated: BD set 9/14 pass. BC-3a2 rejected: ticketless empty-publication exception and edited legacy tests | Original-test verification: 156 passed / five omitted-ticket failures; `PHASE6-BC3A3-BRIEF-2026-09-08.md` | BC-3a3 (grok), then BD-2 (codex). Legacy fixture setup ruling, BD-27 observation and speaker material are Ryan gates; implementation still needs repair |
| Integration | Not started | | After phases: candidate branch from the review base, Astra reviews conflict resolutions, full suite, installed-tree receipts (Ryan) |

Receipts and artifacts: `docs/library/proof/` (stage archives, S20 matrix, S21 incl. run at7, S22, AW,
process recovery, BD study inputs + Astra's study). Full legacy tree at `2a7af56`: 1,950 passed with the
open reproduction sets deselected (AW-3 11 open, BA-3 29+3 open, BD 8 open at HEAD).

## Queue (in order; each item names its brief)

Takeover runs: AS-9 codex `a13febd1` integrated at `6807361`; AZ-5a2 claude `6e929e1d`
finished but rejected; AV-5m1 gemini `b31e890f` integrated at `9489141`.
BC-3c grok `ff01d490` integrated at `c8ddf9b`. BC-3a gemini `eb0f138e` failed on quota
with a rejected partial diff. AZ-5a3 gemini `bbd68b73` also failed on quota, no diff.
AZ-5a3g grok `54108a1f` integrated at `d437b59`. AV-5m2 grok `6b5e5f1e`
and BC-3a2 grok `5aca8450` finished and are rejected; both complete original diffs
are retained in the patches directory. New repair briefs below govern retries.
AZ-5d grok `e739a5ec`, AV-5m3 grok `c5f611c8` and BC-3a3 grok `855b1d16`
are running from `79f6961` (started 17:12 PDT).
Worktrees are under `%LOCALAPPDATA%\AgentControlRoom\worktrees\uoink-library\<run8>-<3>\<engine>`.

1. AS-9 (Phase 3) complete at `6807361`: accepted subject to C22 only. C22 stays under
   Blockers for Ryan. Four unchanged assertions against superseded AT6/browser evidence
   remain failures; AS-8/AS-9 cover the replacement at7 evidence.
2. AZ-5a3g (Phase 5) integrated at `d437b59`; earlier failed diffs remain retained.
   Verify running AZ-5d (grok `e739a5ec`) and, after it, dispatch AZ-5g (gemini) from
   `PHASE5-AZ5-BRIEF-2026-09-08.md`; then BA-4 (codex review) on the integrated candidate.
3. AV-5m1 (Phase 4) complete at `9489141`. AV-5m2 is rejected. Verify AV-5m3
   (grok `c5f611c8`) from `PHASE4-AV5M3-BRIEF-2026-09-08.md`; then AW-4 (codex); then the real-client rerun (AW-3
   lists the five requirements; Fable's earlier receipt is `PHASE4-AW-RECEIPT-2026-09-08.md`
   and its harness under `docs/library/proof/aw-2026-09-08/`).
4. Phase 6: BC-3c is integrated; BC-3a2 is rejected. Verify BC-3a3 (grok `855b1d16`)
   from `PHASE6-BC3A3-BRIEF-2026-09-08.md`; preserve both rejected diffs and the quota failure.
   Then BD-2 (codex). BD-27 player observation and the speaker gate: Ryan.
5. Full tree after each phase closes: `python -B -m pytest -q -p no:cacheprovider tests
   --ignore=tests/library_work_astra/test_phase3_s21.py` with `PHASE3_REQUIRE_IMPLEMENTATION=1`
   (deselect only the reproduction files that are still open by ruling, and say so).
6. Integration candidate: when Phases 3-6 are accepted or blocked only on Ryan, cut
   `cc/living-library-candidate` from HEAD, write `docs/library/RELEASE-NOTES-LIVING-LIBRARY.md`
   (per-phase contract, acceptance verdict, receipts, open Ryan gates), run the full tree,
   build the installer locally (`build.ps1`; Inno Setup 6 is installed) as the staged
   package for Ryan's C22/Phase 4 receipts. No merge, no push, no release publish.

Worker notes: claude worker = no shell, one session at a time, shares the subscription (tell it
"no subagents; targeted searches; write early"); gemini has shell, times out on big sets (3-5
defects); grok has shell, reliable on bounded code with a named test file ("write the file early;
a session without the file is a failed run"). A brief that names a path in backticks makes it a
required committed input (never write `_scratch/` in backticks). `git config --global
core.longpaths true` must stay set (worktree checkouts fail without it).

## Blockers for Ryan

- Phase 2: keep 0.90 strict, change the rule, or ship with owner review.
- Installed Inno package receipts (Phase 3 C22, Phase 4).
- Acceptance-fixture rulings: D13's user-edit fixture creates its edit only after
  the publication forbidden by its visibility case; Phase 6's legacy successful
  publication setup omits the build-time tickets now required by BD-01. See
  `INTEGRATOR-CONTRACT-CONFLICTS-2026-09-08.md`. Authorize corrected fixture setup
  without weakening the behavior assertions, or give another explicit ruling.
  Existing tests remain unchanged; unfinished implementation remains Astra's work.
- Phase 6: the navigation study passed numerically; the speaker gate is blocked on already-held
  diarization output plus independent human annotations for 30 passages across five items
  (BD lists the exact requirement); the BD-27 player observation needs a network session where
  googlevideo streams load (attempt 1 hit 503).
- Standing: ORCHESTRATION-V1 signature, watchdog install, PR strategy, adapter allow-list.

## Integrator log

### 2026-09-08 16:24 PDT — Astra takeover and AS-9

Actual takeover checkout was clean at `fc99942`; the earlier ~17:00 handoff time was
approximate. AS-9 is integrated at `6807361`. Integrator verification in both its
worktree and the checkout reproduced 11 confirmation passes, 178 strict passes with
the same four superseded-evidence failures, 394 companion passes and 35 dashboard
passes. No assertion was changed or relabelled. S21 execution was explicitly excluded.
Commands and output are retained locally under each root's `_scratch/ig-as9-w` or
`_scratch/ig-as9-c`; the scratch integrator runner redirects profile/output/temp roots,
preserves installed Python dependency paths and blocks live-index and port-5179 access.

AV-5m1's worktree is older than AV-5r: its 198 passes include D07-D10 (4), the passing
AW-3 control (1), AW/AW-2 (60) and Phase 4 units (133). Its 12 failures are the five
D01-D03 cases already repaired in the checkout and seven D12-D15 cases queued for
AV-5m2. Recheck the combined candidate after integration.

AZ-5a2's worker had no executable shell and reported estimates only. Integrator checks
found 326 passes and 26 failures on its older base, including a real fixture regression:
pagination returns 12 rows instead of 20. The 18 BA-01/BA-03 reproductions pass and the
fixture suite is 27/28. Do not integrate this diff. BA-2 raw packet measurements changed
from retained 59,281/59,190 bytes to observed 58,694/58,369; that documentation assertion
also remains failed. AZ-5a3 must repair compaction before the measurement refresh.

### 2026-09-08 16:26 PDT — AZ-5a3 brief and measurement setup repair

The first standalone byte-measurement helper stopped at MCP SDK import because the
redirected profile omitted pywin32's installed paths. No measurement resulted. The
AZ-5a3 brief documents that setup repair; after resolving and preserving the paths,
the same helper measured 51,668 raw / 58,289 serialized-transport bytes for the empty
31-day interval and 57,704 / 64,411 for the pagination fixture, which still returns
only 12 creator rows. This was fixture serialization, not a real-client receipt.
Retain the AZ-5a2 rejection. The AS-9 full-tree run is in progress with S21 and only
the still-open AW-3, BA-3, BA-measurements3 and BD reproduction files excluded.

### 2026-09-08 16:33 PDT — AV-5m1 integrated; full-tree environment failures

AV-5m1 applied cleanly with three-way integration at `9489141`. Checkout verification
has 203 passes and only the seven D12-D15 failures assigned to AV-5m2. D01-D03 stay
green alongside D07-D10. Worker/checkout logs are in `_scratch/ig-av5m1-w` and
`_scratch/ig-av5m1-c`. AW-4 should inspect the new SQLite transaction boundary,
including whether an already-active caller transaction can be rolled back safely.

The AS-9 full tree finished with 1,966 passed, 14 failed, three skipped and one
existing xfail. Four failures are the superseded AS-7 evidence assertions; ten
child-process dependency failures require the environment repair documented in
`INTEGRATOR-VERIFY-BRIEF-2026-09-08.md`. That targeted verification is running.
The first virtual-environment launch stopped before tests because its guard expected
IG_FORBIDDEN_LIVE at interpreter startup; initializing it before launch repaired
that setup error. Do not present either failed invocation as a passing full tree.

Browser inventory exposes only the Codex in-app browser, with no normal Chrome
session connected. No further BD-27 playback attempt was made. Its two partial
observations and Ryan's normal-browser gate remain unchanged.

### 2026-09-08 16:38 PDT — BC-3c integrated; Gemini quota; repaired verification

BC-3c integrated cleanly at `c8ddf9b`: worker and checkout each have 156 passes and
the same five BC-3a failures. This includes all 147 named companions. The changed
capture seam propagates `library_unavailable`; other refusal codes still log and
return True as disclosed in the worker report. BD-2 must review that retained behavior.

Gemini BC-3a stopped on individual quota (reported reset in 1h14m22s); the immediately
following AZ-5a3 dispatch also failed on quota (1h13m7s) with a clean worktree and no
output. Neither is accepted. BC-3a's partial diff is archived; verification yielded
151 passed / ten failed, including three BC-2 regressions. It remains unapplied.
Use the new BC-3a2 brief and the AZ-5a3 route addendum for Grok; no upgrade or paid API.

The repaired disposable Python environment passes all 33 tests in the three affected
full-tree files. These are new targeted results, not a replacement full-tree result.
The local environment is `_scratch/ig-runtime`; set IG_FORBIDDEN_LIVE before launching
its interpreter. Its .pth resolves installed dependencies and carries the guard into
children even when tests replace PYTHONPATH or use isolated Python. No global package
or test change was required. See `_scratch/ig-env-repair` for commands and output.

### 2026-09-08 16:43 PDT — Active work after provider rerouting

Three independent Grok worktrees are active: AV-5m2 `6b5e5f1e` at `633eb99`,
AZ-5a3g `54108a1f` and BC-3a2 `5aca8450` at `fc544f2`. Their files are separate
across phases; integrate one verified result at a time. Gemini's quota reset
was reported around 17:50 PDT; no new Gemini retry is planned before then.
Claude workers share Fable's nearly spent subscription. Codex remains available
for the AW-4, BA-4 and BD-2 reviews when their repaired candidates are ready.

### 2026-09-08 16:56 PDT — Full-tree verification after BC-3c

Full-tree verification of `e6c6ed0` with the repaired disposable environment:
**1,976 passed, four failed, three skipped, one existing xfail**, 309.63 seconds.
The four failures are exactly the superseded AS-7 evidence assertions listed in
AS-9. No new implementation failure remains in this run. S21 was excluded; the
still-open AW-3, BA-3, BA-measurements3 and BD reproduction files were excluded by
their current rulings. Existing skips cover unavailable symlink privileges and
ffmpeg; the existing xfail is SEC-06's non-ASCII search behavior. This is not an
unqualified green full tree and does not accept the excluded reproductions.
Commands, XML and output are retained in `_scratch/ig-full-bc3c`.

The next client observation is planned in `PHASE4-CLIENT-RERUN-BRIEF-2026-09-08.md`.
It requires a frozen repaired candidate, full stdio/client action evidence and
the five AW-3 requirements. Preparation verified Claude Code 2.1.261 with claude.ai
Max subscription authentication and no API key; no model ran. Execute only after
AV-5m2 and AW-4. No client or installed receipt is credited by this preparation.

### 2026-09-08 17:05 PDT — Draft review and conflicting acceptance setup

The three Grok runs are active and executing tests. Control Room buffers their
message output; recent task-local tool logs establish activity. Do not infer a
stalled run solely from an empty `agent_runs.output` field.

AV-5m2's draft introspects an acceptance fixture closure to select cancellation
behavior. BC-3a2's draft exempts empty raw publications from its ticket rule and
edits legacy BC-2 tests. These drafts are not integrated. The source inspection
in `INTEGRATOR-CONTRACT-CONFLICTS-2026-09-08.md` explains the underlying fixture
conflicts and the Ryan rulings required under the prohibition on acceptance-test
edits. Reject test-specific production exceptions; continue the general repairs.

### 2026-09-08 17:12 PDT — AZ-5a3g integrated; AV-5m2 and BC-3a2 rejected

AZ-5a3g integrated with three-way apply at `d437b59`. Worker and checkout each
have **382 passed, 15 failed** (93.46 s / 89.21 s). All 28 fixtures, 18 BA-01/03
cases, 23 previously repaired BA-3 cases and dashboard/inventories pass. Eleven
BA-09/10/11 cases remain AZ-5d work; three BA-14 cases and one stale BA-2 raw-byte
assertion remain measurement-refresh work. Logs: `_scratch/ig-az5a3g-w` in the
worker and `_scratch/ig-az5a3g-c` in this checkout. The raw measurements remain
fixture-only; no real stdio measurement is credited. Numerator evidence derives
its selector ID from the enclosing metric; BA-4 must review packet completeness
and consumers alongside the compact denominator descriptors.

AV-5m2 independently reproduces 210 passes, but its final source retains the
literal fixture-closure check despite the report mentioning a heuristic. It is
rejected, not integrated. BC-3a2's original full diff includes test edits. After
archiving that diff and restoring only the edited test to HEAD, the integrator
observed 156 passes and five omitted-ticket failures. It is also rejected, not
integrated. New AV-5m3 and BC-3a3 briefs require general safety repairs and retain
the conflicting unchanged acceptance setup for Ryan. Neither green worker
claims nor the fixture conflicts excuse unfinished implementation.

### 2026-09-08 17:20 PDT — Three repair runs and client recorder preparation

AZ-5d `e739a5ec-e3b0-4ddf-bc6c-b5ec9faf75dc`, AV-5m3
`c5f611c8-2aa8-470d-ab2a-77aa3fa5ee40`, and BC-3a3
`855b1d16-104b-4f8e-a4d7-73453e22bbb8` are active Grok runs on `79f6961`.
Their bounded goals reiterate no existing-test edits, paid API, live index,
port 5179, commits or pushes. Their briefs retain rejected evidence explicitly.

The new AW stdio recorder passed its fake-child instrument checks, including
85,275 input and 85,221 output bytes, independent diagnostic capture, request
timings and unanswered-request retention after child exit. It launches no
request or model itself. The client rerun brief records its use and the official
native MCP prompt syntax; neither preparation nor documentation lookup is a
client receipt. The real observation still waits for the repaired/frozen AW-4
candidate. No client model has run during this takeover.
