# Inno process and path boundary repair worker (Grok)

Worker: grok
Worktree: `C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\d0577a56-f15\grok`
Branch: `control-room/d0577a56-f15-grok`
Base HEAD: `b6119e5f4698320a73203c0f1f276d5417b809b0`
(`Library installer: retain second review and require Inno boundary repair`)

Status: **source complete in this worktree**. Integrator/Astra owns independent
root verification, rebuild and any installed pass. This worker did not run
Setup.exe, did not run uninstall, did not contact port 5179 (including negative
probes), did not open the live index, did not set `ANTHROPIC_API_KEY`, did not
enable `librarian_apply_enabled`, did not fetch, did not run a model/client,
and did not commit or push.

No subagents. No existing test, assertion, fixture, skip or parameter edits.
The original 27 isolation cases, 14 isolation-repair cases, seven sealed review
tests, and the rest of the named fourteen-file union are unchanged. Python
ownership (`uoink_install_isolation.py`) was not edited after the archived
patch apply.

## Input applied

- Brief: `docs/library/RYAN-INNO-FINAL-BOUNDARY-REPAIR-BRIEF-2026-09-09.md`
- Patch: `docs/library/proof/ryan-install-review-02-2026-09-09/original.patch`
  SHA256 `2cd24eeedff376026b07a68e110e9df36b2b25f912e32310a190ea54505608db`
  applied with `git apply --3way --whitespace=nowarn`.
- The second isolation patch's 113 worker passes and one existing skip remain
  a separate sealed result under
  `docs/library/proof/ryan-install-review-02-2026-09-09/`. This worker does not
  relabel them.

This report was written before the guarded rerun and is completed with
measured evidence below.

## Inno repairs

### 1. Restart Manager / close-application switches

`CloseApplications=force` stays for ordinary upgrades (frozen static check).
Skipping `wpPreparing` is no longer treated as a disable: Inno never calls
`ShouldSkipPage` for that page, so the skip was removed. The `wpPreparing`
name remains only in comments. `RegisterExtraCloseApplicationsResources`
still exists and still adds nothing in isolated mode; that callback cannot
disable Restart Manager.

Isolated setup now requires the documented `/NOCLOSEAPPLICATIONS
/NORESTARTAPPLICATIONS` switches in `InitializeSetup` and again in
`PrepareToInstall`. Any `/CLOSEAPPLICATIONS`, `/FORCECLOSEAPPLICATIONS` or
`/RESTARTAPPLICATIONS` token, in any order, is refused
(`isolated-close-applications-forbidden`). Missing negatives are refused
(`isolated-close-applications-required`). Official Setup switch precedence
is that the positive close/restart switches override the negatives, so
contradictory combinations cannot be accepted.

`/ISOLATED`, `/PROFILE` or `/PORT` without `/ISOLATED=1`, a non-`1`
`/ISOLATED` value, or a duplicate `/ISOLATED` refuse with
`isolated-argument-invalid` and do not fall through to ordinary mode.

Ordinary setup with none of those isolated parameters is unchanged.

### 2. Uninstall evidence, owned stop, persistence

`InitializeUninstall` returns true only for ordinary uninstalls that have
neither persisted `Isolated=1` nor an `isolated-install.json` marker.

If either isolated signal is present it never falls back to
`stop-server.bat`. It reads `GetPreviousData` for `Isolated`, `Profile`,
`Port` and `AppDir` (GetPreviousData does work during uninstall via
UninstallExpandedAppId). Missing/incomplete persistence, a disappeared
marker, a malformed marker, a marker/profile mismatch, a failed Exec, or a
nonzero owned stop all return false and abort deletion. The owned stop is
the exact isolated command (`python.exe uoink_install_isolation.py
--isolated-stop --isolated-from-install-dir "{app}"`) and runs inside
`InitializeUninstall` because `[UninstallRun]` nonzero exit does not gate
deletion. The isolated `[UninstallRun]` entry remains for the frozen check
and runs only if InitializeUninstall already succeeded.

`RegisterPreviousData` now stores Isolated/Profile/Port/AppDir.
`WriteIsolatedMarker` writes the JSON, then read-back
`IsolatedMarkerWellFormed` + `IsolatedMarkerExact` must succeed or the
install raises `isolated-install-marker-write-failed`.
`IsolatedPersisted` treats only `GetPreviousData('Isolated') = '1'` as
isolated identity, not mere marker-file presence.

Normal uninstall behavior is unchanged when those isolated signals are
absent.

### 3. Reparse / device / UNC / ambiguous names

`ExpandFileName` / `GetLongPathNameW` / `GetShortName` are not used as
junction resolution. Before marker read, extraction, stop or directory
creation, isolated `/PROFILE` and `/DIR`:

- reject device and UNC paths (`\\`, `\\.\`, `\\?\`)
- reject ambiguous Windows names (reserved DOS devices, trailing
  space/dot components, `*?<>|"`, extra `:`)
- walk every existing ancestor with `GetFileAttributesW` and refuse
  `FILE_ATTRIBUTE_REPARSE_POINT`
- open the nearest existing ancestor with `CreateFileW` +
  `FILE_FLAG_BACKUP_SEMANTICS` and `GetFinalPathNameByHandleW`; if the
  resolved path is UNC/device or hits ordinary/legacy library roots, refuse

`PrepareToInstall` revalidates close switches, declared inputs and these
path checks. `InitializeUninstall` and `WriteIsolatedMarker` refuse reparse
/ device / UNC `{app}` before stop or marker I/O.

### 4. Bounded marker parser

`IsolatedParseMarker` accepts only a top-level object of at most 8192
bytes with exactly the five keys written by `WriteIsolatedMarker`
(`mode`, `profile`, `port`, `host`, `app_dir`). It rejects nested
objects/arrays, unknown keys, duplicate keys, trailing data, trailing
commas, negative integers, leading zeros, and numeric prefix mismatch
(`IntToStr` must equal the scanned digits). `IsolatedJsonExtractString` /
`IsolatedJsonExtractInt` no longer use `Pos` to hunt `"key":`. Ordinary
`server.py` trees without a well-formed isolated marker are still refused
as isolated.

## Safe isolated switches (for Astra → both receipt kits)

Isolated compile-time behavior still uses `CloseApplications=force` in the
script. The supported isolated command line is:

```text
Uoink-Setup-<version>.exe /ISOLATED=1 /DIR="<absolute app dir>" /PROFILE="<absolute existing profile>" /PORT=<loopback, not 5179> /NOCLOSEAPPLICATIONS /NORESTARTAPPLICATIONS
```

Refuse if any of `/CLOSEAPPLICATIONS`, `/FORCECLOSEAPPLICATIONS`,
`/RESTARTAPPLICATIONS` appear, in any order, even together with the
negative switches. Refuse `/ISOLATED` without `=1`, `/PROFILE` or `/PORT`
without `/ISOLATED=1`, missing negatives, or missing profile/port/dir
validation. Ordinary installs must omit `/ISOLATED`, `/PROFILE` and
`/PORT` and keep current close-application behavior.

This command line was not executed here.

## Compile (dummy staging, Setup not executed)

Dummy staging under `_scratch/inno-boundary-iscc/` and
`_scratch/inno-boundary-iscc-2/` (not an installed tree). ISCC was run
against a copy of `installer/uoink.iss`. Setup.exe was never executed.

| Attempt | Result |
|---|---|
| 1 `_scratch/inno-boundary-iscc` | exit 2: `Duplicate identifier 'FILE_ATTRIBUTE_REPARSE_POINT'` (Inno already defines it) |
| 2 `_scratch/inno-boundary-iscc-2` | exit 0 after dropping the local const and using Inno's identifier |

Successful compile:

```text
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" /Q /O"<worktree>\_scratch\inno-boundary-iscc-2\out" /F"Uoink-Setup-compile-only" "<worktree>\_scratch\inno-boundary-iscc-2\uoink.iss"
```

ISCC exit **0**. Artifact
`_scratch/inno-boundary-iscc-2/out/Uoink-Setup-compile-only.exe`
(2,030,104 bytes, 2026-09-09 10:02:08, SHA256
`de9a4409d30be4e0cf04b36232db80c5946ee218a8bc07e925162cb5ee91ac5b`).
Source `installer/uoink.iss` SHA256
`c03f338917ddc21e510ff728e59f09134d6c6bede8bc82d8ddf5c41fb72d5aa7`.
**Not executed.** No installed pass is claimed from source checks or
compilation.

## Isolated verification

Runner: `docs/library/proof/ryan-corrected-01-2026-09-09/integrator_verify.py`
Guard: that directory's `sitecustomize.py` / `ig_paths.py` (copied by the
runner into disposable scratch).
Interpreter: `C:\Python314\python.exe` (3.14.6). `ANTHROPIC_API_KEY` unset.

Fourteen-file union from the isolation repair worker report, plus
`tests/test_inno_final_boundary.py`:

- `tests/test_install_isolation.py`
- `tests/test_install_isolation_repair.py`
- `tests/test_install_isolation_integrator_review.py`
- `tests/test_installer_files_complete.py`
- `tests/test_installer_dependency_lock.py`
- `tests/test_installer_download_accuracy.py`
- `tests/test_u11_installer_overhaul.py`
- `tests/test_splash_hotfix.py`
- `tests/test_c01_mcp_stdio.py`
- `tests/test_s6_suite_integration.py`
- `tests/test_migration_step0_characterization.py`
- `tests/test_source_subscriptions_migration.py`
- `tests/test_mac_layout_prep.py`
- `tests/test_u12_first_run_polish.py`
- `tests/test_inno_final_boundary.py`

```text
C:\Python314\python.exe -B docs/library/proof/ryan-corrected-01-2026-09-09/integrator_verify.py --root C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\d0577a56-f15\grok --label inno-boundary-g1 <selectors above>
```

Exit **0**. **118 passed, 1 skipped, 5 warnings** in 15.81s
(JUnit `tests=119 failures=0 skipped=1 errors=0 time=15.805`).
The skip is the existing S6 symlink-privilege case (`WinError 1314`), not a
new failure. Log/XML: `_scratch/inno-boundary-g1/`.

New regressions live only in `tests/test_inno_final_boundary.py` (5 cases).
The previous 113/1 isolation-repair result is not replaced.

## Unexecuted installed boundaries

Source inspection, dummy ISCC, and Python tests cannot establish these
runtime guarantees. They remain unexecuted:

- Setup.exe / real Inno install or uninstall
- Restart Manager actually honoring `/NOCLOSEAPPLICATIONS /NORESTARTAPPLICATIONS`
- `GetPreviousData` round-trip through a real uninstall registry
- `InitializeUninstall` owned-stop Exec against an installed tree
- Reparse/junction/subst refusal on a live filesystem
- Live `%LOCALAPPDATA%\Uoink\index.db`
- Port 5179, including negative probes
- Paid API, keys, fetch, model/client execution
- Full tree, installer rebuild/reseal, runbook edit
- Installed receipt / C22
- Commit, push, main merge

## Bounded diff

Tracked vs HEAD (`git diff --stat HEAD`):

```text
 build.ps1                                          |    4 +-
 docs/library/RYAN-INSTALL-ISOLATION-REPAIR-WORKER-2026-09-09.md | 4187 +
 docs/library/RYAN-INSTALL-ISOLATION-WORKER-2026-09-09.md       |  221 +
 installer/uoink.iss                                | 1243 +++++-
 migrate_install.py                                 |   13 +
 server.py                                          |  108 +-
 suite_service.py                                   |   42 +-
 tests/test_install_isolation.py                    |  728 ++++
 tests/test_install_isolation_integrator_review.py  |   38 +
 tests/test_install_isolation_repair.py             |  242 ++
 uoink_dashboard.py                                 |   19 +-
 uoink_install_isolation.py                         | 1403 +++++++
 uoink_mcp.py                                       |    3 +
 uoink_splash.py                                    |   51 +-
 14 files changed, 8246 insertions(+), 56 deletions(-)
```

That set is the archived second isolation patch (including `suite_service.py`
from the 3-way apply) plus this worker's Inno repairs on `installer/uoink.iss`.
Unstaged Inno-only delta after the patch: `installer/uoink.iss` 668 insertions,
79 deletions.

Untracked (this worker):

- `tests/test_inno_final_boundary.py`
- `docs/library/RYAN-INNO-FINAL-BOUNDARY-WORKER-2026-09-09.md`

Existing tracked test files: **unchanged** after the patch apply.
`uoink_install_isolation.py`: **unchanged** after the patch apply.
