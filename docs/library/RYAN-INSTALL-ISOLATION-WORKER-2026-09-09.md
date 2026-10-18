# Install isolation worker report (Grok)

Status: **source complete in this worktree**. Integrator owns independent
verification, rebuild and the final installed operator kit. This worker did
not run Inno, did not contact port 5179 (including negative probes), did not
open the live index, did not set `ANTHROPIC_API_KEY`, did not enable
`librarian_apply_enabled`, and did not commit or push.

## What shipped

One stdlib configuration module, `uoink_install_isolation.py`, is the
explicit interface. HTTP helper, stdio, dashboard, splash, suite lease,
legacy migration and Inno isolated mode reuse it. Default production
behavior is unchanged when isolation is not requested: `127.0.0.1:5179`
and `_platform.user_data_dir()`.

### 1. Isolated profile and non-5179 port (fail closed)

Isolation is requested only by `--isolated-profile` + `--isolated-port`,
the matching `UOINK_ISOLATED_*` inheritance variables, or
`--isolated-from-install-dir` reading `{app}\isolated-install.json`.
Partial or conflicting requests exit 2 before product code can open
default data. Rejected: missing, relative, normal `%LOCALAPPDATA%\Uoink`,
legacy Yoink, Desktop corpus, root volume, protected system paths, and
port 5179.

### 2. Inno isolated-install mode

`/ISOLATED=1 /PROFILE=<abs> /PORT=<non-5179> /DIR=<abs-app>` skips
`upgrade_prep.ps1` (no 5179 probe, no helper-by-prefix stop), skips the
ordinary splash-sentinel delete, skips HKCU Run, skips the finish-page
helper launch, skips ordinary shortcuts, and writes
`{app}\isolated-install.json`. Isolated shortcuts pass the declared
profile and port. Ordinary reuse of `{localappdata}\Uoink` or an existing
`server.py` without the marker is refused. A recorded
`runtime-identity.json` refuses upgrade until the isolated stop command
runs. Normal install/upgrade ownership is unchanged when `/ISOLATED` is
absent.

### 3. Runtime bindings

`server.py` applies isolation before `DATA_ROOT` / token / log / output.
Stdio (`uoink_mcp.py`), dashboard and splash apply it before opening
URLs or sentinels. Suite leases and manifests use the declared port and
write under `<profile>\suite-services.d`, not the user's RyanSuite
directory. Isolated `/file` roots are only the declared profile. Legacy
Yoink migration is `skipped_isolated_install`. Occupied isolated ports
fail closed with `isolated-port-occupied` and exclusive bind
(`SO_EXCLUSIVEADDRUSE` on Windows); they never fall back to 5179.
Splash/dashboard/stdio children inherit `--isolated-profile` /
`--isolated-port` and the matching environment.

### 4. Owned stop identity

Stop is `python uoink_install_isolation.py --isolated-stop ...`. It
reads `<profile>\runtime-identity.json` and terminates only when pid,
executable image and creation time match that record. It never kills by
PID alone, process name, a shared-port probe, or a textual directory
prefix. Isolation upgrade check returns
`isolated-running-requires-stop` while the owned helper is alive.
Stock `stop-server.ps1` / uninstall scripts were not run.

### 5. Staging

`uoink_install_isolation.py` is in `build.ps1` existence check, Copy-Item
staging, py_compile, and Inno `[Files]`.

## Operator commands (for Astra's runbook; not executed here)

Create the disposable profile directory first. Never use the ordinary
`%LOCALAPPDATA%\Uoink` path or port 5179.

Isolated setup (example shape only; do not run the current sealed
package until Astra rebuilds):

```text
Uoink-Setup-<version>.exe /VERYSILENT /NORESTART /SUPPRESSMSGBOXES ^
  /DIR="<absolute app dir>" /ISOLATED=1 ^
  /PROFILE="<absolute existing profile dir>" /PORT=<non-5179>
```

Start:

```text
"<app>\python\pythonw.exe" "<app>\server.py" --isolated-profile "<profile>" --isolated-port <port>
```

Stdio:

```text
"<app>\python\python.exe" "<app>\uoink_mcp.py" --isolated-profile "<profile>" --isolated-port <port>
```

Stop:

```text
"<app>\python\python.exe" "<app>\uoink_install_isolation.py" --isolated-stop --isolated-from-install-dir "<app>"
```

Equivalent explicit stop:

```text
python uoink_install_isolation.py --isolated-stop --isolated-profile "<profile>" --isolated-port <port>
```

Upgrade preflight (must be stopped first):

```text
python uoink_install_isolation.py --isolated-upgrade-check --isolated-from-install-dir "<app>" --isolated-profile "<profile>" --isolated-port <port>
```

### Validation errors (stderr `uoink isolated install: <code>: ...`, exit 2 unless noted)

| Code | When |
|---|---|
| `isolated-profile-missing` | Isolation requested without a profile |
| `isolated-profile-relative` | Profile is not absolute |
| `isolated-profile-not-found` | Profile directory does not exist |
| `isolated-profile-not-directory` | Profile path is not a directory |
| `isolated-profile-normal-data` | Profile is/contains ordinary Uoink data or Desktop corpus |
| `isolated-profile-legacy-data` | Profile collides with Yoink data |
| `isolated-profile-root-volume` | Profile is a drive/volume root |
| `isolated-profile-unsafe` | Profile is a protected system path |
| `isolated-profile-conflict` | CLI/env/marker disagree, or profile equals app dir |
| `isolated-port-missing` | Isolation requested without a port |
| `isolated-port-invalid` | Port is not an integer 1-65535 |
| `isolated-port-forbidden` | Port is 5179 |
| `isolated-install-ordinary-reuse` | Isolated mode pointed at the ordinary install or an unmarked `server.py` |
| `isolated-install-marker-mismatch` | Existing `isolated-install.json` disagrees |
| `isolated-install-marker-missing` | `--isolated-from-install-dir` has no marker |
| `isolated-port-occupied` | Declared port cannot be bound (helper exit 1) |
| `isolated-running-requires-stop` | Upgrade check while owned helper is alive (exit 3) |
| `isolated-stop-identity-missing` | Stop with no identity is a no-op success |
| `isolated-stop-identity-mismatch` | Identity does not match the live process (exit 4) |

## Tests

New file only: `tests/test_install_isolation.py` (27 cases). No existing
test, fixture, assertion, skip or parameter was edited.

Covered: fail-closed validation before canary/default access; valid
startup on a disposable profile and non-5179 loopback port; GUI/stdio
inheritance; exclusive occupied-port refusal; owned stop that refuses a
same-executable decoy; installer source checks; suite lease address.

## Commands and results

Worktree:

`C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\fd647a72-24b\grok`

Syntax:

```text
python -B -m py_compile uoink_install_isolation.py server.py uoink_mcp.py uoink_dashboard.py uoink_splash.py suite_service.py migrate_install.py tests/test_install_isolation.py
```

Exit 0.

### Preserved failures (before repair)

Unguarded process run of four helper tests, 141.35 s, **4 failed**:

- `test_isolated_startup_binds_profile_and_port` — helper hung; stdout PIPE filled by logging.
- `test_occupied_isolated_port_is_refused` — same hang, then Windows `SO_REUSEADDR` allowed a second bind.
- `test_upgrade_check_refuses_a_live_owned_helper` — helper never answered `/health` (pipe hang).
- `test_stdio_inherits_isolated_profile` — child ImportError for the MCP SDK because `APPDATA` was redirected to the canary.

Those results stay failed. They are not the guarded suite.

### Repairs before rerun

1. Helper process tests write stdout to a log file instead of an unread PIPE.
2. Isolated `_YoinkHTTPServer.server_bind` sets `allow_reuse_address=False` and `SO_EXCLUSIVEADDRUSE`; the occupancy holder does the same.
3. Child env no longer overrides `APPDATA`; user site-packages is prepended onto `PYTHONPATH`; stdio skip checks `FastMCP`/`anyio`.

Rerun of `tests/test_install_isolation.py` after those repairs: **27 passed**, 8.13 s.

### Named guarded suite (authoritative for this worker)

```text
python -B docs/library/proof/ryan-corrected-01-2026-09-09/integrator_verify.py --root <worktree> --label iso-g1 tests/test_install_isolation.py tests/test_installer_files_complete.py tests/test_installer_dependency_lock.py tests/test_installer_download_accuracy.py tests/test_u11_installer_overhaul.py tests/test_splash_hotfix.py tests/test_c01_mcp_stdio.py tests/test_s6_suite_integration.py tests/test_migration_step0_characterization.py tests/test_source_subscriptions_migration.py tests/test_mac_layout_prep.py tests/test_u12_first_run_polish.py
```

`ANTHROPIC_API_KEY` removed. Guard forbids live `%LOCALAPPDATA%\Uoink\index.db` and port 5179. Exit **0**.

**92 passed, 1 skipped, 5 warnings, 19.43 s.** The skip is the existing S6 symlink-privilege case (`WinError 1314`), not a new failure. Pytest command, XML and log: worktree `_scratch/iso-g1/` (`tests.log`, `tests.xml`, `results.json`).

Startup/path companions identified and included: `tests/test_mac_layout_prep.py`, `tests/test_u12_first_run_polish.py`.

## Bounded diff

Tracked edits (`git diff --stat`):

```text
 build.ps1           |   4 +-
 installer/uoink.iss | 255 ++++++++++++++++++++++++++++++++++++++++++++++++++--
 migrate_install.py  |  13 +++
 server.py           | 105 +++++++++++++++---
 suite_service.py    |  42 ++++++--
 uoink_dashboard.py  |  19 +++-
 uoink_mcp.py        |   3 +
 uoink_splash.py     |  51 ++++++---
 8 files changed, 440 insertions(+), 52 deletions(-)
```

Untracked (required deliverables):

- `uoink_install_isolation.py`
- `tests/test_install_isolation.py`
- `docs/library/RYAN-INSTALL-ISOLATION-WORKER-2026-09-09.md`

`_platform.py` and every existing test file are unchanged. Full patch is the worktree working tree; workers do not commit.

## Not done here (integrator / Astra)

- Independent checkout verification of this diff
- Full tree
- Installer rebuild/reseal
- Editing `INSTALL-RECEIPT-RUNBOOK-2026-09-09.md`
- Any installed receipt, C22, or live helper observation
