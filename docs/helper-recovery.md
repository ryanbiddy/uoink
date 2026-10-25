# Helper recovery

Open Uoink to start it again after Quit or a crash loop. Run `uoink doctor`
to read the last exit and recovery state, including when the helper is offline.
The dashboard health panel and the MCP `get_job_status` result include the same
`helper_recovery` block. The native dashboard can read it while disconnected;
a browser tab shows reconnect instructions when the helper cannot answer.

## Restart policy

The per-user supervisor starts the helper, then requires two consecutive
`/health` responses with the child's PID and a fresh run identifier. Startup
has a 120 second deadline. Responses from an old helper or another listener
cannot satisfy readiness. Once ready, a slow capture or health request does
not cause a restart. Only process exit triggers recovery.

A nonzero exit, failed process launch or startup timeout allows up to three
restarts in a rolling ten minute window. Delays are 5, 15 and 45 seconds.
The next failure stops recovery, saves the cause and shows an OS notification
from the supervisor. A bind failure or an already running helper stops after
one launch, without retries or a crash-loop notification. The state explains
the port conflict and how to use or close the other helper or app. Other
failures direct the user to doctor and the logs.

Exit zero stops recovery. Tray Quit, dashboard Quit and the installed Stop
shortcut also save `helper-stop.json` before stopping the helper. That marker
blocks retries in the same login, including during backoff. A new login or
manual launch clears it and starts a new retry budget. Windows uses the logon
token's AuthenticationId; macOS uses the GUI audit session and boot time.

The supervisor holds an OS file lock for its lifetime. Simultaneous task and
shortcut launches therefore cannot start two supervised helpers in one profile.

## Windows startup and upgrades

`scripts/install-watchdog.ps1` registers `Uoink Helper-<user SID>`, with an
interactive, limited principal and a trigger for that user's login. The task
runs the bundled Python and `uoink_supervisor.py --startup`. It has no time
limit, continues on battery, and ignores duplicate task starts. Python owns
the retry budget; Task Scheduler has no separate retry loop.

Registration installs an enabled task before removing the owned legacy
`Uoink` Run value. If removal fails, it restores that value or the previous
task. If setup dies between those operations, startup remains available.
Legacy `server.py` launches in this build also enter the supervisor lock,
so overlapping startup entries cannot start two helpers. An owned task from
the older watchdog script is disabled and removed after registration.
Foreign startup definitions are retained. First-run data migration uses the
registrar's read-only ownership check and does not recreate a Run value when
an owned task exists, including a disabled task.

The installer registers on install and upgrade after the existing files-only
verification. Upgrade prep writes a stop request before the existing graceful
stop and file replacement. Setup stops if preparation fails or the helper's
port remains occupied. Uninstall checks startup ownership without changes
before confirmation, then unregisters at the confirmed uninstall step. It
aborts before deleting files if unregistering fails. Disabling login startup
in settings disables the task without interrupting a capture. Isolated installs do not register
tasks or change ordinary startup.

## State and logs

The state and stop files use the Uoink user data folder. An explicit
`UOINK_ISOLATED_PROFILE` selects that profile instead. Writes replace the file
atomically; the supervisor never imports the server or opens the library.
`helper-stop.json` contains a UTC `requested_at` timestamp and a short `reason`.

`helper-recovery.json` schema version 1:

| Field | Value |
| --- | --- |
| `schema_version` | `1` |
| `status` | `starting`, `running`, `backoff`, `stopped`, `crash_loop`, or `supervisor_error` |
| `last_exit_code` | Integer exit code, or null if no child could start |
| `restart_count` | Retries admitted in the current window |
| `last_start_at`, `last_stop_at`, `ready_at` | UTC ISO timestamps or null |
| `reason`, `action` | Short explanation and recovery instruction |
| `restart_times` | Retry timestamps used to enforce the rolling budget |
| `session` | OS login identity, used only locally |
| `supervisor_pid`, `helper_pid` | Diagnostic process IDs, never authority to kill a process |

Public health, MCP and dashboard status omit the retry timestamps, session
identity and process IDs from this block. Missing state reports
`available: false`; unreadable state includes a recovery instruction.

`helper-output.log` captures stdout and stderr in 1 MiB files with three
backups. The existing `server.log` keeps its 5 MiB limit and three backups.

## macOS source contract

The LaunchAgent invokes the same supervisor. It uses
`KeepAlive: {SuccessfulExit: false}` and `ThrottleInterval: 30`. Quit and
crash-loop exhaustion return zero, so launchd does not relaunch them.
The native launcher retains the CLI entry for commands such as doctor.
Supervisor identity is recorded separately from helper identity for owned
LaunchAgent removal. Uninstall saves a stop intent before stopping a manually
launched helper. Helper output goes through the same rotating logger.

This change does not qualify a macOS release. Native launchd, login-session
identification, notifications, bundle signing and process cleanup still need
verification on a Mac. Windows task registration, upgrade migration and
uninstall still need a real disposable install. Automated tests use fake
helpers and mocked task, registry and launchctl calls.
