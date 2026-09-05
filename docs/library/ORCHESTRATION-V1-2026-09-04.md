# Orchestration protocol v1: Fable + Astra (2026-09-04, awaiting Ryan's signature)

Supersedes the v0 draft. Incorporates every amendment in
`ORCHESTRATION-ASTRA-RESPONSE-2026-09-04.md`; Fable accepted all of them.

## Roles

- **Fable** (Claude Fable 5.1, the interactive session): session coordinator and integrator.
  Owns dispatch, migration-number allocation, integration in dependency order, the shared
  status record (memory), and Ryan-facing decisions. May choose compatible implementation
  details within a ratified contract. Commits inspected files for workers whose sandbox
  cannot write the shared gitdir, recording that the worker's own commit failed.
- **Astra** (GPT-6 Astra as the Control Room `codex` engine): planner and independent
  reviewer. Owns the per-phase contract, the retry/undo/recovery review, and the final
  acceptance report on the integrated SHA. When assigned implementation, another worker
  reviews Astra's patch; Astra never certifies its own implementation solely with tests it
  wrote.
- **Workers** (Grok, Gemini, Claude Fable engine, Astra when assigned): build in isolated
  worktrees from a named base SHA, one owner per shared surface per dispatch.
- **Ryan**: main-merge gate, paid-spend gate, and the decider on unresolved acceptance disputes.

## Rules

1. Routine integration choices are Fable's. A reviewer may withhold acceptance only with a
   reproducible failing case. An unresolved substantive dispute goes to Ryan with both
   positions and a concrete candidate.
2. A disputed change stays out of the release candidate. Already accepted work proceeds.
   Neither orchestrator can declare the other's failing evidence resolved by preference.
3. Every worker's output is verified before it is trusted, including both orchestrators.
   Attribution routes a repair; it is not verification.
4. Astra owns the acceptance run on the integrated candidate, including every conflict
   resolution. Worker-base results cannot certify a later tree. Any code or prompt change
   invalidates the affected acceptance result.
5. Measured, estimated, reported-usage, and paid-cost are separate fields. An acceptance
   gate needs observed evidence. Nothing estimated is ever labeled "measured".
6. Reviews never open the user's live index at all. Use the named copy, then a writable
   disposable duplicate when mutation is required; record its hash and source date.
7. D-17 as resolved: the server performs no LLM reasoning except behind named, default-off,
   metered feature flags; agent cognition lives in the calling client.
8. Serialize edits to `server.py`, the tool registry, the dashboard, and migration numbers:
   one owner per dispatch. Fable reserves migration names in the brief.
9. Per-phase reviews, not an unconditional daily model pass. A daily diff review can be
   added later as its own dispatch with its own budget.

## Packets

- **Dispatch packet** (Fable): base SHA, allowed files per worker, contract version, source-
  copy fingerprint, required outputs, gates, and the scope of any model execution.
- **Completion packet** (worker): final diff, commands run, measured results, skipped checks,
  unresolved findings.
- **Integrator receipt** (Fable): candidate SHA and which results were rerun after
  integration.
- **Acceptance report** (Astra): on the candidate SHA, with observed-versus-expected for every
  gate, and a computer-use verification receipt when a build exists.

## First computer-use verification (Astra-owned, not yet run)

Installed-build acceptance in an isolated Windows session with a dedicated browser profile,
per `ORCHESTRATION-ASTRA-RESPONSE-2026-09-04.md`: build and install the candidate, drive the
extension and dashboard, call `search_clips` / `get_evidence_card` from a connected client
and open the returned links, capture a fixture and check deduplication, kill the test helper
and observe watchdog recovery. Never touches the resident helper on `127.0.0.1:5179`.
