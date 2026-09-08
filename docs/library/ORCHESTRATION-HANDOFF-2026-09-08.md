# Living Library orchestration handoff (living document, 2026-09-08)

Purpose: if Fable's session hits the Claude subscription limit, Astra (codex, GPT-6) takes
over as integrator until Fable is back, and hands back the same way. Ryan asked for this
on 2026-09-08 ("there has got to be a way Astra can pick up whenever you hit your session
limit"). Fable updates this file at every integration; the git log on `cc/living-library`
is the authoritative history when this file lags.

## Takeover command (Ryan runs it from `E:| 2 | Done. Stage 4 P2-7 FAIL (39/46, 6/11), record clean, AX-1 repaired | `STAGE4-AUDIT-2026-09-08.md`: option 3 recommended | Ryan decides the 0.90 rule |
AI| 3 | AS-02b repaired (`d2ec84a`); C20 full browser matrix receipt (`56c1c86`, `PHASE3-S20-MATRIX-RECEIPT`); C21 per-item waiting-for-client surface (`867605b`); two dashboard defects fixed (`12339c3`) | AS-7 DISPATCHED (codex, brief `PHASE3-ACCEPTANCE-7-BRIEF`) | Integrate the AS-7 verdict; C22 Inno is Ryan's |
projects| 4 | AV-4r (grok) + AV-4m (gemini) integrated (`6559a71`): AW-2 set 28/28, AW set 32/32; two legacy tests aligned to D11/D12 | AW-3 DISPATCHED (codex, brief `PHASE4-ACCEPTANCE-3-BRIEF`) | Integrate the AW-3 verdict; real-client rerun (Fable) when Astra names it |
agent-control-room`)

```powershell
node bin/control-room.mjs run "uoink-library" "Living Library TAKEOVER: you are GPT-6 Astra acting as integrator while Fable is out. Open docs/library/ORCHESTRATION-HANDOFF-2026-09-08.md, follow its rules and work the queue in order: integrate finished worker runs from their worktrees (git apply --3way from each worktree's diff, run the named suites, commit on cc/living-library with the message form below), dispatch the next runs with node bin/control-room.mjs from E:| 5 | BA-3 NOT ACCEPTED (`b67b836`): 62 new reproductions, 12 items open | `PHASE5-ACCEPTANCE-3-2026-09-08.md` | AZ-5a (gemini), AZ-5c (claude), AZ-5e (grok) DISPATCHED from `PHASE5-AZ5-BRIEF`; then AZ-5b, AZ-5d (grok), AZ-5f (claude), AZ-5g (gemini) in the brief's order; then BA-4 |
AI| 6 | BC-2 integrated (`fd1825c`, 19/19 + 11/11); study inputs sealed (`d83e6d7`, 25 eligible items) | BD DISPATCHED (codex, brief `PHASE6-BD-BRIEF`) | Integrate the BD verdict; execute the one player observation Astra names; speaker gate is Ryan's |
projects\agent-control-room using the brief files named in the queue, and update this handoff file and commit it after every step. Never push, never touch the live index or port 5179, never set ANTHROPIC_API_KEY, never edit acceptance tests to make them pass, never relabel a failed measurement as passed. Stop and write a blocker into this file when a decision is Ryan's." --mode work --strategy parallel --agents codex --lead codex --approve
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

## State at handoff (updated 2026-09-08 ~16:20 PDT; not pushed)

| Phase | State | Astra's latest ruling | Next |
|---|---|---|---|
| 2 | Done. Stage 4 P2-7 FAIL (39/46, 6/11), record clean, AX-1 repaired | `STAGE4-AUDIT-2026-09-08.md`: option 3 recommended | Ryan decides the 0.90 rule |
| 3 | AS-7 (`229ea90`): AS-02b closed; repairs landed (`1d9e438` pill pagination + accepted label + fetch strip; scenario 03 rerun with the frozen complete state package) and the replacement S21 run at7 (`3d930e5`: executed launcher bytes, exit 0, nine artifacts, database, bound browser observation, `SUPERSESSION-at7.md`) | AS-8 DISPATCHED (codex, brief `PHASE3-ACCEPTANCE-8-BRIEF`) | Integrate AS-8; if accepted subject to C22, Phase 3 waits only on Ryan's Inno receipt |
| 4 | AW-3 (`f7a6e69`) NOT ACCEPTED: D04/D11/D16 closed, 11 open, 16 reproductions in `test_phase4_aw3_acceptance.py`; real-client rerun requirements listed in AW-3 (five numbered items) | `PHASE4-ACCEPTANCE-3-2026-09-08.md` | AV-5r (grok D01-03) and AV-5m1 (gemini D07-10) DISPATCHED from `PHASE4-AV5-BRIEF`; then AV-5m2 (grok D12-15), AW-4, then Fable's real-client rerun |
| 5 | AZ-5c (claude) + AZ-5e (grok) integrated (`46163a4`): 17 of 62 BA-3 reproductions closed; AZ-5a (gemini) retained as `docs/library/patches/az5a-gemini-2026-09-08.patch` (closes 18 but breaks the 64 KiB cap) | `PHASE5-ACCEPTANCE-3-2026-09-08.md` | AZ-5a2 (claude: apply the patch, compact descriptors), AZ-5b (grok BA-04/07), AZ-5f (gemini BA-13) DISPATCHED; then AZ-5d (grok BA-09/10/11), AZ-5g (gemini BA-14), then BA-4 |
| 6 | BD (`9e6af04`) withheld with BD-01..09 (14 reproductions); navigation study PASSED numerically (50 tasks, baseline MAE 72.06 s -> 0 s); player observation BD-27 PARTIAL (`65f2301`: player at 0:34, media 503); speaker gate blocked (Ryan) | `PHASE6-BD-2026-09-08.md` | BC-3b (grok BD-02/07) DISPATCHED from `PHASE6-BC3-BRIEF`; BC-3a (claude/gemini BD-01/03/05/06) and BC-3c (gemini BD-04/08/09) next; retry the BD-27 observation; then BD-2 |
| Integration | Not started | | After phases: candidate branch from the review base, Astra reviews conflict resolutions, full suite, installed-tree receipts (Ryan) |

Receipts and artifacts: `docs/library/proof/` (stage archives, S20 matrix, S21, S22, AW, process
recovery, BD study inputs). Full legacy tree last run at `fd1825c`: 1,279 passed; Astra's tree
671 passed with the 62 open BA-3 reproductions deselected.

## Queue (in order; each item names its brief or how to write it)

Running now (dispatched ~15:55-16:15 PT): AS-8 (codex), AZ-5a2 (claude), AZ-5b (grok),
AZ-5f (gemini), AV-5r (grok), AV-5m1 (gemini), BC-3b (grok). Integrate each as it lands
(worktree diff, `git apply --3way`, the suites named in its brief), commit, then:

1. Phase 3: AS-8 verdict. If accepted subject to C22, record that in this file and the
   memory; C22 = Ryan's installed Inno receipt (AS-7 lists its contents).
2. Phase 5: after AZ-5a2 and AZ-5b land, dispatch AZ-5d (grok) from `PHASE5-AZ5-BRIEF`;
   after AZ-5d, AZ-5g (gemini); then BA-4 (codex) on the integrated candidate.
3. Phase 4: after AV-5m1 lands, dispatch AV-5m2 (grok) from `PHASE4-AV5-BRIEF`; then AW-4
   (codex); then Fable's real-client rerun per AW-3's five requirements (claude -p, no paid
   API).
4. Phase 6: dispatch BC-3a and BC-3c from `PHASE6-BC3-BRIEF` when claude/gemini free; retry
   the BD-27 player observation (https://www.youtube.com/watch?v=D_FCYsshMI4&t=34s, record
   the player clock and onset; attempt 1 hit CDN 503); then BD-2 (codex).
5. Integration candidate and release notes; Ryan's gates.

Control Room notes: a brief that names a path in backticks makes that path a required
committed input (never write `_scratch/` in backticks); `git config --global core.longpaths
true` is required because the retained S21 artifact archive has paths over 260 characters
inside worktrees (set 2026-09-08 ~16:00 PT).

## Blockers for Ryan (unchanged)

- Phase 2: keep 0.90 strict, change the rule, or ship with owner review.
- Installed Inno package receipts (Phase 3 C22, Phase 4).
- Phase 6: the navigation study passed numerically; the speaker gate is blocked on already-held
  diarization output plus independent human annotations for 30 passages across five items
  (BD lists the exact requirement); the BD-27 player observation needs a network session where
  googlevideo streams load (attempt 1 hit 503).
- Standing: ORCHESTRATION-V1 signature, watchdog install, PR strategy, adapter allow-list.
