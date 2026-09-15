# Installer isolation review and repair — 2026-09-09

The first isolation worker `fd647a72` is complete but not accepted. Astra
will preserve its raw patch and independently run its named suite, then
probe these concrete boundaries in a new review file. No existing tests
may be edited, including the worker's original 27 cases after they are frozen.

1. `_parse_isolation_inputs` ignores a trailing `--isolated-profile`, port
   or marker flag with no value, making the request look absent. Reject any
   malformed or contradictory isolation argument before product imports.
2. Ownership accepts a missing creation time, an unavailable creation lookup,
   an empty expected executable, and creation times within two seconds. The
   Windows terminating handle is opened after earlier checks and is not itself
   checked for creation identity. Require the complete exact process identity
   on the same open handle used for termination; uncertain identity must never
   authorize a kill. Wait for confirmed process exit before removing identity.
   Retain conservative stale-record handling and never act on another process.
3. Inno's `IsolatedInstall` only reads a setup command-line flag. An ordinary
   uninstaller invocation can therefore run `stop-server.bat` for an isolated
   install. Persist and resolve uninstall mode before any stop action; missing
   or damaged isolated metadata must refuse safely. Normal setup against an
   isolated target must also refuse before ordinary preparation.
4. `InitializeSetup` resolves `{app}` before the wizard directory is ready.
   Validate explicit arguments early, and validate the final chosen directory
   at the proper pre-install boundary. Reject normalized aliases, nested normal
   or legacy data, system/root paths and conflicting profile/app paths. Match
   marker fields exactly, not with substring searches. A marker write failure
   cannot be a successful isolated install. Isolated installation must have
   distinct uninstall registration and shortcut names, and must not let Inno's
   automatic application-closing mechanism stop a process outside the explicit
   ownership check. Normal installation behavior must remain protected.

The evidence probes must only inspect their own process identity and resolve
configuration strings. No default helper startup, live data, 5179 connection,
real Inno execution or actual termination is needed to show these defects.
The complete original 92-pass/one-skip worker claim remains a separate result.

A repair run must use the retained first-worker patch as input and preserve
its failures. Keep the interface agreed with both receipt-kit workers:
`--isolated-profile`, `--isolated-port`, `--isolated-from-install-dir`,
`--isolated-stop`, `--isolated-upgrade-check`, `isolated-install.json` and
`runtime-identity.json`. Add the review tests unchanged and new meaningful
regressions for repaired behavior. Compile the Inno script without executing
Setup; use explicit scratch output and the existing staged source if needed.
No installed pass is claimed from source checks or compilation.

Run the review file and the complete suite from
`RYAN-INSTALL-ISOLATION-IMPLEMENTATION-2026-09-09.md`, including the two
startup/path companions named in the first worker report. Record exact
commands/counts, any repair before a rerun, and all unexecuted boundaries.
Astra then independently verifies both roots before integration and the full
package build. No subagents, paid API, API keys, existing-test edits, live
index, 5179, new fetch, model/client runs, main merge, commit or push.

## Input and observed results

Apply `docs/library/proof/ryan-install-review-2026-09-09/original.patch`
in the new worker worktree, preserving current SDK and Phase 6 source.
Copy the sealed `test_install_isolation_integrator_review.py` unchanged into
`tests/`. The original patch and 18-file proof seal are committed inputs.

Astra's own-process/configuration probes: **seven failed**, 0.23 seconds.
All three missing-value flags and all four incomplete/different identity
checks reproduced the defects without opening data, connecting or killing.

The independent original named suite through the private venv is **90 passed,
two failed, one skipped**, 48.85 seconds. Its Windows venv launcher gives
`Popen.pid` for the redirector while `server.py` records the real child PID;
the startup assertion differs (69748 / 42660). The upgrade check also returned
0 while the helper was alive. Investigate real executable identity versus
`sys.executable` under the venv: do not falsify PID or relax assertions.
The guarded original worker used `C:\Python314\python.exe` directly, with
92 passes / one skip. For independent process checks use that same direct
runtime with the retained guard and document the invocation difference; keep
the failed private-venv observation. Do not edit those existing test fixtures.
A metadata-only process inventory after cleanup found no helper matching the
exact `fd647a72` / `iso-wi1` launch profiles.

The failed full-helper startup logs also contain `cannot start a write
transaction while another transaction is active` during standing-capture
startup reconciliation and the first scheduler tick on an empty synthetic
profile. Report this concrete startup finding; coordinate its repair through
Astra rather than disabling background services or hiding the exception.
