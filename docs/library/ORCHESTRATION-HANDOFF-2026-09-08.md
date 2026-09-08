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

## State at handoff (updated 2026-09-08 ~15:15 PDT; not pushed)

| Phase | State | Astra's latest ruling | Next |
|---|---|---|---|
| 2 | Done. Stage 4 P2-7 FAIL (39/46, 6/11), record clean, AX-1 repaired | `STAGE4-AUDIT-2026-09-08.md`: option 3 recommended | Ryan decides the 0.90 rule |
| 3 | AS-02b repaired (`d2ec84a`); C20 full browser matrix receipt (`56c1c86`, `PHASE3-S20-MATRIX-RECEIPT`); C21 per-item waiting-for-client surface (`867605b`); two dashboard defects fixed (`12339c3`) | AS-7 DISPATCHED (codex, brief `PHASE3-ACCEPTANCE-7-BRIEF`) | Integrate the AS-7 verdict; C22 Inno is Ryan's |
| 4 | AV-4r (grok) + AV-4m (gemini) integrated (`6559a71`): AW-2 set 28/28, AW set 32/32; two legacy tests aligned to D11/D12 | AW-3 DISPATCHED (codex, brief `PHASE4-ACCEPTANCE-3-BRIEF`) | Integrate the AW-3 verdict; real-client rerun (Fable) when Astra names it |
| 5 | BA-3 NOT ACCEPTED (`b67b836`): 62 new reproductions, 12 items open | `PHASE5-ACCEPTANCE-3-2026-09-08.md` | AZ-5a (gemini), AZ-5c (claude), AZ-5e (grok) DISPATCHED from `PHASE5-AZ5-BRIEF`; then AZ-5b, AZ-5d (grok), AZ-5f (claude), AZ-5g (gemini) in the brief's order; then BA-4 |
| 6 | BC-2 integrated (`fd1825c`, 19/19 + 11/11); study inputs sealed (`d83e6d7`, 25 eligible items) | BD DISPATCHED (codex, brief `PHASE6-BD-BRIEF`) | Integrate the BD verdict; execute the one player observation Astra names; speaker gate is Ryan's |
| Integration | Not started | | After phases: candidate branch from the review base, Astra reviews conflict resolutions, full suite, installed-tree receipts (Ryan) |

Receipts and artifacts: `docs/library/proof/` (stage archives, S20 matrix, S21, S22, AW, process
recovery, BD study inputs). Full legacy tree last run at `fd1825c`: 1,279 passed; Astra's tree
671 passed with the 62 open BA-3 reproductions deselected.

## Queue (in order; each item names its brief or how to write it)

1. AS-7 (Phase 3): DISPATCHED to codex (run started ~14:46 PT). Integrate; if NOT ACCEPTED,
   write the round-8 brief from its defect table and dispatch grok.
2. AW-3 (Phase 4): DISPATCHED to codex (~14:52 PT). Integrate; if open items remain, group
   them (3-5 per session) for gemini/grok; then the real-client rerun Astra specifies.
3. AZ-5a (gemini), AZ-5c (claude), AZ-5e (grok): DISPATCHED (~15:00 PT) from
   `PHASE5-AZ5-BRIEF-2026-09-08.md`. Integrate each (3-way apply; `library_analysis.py` is
   shared by 5a and 5c, keep both sides), run the Phase 5 suites, then dispatch AZ-5b (grok),
   then AZ-5d (grok), AZ-5f (claude after 5c), AZ-5g (gemini after 5d), then BA-4 (codex).
4. BD (Phase 6): DISPATCHED to codex (~15:12 PT). Integrate the verdict and study; execute
   the player observation it names (Chrome); if open items remain, brief BC-3.
5. Integration candidate and release notes; Ryan's gates.

Control Room note: a brief that names a path in backticks makes that path a required
committed input; never write `_scratch/` or another untracked path in backticks in a brief.

## Blockers for Ryan (unchanged)

- Phase 2: keep 0.90 strict, change the rule, or ship with owner review.
- Installed Inno package receipts (Phase 3 C22, Phase 4).
- Phase 6 measured study: navigation study feasible from existing metadata; the speaker
  gate needs diarization runs that do not exist (a fetch/transcription scope decision).
- Standing: ORCHESTRATION-V1 signature, watchdog install, PR strategy, adapter allow-list.
