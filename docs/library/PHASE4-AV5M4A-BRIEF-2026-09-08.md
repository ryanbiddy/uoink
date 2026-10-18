# AV-5m4a: finish destination authority, temp identity and staging

Engine: Gemini. Start at current `cc/living-library`, containing AV-5m3.
Read `PHASE4-ACCEPTANCE-4-2026-09-08.md`, the AV-5m3 brief and AW-3. Close
the four AW4-01/02/03/04 reproductions in
`tests/library_work_astra/test_phase4_aw4_acceptance.py` without changing tests.

1. Missing binding after prior consent/export must require reconciliation,
   including loss followed by a replacement empty vault. Preserve a durable
   authority witness; never infer fresh initialization from missing state.
   Preserve an explicit user-authorized destination change.
2. Persist binding atomically and durably. Remove the direct `Path.write_text`
   before `_atomic_local`; a failed replacement must leave the prior binding
   intact and return a refusal. Do not silently acknowledge partial persistence.
3. Bind each temp allocation to actual file identity and content. Protect a
   different file at that path even when its bytes are identical. Carry identity
   through pending generations and cleanup. Check at destructive I/O, not merely
   at a distant parent read. Unknown old records have no deletion authority;
   retain unresolved cleanup and never guess by a filename.
4. Add the isolated worker to `build.ps1` validation and every staging path.
   Verify the real source-only staged worker starts, performs a disposable
   mutation and terminates, without reading the source tree at runtime.

The lifecycle region is reserved to AV-5m4b in a parallel worktree: avoid
unnecessary edits to `_VaultIoSession`, job APIs, lock/lease paths and
`_run_cancellable`. A minimal worker protocol extension for file identity is
allowed; document it so Astra can resolve integration. No whole-file rewrite.

Run AW/AW-2/full AW-3/new AW-4, seven AV-5m3 implementation tests, resources,
prompts, briefs, mirror, mirror wiring, Phase 4 stdio and C01. Keep the eight
unchanged parent-interceptor failures visible under Ryan's fixture ruling.
Add focused implementation coverage if needed; never change an existing test,
helper or acceptance assertion. No fixture introspection or production bypass.

Write `docs/library/PHASE4-AV5M4A-GEMINI-2026-09-08.md` early and record exact
commands, counts, files, staged-worker evidence and limits. Gemini's prior
subscription reset was reported around 17:50 PDT; stop on quota without paid
fallback or upgrade. No live index, port 5179, models, API key, paid API,
commits, pushes or subagents. Apply false. Use short disposable roots and
resolved installed dependencies. Astra verifies and integrates.
