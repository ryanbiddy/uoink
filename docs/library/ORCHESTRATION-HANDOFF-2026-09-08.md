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

### Ryan's rulings, 2026-09-09 (supersede earlier conflicting instructions)

- Five fixture corrections are authorized: AW-11 production stop/forget cleanup,
  D13 independent user-edit ordering, D15 atomic-persistence interception, Phase 6
  legacy build-time tickets, and the Phase 5 unary clock probe. Behavior assertions
  stay unchanged. Record the exact diff/reason and one-page review, then run the
  corrected full tree on a committed candidate. Any remaining failure is a product
  defect: write a repair brief; do not edit fixtures further.
- Phase 2 option 3: retain 0.90 for autonomous filing, apply remains false, and
  proposals ship as reviewable suggestions. The failed quality measurement remains.
- Phase 4's X HTTP 403 stays a documented blocked-link condition. No access repair
  or new fetch. Phase 6 ships chapters and cited ranges without speaker attribution
  claims; its speaker gate stays blocked and no diarization run is authorized.
- Backup push is authorized only as `git push origin cc/living-library`. No main
  merge, no candidate-branch push, no publication. Advance the local backup branch
  by fast-forward to the completed candidate so the authorized push backs up this
  work; do not overwrite divergent work or force-push.
- Rebuild/reseal only if production source changes. Finish
  `INSTALL-RECEIPT-RUNBOOK-2026-09-09.md` for Ryan's one disposable Windows-profile
  receipt session covering AS-7's C22 list, Phase 4 and everyday flows. Phase 5
  Part B is deferred. Live-index, 5179 and paid-API prohibitions remain in force.

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

## State at handoff (updated 2026-09-09; integrated tree `8fc6a40`, installer source `8a607c3`)

| Phase | State | Astra's latest ruling | Next |
|---|---|---|---|
| 2 | Option 3 authorized by Ryan on 2026-09-09; Stage 4 P2-7 remains FAIL (39/46, 6/11) | Keep 0.90 for autonomous filing and apply false; proposals are reviewable suggestions | No quality-rule decision pending |
| 3 | AS9 historically accepted subject to C22; original AT6 exit gap remains | Isolated package built; original bundled helper starts and exits zero. Third C22 instrument 41 passed / two failed, with reviewed oracle gaps | Finish C22 worker 6a890eee, verify/integrate, then Ryan's actual installed receipt |
| 4 | Historical client acceptance retains installed/fixture conditions; eight parent-interception failures remain | P4 plus operator supplement integrated: 57 passed / one frozen path failure in both roots; both original prompts succeed. X HTTP 403 stays blocked | Observe bundled operator kit, final tree and Ryan's installed/client receipt |
| 5 | Part A repaired; SDK union 267 passed in each root and corrected complete-tree case passes | BA-4/unary-clock failures close; dashboard 24,576-byte target remains missed | Preserve performance limit in final notes; Part B deferred |
| 6 | Refusal repair 71 passed in each root, also present in complete tree | Chapters/cited ranges only; navigation 50/50 frozen tasks at zero mean error, no speaker claim | Speaker gate remains blocked by Ryan; no diarization |
| Integration | Installer built/sealed at `8a607c3`; complete `8fc6a40` tree: 2,254 passed / ten failed / three skipped / one xfailed, 573.49 s | 62 new cases, no missing cases; one new read-promotion ordered failure; eight-case fixture proposal and historical exit gap remain | Both setup proposals pending; finish two receipt kits, final tree and complete operator bundle/runbook |

Receipts and artifacts: `docs/library/proof/` (stage archives, S20 matrix, S21 incl. run at7, S22, AW,
process recovery, BD study inputs + Astra's study). Full legacy tree at `2a7af56`: 1,950 passed with the
open reproduction sets deselected (AW-3 11 open, BA-3 29+3 open, BD 8 open at HEAD).
Latest integrated full tree, `8fc6a40`: **2,254 passed, ten failed, three skipped,
one xfailed**, 183 warnings, 573.49 seconds. Sixty-two new cases, no missing
cases or previous-failure closures. The new read-promotion case fails only in
this complete observation so far; follow `RYAN-READ-PROMOTION-ORDER-INVESTIGATION-BRIEF-2026-09-09.md`.
Proof: `proof/ryan-integrated-tree-02-2026-09-09/SHA256.json`.

Earlier integrated full tree, `263b7e4`: **2,193 passed, nine failed, three
skipped, one xfailed**, 183 warnings, 728.37 seconds. No existing test changes
since `4a35316`; eight new regressions pass. Eleven of its failures now pass,
no case is missing and no new failure appears. Nine failures remain: the
historical AT6 exit record and eight mirror-interception cases. Proof:
`proof/ryan-integrated-tree-01-2026-09-09/SHA256.json`. Installation workers
are not part of this checkpoint and the final integrated source needs a new run.

Earlier corrected full tree, `4a35316`: **2,174 passed, 20 failed, three skipped,
one existing xfail**, 183 warnings, 607.27 seconds. Only S21 excluded; case
membership is unchanged from `6c313ea`. All 20 failures also failed there,
and 72 previous failures pass in this new observation. See
`proof/ryan-corrected-01-2026-09-09/SHA256.json` and
`CORRECTED-TREE-PRODUCT-REPAIR-BRIEF-2026-09-09.md`. No further fixture edits.

Historical candidate full tree, `6c313ea`: **2,102 passed, 92 failed, three skipped,
one existing xfail**, 550.41 seconds, with only S21 excluded. The preceding
`44968d9` run had 2,106 passed / 26 failed, excluding the then-open AW-5/AW-7
files as well. All 67 additional mirror failures passed the focused union on
the same source; a reduced pair proves AW-11's direct teardown leaves a dead
I/O binding for subsequent fixtures. No corrected full-tree run had occurred
at that checkpoint; the authorized correction and new result are above.
See `CANDIDATE-MIRROR-ORDER-BRIEF-2026-09-09.md`; this result stays failed.

## Queue (in order; each item names its brief)

1. Review and integrate the already running C22 correction
   `6a890eee-6163-49bf-836b-cb4b8736b169` under
   `RYAN-C22-FINAL-ORACLE-REPAIR-BRIEF-2026-09-09.md`, and the independent P4
   correction `1f64672e-95b7-4608-9fa6-5823b7e8eeda` under
   `RYAN-P4-EVIDENCE-COMPLETENESS-REPAIR-BRIEF-2026-09-09.md`. They may finish
   in either order; do useful independent work while waiting. P4 plus the bounded
   operator supplement is integrated with 57 passed / one failed in both roots;
   its bundled command path remains to be observed. Finished third
   versions remain rejected as complete receipt instruments. No new original
   product or installed acceptance is inferred from their status flags.
2. Verify each finished full diff in its worktree using the named suites. Preserve
   staged AND unstaged content with git diff HEAD, including new files. Apply the
   raw patch with three-way apply in this checkout, rerun the same suites, record
   exact counts and the review verdict, then commit the integration and handoff.
   Do not edit any existing test assertion or fixture to make a new kit green.
3. Both exact setup proposals under Blockers for Ryan remain unapplied. If Ryan
   explicitly approves them, apply only their sealed diffs, record the ruling,
   assertion audit and review, verify the ordered read pair and affected mirror
   union, then include them in the committed complete tree. Waiting is not approval.
   The separate original AT6 exit status remains unavailable; never invent it.
4. Run the final kit-inclusive complete tree at a committed SHA under a new
   documented final-verification brief. Use the guarded native runtime and only
   exclude S21. Seal exact case membership/counts/log/XML; retain every failure.
   Any newly exposed product defect needs its own repair brief and fresh evidence.
5. Package build source is 8a607c3, current executable SHA-256 d024baf5e27fc15b292c17c3c7a551b41c9564378ce352e81ed25a9908bfd5b1.
   Its compiler inputs and bundled original-entry/helper observation are sealed.
   Run the completed kits against the bundled runtime with disposable fixtures,
   retaining pre-Inno labels. Rebuild/reseal only if packaged source changes;
   otherwise verify all 142 source bindings against the final validation commit.
6. Finish the portable operator bundle and replace the runbook's old blocked
   preflight with exact hash-bound commands for Ryan's one throwaway Windows-profile
   session. Include migrations required by the fixture generator, original installed
   routes, C22/P4 manifests, full release notes, everyday-flow checks and receipt
   collection/restoration steps. Do not run Setup/uninstall or claim their receipts.
7. Update the release notes, State table and remaining Ryan items. Fast-forward
   the authorized backup branch and push only origin/cc/living-library, without
   force, then verify the remote SHA. Report actual counts, build/validation/backup
   commits, artifacts and open gates. No main merge or publication.

### Earlier continuation record (historical; active queue above supersedes it)

Current continuation under Ryan's 2026-09-09 rulings:

Completed: five corrections/review committed at `4a35316`; one corrected full
tree sealed with actual counts. Product integrations through `db95457` are
measured together at `263b7e4` (2,193 passed / nine failed); the unapplied
fixture proposal and historical exit gap remain. All remaining failures are assigned in
`CORRECTED-TREE-PRODUCT-REPAIR-BRIEF-2026-09-09.md`. Retain the old package;
production source has changed and a new package is owed. The runbook documents the complete
receipt requirements but is blocked before installation; it is not an
executable installed scenario kit yet. Backup result is recorded in the log.

1. Follow product brief sections 1–5 in phase order: recover Phase 3 evidence
   truthfully, repair Phase 4 lifecycle and interrupted-write/ownership behavior,
   Phase 5 SDK settlement and Phase 6 refusal semantics. Review each production
   diff before a fresh named run. No further fixture edits or measurement waivers.
   Ryan reiterated continuing through release readiness on 2026-09-09.
   Phase 3 originals and verification are sealed; its exit gap remains. Independent bounded worker
   briefs are `RYAN-PHASE4-LIFECYCLE-REPAIR-2026-09-09.md`,
   `RYAN-PHASE5-SDK-REPAIR-2026-09-09.md` and
   `RYAN-PHASE6-REFUSAL-REPAIR-2026-09-09.md`, dispatched in that order.
   Phase 4 lifecycle plus Astra's conservative-lease correction is integrated at
   `1063843`. Phase 5's outgoing-frame supplement at `0ad33d4` has 267 passes
   in both roots. Phase 6 is integrated with 71 passes in each root; see its
   integrator report. The exact mirror-interception fixture proposal is pending
   Ryan's reply; do not apply it or infer consent from continued work.
2. Follow `INSTALL-ISOLATION-REPAIR-BRIEF-2026-09-09.md`: the current Inno prep
   and helper launch use 5179, even from another Windows profile. Implementation
   worker `fd647a72-24b6-468a-905f-ddfdfa5899ac` follows
   `RYAN-INSTALL-ISOLATION-IMPLEMENTATION-2026-09-09.md` from `5bae13c`. Provide a
   supported isolated product path and complete operator kit. Do not ask Ryan
   to waive the no-5179 rule or execute the current installer.
   C22 kit worker `9c866bb0-cb4d-4008-894b-df359998b5f1` follows
   `RYAN-INSTALLED-C22-KIT-BRIEF-2026-09-09.md` from `c9b5407`.
   Phase 4 kit worker `81060797-d8be-4e56-8d7c-6f8b0dd30a94` follows
   `RYAN-INSTALLED-PHASE4-KIT-BRIEF-2026-09-09.md` from `1063843`.
   Review disposition: original isolation `fd647a72` and C22 `9c866bb0`
   are rejected with archived patches. Replacement isolation `3a3bd6cb`
   follows `RYAN-INSTALL-ISOLATION-REVIEW-BRIEF-2026-09-09.md`; replacement
   C22 `6accc421` follows `RYAN-C22-KIT-REPAIR-BRIEF-2026-09-09.md`.
   Phase 4's 11-case instrument check passes independently, but original-route
   coverage and packaging/guard gaps require `RYAN-PHASE4-KIT-REPAIR-BRIEF-2026-09-09.md`.
   Startup anchor repair `db95457` has 21 focused passes; verify the complete
   real helper after the isolation repair. No original kit is installed credit.
   Replacement isolation has 113 independent passes / one skip, but Inno review
   found active Restart Manager closing, non-gating uninstall errors and path /
   marker parsing gaps. Follow `RYAN-INNO-FINAL-BOUNDARY-REPAIR-BRIEF-2026-09-09.md`
   before integration. The second raw patch and all three observations are sealed.
   Final isolation worker plus Astra's documented Inno correction is now integrated:
   118 passed / one skip in the corrected worker, 130 passed / one skip in checkout
   with twelve read/startup companions. Exact-script dummy compile exits zero;
   `RYAN-INNO-FINAL-INTEGRATION-REVIEW-2026-09-09.md` preserves installed limits.
   Source through `022ff43` can be measured while both kits finish under
   `RYAN-ISOLATION-CHECKPOINT-TREE-BRIEF-2026-09-09.md`; retain its checkpoint
   label and run the final kit-inclusive tree after those integrations.
   Checkpoint `8fc6a40` has 2,254 passed / ten failed. Follow
   `RYAN-READ-PROMOTION-ORDER-INVESTIGATION-BRIEF-2026-09-09.md` for the one
   additional failure; do not edit fixtures or replace this failed observation.
   C22 replacement independently has 26 passes / two failures, 69.61 s. Its
   receipt still substitutes direct child-record calls for helper recovery,
   miscounts charges and compares protected state only after all scenarios.
   Follow `RYAN-C22-SCENARIO-TRUTH-REPAIR-BRIEF-2026-09-09.md`; no installed credit.
   Second Phase 4 kit has 20 independent passes / one frozen failure, and an
   incomplete original-route observation. Follow
   `RYAN-P4-FINAL-INSTRUMENT-REPAIR-BRIEF-2026-09-09.md` for manifest/guard,
   bounded transport, complete evidence and executable operator corrections.
   Third C22 instrument independently has 41 passes / two frozen failures,
   666.34 s; its original source observations are sealed separately. Further review finds non-independent protected-state
   allowances, missing child-survival/relaunch gates, permissive provenance and
   guard/resume defects. Follow `RYAN-C22-FINAL-ORACLE-REPAIR-BRIEF-2026-09-09.md`
   using its archived input; no earlier status supplies installed credit.
   Third Phase 4 instrument has 36 independent passes / one frozen failure,
   24.86 s. Its completeness flag wrongly accepts a refused reshelve prompt and
   aggregates sessions; cleanup can block on a full stdin pipe and failed canary
   does not stop product launch. Preserve `ryan-p4-kit-review-03-2026-09-09` and
   follow `RYAN-P4-EVIDENCE-COMPLETENESS-REPAIR-BRIEF-2026-09-09.md`.
   Existing-preview read repair is reviewed in `RYAN-PREVIEW-RESTART-REVIEW-2026-09-09.md`:
   nine new passes; broader 212 passed / eight known mirror-hook failures. The
   six initial subprocess failures proved storage mutation, not missing service.
   Include this source in the final tree and packaged original-route observation.
3. After source repairs, run applicable suites in worker/checkout and the full
   tree at a committed SHA; rebuild/reseal only when production source changed.
   Current product is measured at 8fc6a40; build the isolated replacement while
   kits finish under `RYAN-ISOLATED-PACKAGE-BUILD-BRIEF-2026-09-09.md`. If later
   packaged source is unchanged, retain its build SHA and verify exact bindings
   against the final kit-inclusive validation commit rather than rebuilding notes.
   Replace the runbook's stop preflight with exact reviewed install/restart and
   scenario commands, then Ryan supplies C22 and Phase 4 installed receipts.
4. Preserve Phase 2 option 3, blocked X link, chapters/ranges without attribution,
   and deferred Phase 5 Part B. Update this handoff after every integration.
   Backup push remains `git push origin cc/living-library` only; never main.

The queue history below records completed/rejected runs and their earlier authority.

Takeover runs: AS-9 codex `a13febd1` integrated at `6807361`; AZ-5a2 claude `6e929e1d`
finished but rejected; AV-5m1 gemini `b31e890f` integrated at `9489141`.
BC-3c grok `ff01d490` integrated at `c8ddf9b`. BC-3a gemini `eb0f138e` failed on quota
with a rejected partial diff. AZ-5a3 gemini `bbd68b73` also failed on quota, no diff.
AZ-5a3g grok `54108a1f` integrated at `d437b59`. AV-5m2 grok `6b5e5f1e`
and BC-3a2 grok `5aca8450` finished and are rejected; both complete original diffs
are retained in the patches directory. New repair briefs below govern retries.
AV-5m3 integrated at `270e569`, BC-3a3 at `00fe216`, AZ-5d2 at `3d2fa9f`,
BC-3d at `897f0d2`, BC-3e at `d792875`, AV-5m4a2 at `b833167`, and
AZ-5h at `8e3e4f0`. These integrations are not Phase 4/5/6 acceptance.
AZ-5d, AV-5m4a, AV-5m4b, AV-5m4b2 and AZ-5g are rejected with retained
complete/partial diffs as described below. BC-3f
Grok `33751bb7` integrated at `986b555`.
AV-5m4a3 Grok `888d4940` integrated at `ffdbef4`. AZ-5h2 Grok `098fb14d` integrated at `45bb2f6`;
AV-5m4b3 Grok `260ef22c` is rejected with its complete diff retained.
AZ-5g2 Grok `769107e6-1cc5-447a-85d7-25de3c4ff054` is integrated at `a39c7e6`
with an independent supplement. AV-5m4b4 Grok `e2580c74-1d67-43ad-a5d2-f443409a0c6c`
finished from `564836c` and is rejected after AW-9. AV-5m4b5 Grok
`a4af542b-c8bb-4958-97f4-185951daaad0` finished from `39d7e19` and is
rejected after AW-10. Its complete diff and independent proof are retained.
AV-5m4b6 Grok `9577904a-b4f7-4a0f-ac3c-93467f2e1b50` finished from
`17f3714` and is rejected after AW-11. Its complete diff and independent proof
are retained. AV-5m4b7 Grok `b00703c8-7ca0-4e4b-b3ba-c6f1bad3d6ac`
finished from `7995c0e`. Its original patch is retained. B7 plus Astra's AW-12
review correction is integrated at `6858b81`; no external worker is active.
Worktrees are under `%LOCALAPPDATA%\AgentControlRoom\worktrees\uoink-library\<run8>-<3>\<engine>`.

1. AS-9 (Phase 3) complete at `6807361`: accepted subject to C22 only. C22 stays under
   Blockers for Ryan. Four unchanged assertions against superseded AT6/browser evidence
   remain failures; AS-8/AS-9 cover the replacement at7 evidence.
2. AZ-5a3g (Phase 5) integrated at `d437b59`; earlier failed diffs remain retained.
   AZ-5d2 and AZ-5h are integrated. AZ-5g finished with a rejected incomplete
   record (474 passed / one frozen failure in independent verification).
   AZ-5h2 is integrated at `45bb2f6`; G2 and its supplement at `a39c7e6`.
   Final BA-4 accepts Part A with the unary/clock condition for Ryan. The
   closure full tree on `44968d9` completed with 2,106 passed / 26 failed. The original partial measurement stays retained and
   is not integrated; its raw patch bytes are separately preserved by G2.
3. AV-5m3, AV-5m4a2 and AV-5m4a3 (`ffdbef4`) are integrated.
   AV-5m2 remains rejected. AV-5m4a
   timed out and its partial diff is rejected. AV-5m4b and AV-5m4b2 are
   rejected after AW-5/AW-7. B3 is rejected after AW-8; B4 is rejected after
   AW-9. B5 is rejected after AW-10; B6 after AW-11. B7 plus the bounded
   integrator correction in `PHASE4-AW12-2026-09-08.md` is integrated at
   `6858b81`, with 286 passed / nine frozen failures in both roots. Original
   B7 and all failed observations remain retained. Final AW-4's four broader
   companion files passed 113 tests; see `PHASE4-AW4-FINAL-2026-09-08.md`.
   Real-client observation 01 stays partial on `7eec17b`. Its planned supplement
   is complete on documentation-only successor `49026e4`; see
   `PHASE4-CLIENT-02-2026-09-09.md`. Required client behavior is accepted with
   the installed/fixture conditions and explicit blocked X-source link. The
   original receipt and every failed/partial observation stay retained. No
   new worker or client rerun is warranted without a documented repair/brief.
4. Phase 6: BC-3a3 is integrated at `00fe216`; BC-3a2 remains rejected.
   BC-3d integrated at `897f0d2`; BC-3e integrated at `d792875`.
   BC-3f integrated at `986b555`. Final BD-2 on `d1d5fb8` closes implementation
   review, preserving eleven failed fixture results and four broader superseded-
   evidence failures. Phase 6 is accepted subject to Ryan's fixture and speaker
   gates. Preserve both rejected diffs and the quota failure.
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
   Candidate branch was cut from `9217846`; release notes are now tracked.
   Full tree on `6c313ea` finished with 2,102 passed / 92 failed. The new
   order-dependent fixture-cleanup ruling is under Blockers for Ryan; original
   tests remain unchanged. Local installer completed from `e47e4f2` on
   2026-09-09 at 00:30 PDT: `build/Uoink-Setup-3.8.0.exe`, 339,042,658 bytes,
   SHA-256 `9defc2a98ba680f8b4cdf06bdd09eadbb1153f2028070881b5472ce97f7e927d`.
   Bundled Python 3.11.9/MCP 1.27.1 observation 02 passed its synthetic stdio
   scope after the documented guard repair; observation 01 remains failed.
   See `CANDIDATE-PACKAGED-RUNTIME-REPAIR-BRIEF-2026-09-09.md`, the release
   notes and `proof/candidate-package-01-2026-09-09/SHA256.json` (28 files).
   Candidate work is complete for local review. Next actions depend on Ryan's
   gates; no worker or client session remains active. Do not manufacture a
   green full tree with reordered or reset fixtures.

Worker notes: claude worker = no shell, one session at a time, shares the subscription (tell it
"no subagents; targeted searches; write early"); gemini has shell, times out on big sets (3-5
defects); grok has shell, reliable on bounded code with a named test file ("write the file early;
a session without the file is a failed run"). A brief that names a path in backticks makes it a
required committed input (never write `_scratch/` in backticks). `git config --global
core.longpaths true` must stay set (worktree checkouts fail without it).

## Blockers for Ryan

Pending 2026-09-09: `RYAN-IO-FIXTURE-PROPOSAL-REVIEW-2026-09-09.md`
contains the exact three-file/eight-case interception patch (4,298 bytes,
SHA-256 `d64bde5d71b4349cb498bf267e6dda9b73a67f1f673b85889e9ac0c32e256929`).
All 150 assertion syntax trees are unchanged. Approval was requested because
Ryan froze further fixture edits. The proposal has not been applied or run.
This does not waive the separate missing historical AT6 child exit status.

Additional 2026-09-09 proposal: `RYAN-READ-FIXTURE-PROPOSAL-REVIEW-2026-09-09.md`
documents the new read-opening test's two-line setup correction. The earlier
discovery-route test leaves the backend getter replaced; the ordered pair
reproduces one failure / three passes. All 13 assertions remain identical.
Exact unapplied patch: 649 bytes, SHA-256
`32ecbcce8d4040308324cc739914eb56106535e91e780991d7cc02683659a0f5`.
Together both proposals touch four files and preserve 163 assertion trees.
No fixture edit or pass is inferred from this diagnosis.

- Installed Inno package receipts (Phase 3 C22, Phase 4), once product work
  supplies the final reviewed operator kit. The isolated package is built;
  keep the operator session pending while both instruments finish review.
- Phase 6 speaker gate remains blocked by Ryan's explicit ruling. No diarization
  runs or attribution claims; chapters and cited ranges are the release scope.
- Main merge remains unauthorized. No new fetch scope is authorized.
- Standing: ORCHESTRATION-V1 signature, watchdog install, PR strategy, adapter allow-list.

The five fixture decisions, Phase 2 option 3 and retained X-link condition are
resolved owner rulings. Residual test failures after the corrected tree belong
in product repair briefs, not under Blockers for Ryan.

The installation-path defect is also product work. Do not treat a missing
safe installer command as a request for another owner permission.

## Integrator log

### 2026-09-09 00:07 PDT - Candidate branch and final verification plan

Cut `cc/living-library-candidate` from clean `9217846`, as explicitly authorized
by Queue 6. No Git merge/conflict entries exist. All implementation overlays
were previously reviewed and tested in worker and checkout roots. Release
notes now cover all phases and retain every owner gate and absent feature.
The next full tree includes every closed Phase 4 reproduction; only S21 is
excluded under the standing command. Preserve failures and classify against
the prior 26-case baseline before building. No test expectation will change.

The supplemental archive's 112 staged hashes verified before commit. Ordinary
Git whitespace checking flagged its original CRLF bytes; the CR-at-EOL-aware
check found only a final blank line in the raw terminal JSON capture. That
exact file is preserved, not reformatted. All other new files passed that
check; authored documentation passed the normal check.

### 2026-09-09 00:03 PDT - Client supplement closed; candidate prerequisites met

The supplement on `49026e4` has 112 hash-sealed proof files. Both text-source
corpus routes matched all 897 original bytes; four hostile card/excerpt and
two brief comparisons matched in full. All 12 actual client tool requests were
permitted reads. Sentinel attempts were zero, library/settings and 15 auxiliary
file hashes stayed unchanged, and SQLite integrity/foreign-key checks passed.
The held X link failed with HTTP 403; it is not a passed click. See the new
Blockers for Ryan entry and `PHASE4-CLIENT-02-2026-09-09.md`.

Live unattached stdio refused the missing fixture index in 1.6269/1.5294 ms
without creating a replacement. Recall delivered the hostile quoted fact in
56.0376 ms, then failed silently on unavailable storage in 54.1236 ms. Both
closed database files were restored byte-identically. Actual Mirror fixture
disconnection drained three pending actions after reconnect; the later edited
source purge preserved user bytes and correctly paused with two pending actions,
one deletion and one user-edit conflict. No temporary artifact remained.

All client children exited and the temporary access-only credential was removed.
Automatic approval review rejected the first combined computed-path cleanup;
separate contained fixture restoration and literal-path credential deletion
succeeded. Neither normal client configuration nor its credential was removed.
The read-only collector's initial nested-error-field/newline assumptions were
corrected against retained captures, as documented; no model session was rerun.

The setup-only hostile brief's initial cold-import deadline failure stays
retained. Its documented repair reused the exact saved packet/key/document
and existing receipt. It is not a client-authored brief workflow. Native
template discovery and Claude Desktop remain unobserved, with scope stated
separately from the successful required Code routes. Corrected the installed
CLI guide's obsolete claim that native resource tools are absent.

Proceed to Queue 6: candidate, full tree with only S21 omitted, release notes
and local installer. Preserve all nine Phase 4, eleven Phase 6 and other
retained fixture failures. No production changes occurred in this supplement.

### 2026-09-08 16:24 PDT â€” Astra takeover and AS-9

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

### 2026-09-08 16:26 PDT â€” AZ-5a3 brief and measurement setup repair

The first standalone byte-measurement helper stopped at MCP SDK import because the
redirected profile omitted pywin32's installed paths. No measurement resulted. The
AZ-5a3 brief documents that setup repair; after resolving and preserving the paths,
the same helper measured 51,668 raw / 58,289 serialized-transport bytes for the empty
31-day interval and 57,704 / 64,411 for the pagination fixture, which still returns
only 12 creator rows. This was fixture serialization, not a real-client receipt.
Retain the AZ-5a2 rejection. The AS-9 full-tree run is in progress with S21 and only
the still-open AW-3, BA-3, BA-measurements3 and BD reproduction files excluded.

### 2026-09-08 16:33 PDT â€” AV-5m1 integrated; full-tree environment failures

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

### 2026-09-08 16:38 PDT â€” BC-3c integrated; Gemini quota; repaired verification

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

### 2026-09-08 16:43 PDT â€” Active work after provider rerouting

Three independent Grok worktrees are active: AV-5m2 `6b5e5f1e` at `633eb99`,
AZ-5a3g `54108a1f` and BC-3a2 `5aca8450` at `fc544f2`. Their files are separate
across phases; integrate one verified result at a time. Gemini's quota reset
was reported around 17:50 PDT; no new Gemini retry is planned before then.
Claude workers share Fable's nearly spent subscription. Codex remains available
for the AW-4, BA-4 and BD-2 reviews when their repaired candidates are ready.

### 2026-09-08 16:56 PDT â€” Full-tree verification after BC-3c

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

### 2026-09-08 17:05 PDT â€” Draft review and conflicting acceptance setup

The three Grok runs are active and executing tests. Control Room buffers their
message output; recent task-local tool logs establish activity. Do not infer a
stalled run solely from an empty `agent_runs.output` field.

AV-5m2's draft introspects an acceptance fixture closure to select cancellation
behavior. BC-3a2's draft exempts empty raw publications from its ticket rule and
edits legacy BC-2 tests. These drafts are not integrated. The source inspection
in `INTEGRATOR-CONTRACT-CONFLICTS-2026-09-08.md` explains the underlying fixture
conflicts and the Ryan rulings required under the prohibition on acceptance-test
edits. Reject test-specific production exceptions; continue the general repairs.

### 2026-09-08 17:12 PDT â€” AZ-5a3g integrated; AV-5m2 and BC-3a2 rejected

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

### 2026-09-08 17:20 PDT â€” Three repair runs and client recorder preparation

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

### 2026-09-08 17:26 PDT â€” BD-27 observed through Windows computer-use

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

### 2026-09-08 17:40 PDT â€” BC-3a3 integrated; BD-2 review started

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

### 2026-09-08 17:44 PDT â€” BD-2 owning defects and AZ-5d rejection

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

### 2026-09-08 17:53 PDT â€” AV-5m3 integrated; AW-4 repairs reserved

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

### 2026-09-08 18:18 PDT â€” AZ-5d2 verified and integrated

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

### 2026-09-08 18:20 PDT â€” BC-3d integrated; two bounded repair continuations

BC-3d integrated at `897f0d2` after clean three-way apply and independent
**158 passed, 11 failed** in each root (79.87 s worker, 72.70 s checkout).
Logs/commands/XML: worker `_scratch/bc3d-wi`, checkout `_scratch/bc3d-ci`.
All three BD-2 cases pass. New frozen BD-3 has **one failure**, 9.16 s in
the worker: changing only transcript provenance lets stale capture A overwrite
completed B. `PHASE6-BC3E-BRIEF-2026-09-08.md` requires every consumed
plan input bound and rechecked at publication. No Phase 6 acceptance claim.

AV-5m4a independently produced **213 passed, eight failed**, 76.63 s
(worker `_scratch/av5m4a-wi`). Its four AW-4 cases pass, but direct initial
binding writes, swallowed witness failure, unchecked unlink retry and parent
mutation fallback violate the brief. The complete partial diff is retained
in `patches/av5m4a-gemini-timeout-rejected-2026-09-08.patch`. No portion
is integrated. AV-5m4a2 has a bounded Grok repair brief; AV-5m4b retains
its separate lifetime/exclusion scope. AZ-5g Gemini was dispatched from
`14f9e1b`; source-only client preparation is still unexecuted.

### 2026-09-08 18:26 PDT â€” final SDK serialization gap; active runs

Preliminary BA-4 added an independent actual SDK stdio probe on the current
AZ-5d2 implementation. It injects elapsed time at final JSON-RPC serialization
after the handler returns. **One failure**, 1.19 s: success is emitted after
the deadline, with active admission zero. `_scratch/ba4-sdk` retains the
command/log/XML. The prior passing handler probe remains a pass for its
narrower boundary; it does not prove the later SDK writer.
`PHASE5-BA4-2026-09-08.md` records the distinction. AZ-5h is briefed to
repair the actual transport, after retaining AZ-5g's current measurements.
No acceptance test/helper was changed and no model was involved in the probe.

Active Control Room IDs: AZ-5g Gemini `5e9baea5` (base `14f9e1b`),
BC-3e Grok `21cb8de9` and AV-5m4a2 Grok `53f50b6f` (base `d9ccba5`),
AV-5m4b Grok `5c22dbae` (base `98d8b35`). The first three started at
18:16/18:20/18:20 PDT; AV-5m4b remains on its original lifetime scope.

### 2026-09-08 18:31 PDT â€” AV-5m4b rejected; AW-5 reproduced

AV-5m4b Grok `5c22dbae` finished. Independent full union: **214 passed,
14 failed**, 65.52 s (`_scratch/av5m4b-wi`). Twelve are the eight retained
parent interceptors plus four AW-4 cases assigned to the other worker. Two
new child-timeout tests also fail in the combined run (returned success);
the worker's separate seven-pass report does not replace those results.
The complete original diff, proposed tests and report are retained in
`patches/av5m4b-grok-rejected-2026-09-08.patch`. Nothing is integrated.

New frozen AW-5 independently produced **two failures, one pass**, 6.84 s
(worker `_scratch/aw5-review`). Real parent loss kills the assigned child.
But an independent connection's write reservation is mistaken for our
deferred connection's ownership, and a blocked destination lease write
traps resync outside its cancellable boundary beyond five seconds.
AV-5m4b2 is briefed to fix those, diagnose the combined-test failures and
audit late intent writes and unknown process liveness. The original
proposed implementation tests remain archived; only implementation-specific
path assertions in those unintegrated tests may be adapted with explanation.
All committed acceptance tests remain frozen.

### 2026-09-08 18:42 PDT â€” AZ-5g retained as incomplete; transport repair next

AZ-5g Gemini `5e9baea5` ended with Control Room status completed but no
required report. Independent full union produced **474 passed, one failed**,
123.69 s (worker `_scratch/az5g-wi`). The single failure is the unchanged
unary/clock setup. Four old measurement-document assertions pass against
the proposed text; that does not certify its complete measurement record.

The proposed script labels an old document blob ID as `git_tree_hash`,
uses returned sample lengths as totals and retains no complete packet/wire
bytes. The wrong tree metadata is directly verified: `3d2fa9f` tree is
`a22c81c97a8c8341e2cc34e56223acdca75b30bd`; worker base `14f9e1b` tree is
`8cbd5cc50160b193990cccedf51708abf66ee990`. The partial script labels
`c3c8e1b72d3354bdfe85b1ce881e1e765aa28ea0` as a tree. Complete original
diff/artifacts are retained in `patches/az5g-gemini-partial-rejected-2026-09-08.patch`.
No portion is integrated. AZ-5h repairs the actual SDK transport boundary,
then AZ-5g2 has a bounded Grok brief for a complete measured refresh.

AV-5m4b2 is running as Grok `3ddbb5ef` from `66083f6` (18:31 PDT).
The AW expected-packet preparation helper was independently checked against
complete timed/text-only synthetic resource responses: two passes, 0.98 s
(`_scratch/aw-expected-unit-fixed`). Two earlier scratch-verifier setup
errors are retained, with their repair brief. No production/helper or
committed test changed, and no measured copy, client or model was run.

### 2026-09-08 18:53 PDT - BC-3e integrated; publisher-entry gap retained

BC-3e Grok `21cb8de9` integrated at `d792875` after clean three-way apply.
Independent verification: **167 passed, eleven failed** in each root,
142.25 seconds worker and 138.13 seconds checkout. Commands, logs and XML:
worker scratch `bc3e-wi`, checkout scratch `bc3e-ci`. All eight new tests and
BD-3 pass; the eleven omitted-ticket failures remain unchanged.

New BD-4 fails when a pending caption correction arrives inside the call to
the Index publisher, after the owner's final standalone check. The first
exact-byte probe failed in 7.22 seconds. Before freezing the new test, an
additional decoded-caption assertion made the content loss explicit; it
failed in 6.37 seconds. Both failures and the scratch observability-repair
brief remain retained. `PHASE6-BD4-2026-09-08.md` and the BC-3f brief govern
the next repair. No Phase 6 acceptance is claimed.

AZ-5h Grok `f62e5609` started from `e0d8bef` at 18:42 PDT. AV-5m4a2
`53f50b6f` finished; AV-5m4b2 `3ddbb5ef` continues its separate repair scope.
Five old Windows-1252 dash bytes in this handoff were converted to UTF-8
without changing their text so subsequent edits can read the document.

### 2026-09-08 19:04 PDT - AV-5m4a2 integrated; immediate cleanup gap

AV-5m4a2 Grok `53f50b6f` integrated at `b833167`, verified at **219 passed, nine failed** in each
root, 76.01 seconds worker and 72.05 seconds checkout. Logs/XML/commands:
worker scratch `av5m4a2-wi`, checkout scratch `av5m4a2-ci`. Three-way apply
was clean. Its seven new tests and all four AW-4 cases pass, including the
actual isolated source-stage worker. Eight old parent interceptors remain
failed; D15 now fails because it injects into the removed direct write.
The latter is documented as a ninth frozen setup issue for Ryan.

New AW-6 has **one failure**, 0.69 seconds (worker scratch `aw6-finally`):
immediate finally cleanup deletes a replacement at the allocated temp name
after publication fails. The original allocated file remains moved aside.
AV-5m4a3 repairs that operation-wide identity gap. This implementation work
remains in our queue. No client or installed receipt is credited yet.

BC-3f Grok `33751bb7` started at 18:58 PDT from `ae40b57`. AZ-5h and
AV-5m4b2 remain active. The handoff's Queue is current; older run-start
paragraphs above are retained history.

### 2026-09-08 - AZ-5h integrated; BA-5 and AW-7 retained

AZ-5h Grok `f62e5609` integrated at `8e3e4f0`, clean three-way apply.
Independent named union plus Phase 4 resources/prompts/briefs: **561 passed,
six failed** in both roots (115.63 seconds worker, 113.79 seconds checkout;
scratch `az5h-wi` / `az5h-ci`). Seven actual-entry tests pass. The original
BA-4 test still fails on the replaced SDK stream route, which is retained
as a route-limited result. Five other failures remain the unary/clock
fixture and four stale measurement assertions.

New BA-5 observes 4.6680728 seconds from inbound admission with 1.5 seconds
of simulated dispatch and a real SQLite EXCLUSIVE holder (one failure,
7.09 seconds including setup). Its separate large-id test returns a
65,838-byte refusal (one failure, 1.39 seconds). Worker scratch
`ba5-inbound-clock` / `ba5-refusal-wire` retain the raw verification.
AZ-5h2 is briefed before AZ-5g2; neither defect is a Ryan gate.

AV-5m4b2 independently has **226 passed, twelve failed**, 71.70 seconds
(worker scratch `av5m4b2-wi`). Three AW-5 cases pass. New AW-7 has **one
failure**, 3.65 seconds: the delayed parent writes its destination lease
after timeout returns. The complete B2 diff/reports/proposed tests are
retained in `patches/av5m4b2-grok-rejected-2026-09-08.patch`; nothing is
integrated. B3 must isolate lease mutations, protect final local intent
mutations, prove SQLite ownership without guessing native object pointers,
and replace the unsupported real-child timeout explanation with evidence.

The broader BD-2 check on `831714d` produced **382 passed, four failed**,
57.90 seconds, with all Phase 3 files except S21 plus nine named adapter,
podcast, clip and resource files. Failures are only the unchanged AS-7
superseded-evidence cases. Logs/XML/expanded command are in checkout scratch
`bd2-broader-bc3e`. Later BC-3f/AZ-5h integration still needs final verification.

### 2026-09-08 - Follow-on runs and process-isolation lesson

AZ-5h2 Grok `098fb14d-115d-42c8-b40b-35e37a009d81` and AV-5m4b3
Grok `260ef22c-4a89-42c4-ad46-695f7e0ed80e` started from `533ef6f`
at 19:20 PDT. BC-3f and AV-5m4a3 have finished; their independent named
worker unions are running. No result is credited before verification.

During A3, a PowerShell automatic-variable collision with `$args` launched
bare pytest instead of the named suites. Its task-specific kill succeeded.
Automatic approval review rejected a separate machine-wide Python/pytest
kill because it could stop unrelated work; there is no evidence that broad
kill executed. Use explicit selectors or a task-specific variable and stop
only processes whose ownership by the exact run is established. Preserve
the accidental invocation as aborted, not as a verification result.

Client preparation found that `reshelve-review` requires an attached Phase 2
service and a valid preview. The standalone unattached reader correctly
returns `feature_unavailable`. A valid-prompt observation must document its
fixture service/preview preconditioning before freezing before-and-after
state, and distinguish that setup from the default unattached launch. No
real-client session or archive-copy preparation has run yet.

### 2026-09-08 - AV-5m4a3 integrated

AV-5m4a3 Grok `888d4940` integrated at `ffdbef4` after clean three-way
apply. Independent union: **224 passed, nine failed** in each root,
79.99 seconds worker and 71.68 seconds checkout. Logs/XML/commands:
worker scratch `av5m4a3-wi`, checkout scratch `av5m4a3-ci`. All four
new tests and AW-6 pass. The nine frozen interceptors remain failed.

Creating file/volume/hash authority now follows immediate cleanup and
bound source publication. Windows write-error deletion uses the creating
handle before close. POSIX bound delete/rename refuses where equivalent
exclusion is unavailable. A separate disposable check of exact binary
bytes and an emoji-containing vault path passed (one test, 0.25 seconds,
checkout scratch `aw8-unicode`); it found no additional defect.

B3 must preserve `_IO_CTX.authority`, bound replace/unlink and the child
write-error implementation while adding session lifetime and local intent
exclusion. Phase 4 remains unaccepted until B3, AW-4 and the client rerun.

### 2026-09-08 - BC-3f integrated; B3 draft intent diagnostic

BC-3f Grok `33751bb7` integrated at `986b555` after clean three-way apply.
Independent full named union: **174 passed, eleven failed** in each root,
171.71 seconds worker and 185.87 seconds checkout. Logs/XML/commands:
worker scratch `bc3f-wi`, checkout scratch `bc3f-ci`. BD-2/3/4 and all
six new publisher-boundary cases pass. The frozen omitted-ticket calls
remain failed for Ryan. The broader final BD-2 review waits for AZ-5h2's
shared transport repair; no navigation or speaker measurement was rerun.

The original consumed binding, exact sidecar path and podcast transcript
bytes now reach the actual publisher. Checks run before publication writes
and before the final carrier replacement. A late conflict leaves the
sidecar and committed DB snapshot intact, although owned artifacts/corpus
can remain in the documented interrupted state for retry. The disk reread
is not a general filesystem lock.

B3 is still active. A draft-only diagnostic at its actual parent
`os.replace` boundary produced **one failure**, 0.29 seconds: old operation
A replaced operation B's newer local intent after B took the generation.
The draft source hash was
`3a55774ffa95d194d7202890e17516bb20b831f14685c8ed1440fa58d11dc29f`.
The source, probe, command, log and XML are retained together in checkout
scratch `aw8-draft-retained`; worker output is in `aw8-draft-intent`.
This is not a final B3 verdict. Its final review must close the actual
mutation gap or leave a repair in our queue. The probe is a retained
diagnostic of the parent syscall, not a new frozen fixture that assumes
a future isolated child must execute that parent interceptor.

### 2026-09-08 - Native-prompt fixture preparation

The optional `prepare_prompt_session.py` helper preserves the default
unattached launch and creates a separately named application fixture that
attaches the real Phase 2 service. Its valid preview uses two synthetic
exclusions, with apply false and no assignment. All setup calls and semantic
before/after state are frozen before the client starts. The synthetic staging
and real-service recheck passed once in 0.85 seconds (`aw-prompt-prep-synthetic`).
This is instrument preparation only. Actual archive/client work still waits
for AW-4 and the shared transport repair. Create the 15-minute preview only
when the client can immediately observe it.

### 2026-09-08 - AZ-5h2 integrated; measurement refresh next

AZ-5h2 Grok `098fb14d` integrated at `45bb2f6` after clean three-way apply.
Independent full union: **570 passed, six failed** in each root, 136.49
seconds worker and 127.55 seconds checkout. Logs/XML/commands: worker
scratch `az5h2-wi`, checkout scratch `az5h2-ci`. Both frozen BA-5 cases
and all seven new cases pass. Activity uses the original inbound stamp
through remaining SQLite waits; excessive envelopes refuse before domain
work, and completed refusal frames are capped. Ordinary accepted IDs and
busy-timeout restoration pass.

The six retained failures are unchanged: unary/clock setup for Ryan, four
measurement-document assertions for AZ-5g2, and the old BA-4 SDK route.
The shipped entry is covered independently; the old route remains failed.
AZ-5g2 must now measure this integrated transport, with complete packets,
wire bytes and actual commit/tree IDs. Final BA-4 and broader BD-2 follow.

B3 also hit the PowerShell `$args` collision while rerunning groups and
started a bare full suite. It stopped only its own named task successfully
and switched to explicit selectors. Its earlier correctly named union is
separate evidence; the unintended invocation is aborted, not a full-tree
result. Apply this setup lesson to every further worker brief.

### 2026-09-08 - B3 rejected; final BD-2 disposition; G2 active

B3 Grok `260ef22c` independently produced **240 passed, fourteen failed**,
81.11 seconds (worker scratch `av5m4b3-wi`). Nine are frozen Phase 4 setup
failures, one is AW-6 already repaired by A3, and four are unproven child-stall
setups. Its complete final diff is retained, unapplied. AW-8 also records a
final intent-mutation failure (0.32 seconds) and an unconfirmed-death tracking
failure (0.31 seconds). These remain implementation work. B4's brief requires
actual final mutation exclusion, retained uncertain-child ownership and a
real writer-stall observation under the integrator's runtime.

The Windows virtual environment can launch a redirector PID that starts a
separate Python writer. Suspending the redirector alone does not prove that
the writer stopped. AW-8 retains the actual process topology and all failed
results. Its ten proof artifacts are sealed with hashes and `-text` attributes.
Cancellation also does not establish physical death: never discard an uncertain
child merely because a logical dead flag makes `alive` false.

Final BD-2 on `d1d5fb8` closes Phase 6 implementation review subject to Ryan's
eleven frozen omitted-ticket calls and speaker material. The broader named
regression has **382 passed, four failed**, 61.29 seconds, with only the old
AS-7 evidence assertions failed. Scratch `bd2-broader-final-h2-fixed` retains
the result. The earlier launch ran no tests because the guard environment
was absent; `BD2-FINAL-ENV-REPAIR.md` records its repair and exit propagation.
Current full-tree verification is next. No navigation or speaker result changed.

AZ-5g2 Grok `769107e6-1cc5-447a-85d7-25de3c4ff054` started at 19:54 PDT
from `d1d5fb8`. Its measured refresh must still be verified before integration.

### 2026-09-08 20:10 PDT - B4 dispatched; Phase 6 closure full tree

AV-5m4b4 Grok `e2580c74-1d67-43ad-a5d2-f443409a0c6c` started from
`564836c`. All ten AW-8 proof hashes match working files and committed blobs.
The Phase 6 closure full tree will run on this handoff commit with S21 excluded
as required, plus only the still-open AW-5 and AW-7 reproduction files excluded
under their B4 repair ruling. Other frozen and stale-document failures remain
included. The checkout will remain fixed during that run. This does not credit
the excluded cases or replace any earlier failed or aborted invocation.

### 2026-09-08 - Phase 6 closure full tree completed

Full tree on fixed `669725f`: **2,102 passed, 30 failed, three skipped,
one existing xfail**, 529.82 seconds. Checkout scratch `full-bd2-final`
contains the expanded command, log and XML. The thirty failures are four
superseded AS-7 evidence assertions, nine frozen Phase 4 setup/interceptor
cases, eleven omitted-ticket Phase 6 calls, the Phase 5 unary/clock case,
the replaced BA-4 SDK route and four stale measurement-document cases.
No additional failure appeared in the included tree. S21 and only the
still-open AW-5/AW-7 reproduction files were excluded. Those two files remain
B4's work, not passes or Ryan blockers.

Read-only client preparation reconfirmed Claude Code's claude.ai Max
authentication with no API key. Its documented startup and per-server tool
timeouts permit a declared 10-second limit for the later broken-transport
observation. No client/model or archived-copy preparation has run.

### 2026-09-08 - G2 integrated; final BA-4 accepted with conditions

AZ-5g2 Grok `769107e6` integrated at `a39c7e6`. Independent full union:
**574 passed, two failed** in both roots (117.69 seconds worker, 126.97
seconds checkout). Logs/XML/commands: `az5g2-wi` / `az5g2-ci`. Three-way
apply conflicted only in `.gitattributes`; both proof preservation rules
were retained. All 49 sealed artifact hashes match the staged blobs.

G2's complete activity packets and measured response bytes are retained.
The original record lacked initialization response bytes and directly observed
replay only on 548. The separately briefed integrator supplement adds all 24
input and 16 output frames, serialization/write/flush timestamps and replay
observations on both 548 and 10k. All eight response flushes held admission;
the six immutable synthetic database hashes are unchanged. It is in-memory
shipped-writer evidence, not a physical-pipe or real-client receipt. The old
helper's hardcoded replay path label remains disclosed with exact DB identities.

The old rejected Gemini patch's observed CRLF bytes differ from its existing
LF Git blob. G2's original manifest is preserved, with an explicit mapping to
a separate byte-exact archive; the original patch is unchanged. Preserve
raw logs with force-add when global ignore rules would hide them. Both G2's
failed SDK import and nonwaiting union launcher are archived separately from
its successful measurement and two-failure union.

Final BA-4 accepts Part A subject to Ryan's unary/clock fixture ruling. The
original SDK-route test remains failed; the supported replacement route is
accepted on independent final-wire evidence, not waived to Ryan. Four stale
document failures are closed. Primary JSON-RPC sizes are 64,732 / 64,601 bytes
before newline; the 24 KiB dashboard target remains missed. Run the full tree
on this handoff commit with S21 and still-open AW-5/AW-7 excluded, as before.
B4 remains active; Phase 4 implementation/client work remains our queue.

### 2026-09-08 20:50 PDT - Phase 5 closure full tree; B4 rejected by AW-9

Full tree on fixed `44968d9`: **2,106 passed, 26 failed, three skipped,
one existing xfail**, 514.25 seconds. The four stale G2 measurement-document
failures are closed. Remaining failures: four superseded AS-7 assertions,
nine frozen Phase 4 setup cases, eleven omitted-ticket Phase 6 calls, the
Phase 5 unary/clock case and the replaced BA-4 SDK route. No additional
failure appeared. S21 and only the still-open AW-5/AW-7 files were excluded.
The log/XML/expanded command are sealed in `proof/full-ba4-2026-09-08/`.
All 49 G2 sealed committed blobs were verified; the integrator receipt now
also has an exact `-text` attribute for future checkout preservation.

B4 Grok `e2580c74` independently produced **255 passed, nine failed**,
134.12 seconds. AW-9 rejects its final diff for three implementation gaps:
unknown writer liveness becomes death after launcher exit; the destination
mutex is abandoned when its acquiring thread exits despite retaining its
handle; startup failure loses session ownership before Mirror stores it.
Final unchanged lifetime probes: **two failed**, 1.01 seconds; additional
startup probe: **one failed**, 3.12 seconds. Draft two-failure output (0.96
seconds) remains separate. Final source hashes were captured before the
recheck and remained unchanged. The complete rejected patch and sealed
proof are committed; the three cases are frozen for AV-5m4b5.

A Windows mutex belongs to a thread, not a retained handle. Exclusion must
have a lifetime owner established before child launch, independent of the
request thread, and survive any unconfirmed start/stop failure. An uncertain
writer remains implementation work. The next B5 brief requires those actual
boundaries and preserves A3 identity and isolated final local mutation.

### 2026-09-08 20:52 PDT - B5 dispatched

AV-5m4b5 Grok `a4af542b-c8bb-4958-97f4-185951daaad0` started at
20:50 PDT from `39d7e19`. Its brief requires all three AW-9 cases and the
full B4 union, plus proof that the gate becomes available after proven
physical death. AW-9 and full-tree proof seals matched every staged blob
before the preceding commit. The real-client run remains gated on the
finished implementation review; source/client preparation can continue.

### 2026-09-08 21:04 PDT - Client receipt instrumentation prepared

`cd3d444` adds complete packet/prompt inspection. Four synthetic checks
passed (1.70 seconds), including changed-tail and missing-native-prompt
failures of the checker. Native resource tools must remain in the client
built-in allowlist; an empty list would remove that route.

A safe SQLite file URI exposed a fixture-guard setup defect: one failed in
1.19 seconds. The documented repair decodes local URIs before applying the
same resolved containment check and rejects remote authorities. The unchanged
case plus three escape negatives passed (0.36 seconds). This is not a product
or client failure. The first output is retained with the repaired output.

The action observer's four synthetic checks passed (3.20 seconds). It records
full tool-hook inputs/decisions, supplies an inert action sentinel and wraps
only a separate Recall fixture. Client validation rejections may precede
hooks, so retain the full client stream in addition to hook logs. All these
checks are sealed under the AW rerun preparation-checks directory. No archived
copy, actual client/model, live index or port 5179 was used. B5 remains active.

### 2026-09-08 21:10 PDT - Destination alias diagnostics retained

B5's brief already requires exclusion across supported destination aliases.
Additional diagnostics on rejected final B4 bytes found that a trailing-dot
alias shares the mutex (**one passed**, 0.77 seconds), while an owned junction
to the same physical directory obtains a different mutex (**one failed**,
0.75 seconds). Only disposable paths and read-only gate operations were used.
Both observations and scripts are sealed in `proof/aw9-alias-2026-09-08/`.
Do not assume every lexical Windows alias fails, or count these as B5 results.

After B5 finishes, inspect its final alias handling and probe its session-start
boundary from a competitor process while the original destination is held.
Canonical exclusion or explicit refusal before admission is acceptable. The
scratch `AW10-ALIAS-RECHECK-BRIEF.md` specifies that check; preserve the B4
low-level observations separately. B5 remains in progress.

### 2026-09-08 21:30 PDT - B5 independently verified; alias repair required

B5 independently produced **267 passed, nine failed**, 132.05 seconds, and
closes all three AW-9 lifetime cases. The final mirror source hash remained
unchanged before and after the checks. AW-10's separately briefed session
admission probe failed (**one failed**, 2.90 seconds): an owned junction and
its verified same-directory target admitted two live writers before either
had a lease. Cleanup confirmed death for both task-created sessions.

The 233,882-byte complete B5 patch is retained unapplied. AW-10 proof seals
19 files, including the patch, original focused failures, long-path failure,
final union and final source bytes. All eight prior B4 alias archive hashes
match committed blobs. The new AW-10 case is frozen for B6.

A lexical destination hash cannot exclude a physical alias. B6 may use one
shared Windows writer-admission gate, conservatively serializing unrelated
destinations without parent filesystem resolution. Preserve exact operation
bindings and lifetime ownership; a process-global owner lookup alone cannot
authorize a foreign operation. This is implementation work, not a Ryan gate.

### 2026-09-08 21:32 PDT - B6 dispatched and AW-10 seal verified

AV-5m4b6 Grok `9577904a-b4f7-4a0f-ac3c-93467f2e1b50` started at
21:30 PDT from `17f3714`. The brief requires the unchanged AW-10 case,
the complete B5 union and new alias/operation-ownership evidence. All 19
AW-10 sealed files match committed bytes. No B5 production change has been
integrated; the checkout remains on the accepted A3 production baseline.

### 2026-09-08 21:36 PDT - Explicit client configuration prepared

The AW preparation now generates fresh, explicit client settings and launch
arguments from the frozen staged inventory. Only two native resource tools,
three bounded reads and the inert sentinel are allowed; other uoink tools
are explicitly denied. Ordinary and Recall settings are separate. Hook
commands use executable/argument arrays, and the original MCP configuration
is preserved. Two synthetic checks passed in 0.68 seconds; five artifacts
are sealed in the client-config-check archive. These are preparation checks,
not client observations. B6 is still active; real-client execution waits for
its integrated result and final AW-4 ruling.

### 2026-09-08 - Candidate notes prepared while B6 runs

All five client-configuration preparation hashes match committed blobs at
`09c88dd`. Its staged metadata inventory is the shared registry; the actual
stdio inventory must still come from client discovery. The release-notes
draft is in checkout scratch as `RELEASE-NOTES-LIVING-LIBRARY-draft.md`.
Phase 3/5/6 dispositions and retained results are filled in; Phase 4, final
full-tree, candidate SHA and installer fields remain explicitly pending.
Promote it only after the Queue's candidate prerequisites are satisfied.

### 2026-09-08 - Installer SDK source comparison

The installer pins MCP 1.27.1 while current user-site verification uses
1.28.1. The 216,260-byte pinned public wheel was downloaded to checkout
scratch for read-only source inspection; no package was installed. Its
SessionMessage, stdio and types sources are byte-identical to the installed
version. FastMCP's server differs only in client-id documentation comments.
The hashes and diff are in `proof/sdk-source-preflight-2026-09-08/`. This
reduces the specific source-API uncertainty; it does not replace a smoke
against the installer's embedded Python and full pinned dependency graph.
B6's first full worker union had 229 passed / 55 failed and is under repair;
its focused 23 passes do not override those regressions.

### 2026-09-08 22:10 PDT - B6 worker regression repair completed

B6's second union had **272 passed, twelve failed**, 137.21 seconds. Three
new failures were helper operations trying to acquire a second writer while
their original session held the shared gate. The worker retained both failed
unions and documented each repair before rerunning. Its latest union has
**275 passed, nine failed**, 132.64 seconds; only the frozen Phase 4 cases
remain in that result. Independent verification and final review are pending.

Final review must check prepared-session cancellation before Popen and B6's
new local-helper reuse. A logically cancelled session is not proof that a
launcher cannot still create a child. A shared Mirror object alone is not
operation context for a foreign thread. The scratch AW11-START-CANCEL-REVIEW-
BRIEF and its two diagnostic files define these checks before execution.
They are hypotheses, not reported failures. No B6 production bytes have been
integrated, and the actual client receipt still waits for AW-4.

### 2026-09-08 22:16 PDT - B6 independently verified; AW-11 requires repair

B6 independently reproduced **275 passed, nine failed**, 153.63 seconds.
All four final production source hashes remained unchanged across verification
and the additional review. AW-11's three cases failed in 0.88 seconds: one
cancelled-start retention case and foreign-thread intent put/unlink cases.
The complete 265,652-byte patch is retained unapplied, with 25 sealed files.

Cancelling a prepared session let its original caller later start an idle
child after Mirror/global retention and the gate were released. No lease or
content mutation was sent; this is not post-timeout publication evidence.
Separately, B6's helper fallback let a thread without operation context replace
and delete an intent through the current Mirror writer. All task-owned child
cleanup was confirmed. These are implementation defects, not Ryan gates.
The three new frozen cases and B7 brief require retained launch transitions
and explicit helper-operation ownership while preserving existing controls.

### 2026-09-08 22:18 PDT - B7 dispatched

AV-5m4b7 Grok `b00703c8-7ca0-4e4b-b3ba-c6f1bad3d6ac` started at
22:16 PDT from `7995c0e`. Its brief limits the repair to the two AW-11
boundaries, requires the complete B6 union and all three unchanged AW-11
cases, and adds actual Popen-handoff coverage. All 25 AW-11 proof hashes
match committed blobs. The checkout remains on the accepted A3 production
baseline; no B-series production change has been integrated.

### 2026-09-08 22:24 PDT - Isolated client capacity observed

Claude Code 2.1.261's native `/usage` refreshed to **70% all-model weekly
use, 88% Fable weekly use, 0% current-session use; usage credits off**. Its
session accounting showed zero tokens and $0. No task prompt was submitted;
the client made its own startup quota-check request, retained as such. The
receipt and selected noncredential evidence are sealed under
`proof/client-capacity-2026-09-08/`. This does not establish product acceptance.

The initial normal-profile trust prompt was declined. A fresh client profile
used only a temporary copy of the still-valid subscription access credential,
without its refresh credential, and account metadata. The temporary credential
was deleted after exit. The real client run must also use a separate profile
and freeze its own launch/model metadata. B7 remains active; the archived copy
and native library prompts still wait for the accepted implementation.

### 2026-09-08 - B7 first union; final review preparation

B7's first focused seven cases passed. Its first combined union has **281
passed, ten failed**, 137.89 seconds: the nine frozen failures plus its new
originating-helper control. The worker is repairing that regression; focused
passes do not replace this failed union. Final independent verification waits
for finished source and retained repair notes.

All eight capacity-preflight proof hashes match committed blobs at `b5207ff`.
The candidate build wrapper is prepared in scratch, with exact branch/SHA and
recursive-target checks plus a disposable data profile; parsing passed, but
no full build ran. Build cache and installer staging are absent. The final
AW-4 report draft is also in scratch with pending fields clearly marked.

The scratch AW12-THREAD-IDENTITY-REVIEW-BRIEF specifies a final check of B7's
integer-thread-ID helper fallback. Python permits those IDs to be reused;
any diagnostic must distinguish simulated ID reuse from observed Windows
allocation. No such diagnostic has run and no new result is claimed.

### 2026-09-08 22:53 PDT - B7 verified; bounded AW-12 correction

B7 independently reproduced **282 passed, nine failed**, 159.69 seconds.
The worker's unknown `console_output_file` option warning was a command
configuration warning, not a product exception. Final source remained fixed
at mirror hash `8b670a0cdde7660abdfa3c96b16a968d52c59d7acb86caba4616f8de1001e953`.
The original 300,847-byte patch and observations are retained separately.

AW-12's three cases failed in **3.77 seconds**. Simulated integer-thread-ID
reuse authorized an actual foreign intent replacement; Windows allocation
reuse itself was not observed. Prepared-only cancellation retained an unused
gate. Cancellation also closed the job while launch still held it for
assignment; the probe prevented a stale-handle kernel call. All task-created
child cleanup was confirmed. These remain implementation findings.

Astra made the bounded correction in the finished B7 worktree: actual Thread
identity for helper authority, release after cancelled preparation, retained
job ownership through assignment, and one nonblocking termination owner.
Graceful shutdown uses the same final cleanup. The original worker report
and patch are preserved. The corrected focus passed **11 tests**, 13.25
seconds, including unchanged AW-11/B7 cases and one concurrent-termination
case. The complete corrected union is running; checkout integration waits
for it. Mirror hash is now
`33bd644ca3ac13070716fa8493221260c4b713ba71e4a402683d608de06761b3`.

### 2026-09-08 23:00 PDT - B7 and AW-12 integrated

Integration `6858b81` applied all 22 files without conflicts. The complete
corrected union has **286 passed, nine failed** in both roots: 168.87 seconds
in the worker and 168.01 seconds in the checkout. All four new AW-12 cases
and the unchanged AW-11/B7 cases pass. Existing acceptance assertions and
helpers remain unchanged. The original B7 result and all three AW-12 failures
are separately retained; the correction is explicitly Astra's work.

The original proof seal's 21 hashes matched committed bytes before integration.
The final proof seal covers 38 files, including both full corrected outputs
and the applied patch. The checkout mirror hash is
`e04509fb9fa1752351af0e32e43a535a30536aeee3e7934efdbf709fffca5d45`;
its difference from the worker hash is only line endings. Normalized bytes
match exactly, and the other three production hashes match directly.

Finish AW-4 with the four broader companion files: stdio clip tools, Phase 0
registry capture, library adapters and live documentation contracts. The full
named implementation union has just been checked in both roots; record the
broader result separately. The actual client receipt and eventual candidate
full tree remain required. Phase 4 is not yet accepted.

### 2026-09-08 - AW-4 implementation review closed

The four broader companion files passed **113 tests**, 1.27 seconds, on
`fad7e87` with unchanged production bytes from `6858b81`. Their separate
result is sealed under `proof/aw4-final-2026-09-08/`. All 38 final AW-12
proof hashes match committed bytes. `PHASE4-AW4-FINAL-2026-09-08.md` closes
the observed implementation findings and states the remaining scope and limits.

The real-client receipt can now begin from the clean committed SHA. Use a
fresh archived-copy fixture and separate Claude profile, keep usage credits
off and apply false, and retain the actual client/model/launch bindings.
This is still a required observation, not a Ryan blocker or a phase pass.

### 2026-09-08 - Actual native client routes observed

Client observation 01 on frozen `7eec17b` used Claude Code 2.1.261,
`claude-haiku-4-5-20251001`, claude.ai Max and a disposable access-only profile.
Usage credits stayed off. The CLI's $0.1917 token-cost display is not a paid
API invoice. Native resources and both required native prompts actually work
in this client: complete packets and `prompts/get` traffic are retained. Do
not repeat the earlier receipt's claim that these routes are unavailable.
The consult command consumed topic `object`, the first positional word.

All eight card/excerpt comparisons matched complete independently frozen
text. Explicit reconnect replaced 61780 with 71588 and preserved both full
item responses. Unavailable corpus reads refused in 1.8373 / 1.9249 ms.
A distinct suspended-child request timed out in the client after 10.003
seconds, with no retry/reconnect in that case. The child was resumed and
all client children exited; temporary access credentials were removed.
The returned YouTube link played in a fresh anonymous Chrome context.
Library and settings state remained unchanged, with 548 items and clean
integrity/foreign-key checks. Seventy-seven artifacts are sealed.

Windows denied moving the open SQLite directory; that setup produced no
product request. Corpus disconnection is a separate result, not proof of
database disappearance. The client did not request resource templates;
its 32-tool/four-prompt discovery is observed, template discovery is not.

The held text-only row lacks URL metadata. Its card links remain null,
while the held corpus and sidecar retain the original public source. Use
the returned bounded corpus URI for the next actual-client source-link
observation before proposing a canonical-card change. The client supplement
also covers hostile content, Recall and vault cases. These are our remaining
work; Phase 4 is still unaccepted and no new implementation defect is ruled.

### 2026-09-09 00:23 PDT - Candidate full tree retained; fixture cleanup ruling

The candidate's full tree on `6c313ea` completed with 2,102 passes and 92
failures, three skips and one xfail in 550.41 seconds. Only S21 was excluded.
All 67 additional mirror failures were passing cases in the earlier focused
AW-12 checkout union on identical production source. One old D15 assertion
did not fail here; this contaminated result does not supersede its ruling.

The diagnostic prefix reproduced seven passes followed by the failed ordinary
export. A two-case reduction reproduced the same failure: the AW-11 foreign-
helper test passes, then AW-2's first ordinary export fails. Read-only snapshots
show the first fixture has directly terminated its private session but left
that exact dead session in the main thread's I/O context. No process, owner
or mutex remains. The next fixture inherits the dead operation and refuses.
The current observer adds I/O context fields absent from the first diagnostic;
the first observer was not separately hash-frozen. Both failed results remain.

Production resync/stop/kill uses `_forget_session` after proven death. Four
separate synthetic lifecycle observations completed with no stale context,
retained session, owner or mutex, without resetting globals. Do not remove
the expired-operation refusal to make the fixture pass: it protects late
helpers from adopting a new operation. Request consistent fixture teardown
under Ryan's existing acceptance-test rule. No acceptance file or product
source changed, and no corrected full tree was attempted.

The 17-file seal in `proof/candidate-full-01-2026-09-09/` preserves the full
result, both diagnostics, full comparisons and production control. Release
notes and Blockers for Ryan retain the failed result and additional teardown
condition. Continue the local installer build from the clean receipt commit;
it is a review package, with installation/main merge still Ryan's decisions.

### 2026-09-09 00:36 PDT - Local installer and bundled-runtime receipt complete

Built `build/Uoink-Setup-3.8.0.exe` from frozen candidate `e47e4f2`, ending
at 00:30 PDT after 368.93 seconds. The 339,042,658-byte artifact has SHA-256
`9defc2a98ba680f8b4cdf06bdd09eadbb1153f2028070881b5472ce97f7e927d`.
The exact 142-package inventory verified. Staged schema/version, tray,
dashboard, splash and WhisperX import checks passed. Build regeneration changed
only the third-party notice date from 2026-07-25 to the source-bound 2026-09-09;
the package table is unchanged. No installation or inference occurred.

The first original-entry stdio attempt failed because its blanket socket
guard blocked Windows asyncio's internal socket pair. Its child exited one;
the caller timed out with no initialization response. The repair brief was
written before observation 02. The new guard permits only the original
standard-library socket-pair function's verified local bind/connect; 5179,
all other network access and nested processes remain forbidden.

Observation 02 on the unchanged bundled Python 3.11.9 and MCP 1.27.1 passed:
32 tools, five templates, four prompts, full native/fallback card equality,
native consult prompt and a successful small activity call. Child exit was
zero and both drains completed. This is synthetic staged-runtime evidence,
not an installed C22/Phase 4 or speaker receipt. The original failed attempt
is preserved and never becomes a pass.

The archive collector initially rejected the staged token/log generated by
server imports. Inspection confirmed neither is an Inno source input. The
token was created after compilation, and it was removed after both children
exited. The collector now records that side effect separately; no runtime or
build was rerun for the archive correction. The seal retains 28 files, a
32,202-file staged input inventory and 141 source bindings. Input timestamps
still match the frozen source epoch. Token contents and fixture databases
are excluded from proof. The inventory is not an extracted installer listing.

Release notes, State and Queue now identify the completed local candidate.
The 2,102-pass/92-failure full-tree result and every owner condition remain.
No product or acceptance-test source changed after final verification. All
Control Room/client work is finished; further acceptance work requires Ryan's
listed rulings or material. No push, merge, installation or live-index access.

### 2026-09-09 07:25 PDT - Ryan rulings and reviewed fixture correction

Ryan authorized exactly five setup/cleanup corrections and the branch-only backup.
The six-file patch is retained with its SHA in the conflicts log. All 690 assertion
syntax trees remain identical; no production source, threshold, parameter case or
skip/xfail changed. Phase 6 acquires tickets before constructing replacement inputs
and retains original tickets across retries. Missing-ticket negative cases remain.
The other Phase 4 syscall interceptors were not included in the authorization.

The one-page review approves execution only. Commit this state before the full
tree; only S21 is excluded under the standing command. Any residual failure is
a product defect under Ryan's new ruling, with a repair brief and no further
fixture edits. Phase 2 option 3 and the X blocked-link condition are resolved;
speaker attribution stays unaccepted, no diarization, and Part B is deferred.

### 2026-09-09 07:39 PDT - Corrected tree failed; product briefs and installation blocker

Fixture/review commit `4a3531642692736d4aaa4098077ab8fde464aeb4` is the
tested candidate. Full tree `igr1` completed with **2,174 passed, 20 failed,
three skipped, one xfailed**, 183 warnings, 607.27 seconds. Only S21 was
excluded. The complete log/XML, commands, Python/dependency provenance,
unchanged-assertion audit and case comparison are sealed under
`proof/ryan-corrected-01-2026-09-09`. All 20 failures were present in the
previous tree; 72 previous failures pass here. Neither result replaces the
other. The failures are four Phase 3 evidence checks, thirteen Phase 4 mirror
checks, one Phase 5 SDK serialization check and two Phase 6 refusal checks.
`CORRECTED-TREE-PRODUCT-REPAIR-BRIEF-2026-09-09.md` assigns all twenty;
there was no further fixture edit or runtime rerun.

Installation source inspection found an additional product blocker:
`installer/uoink.iss:447` invokes upgrade preparation, and
`installer/upgrade_prep.ps1:61` performs a TCP probe of 5179. The normal
helper path probes and binds that fixed port as well. Silent Inno mode and
a throwaway Windows account do not isolate the port. No installer/helper
was launched for this finding. The new installation repair brief defines
the supported isolated path and operator kit needed before Ryan can act.
The requested runbook includes AS-7 C22, installed Phase 4, evidence return
and the four everyday checks, but its only current executable step records
a preflight block. Complete installed execution commands remain product work.

Production source did not change, so the `e47e4f2` installer and its existing
28-file seal are retained without rebuilding or resealing. The runbook's
PowerShell preflight was syntax-parsed only. A metadata-sealing helper's first
launch was blocked before execution by an inherited old Python startup guard
missing its environment value; isolated standard-library execution then sealed
the already-completed output. This was not another test or product observation.
The authorized backup will include this failed checkpoint and its open briefs;
no main merge, install, new fetch, diarization or paid API occurred.

### 2026-09-09 07:44 PDT - Authorized branch backup verified

Results, product briefs, release notes and the blocked installation runbook
are committed at `ba3d2569754758f18eb53bb2743674dd6bb8ba50`. The local
`cc/living-library` ref was advanced from `9217846` to that descendant after
checking ancestry and confirming it was not checked out in another worktree.
`git push origin cc/living-library` succeeded; `git ls-remote` independently
reported that exact SHA at `refs/heads/cc/living-library`. The candidate branch
was not pushed and no main ref was merged or updated.

The initial push waited on Git Credential Manager and failed because no
terminal prompt was available. Its task-owned waiting credential helper was
stopped. GitHub CLI already held Ryan's authenticated `ryanbiddy` account;
an ephemeral credential-helper setting reused that sign-in for the successful
push. No token was printed or stored in the repository and no persistent
credential configuration was changed.

Before the results commit, all 13 corrected-run proof files and all 28 retained
package proof files matched their seals and staged bytes. The installer hash
and 339,042,658-byte size matched. The exact fixture patch and all 690 unchanged
assertions verified again; all twenty failures are named in the product brief.
There is no source/test change after the measured `4a35316`. This log-only
backup receipt will be committed and included in the same authorized branch
backup. Product repairs and the executable installed operator kit remain open.

### 2026-09-09 - Continued release work; originals located

Ryan explicitly asked Astra to continue until the product works and the release
notes/package are ready, rather than stopping at another checkpoint. All earlier
specific restrictions remain. The original AT6 scratch root still exists; all
eight artifact hashes match the original receipt, including the four missing
archive entries. A separate original receipt for feed 64703 also exists. The
feed 49557 overlay retains its original database/WAL and launch log, but no
completion receipt. Recovery will preserve original bytes and distinguish
post-hoc state recovery from a contemporaneous receipt. No new capture, source
request or successful exit status is inferred from those files.

Three bounded product briefs prepare independent Phase 4 lifecycle, Phase 5
SDK and Phase 6 refusal work while Astra completes evidence recovery. Workers
must preserve all existing tests and failed observations; integration remains
sequential with independent verification in each root. The eight Phase 4
interception cases and installation isolation remain separate work afterward.

### 2026-09-09 - Original evidence archived; three repair workers active

The 33-file original recovery is described in
`PHASE3-ORIGINAL-EVIDENCE-RECOVERY-2026-09-09.md`. All eight AT6 and eight held
browser artifacts match their original hashes. Feed 64703's actual receipt
source is `6d9a819`, correcting the historical image-name association. C21's
original database/WAL were copied without changes; the derived closed backup
passes integrity/foreign-key checks and matches the visible one-capture,
waiting-for-client state. No new observation is claimed. The original shell
discarded the S21 child exit status, and Windows denied the narrow process-exit
event query. Leave that gap open; do not substitute another process's success.

From frozen brief commit `a74385c`, Grok workers are active: Phase 4 lifecycle
`cc391d36-97ff-40e0-b8e8-9c8e70c661bb`, Phase 5 SDK
`8cef3e8a-3ada-4fed-8e48-4b27c84ce185`, and Phase 6 refusal
`d4d402e8-2461-436f-b9c6-9fed61a1605d`. API-key environment variables were
removed for each dispatch; subscription only, no existing-test edits. A
nonessential mailgraph MCP startup handshake failed in their normal CLI
startup; no success or acceptance is inferred from the absence of streamed
worker text. Wait for completed source/results and independently verify.

### 2026-09-09 - Recovery verification sealed; installer repair dispatched

On committed recovery `239dbbd`, AS-7/8/9 has **22 passed, one failed**,
1.38 seconds. Strict Phase 3 has **181 passed, one failed**, 45.43 seconds;
both failures concern the missing original AT6 child exit status. Confirmation
has 11 passes and dashboard 35. Companion groups have 377 passes / 17 failures;
all 17 are the Phase 4 historical driver's blocked isolated subprocesses.
Preserve the original driver and failed output; the companion note defines
the current guarded invocation after a documented Phase 4 repair. No existing
test changes. The 23-file seal is `proof/p3-original-checks-2026-09-09/SHA256.json`.

Installer worker Grok `fd647a72-24b6-468a-905f-ddfdfa5899ac` started from
`5bae13c` under the implementation brief. It owns the supported mechanism;
Astra still owns the complete operator kit, independent verification and build.
Phase 5 SDK and Phase 6 refusal workers have finished; independent review is
in progress. Phase 4 lifecycle is still active. No worker output is accepted
before verification in both roots.

### 2026-09-09 - Lifecycle integration and final SDK review

Phase 4 lifecycle is independently **163 passed / eight failed** in both roots,
176.98 / 174.21 seconds. All five lifetime cases pass; the eight parent-process
interception failures remain. Astra's new real-owner probe rejected the worker's
unreadable-lease exception (one failure, 0.90 seconds), then passed after its
removal. A separate cancelled-plan control passed before repair. The original
worker patch, failed probe and corrected observations are retained. See the
lifecycle integrator report and its 24-file seal. Only `.gitattributes` had a
three-way conflict; both raw-proof rules were preserved. No existing test edits.

The SDK worker independently passed 266 cases, then the local-response-copy
review failed: its global serializer hook released a request before the real
outgoing frame. Astra's documented message/stream adapter removes that hook and
binds settlement to the actual outgoing frame. Four focused cases and all 267
named cases pass in the worker; checkout integration remains next. Phase 6's
71 independent worker checks also pass, with no publication without a ticket.

The original full tree remains the `4a35316` failed result until a fresh committed
tree is measured. Production source has now changed, so a new package is owed
after the remaining verified integrations. The old package/proof stay retained.

### 2026-09-09 - SDK settlement integrated; three installation workers active

The reviewed SDK supplement independently has **267 passes, zero failures**
in worker and checkout, 127.82 / 138.83 seconds. The original worker's 266-pass
union and the failed local-copy probe are preserved. The applied code binds
settlement to the outgoing frame and leaves the shared SDK serializer unchanged.
No existing tests changed. See `RYAN-PHASE5-SDK-INTEGRATOR-2026-09-09.md` and
its 27-file proof seal. Phase 6's 71-case checkout verification is next.

Three independent Grok workers now cover the installation finish: isolation
`fd647a72`, C22 scenario kit `9c866bb0`, and Phase 4/everyday kit `81060797`.
The last started from `1063843`. They may write new tooling and tests, but
cannot run Inno, the normal helper, actual clients/models or any forbidden
data/port. Astra still verifies and assembles the exact operator runbook and
hash-bound package before Ryan's actual receipt session.

### 2026-09-09 - Phase 6 refusal integrated; fixture proposal pending

Phase 6 has **71 passed, zero failed** in worker and checkout, 208.89 /
203.59 seconds. The raw patch applied cleanly to `0ad33d4`; source hashes,
commands and results are in its 17-file seal. Missing tickets remain unable
to publish. The new classification only recognizes validated committed-history
snapshots as stale. No existing tests changed; speaker scope remains blocked.

The exact mirror-hook proposal is archived with its assertion audit and
one-page review. Ryan's reply is pending; it was neither applied nor executed.
The current guarded AW companion observation is 31 passed / one failed within
the earlier lifecycle union, so no repeated run is needed to close the driver
follow-up. Historical failed outputs remain retained.

Installation isolation worker `fd647a72` has completed. Its report claims
92 passes / one existing skip; independent source and process review are next.
C22 `9c866bb0` and Phase 4 kit `81060797` remain active. No current source
package or installed receipt is claimed.

### 2026-09-09 - Installer review rejected incomplete ownership; backup verified

Authorized backup `origin/cc/living-library` is exactly
`512fecbb4aa384e27fdd7bc822c4d77255183522`, verified with ls-remote. No main or
candidate-branch push occurred.

Installer isolation `fd647a72` is not integrated. Independent original suite:
90 passed / two failed / one skipped (48.85 seconds), distinct from the
worker's 92-pass/one-skip claim. Venv redirector/process-image differences
require a direct-runtime observation without changing fixtures. Seven new
read-only review probes fail: missing option values become normal mode, and
incomplete or different process creation/executable identity is accepted.
Source review also finds uninstall mode not recovered from durable metadata
and premature/final-directory validation issues. The full original patch and
18-file proof seal are under `proof/ryan-install-review-2026-09-09`.
`RYAN-INSTALL-ISOLATION-REVIEW-BRIEF-2026-09-09.md` governs the repair; no Inno
execution or default helper/port probe is authorized. Empty-helper logs also
expose a standing-capture transaction error to investigate after kit review.

### 2026-09-09 - C22 kit source rejected; production startup cause identified

C22 kit `9c866bb0` is complete but rejected on source review. Its stub-only
19-pass result is not an installed test. Required scenarios call nonexistent
production `/c22/snapshot`; populated replay has an unconditional identity
success; protected-state comparison does not compare before/after. Its stop
path uses incomplete/tolerant identity followed by PID-only taskkill. Preserve
all original source in `patches/ryan-c22-kit-original-2026-09-09.patch`.
`RYAN-C22-KIT-REPAIR-BRIEF-2026-09-09.md` defines five bounded repairs.

Installer repair `3a3bd6cb` is active from `b6aa527`. Astra independently
located an uncommitted write in `writing_studio.seed_default_anchors` along
the observed empty-helper startup path; a new regression and narrow durable
transaction repair are next. Do not weaken Index's transaction refusal.

### 2026-09-09 - Default startup styles now settle their transaction

Astra's three new default-seed regressions all failed before repair. The
Index-owned transaction repair with legacy connection/lock savepoint support
passes **21 checks, zero failures** (2.21 seconds), including the existing
style/writing and source-migration files. The intermediate 18-pass/three-fail
adapter observation is retained. No existing tests changed. See the startup
anchor review and proof seal. Full-helper startup verification remains next
after the installer source is ready; no installed receipt is claimed.

### 2026-09-09 - Phase 4 instrument check passes; installed kit coverage incomplete

The original Phase 4 kit independently passes 11 instrument tests in 4.49
seconds (`proof/ryan-p4-kit-review-2026-09-09`). Source review finds its
original route only initializes/lists tools; full packets and bounds are
checked only against a synthetic child. The blocking read has no deadline,
the profile path nests Uoink contrary to the supported mechanism, and the
embedded-runtime guard/package provenance are incomplete. The original patch
is retained. `RYAN-PHASE4-KIT-REPAIR-BRIEF-2026-09-09.md` governs replacement;
these instrument passes do not make an installed receipt. No current package
or installed pass is claimed. C22 repair `6accc421` is active from `24a5fe0`.

### 2026-09-09 - Native verification identity confirmed; integrated tree next

The private native Python runtime preserves real Popen/child PID identity and
retains the inherited audit guard even with PYTHONPATH absent. Vendor hashes
match; a disposable canary write was refused. The unchanged first installer
suite has 92 passes / one skip in 18.81 seconds with it. This resolves the
verification-launcher discrepancy, not the rejected ownership defects.
The old e47e4f2 installer has a separate verified byte-identical retained copy
under `_scratch/retained-package-e47e4f2` before any rebuild.

`RYAN-PRODUCT-CHECKPOINT-TREE-BRIEF-2026-09-09.md` now governs a complete
committed checkpoint while the three replacement installation workers run.
It includes all integrated product repairs and only excludes standing S21;
the proposed mirror fixture patch remains unapplied. This checkpoint will not
replace the final tree required after the pending source integrations.

### 2026-09-09 - Integrated full-tree checkpoint sealed

On exact `263b7e422a4cb5b0c3357a86e4ac957eec28a4cf`, the full tree has
**2,193 passed / nine failed / three skipped / one xfailed**, 183 warnings,
728.37 seconds. Only standing S21 is excluded. Compared with `4a35316`,
eleven prior failures pass, eight new regressions pass, no case is missing
and no new failure appears. The eight mirror parent-interception cases and
unrecorded original AT6 child exit remain failed. The fixture proposal remains
unapplied. No historical result is relabeled. Complete case comparison and
raw output are sealed under `proof/ryan-integrated-tree-01-2026-09-09`.

Native verifier provenance and original-installer invocation comparison are
also sealed (14 files). The unchanged first installer suite has 92 passes /
one skip with native child identity, separate from its rejected ownership
probes. Installer repair `3a3bd6cb` currently reports 113 passes / one skip;
its compilation/review must finish before independent acceptance. Phase 4 kit
replacement `a75cec28` is active from `80e4c3c`; C22 `6accc421` remains active.
No new package or installed receipt is claimed.

### 2026-09-09 — second isolation review retains Inno defects

Astra independently reproduced 113 passes / one skip, 17.47 seconds, for
3a3bd6cb using the native private verifier. The worker's 113 / one skip and
seven review passes remain separate. Proof is sealed under
proof/ryan-install-review-02-2026-09-09. Source review still rejects the Inno
boundary: ShouldSkipPage never receives wpPreparing, registering no extra
resources does not disable Restart Manager, and InitializeUninstall accepts
damaged metadata without a checked stop before deletion. Path aliases and
ambiguous marker parsing also need the bounded repair brief. Compilation and
Python tests cannot establish these installed runtime guarantees.

### 2026-09-09 — C22 second-kit evidence and archive correction

Independent guarded C22 instrument union: 26 passed / two failed, 69.61 s.
The old Inno-argument assertion and stub-helper acceptance assertion remain
failed. Source review additionally found ordinary-index hashing (forbidden),
post-only protected-state snapshots, nonexistent charge columns, direct child
record calls outside helper recovery, and an operator preparation flow that
cannot continue its own receipt. The next bounded brief fixes the instrument;
production URL validation must keep refusing loopback standing sources.
The original patch, named-run output and worker scenario JSON are retained in
proof/ryan-c22-review-02-2026-09-09 with a hash seal.

Astra's explicit isolation archive path list accidentally omitted the modified
suite_service.py. The original patch is unchanged; omitted-suite-service.patch
now retains those exact bytes and is added to that seal. Astra applied this
companion patch cleanly in the d0577a56 worker before its verification, without
touching the worker-owned Inno file. Integrate both patches together.

### 2026-09-09 — Original stdio preview reads must not recover storage

Astra's six-case original-entry reproduction pre-r1 returned correct answers
but all six failed unchanged-state checks. Index.open automatically migrated,
backfilled and recovered the work service during an existing-only read. The
brief retains the disproved missing-service hypothesis and corrected diagnosis.
Index.open_existing now uses read-only SQLite without initialization; explicit
ordinary work can promote the same handle under its lock. A pure preview reader
shares the original validation without attaching or recovering a service.
Nine new tests pass (7.67 s); the named union has 212 passed / eight failed
(72.66 s), all eight the existing mirror interception cases. No frozen test
changed. Fourteen raw files are sealed under proof/ryan-preview-read-2026-09-09.
Final committed-tree and packaged original-entry checks must include this repair.

### 2026-09-09 — Second Phase 4 kit is retained, not installed credit

Grok a75cec28 has 20 independent passes / one failure (20.39 s); the frozen
first kit still expects the obsolete profile/Uoink/settings.json location.
Its original source-runtime observation returns 32/5/4 but both native saved
preview calls fail feature_unavailable. Exact replies and raw frames are in
the 12-file seal proof/ryan-p4-kit-review-02-2026-09-09. e86bc16 supplies the
pure preview reader; the next observation must use it unchanged.
Review also found a 40-versus-64-character source-commit error, commented
import-site guard bypass, unbounded stdin writes, incomplete tree cleanup
claims, partial packet acceptance and deletion of the held original database
if a replacement appears. Follow RYAN-P4-FINAL-INSTRUMENT-REPAIR-BRIEF-2026-09-09.md.
The old failed observation and frozen test remain; no installed claim is made.

### 2026-09-09 — Isolation integrates with bounded Inno correction

Grok d0577a56 and Astra's RYAN-INNO-REVIEW-SUPPLEMENT-BRIEF corrections are
integrated through an exact raw diff and clean git apply --3way. The patch
includes cached suite_service.py, which the second archive had omitted.
The original worker patch and source are retained before the local correction.
Worker original 118 passed / one skip (15.69 s); corrected worker 118 / one
skip (15.79 s); checkout plus twelve preview/read/startup companions 130 /
one skip (22.09 s). Corrected exact-script dummy ISCC exits zero; Setup was
never run. Twenty-six raw files are sealed under proof/ryan-inno-final-2026-09-09.
No frozen test changed. The saved identity, marker app path, strict switches,
UTF-8 JSON, reparse leaf checks and failed persistence are now checked before
isolated operations. Real Inno persistence and installed C22/Phase 4 remain
unexecuted. Two receipt workers remain; final committed tree/package still owed.

### 2026-09-09 — Backup authentication repair and next source checkpoint

The backup attempt for 5162fcb stalled in Git Credential Manager and failed
without a confirmed push after its exact owned credential child was stopped.
GitHub CLI's existing account authentication was valid. A process-local
credential-helper override (no saved config or credentials changed) completed
the authorized git push origin cc/living-library. Independent ls-remote shows
022ff43270626f0d469ccc1dc9a027af3ea0227d. No candidate branch/main was pushed.
The complete original helper in iso-c5 also reached /health after committing
all five default style anchors, without the earlier reconciliation error.
Use RYAN-ISOLATION-CHECKPOINT-TREE-BRIEF-2026-09-09.md for this product source
while C22 and Phase 4 instruments finish. Their final integration still needs
its own complete committed tree and rebuilt artifact.

### 2026-09-09 — Second complete checkpoint retains one additional failure

8fc6a40: 2,254 passed, ten failed, three skipped, one xfailed, 183 warnings,
573.49 s. Only S21 excluded. All 62 new cases are included; no earlier case
is missing. The nine earlier failures remain. The additional read-promotion
case receives a different Index from the ordinary getter, although its
focused and integration unions passed. Investigate an earlier route fixture's
direct getter substitution with the named brief before claiming a product
repair or seeking a setup correction. Twelve raw files are sealed in
proof/ryan-integrated-tree-02-2026-09-09. The result remains failed.

### 2026-09-09 — New ordered failure is a substituted test getter

The unchanged discovery-route file followed by the unchanged new read-opening
file reproduces three passes / one failure in 1.25 s. The older test leaves
server._get_index as its fixture lambda, so the new check never calls production
promotion. The two-line proposal captures/binds the real getter for this test;
all 13 assertions are preserved. It is unapplied and the failed observations
stay failed. The exact patch/review and five-file proof are in the named
RYAN-READ-FIXTURE-PROPOSAL-REVIEW report. Continue both receipt workers while
Ryan considers the four-file total of this and the existing mirror proposal.

### 2026-09-09 — replacement package built; third P4 instrument needs correction

Real installer build completed at exact source `8a607c37095cb4f3b66d2aee285cfb710ab5e586`.
Artifact: `build/Uoink-Setup-3.8.0.exe`, 339,059,131 bytes, SHA-256
`d024baf5e27fc15b292c17c3c7a551b41c9564378ce352e81ed25a9908bfd5b1`.
Staged smoke succeeded; dependency inventory verifies 142 packages. Before any
receipt instrumentation, 32,203 compiler-input files and 142 exact Git/source
bindings were captured in `proof/candidate-package-02-2026-09-09/SHA256.json`.
This proves build inputs and package bytes, not extraction, installed behavior
or release acceptance. Old installer remains retained separately. No setup ran.

Third P4 worker f3723b7a independently produces 36 passes / one frozen failure,
24.86 s. Original raw patch and logs/frames are sealed in
`proof/ryan-p4-kit-review-03-2026-09-09/SHA256.json`. Review found false completeness
on a refused valid-preview prompt, cross-session aggregation, a possible close
deadlock after a blocked buffered write, unknown job queries treated as empty,
and canary failure followed by original product launch. Do not integrate it as
complete. The bounded correction brief above preserves existing assertions and
requires positive complete-session and large-write oracles. The refusal's exact
cause must be diagnosed before any product repair or fixture-generator rerun.
Both previously proposed fixture patches remain unapplied pending Ryan's answer.

### 2026-09-09 — bundled original entry works; stricter C22 oracles required

At observation source `175bcef`, packaged product bindings still exactly match
build source `8a607c3` (142 files) and executable SHA-256 d024baf5e27fc15b292c17c3c7a551b41c9564378ce352e81ed25a9908bfd5b1.
Bundled Python 3.11.9 / MCP 1.27.1 / schema 30 ran original uoink_mcp.py with the
explicit private profile and port 18191: 32 tools, five templates, four prompts,
native/fallback card equality, successful consult-library AND reshelve-review.
SQLite logical state and library files were unchanged by reading. The original
server.py then started on the explicit isolated profile/port, reported apply false
and model not loaded, and exited zero after authenticated quit. Both processes
exited zero; automatic guard canary passed, guard removed and _pth unchanged.
Proof: `proof/ryan-bundled-runtime-03-2026-09-09/SHA256.json` (18 files).
This is synthetic staged-runtime evidence only. PID/owned-handle termination was
observed; a persisted creation-time identity and surviving-child/restart receipt
were not part of this narrow probe. Complete C22/P4 kits and actual Inno remain.

Third P4 seed explicitly uses profile/prompt-store at generator line 402, whereas
the original pure preview reader uses profile/library. The narrow packaged probe
uses the real default store and succeeds. The fourth P4 brief already requires
diagnosing/correcting that generator and retaining the original refused request.

Third C22 review found that the protected-state allowance is synthesized from all
observed new rows, so unexpected new work can authorize itself; child cases do
not gate on helper restart during child survival; a module ERROR string can earn
provenance credit; guard restoration checks only the parent and removes changed
bytes; continuation regenerates baselines. Its original input and worker union
41/2 are retained in `proof/ryan-c22-review-03-input-2026-09-09/SHA256.json`.
Independent union continues separately. Follow the final-oracle repair brief;
passing status assertions do not substitute for these missing observations.

### 2026-09-09 — third C22 independent result and branch backup

Independent 7a3c3ae2 kit union completed: 41 passed / two failed, 666.34 s,
native guarded interpreter, label c22-w3. Original Inno-flag and stub-helper
assertions remain failed. Raw log/XML, source protocol, helper commands and
scenario snapshots are sealed in `proof/ryan-c22-review-03-verify-2026-09-09/SHA256.json`.
The recorded source scenario status flags remain subject to the final-oracle
review; the original third input has not been integrated.

Correction workers dispatched: P4 1f64672e-95b7-4608-9fa6-5823b7e8eeda from
12f830e, C22 6a890eee-6163-49bf-836b-cb4b8736b169 from 3347be8. Both follow
their committed briefs, frozen test assertions, no product edits, no Inno or
installed-credit claims. Verify complete worker diffs and suites before integration.

Authorized branch backup fast-forwarded from 022ff43 to
cee17ced3cd461e2a178376cc31c936dd8904cd0; push succeeded and ls-remote confirmed
that exact origin/cc/living-library SHA. Process-local GitHub CLI credentials
avoided the GCM prompt; no global auth config changed, no force or main push.

### 2026-09-09 — active release queue consolidated

The front State table and active Queue now identify the two actual in-flight
corrections, final full-tree/packaged-kit work, portable bundle and Ryan's session.
Earlier queue text remains explicitly historical so a future integrator does not
redispatch rejected or completed runs. Release notes were refreshed at cee17ce;
the final kit-inclusive counts and operator commands still need completion.


## Integrator log — 2026-09-09, P4 operator integration

P4 worker 1f64672e completed. Independent original fourth union: 47 passed /
one failed, 56.03 s. Its raw input and 23 evidence files are sealed in
proof/ryan-p4-kit-review-04-2026-09-09. Default-store generator v2 fixes both
original reshelve prompts; prior invalid-preview measurements stay unchanged.

Astra's operator supplement is reviewed in RYAN-P4-OPERATOR-INTEGRATION-REVIEW-
2026-09-09.md. Worker op-w3: 57 passed / one failed, 26.27 s; three-way checkout
op-c1: 57 passed / one failed, 25.39 s. Ten new operator regressions pass,
including all three previously failing UI cases. The only failure is the frozen
nested settings path; no existing test was changed. Eleven proof files retain
the integrated patch and both-root outcomes. Product source is unchanged.

The actual client now binds the original entry. Visual/client observations remain
pending independent review, synthetic sentinel checks have no actual-client
credit, and a guarded command driver preserves full output and confirmed child-job
cleanup. Modified guard bytes cannot be reported as restored. The provenance wait
has an actual process deadline. Next: bundled operator observation without Setup
or a client; C22 fourth worker remains running. Final full-tree and portable
runbook/bundle remain agent work. Both exact fixture proposals remain unapplied.
