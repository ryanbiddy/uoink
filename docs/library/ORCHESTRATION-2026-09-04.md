# Orchestration protocol: Fable + Astra (draft v0, 2026-09-04)

Ryan's instruction: "I need Astra and Fable to work together orchestrating now."
This is Fable's draft of how that works. Astra reviews it in run C and proposes changes;
the two positions get reconciled in v1, which Ryan signs.

## Roles

**Fable** (Claude Fable 5.1, the interactive Claude Code session Ryan talks to)
- Session orchestrator and integrator. Owns dispatch, worktree integration, test verification,
  the memory file, Ryan-facing reporting, and the final call when two workers conflict.
- Commits on behalf of workers whose sandbox cannot write the shared gitdir (Codex, Claude
  engine). Nothing reaches `origin/main` without Ryan.

**Astra** (GPT-6 Astra as the Control Room `codex` engine, gpt-6-astra)
- Lead planner and reviewer. Owns per-phase build plans, deep reviews of merged work, council
  synthesis as Control Room lead, and computer-use verification: driving the real helper,
  dashboard and extension end to end once a build exists, and reporting what it saw.
- Writes plans and reviews into `docs/library/`; edits code only when a phase brief assigns it.

**Workers** (Grok, Gemini, Claude Fable in Control Room, Codex/Astra when assigned)
- Build in isolated worktrees from a frozen base, one contract owner per surface.

## The loop, per phase

1. Astra writes the phase plan: scope, contracts, files, gates, which engine owns what.
2. Fable reviews it against `DECISIONS-2026-09-04.md`, the direction doc, and memory; edits or
   pushes back in writing; dispatches the workers.
3. Workers build. Fable commits for the ones that cannot.
4. Astra reviews every worktree diff and runs verification (tests, the live-index copy,
   the app itself where it can).
5. Fable integrates, runs the full suite, updates memory, reports to Ryan.
6. Ryan gates merges to main and any spend beyond subscriptions.

## Rules both orchestrators carry

- D-17 as resolved: server does no LLM reasoning except behind named default-off metered
  flags; agent cognition lives in the calling client.
- Never open the live index for writing. Work against a copy.
- Gemini output is fact-checked before it is trusted (four errors in the 09-03 council round).
- Disagreement: each orchestrator states position and evidence in the phase doc. Ryan breaks
  ties. Until he does, the more conservative option ships.
- Every number in a report was produced, not estimated, or is labeled as an estimate.

## Open questions for Astra

- Should Astra also own the *daily* run (a scheduled review of what changed) or only per-phase?
- Which verification can Astra do that no other worker can (computer use), and what does the
  first such check look like on uoink?
- What does Fable get wrong in this draft?
