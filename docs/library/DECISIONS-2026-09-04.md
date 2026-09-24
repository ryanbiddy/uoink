# Living Library: Ryan's decisions (2026-09-04)

Ryan: "go with defaults" (morning of 2026-09-04), then "dispatch". These are the
nine decisions from THE-LIVING-LIBRARY-2026-09-04.md §10, resolved with the
orchestrator's recommended defaults. Any of them can be reversed by Ryan; until
then they are the contract every engine builds against.

| # | Decision | Resolved |
|---|----------|----------|
| 1 | Wedge | **Recurring-source follower** (the Morgan case): people who follow 20-100 recurring long-form audio/video sources and need evidence from them. |
| 2 | GUI-only user | **Pure client-run (option iii).** The Librarian runs only when a subscribed client runs (Claude Code routine, Hermes cron, Gemini scheduled action, Codex). Revisit a local small-model daemon after Phase 1 is measured. |
| 3 | D-17 wording | **Adopt the re-stated version:** "the server performs no LLM reasoning on the user's behalf except through named, default-off, metered feature flags; all agent cognition happens in the calling client." **Entity extraction gets a named default-off flag** like the other two background jobs; the `usage` field gets read. |
| 4 | yt-dlp posture | **Status quo capture** from the home residential IP, low rate. Detection (RSS) and capture stay separable. |
| 5 | Watcher consent | **Per-source opt-in, default off.** Back-catalog cap **25 items** per source; daily ingest cap **10 per source**. Placeholders; tune after Phase 3 measurement. |
| 6 | Suite removals | **Confirmed.** Writing Studio / scripts / critique / Voice DNA leave uoink for Writer (freeze growth now); zing = sibling consumer; hub dormant, may not spend; For-You demoted, Library is home. |
| 7 | Encrypted sync | **Out of scope this cycle.** Remains the only candidate paid line ($12-15/mo). |
| 8 | Priority | **Clip index (Phase 1) + Phase 0 repairs ahead of the P1 integration queue** (49 unmerged drafts). |
| 9 | Twitch / X | **Twitch notify-only. X watching deferred** until a compliant path exists. |

## State at dispatch

- Branch `cc/living-library` in `E:\AI\projects\uoink\checkouts\Yoink-library`, base `88279ca` (3.8.0 release-build line, 7 commits ahead of `origin/main`).
- Commit `3e06c65`: Phase 1 draft (migration 0024, clips.py, search_clips, get_evidence_card, bm25 weights, recall hook, Librarian dry-run harness).
- Proof on a copy of the live index (548 items, 2026-09-04 07:58 snapshot): 134,500 transcript cues -> 3,216 clips, 212/212 transcript-bearing items covered, 2.2 s rebuild, sub-millisecond queries.
- Known red: three tests pin the registry at 65 tools / schema 23 / docs count 65 (now 67 / 24 / 67). Assigned to Codex.
- Live index untouched. Live count is now 551 items (537 at council time).

## Dispatch (Control Room, work mode, parallel)

Run A: codex + grok + gemini + claude, shared brief `docs/library/DISPATCH-2026-09-04.md` (in the repo, so it is inside every worktree).
Run B: codex only, Phase 0 repairs, brief `docs/library/PHASE0-BRIEF-2026-09-04.md`.
Orchestrator (Fable, this session) integrates: reviews every worktree diff before anything merges; nothing merges to `origin/main` without Ryan.
