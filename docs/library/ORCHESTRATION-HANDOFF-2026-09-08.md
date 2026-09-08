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

## State at handoff (updated 2026-09-08 16:38 PDT; implementation/review HEAD `c8ddf9b`; not pushed)

| Phase | State | Astra's latest ruling | Next |
|---|---|---|---|
| 2 | Done. Stage 4 P2-7 FAIL (39/46, 6/11), record clean, AX-1 repaired | `STAGE4-AUDIT-2026-09-08.md`: option 3 recommended | Ryan decides the 0.90 rule |
| 3 | AS-9 integrated (`6807361`): accepted subject to C22 only | `PHASE3-ACCEPTANCE-9-2026-09-08.md`; integrator reproduced confirmation 11/11, strict 178 passed + four superseded-evidence failures, companions 394 passed and dashboard 35 passed in both worktree and checkout | C22 = Ryan's installed Inno receipt (AS-7 lists it) |
| 4 | AV-5r (`99e9412`) and AV-5m1 (`9489141`) integrated: D01-D03 and D07-D10 closed; AW-3 has 10 passing cases including the control, seven open | `PHASE4-ACCEPTANCE-3-2026-09-08.md`; integrator combined checkout suites: 203 passed, seven D12-D15 failures | Dispatch AV-5m2 (grok D12-D15) from `PHASE4-AV5-BRIEF`; then AW-4 (codex); then the real-client rerun per AW-3's five requirements (claude -p on the subscription, no paid API) |
| 5 | AZ-5c/5e (`46163a4`), AZ-5f (`1fb7f78`), AZ-5b (`48655c5`) integrated: BA-3 acceptance set 23 of 52 closed, dashboard3 7/7, measurements3 0/3. AZ-5a2 rejected: fixture pagination returns 12 of the required 20 rows | `PHASE5-ACCEPTANCE-3-2026-09-08.md`; AZ-5a2 worktree verification: 326 passed, 26 failed; fixture set 27/28 | Write AZ-5a3 with measured byte counts and preserve AZ-5a2 unapplied; then AZ-5d (grok BA-09/10/11), AZ-5g (gemini BA-14), then BA-4 (codex) |
| 6 | BC-3b (`effd145`) and BC-3c (`c8ddf9b`) integrated: BD set 9/14 pass, five BD-01/03/05/06 cases open. BC-3a failed quota/partial and is rejected | `PHASE6-BD-2026-09-08.md`; BC-3c worker and checkout each 156 passed / five open, including 147 companion passes | Dispatch BC-3a2 on Grok from `PHASE6-BC3A2-BRIEF-2026-09-08.md`; then BD-2 (codex). Navigation study passed numerically; BD-27 partial twice and speaker material remain Ryan gates |
| Integration | Not started | | After phases: candidate branch from the review base, Astra reviews conflict resolutions, full suite, installed-tree receipts (Ryan) |

Receipts and artifacts: `docs/library/proof/` (stage archives, S20 matrix, S21 incl. run at7, S22, AW,
process recovery, BD study inputs + Astra's study). Full legacy tree at `2a7af56`: 1,950 passed with the
open reproduction sets deselected (AW-3 11 open, BA-3 29+3 open, BD 8 open at HEAD).

## Queue (in order; each item names its brief)

Takeover runs: AS-9 codex `a13febd1` integrated at `6807361`; AZ-5a2 claude `6e929e1d`
finished but rejected; AV-5m1 gemini `b31e890f` integrated at `9489141`.
BC-3c grok `ff01d490` integrated at `c8ddf9b`. BC-3a gemini `eb0f138e` failed on quota
with a rejected partial diff. AZ-5a3 gemini `bbd68b73` also failed on quota, no diff.
AV-5m2 grok `6b5e5f1e` is running at `633eb99`. Route AZ-5a3g and BC-3a2 to Grok.
Worktrees are under `%LOCALAPPDATA%\AgentControlRoom\worktrees\uoink-library\<run8>-<3>\<engine>`.

1. AS-9 (Phase 3) complete at `6807361`: accepted subject to C22 only. C22 stays under
   Blockers for Ryan. Four unchanged assertions against superseded AT6/browser evidence
   remain failures; AS-8/AS-9 cover the replacement at7 evidence.
2. AZ-5a2 (Phase 5) rejected and retained as `patches/az5a2-claude-2026-09-08.patch`.
   Dispatch `PHASE5-AZ5A3-BRIEF-2026-09-08.md` as AZ-5a3g on Grok; it records
   the measured byte counts and requires all 18 BA-01/BA-03 cases and the 28 fixture tests.
   Then dispatch AZ-5d (grok) and, after it, AZ-5g (gemini) from
   `PHASE5-AZ5-BRIEF-2026-09-08.md`; then BA-4 (codex review) on the integrated candidate.
3. AV-5m1 (Phase 4) complete at `9489141`. Verify running AV-5m2 (grok `6b5e5f1e`) from
   `PHASE4-AV5-BRIEF-2026-09-08.md`; then AW-4 (codex); then the real-client rerun (AW-3
   lists the five requirements; Fable's earlier receipt is `PHASE4-AW-RECEIPT-2026-09-08.md`
   and its harness under `docs/library/proof/aw-2026-09-08/`).
4. Phase 6: BC-3c is integrated. Dispatch BC-3a2 from `PHASE6-BC3A2-BRIEF-2026-09-08.md`
   on Grok; preserve BC-3a's failed partial diff and the quota failure.
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

## Blockers for Ryan (unchanged)

- Phase 2: keep 0.90 strict, change the rule, or ship with owner review.
- Installed Inno package receipts (Phase 3 C22, Phase 4).
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
