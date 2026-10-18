# Installed receipt isolation: product repair brief

Finding from source inspection on `4a35316`; installer built from `e47e4f2`.
No installer or helper was launched for this finding. Runtime acceptance is
not claimed. This is product work, not a request to waive Ryan's no-5179 rule.

## Reproduction and scope

`installer/uoink.iss:447` runs `upgrade_prep.ps1` in `PrepareToInstall`, without
a fresh-install or isolated-profile bypass. `installer/upgrade_prep.ps1:61`
calls `Test-Port5179Bound`, which creates a TCP connection to 127.0.0.1:5179.
The script also has helper-quit and wait-for-port paths. Inno's silent option
skips its postinstall launch but not this preparation hook.

`server.py:147` fixes PORT at 5179. `main` first probes the existing server
and later binds that port; the stock shortcut and HKCU Run value call this
path. `run_cli` has no supported port argument. Consequently the current
package has no documented installed start/upgrade procedure that satisfies
Ryan's explicit no-5179 requirement. Changing Windows account does not
isolate this host's TCP namespace.

## Required repair and review

Provide a supported, explicit isolated installation and runtime procedure
that stays within a named disposable profile and declared non-5179 loopback
endpoint. Inspect installation preparation, launch, existing-helper discovery,
shutdown, upgrade/replay, registration and relaunch together. Scope any process
termination by the owned executable/data root and creation identity. Never
stop a resident helper just because it answers a shared port.

Preserve ordinary production behavior and ownership protection. Do not patch
installer bytes, use process interception to hide forbidden contacts, weaken
the test assertions, or substitute a source overlay for actual installation.
Keep model downloads/inference and paid/client spawns out of C22 scenarios.
Provide a complete operator kit for the AS-7 capture-order, real-process restart,
launch-interruption and registration-failure scenarios, with exact fixture
inputs and instrumentation. The historical S21 overlay and extracted backend
process probe are not this installed-path kit.

Before any observation, review the implementation diff and define the named
verification suites. Any new execution must use a documented repair and a fresh
receipt. Existing fixtures cannot receive further corrections under Ryan's
ruling. Verify worker and checkout roots before integration if dispatched through
Control Room. After source changes, rerun the applicable full tree, rebuild and
seal a new installer, and replace the runbook's stop preflight with the actual
reviewed commands and new hashes. Keep the current installer/receipts intact.

Until then, the runbook's current executable step stops before installation;
all C22/installed Phase 4 cases remain unexecuted. The no-live-index, no-5179,
no-paid-API and no-main-merge rules remain unchanged.
