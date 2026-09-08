# Living Library orchestration handoff (living document, 2026-09-08)

Purpose: if Fable's session hits the Claude subscription limit, Astra (codex, GPT-6) takes
over as integrator until Fable is back, and hands back the same way. Ryan asked for this
on 2026-09-08 ("there has got to be a way Astra can pick up whenever you hit your session
limit"). Fable updates this file at every integration; the git log on `cc/living-library`
is the authoritative history when this file lags.

## Takeover command (Ryan runs it from `E:\AI\projects\agent-control-room`)

```powershell
node bin/control-room.mjs run "uoink-library" "Living Library TAKEOVER: you are GPT-6 Astra acting as integrator while Fable is out. Open docs/library/ORCHESTRATION-HANDOFF-2026-09-08.md, follow its rules and work the queue in order: integrate finished worker runs from their worktrees (git apply --3way from each worktree's diff, run the named suites, commit on cc/living-library with the message form below), dispatch the next runs with node bin/control-room.mjs from E:\AI\projects\agent-control-room using the brief files named in the queue, and update this handoff file and commit it after every step. Never push, never touch the live index or port 5179, never set ANTHROPIC_API_KEY, never edit acceptance tests to make them pass, never relabel a failed measurement as passed. Stop and write a blocker into this file when a decision is Ryan's." --mode work --strategy parallel --agents codex --lead codex --approve
```

Astra can run shell, tests and git in its Control Room worktree. To commit to the branch
itself, Astra must work in the checkout `E:\AI\projects\uoink\checkouts\Yoink-library`
(Control Room worktrees are branched copies); the takeover prompt above grants that for the
takeover only. Commit message form: `<Phase> (<run id>, <engine>): <what>` and the trailer
`Co-Authored-By: GPT-6 Astra <noreply@openai.com>` plus `Integrated-by: Astra takeover`.

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

## State at handoff (HEAD `eb58fe1`, 268 commits ahead of `3e06c65`, not pushed)

| Phase | State | Astra's latest ruling | Next |
|---|---|---|---|
| 2 | Done. Stage 4 P2-7 FAIL (39/46, 6/11), record clean, AX-1 repaired | `STAGE4-AUDIT-2026-09-08.md`: option 3 recommended | Ryan decides the 0.90 rule |
| 3 | Round 5: AS-01/04/05/06 closed; AS-02 (2) and AS-03 (3) open, 12 reproductions in `tests/library_work_astra/test_phase3_acceptance5.py` | `PHASE3-ACCEPTANCE-5-2026-09-08.md`; conditions C20 (browser matrix), C21 (launcher reconciliation), C22 (installed Inno, Ryan) | Run AT-6: brief to write from the AS-5 defect table (Grok did AT-5 well); then S21 rerun, C20/C21 browser work, AS-6 |
| 4 | Code complete; acceptance set `tests/library_work_astra/test_phase4_aw_acceptance.py` at 4 failing (D05, D07 x2, D08) after AV-3m (Gemini) and AV-3r (Claude, partial) | `PHASE4-ACCEPTANCE-2026-09-08.md` NOT ACCEPTED (16 defects, 12 now closed) | Run AV-3s: close D05 (reshelve-review binding, `library_prompts.py`), D07 (brief freshness, `library_briefs.py`), D08 (`server.py` `_purge_trash` calls `library_briefs` purge); then AW-2 review |
| 5 | Second-round set at 15 failing of 70 new (BA-12 dashboard 9, BA-13 faithfulness 4, BA-14 measurements 2); first-round 75 and fixtures 28 green | `PHASE5-ACCEPTANCE-2-2026-09-08.md` NOT ACCEPTED | Run AZ-4c: BA-12 (Grok did BA-12 round 1: `assets/dashboard/index.html`, tests `test_phase5_dashboard2.py`), BA-13/14 (Gemini: `library_analysis.py` evaluator, `PHASE5-AZ-MEASUREMENTS`); then BA-3 review |
| 6 | BC-1 integrated (19/19 tests); 0030 amendment applied | `PHASE6-BD0-2026-09-08.md`: BC-1 not complete; BC-2 requirements listed | Run BC-2 brief to write from BD-0 (publication ownership fence, artifact byte validation, coherent bounded export read, production capture paths through the shared publisher/renderer, registry/stdio adapters for `export_cited_range`, inventories); then BD with the measured study (35 items with real chapters under `E:\Uoink\**\metadata.json`; speaker gate likely blocked) |
| Integration | Not started | | After phases: candidate branch from the review base, Astra reviews conflict resolutions, full suite, installed-tree receipts (Ryan) |

Receipts and artifacts: `docs/library/proof/` (stage archives, S21, S22, AW, process
recovery). Full suite last run at `61eeb07`: 1,461 passed.

## Queue (in order; each item names its brief or how to write it)

1. AT-6 (Phase 3 round 6): write `PHASE3-REPAIR-5-BRIEF-2026-09-08.md` from the AS-5
   defect table (AS-02a intent cleared on interrupted Popen; AS-02b damaged child records
   read as absence; AS-03a worker exit and podcast callback release locks while the child
   is unsettled; AS-03b reconciliation cannot reuse retained locks; AS-03c manual reuse
   reports partial capture). Target: all `tests/library_work_astra/test_phase3_*.py` green
   with `PHASE3_REQUIRE_IMPLEMENTATION=1` (150 tests), companions 365. Engine: grok or claude.
2. AV-3s (Phase 4 D05/D07/D08): grok or claude; target `test_phase4_aw_acceptance.py` 32/32
   and the seven Phase 4 files green.
3. AZ-4c (Phase 5 BA-12/13/14): grok (dashboard) and gemini (evaluator, measurements).
4. BC-2 (Phase 6): write the brief from `PHASE6-BD0-2026-09-08.md`; claude or gemini.
5. Reviews when candidates are ready: AS-6, AW-2, BA-3, BD (Astra).
6. S21 rerun after AT-6 (`python -B tests/library_work_astra/test_phase3_s21.py --execute-s21 --hold-seconds 20`
   with `S21_CANDIDATE_SHA=<sha>`), process-recovery receipt
   (`python -B tests/library_work_astra/process_recovery_receipt.py --execute`), C20/C21
   browser observations (Fable, Chrome).
7. Integration candidate and release notes; Ryan's gates.

## Blockers for Ryan (unchanged)

- Phase 2: keep 0.90 strict, change the rule, or ship with owner review.
- Installed Inno package receipts (Phase 3 C22, Phase 4).
- Phase 6 measured study: navigation study feasible from existing metadata; the speaker
  gate needs diarization runs that do not exist (a fetch/transcription scope decision).
- Standing: ORCHESTRATION-V1 signature, watchdog install, PR strategy, adapter allow-list.
