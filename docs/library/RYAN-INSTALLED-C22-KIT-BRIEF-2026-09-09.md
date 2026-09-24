# Build the executable C22 receipt kit

Worker: Grok. Read the owner rulings in
`docs/library/ORCHESTRATION-HANDOFF-2026-09-08.md`, the C22 list in
`docs/library/PHASE3-ACCEPTANCE-7-2026-09-08.md`, and
`docs/library/INSTALL-RECEIPT-RUNBOOK-2026-09-09.md` completely. The runbook's
current stop preflight is a temporary blocker, not the requested finished kit.
Ryan asked for one throwaway Windows-profile session and complete notes.

Implement new receipt tooling under `scripts/install_receipt/`. Do not edit
existing production, tests, fixtures, assertions or final release notes/runbook.
Astra integrates the separate isolation mechanism and assembles the final kit.
That mechanism's declared interface is `--isolated-profile <absolute-root>`
plus `--isolated-port <non-5179-port>` on supported entry points. Do not launch
the current default helper or installer. Treat the installed app path, package
hash, explicit profile and port as required inputs, never auto-discovered defaults.

Build these four bounded pieces and write source early:

1. A fail-closed operator runner and manifest: validate fresh contained roots,
   exact installed/package/input hashes, no ordinary user profile, no 5179,
   no checkout or user-site resolution in the installed child. Record every
   actual command, timestamp, exit, child creation identity and artifact hash.
   Preserve partial output on failure and refuse overwriting a prior receipt.
   Do not invent expected package hashes; accept a manifest Astra seals later.
2. Deterministic local capture fixtures and a full installed-helper launcher.
   Use the original installed `server.py` startup/HTTP/service path; no copied
   server overlay, extracted AST or replacement backend earns installed credit.
   Synthetic acquisition/transcription and narrowly declared failure injections
   may replace external media work. Keep the real scheduler, consent, ledger,
   capture queue/publication, child registration and reconciliation. No network
   except the declared fixture/helper loopback ports; no model/client spawns.
   Guard inherited child startup as well. Use only new files and synthetic data.
3. Executable scenarios for AS-7 C22: empty migration/replay, a clearly versioned
   populated legacy fixture/replay, unrelated one-off capture, manual-first and
   standing-first dedupe/charges, actual whole-helper termination/relaunch,
   actual registered child lifetime, launch interruption and registration
   failure. Pair a stable post-restart state snapshot with a browser observation
   checkpoint. Preserve the real installed upgrade command as an operator step;
   do not mislabel a same-version reinstall as cross-version upgrade.
4. An evidence collector/verdict input with complete table/file snapshots,
   integrity/foreign-key results, protected Phase 2 before/after hashes, explicit
   allowed enqueue changes, and per-scenario pass/fail/unexecuted outcomes.
   Provide exact commands in `docs/library/RYAN-INSTALLED-C22-KIT-WORKER-2026-09-09.md`.
   No claimed installed pass until Ryan actually runs the sealed kit. State any
   scenario the tooling cannot execute; a checklist alone is not completion.

Validate new tooling with meaningful unit/process tests in a new file using
only declared scratch roots/non-5179 ports. You may run non-installed synthetic
instrument checks with the existing isolated integrator guard, labeled as such.
Do not execute Inno or the production default helper. Each retry needs its
repair recorded before rerun. No test assertion changes after a failing run.
Keep logs, complete byte artifacts and failure observations. No screenshots
or process completion may be synthesized. Astra independently verifies and
tests against the integrated isolated mechanism and staged bundled runtime.

No subagents, paid API, model/client process, external fetch, credentials,
diarization, live index, 5179, label application, commits, pushes, main merge
or other-worktree edits. Never set ANTHROPIC_API_KEY. `librarian_apply_enabled`
stays false. Phase 4 actual client/everyday receipt tooling is Astra's separate
scope, so do not spend this run implementing it.
