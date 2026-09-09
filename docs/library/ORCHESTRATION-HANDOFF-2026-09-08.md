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

## State at handoff (updated 2026-09-08 18:18 PDT; implementation/review HEAD `3d2fa9f`; not pushed)

| Phase | State | Astra's latest ruling | Next |
|---|---|---|---|
| 2 | Done. Stage 4 P2-7 FAIL (39/46, 6/11), record clean, AX-1 repaired | `STAGE4-AUDIT-2026-09-08.md`: option 3 recommended | Ryan decides the 0.90 rule |
| 3 | AS-9 integrated (`6807361`): accepted subject to C22 only | `PHASE3-ACCEPTANCE-9-2026-09-08.md`; integrator reproduced confirmation 11/11, strict 178 passed + four superseded-evidence failures, companions 394 passed and dashboard 35 passed in both worktree and checkout | C22 = Ryan's installed Inno receipt (AS-7 lists it) |
| 4 | AV-5m3 (`270e569`) integrated as intermediate work: 209 passed / eight unchanged parent-interceptor failures in both roots. AW-4 adds four failed ownership/staging cases plus lifecycle findings | `PHASE4-ACCEPTANCE-4-2026-09-08.md`: Phase 4 remains unaccepted | AV-5m4a (gemini binding/temp/staging) and AV-5m4b (grok lifecycle/exclusion), then finish AW-4 and real-client rerun. Frozen fixture ruling is Ryan's |
| 5 | AZ-5d2 integrated: both roots 470 passed / five failed, BA-3 51/52, dashboard3 7/7, fixtures 28/28. Forbidden wrapper inspection removed | Four measurement failures remain; the unary/clock fixture conflict is Ryan's. Independent actual-handler deadline and nested-admission tests pass | AZ-5g (gemini), then BA-4 (codex) |
| 6 | BC-3a3 (`00fe216`) integrated: frozen BD 11/14, five new implementation tests pass. BD-2 reproduces stale-input replacement in capture and podcast owners | `PHASE6-BD2-2026-09-08.md`: two new failures, one passing ledger-history control; prior 11 omitted-ticket failures retained. BD-27 observed | BC-3d (grok), then finish BD-2. Legacy fixture ruling and speaker material remain Ryan gates |
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
AV-5m3 grok `c5f611c8` integrated at `270e569` as intermediate work, not acceptance.
BC-3a3 grok `855b1d16` integrated at `00fe216`. AZ-5d grok `e739a5ec`
finished and is rejected; its full diff is retained. AZ-5d2 and BC-3d are
running from `90151e7` (started 17:44-17:45 PDT): AZ-5d2 `7afd1cb4`, BC-3d
`31d2ed06`. AV-5m4a gemini `eb32f3b4` and AV-5m4b grok `5c22dbae` started
17:53 PDT on `98d8b35`.
Worktrees are under `%LOCALAPPDATA%\AgentControlRoom\worktrees\uoink-library\<run8>-<3>\<engine>`.

1. AS-9 (Phase 3) complete at `6807361`: accepted subject to C22 only. C22 stays under
   Blockers for Ryan. Four unchanged assertions against superseded AT6/browser evidence
   remain failures; AS-8/AS-9 cover the replacement at7 evidence.
2. AZ-5a3g (Phase 5) integrated at `d437b59`; earlier failed diffs remain retained.
   AZ-5d2 is verified and integrated. Dispatch AZ-5g (gemini) from
   `PHASE5-AZ5G-BRIEF-2026-09-08.md` and the original AZ-5 brief.
   BA-4 (codex review) follows on the integrated candidate.
3. AV-5m3 is integrated at `270e569`; AV-5m2 remains rejected. Dispatch/verify
   AV-5m4a (gemini) and AV-5m4b (grok) from their separate `PHASE4-AV5M4A-BRIEF-2026-09-08.md`
   and `PHASE4-AV5M4B-BRIEF-2026-09-08.md` scopes. Finish AW-4 (codex), then the real-client rerun (AW-3
   lists the five requirements; Fable's earlier receipt is `PHASE4-AW-RECEIPT-2026-09-08.md`
   and its harness under `docs/library/proof/aw-2026-09-08/`).
4. Phase 6: BC-3a3 is integrated at `00fe216`; BC-3a2 remains rejected.
   Run BC-3d (grok) from `PHASE6-BC3D-BRIEF-2026-09-08.md` for the reproduced
   owning-input defects; verify/integrate and finish BD-2 (codex). Preserve both
   rejected diffs and the quota failure.
   BD-27 normal-Comet observation is recorded as satisfied;
   the speaker gate remains Ryan's.
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
  the publication forbidden by its visibility case, and eight old Phase 4
  parent-process interceptors cannot observe the new isolated writer's syscall;
  Phase 6's legacy successful
  publication setup omits the build-time tickets now required by BD-01; Phase 5's
  final-wire probe is unary but its shared helper calls it with `clock=NOW`. See
  `INTEGRATOR-CONTRACT-CONFLICTS-2026-09-08.md`. Authorize corrected fixture setup
  without weakening the behavior assertions, or give another explicit ruling.
  Existing tests remain unchanged; unfinished implementation remains Astra's work.
- Phase 6: the navigation study passed numerically; the speaker gate is blocked on already-held
  diarization output plus independent human annotations for 30 passages across five items
  (BD lists the exact requirement). BD-27 is now observed in normal Comet with
  retained playback, chapter-list and 0:34 screenshots; prior Chrome/503 attempts remain partial.
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

### 2026-09-08 17:26 PDT — BD-27 observed through Windows computer-use

Correction to the earlier browser inventory: the browser connector exposes only
the in-app browser, but a separate deferred `node_repl` tool plus the installed
Windows computer-use skill reaches the user's normal Comet window. Read and use
that skill's documented runtime; do not conclude all native app access is absent
from the browser connector's inventory alone. Claude Desktop also appears in
the Windows app inventory; no client observation of it has occurred yet.

The new Comet tab loaded the supplied BD-27 URL and played at observed 0:35.
The source description lists 00:34 Why computer use; its link played at observed
0:36. The final still is paused at exactly displayed 0:34 after manual positioning.
See `PHASE6-BD27-PLAYER-RECEIPT-2026-09-08.md` and its sealed raw images. This
satisfies the playback observation only and preserves both previous partial
Chrome runs. No claim is made about subsecond physical seek accuracy or speaker
accuracy. No capture button or resident-helper request was issued by the observer.

BD-27 receipt/images are committed at `1217dbf`. All seven artifact hashes match
both the working files and committed blobs. The `bd-player-*` proof directory
also needs `-text` attributes so a future Windows checkout cannot change its
sealed JSON line endings; that preservation rule is recorded with this entry.

### 2026-09-08 17:40 PDT — BC-3a3 integrated; BD-2 review started

BC-3a3 integrated with three-way apply at `00fe216`. Worker and checkout each
have **155 passed, 11 failed** (67.37 s / 62.73 s), including all five new
implementation tests. Every failure is an omitted-ticket call in an unchanged
fixture; two expect corrupt-input errors but now meet the ticket requirement
first. They remain failed. Logs and exact commands are in worker-local
`_scratch/bc3a3-w` and checkout-local `_scratch/bc3a3-c`.

The raw and Index boundaries now reject every missing ticket. Sidecar key
removals and edits during ledger work survive the final carrier write. BD-2
still needs to review the whole operation: source inspection shows podcast
transcripts and capture plans can be read before their owning caller mints
the ticket. That timing concern is being reproduced; no new finding or Phase 6
acceptance is claimed from inspection alone.

### 2026-09-08 17:44 PDT — BD-2 owning defects and AZ-5d rejection

BD-2 reproduced stale capture replacement (one failed / one podcast-history
control passed, 9.48 s). The separately briefed unseen-podcast probe also failed
(3.06 s). Both owners can mint the newer base after consuming old input.
`PHASE6-BC3D-BRIEF-2026-09-08.md` assigns the repair; these defects remain our
work, not Ryan blockers. No existing acceptance file was edited.

AZ-5d independently produced **393 passed, four failed**, 109.07 s. It is
rejected because `_read_activity` traverses a test callback's closure to
bypass a mismatched wrapper. Its complete patch/report is retained. The new
AZ-5d2 brief removes that workaround, preserves the general repairs and adds
an independent adapter-deadline test. The frozen unary/clock wrapper conflict
is recorded for Ryan. Four measurement failures remain AZ-5g work.

### 2026-09-08 17:53 PDT — AV-5m3 integrated; AW-4 repairs reserved

AV-5m3 integrated at `270e569`, explicitly as intermediate work. Worker and
checkout each have **209 passed, eight failed** (64.43 s / 67.72 s), including
seven new isolation tests. Logs: `_scratch/av5m3-w` and `_scratch/av5m3-c`.
The old parent replacement callbacks are never invoked by the isolated child;
their eight failures remain visible and require Ryan's fixture ruling.

AW-4 adds four failed reproductions (2.43 s, `_scratch/aw4-review`): missing
binding readopts an empty replacement vault, failed atomic persistence has
already changed binding bytes, temp cleanup deletes a different file with the
same bytes, and the real source stage omits the required new writer. Lifecycle
inspection also finds unchecked job assignment/death, mutable state reused by
a surviving old parent thread, and temp-root-dependent exclusion. AV-5m4a and
AV-5m4b reserve separate repair regions; integrate both with three-way apply
and review their overlap. None of these implementation gaps is a Ryan blocker.

### 2026-09-08 18:18 PDT � AZ-5d2 verified and integrated

AZ-5d2 Grok `7afd1cb4` independently produced **470 passed, five failed**
in both roots (123.01 s worker, 109.21 s checkout). Logs/XML/commands:
worker `_scratch/az5d2-wi`, checkout `_scratch/az5d2-ci`. Three-way apply
was clean. No existing tests changed. BA-3 is 51/52; its unary/clock
fixture TypeError remains failed for Ryan. Both new implementation tests
pass. Four measurement-document failures remain AZ-5g, now governed by
`PHASE5-AZ5G-BRIEF-2026-09-08.md`; no current measurement pass is claimed.

BC-3d finished and independently has 158 passed / 11 omitted-ticket
failures in its worktree (79.87 s). Its three BD-2 races pass, but a new
review probe shows identical cue text with newer transcript provenance
can still be overwritten. Preserve this failed observation and brief a
complete consumed-input binding repair after integration.

AV-5m4a Gemini `eb32f3b4` timed out without its required report. Its
partial diff is under independent verification; it is not accepted. The
draft still directly writes a new binding, swallows witness failures and
fallbacks from identity-checked unlink on TypeError. AV-5m4b remains active.
