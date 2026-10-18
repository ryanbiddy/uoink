# Implement a supported isolated installed profile

Worker: Grok. Read the owner rulings in
`docs/library/ORCHESTRATION-HANDOFF-2026-09-08.md` and
`docs/library/INSTALL-ISOLATION-REPAIR-BRIEF-2026-09-09.md` first. Ryan asked
to continue until release readiness. Current Inno preparation and the normal
helper use port 5179, which this receipt program may never contact. Implement
the product path needed for a disposable installed receipt; do not run Inno
or the resident helper. Astra supplies the final scenario kit afterward.

Resolve these five connected boundaries with a small explicit interface:

1. A supported isolated profile/root and declared non-5179 loopback port must
   be validated before any product import can open default data. Reject missing,
   relative, normal-data, root-volume, unsafe or conflicting profile paths and
   invalid ports. Default production behavior remains unchanged when isolation
   is not requested. Prefer one dependency-free configuration module reused by
   entry points; do not scatter monkeypatches or environment guesses.
2. An explicit Inno isolated-install mode must avoid the normal upgrade-prep
   port probe, legacy helper stop and normal-profile migration. It must not
   create a login autorun or ordinary shortcut/finish launch that later reaches
   5179. Record that mode durably for upgrade/uninstall decisions. Refuse unsafe
   reuse rather than silently treating an ordinary installation as isolated.
   Normal install/upgrade ownership protection must not be weakened.
3. The installed HTTP helper, original stdio entry, dashboard, splash/health
   probes and runtime-lease address must agree on the declared profile/port.
   Startup/stop/relaunch must use those bindings. Inspect data, output, tokens,
   PID/creation identity, legacy migration, suite registry and subprocess
   inheritance together; no path should fall back to the user's real library.
4. Stop/upgrade behavior may act only on the owned installed executable,
   profile and process creation identity. Never kill a process solely by PID,
   name, a shared-port response or a textual directory prefix. Isolation mode
   may refuse a running upgrade and require the explicit safe stop command.
   Do not run stock stop/uninstall scripts during development.
5. Ship the configuration/entry files through the existing build staging and
   Inno source list. Document exact setup/start/stdio/stop arguments and their
   validation errors for Astra's runbook. Do not edit the final runbook or
   claim installed evidence; this worker only repairs the supported mechanism.

Source inspection found fixed endpoints in `server.py`, `uoink_dashboard.py`,
`uoink_splash.py` and `suite_service.py`; `_platform.py` currently resolves
normal data/Desktop paths. `server.main` performs legacy migration and starts
background services. Audit imports before startup, not only main's port bind.
Keep isolated fixture jobs local, standing capture explicitly consented and
`librarian_apply_enabled=false`. Never enable API credits or import ordinary
credentials. No new fetch scope, diarization or speaker attribution claim.

Do not edit any existing tests, fixtures, assertions, skips or parameters.
Add meaningful isolated unit/process regressions in a new test file, covering
fail-closed validation before forbidden access, valid startup/address/profile
bindings, inherited GUI/stdio behavior, occupied-port refusal, and owned stop
identity. No real Inno execution, live index or port-5179 probe, including a
negative probe. Use only a declared disposable root and another loopback port.

Verify the new tests and complete existing files:
`tests/test_installer_files_complete.py`,
`tests/test_installer_dependency_lock.py`,
`tests/test_installer_download_accuracy.py`,
`tests/test_u11_installer_overhaul.py`,
`tests/test_splash_hotfix.py`, `tests/test_c01_mcp_stdio.py`,
`tests/test_s6_suite_integration.py`,
`tests/test_migration_step0_characterization.py`,
`tests/test_source_subscriptions_migration.py`, and the existing startup/path
tests you identify before running. Use the isolated runner/guard retained under
`docs/library/proof/ryan-corrected-01-2026-09-09`. Preserve all failures and
document each repair before a rerun. Syntax/compile validation is allowed;
the integrator owns the full build after verified integration.

No subagents, paid API, external sources, commits, pushes, main merge, other
worktree edits or installations. Never set ANTHROPIC_API_KEY. Write source or
a concrete design/blocker report early. Deliver
`docs/library/RYAN-INSTALL-ISOLATION-WORKER-2026-09-09.md`, exact commands and
results, and the complete bounded diff. Astra independently verifies and
integrates before rebuilding and authoring the complete installed scenario kit.
