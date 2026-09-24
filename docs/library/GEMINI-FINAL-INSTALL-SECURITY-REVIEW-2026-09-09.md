# Gemini Final Install Security Review (Role A) — 2026-09-09

- **Reviewer:** gemini (Role A: Installation Boundary Reviewer)
- **Scope:** Role A only. Independent security and isolation analysis of `installer/uoink.iss`, `uoink_install_isolation.py`, `migrate_install.py`, `server.py` startup/shutdown, and `docs/library/INSTALL-RECEIPT-RUNBOOK-2026-09-09.md`.
- **Target Package:** `Uoink-Setup-3.8.0.exe` (339,059,334 bytes, SHA-256 `a89112bb53425cbd9c5c0c662a2f239cbdde069294af9389c90021ddc2af60fe`), built from commit `67a274d5d0c67f48405c4fa242a1011c2cf671c1`.
- **Host Profile:** Windows 11 Home, non-elevated token (`C:\Users\hello`), no Windows Sandbox.
- **Constraints Maintained:** Read-only security audit. No installer execution, no uninstaller execution, no live index open/stat/hash, no port 5179 probe/connect, no paid API calls, no credential access, no elevation, no existing test/code edits.

---

## Executive Summary and Verdict

Supported isolated Inno mode under `installer/uoink.iss` (source commit `67a274d`) and `uoink_install_isolation.py` enforces rigorous technical boundary containment. When invoked with the mandatory flags (`/ISOLATED=1`, `/DIR="..."`, `/PROFILE="..."`, `/PORT=...`, `/NOCLOSEAPPLICATIONS`, `/NORESTARTAPPLICATIONS`, `/VERYSILENT`, `/NORESTART`, `/SUPPRESSMSGBOXES`), the installer and helper runtime:
1. Prevent data collisions with ordinary Uoink (`%LOCALAPPDATA%\Uoink` and Desktop roots).
2. Avoid port 5179 conflicts via mandatory non-5179 port binding and `SO_EXCLUSIVEADDRUSE`.
3. Disable Restart Manager queries and process terminations across the system.
4. Skip `upgrade_prep.ps1` and ordinary first-run sentinel deletions.
5. Skip legacy Yoink data migration (`migrate_install.py`).
6. Enforce strict Win32 process ownership checks before termination during uninstall.

**Same-Account Disposition:**
While the installer and helper strictly isolate their runtime database, port, and process lifecycle from ordinary Uoink, **observing an Inno installation in the primary Windows account (`C:\Users\hello`) leaves persistent host-level artifacts outside checkout scratch**:
- Writes uninstaller metadata to `HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\{8F3E1B27-9C6A-4E5D-A2B8-7D4C1E0F93A5}_is1`.
- Places four shortcut files into the host user's Start Menu group directory `C:\Users\hello\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Uoink\`.
- Places `Uoink Isolated.lnk` on the host desktop `C:\Users\hello\Desktop` unless `/MERGETASKS=""` or `/TASKS=""` is passed.
- Writes verification logs to `C:\Users\hello\AppData\Local\Temp\uoink-install-verify.log`.

Furthermore, same-account observation is explicitly blocked by two standing policy and runbook gates:
1. `docs/library/INSTALL-RECEIPT-RUNBOOK-2026-09-09.md` line 34 enforces a hard fail-closed stop:
   ```powershell
   if ($env:USERPROFILE -ieq 'C:\Users\hello') { throw 'Use the throwaway Windows account.' }
   ```
2. `docs/library/RYAN-APPROVED-CLOSURE-BRIEF-2026-09-09.md` line 34 establishes the standing rule:
   > *"A run in the ordinary Windows account never gets throwaway-account credit."*

**Final Disposition:** Supported isolated Inno installation mode **cannot and must not be executed under the primary `C:\Users\hello` account for final receipt credit**. A clean, throwaway Windows local user account remains strictly required to capture the full AS-7 installed receipt.

---

## Detailed Boundary and Source Analysis

### 1. Separate AppId and Uninstall Registration
- **Source Lines:** `installer/uoink.iss:35`, `494–502`, `504–510`.
- **Implementation:**
  - `uoink.iss:35` defines `AppId={code:GetInstallAppId}`.
  - `uoink.iss:494–502` defines `GetInstallAppId`:
    ```pascal
    if IsolatedSetupRequested() then
      Result := '{8F3E1B27-9C6A-4E5D-A2B8-7D4C1E0F93A5}'
    else
      Result := '{1CCDA47D-2347-43D1-99F4-BD6E7C231288}';
    ```
  - `uoink.iss:504–510` sets `UninstallDisplayName`: `"Uoink Isolated"` versus `"{#AppName}"`.
- **Security Assessment:**
  - Ordinary Uoink uses AppId `{1CCDA47D-2347-43D1-99F4-BD6E7C231288}`. Isolated mode uses `{8F3E1B27-9C6A-4E5D-A2B8-7D4C1E0F93A5}`.
  - Because Inno registers uninstall metadata under `HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\<AppId>_is1`, the isolated installation will not overwrite or delete the ordinary Uoink uninstall registration.
  - `PrivilegesRequired=lowest` (`uoink.iss:46`) ensures no writes occur to `HKLM`.
  - Severity: Low / Isolated as designed. Host artifact: Registering `{8F3E1B27...}_is1` in `HKCU` is visible in Windows Settings -> Installed Apps.

### 2. Previous-Directory Reuse and Target Directory Containment
- **Source Lines:** `installer/uoink.iss:1100–1128`, `1239–1319`, `1648–1658`; `uoink_install_isolation.py:402–464`, `934–974`.
- **Implementation:**
  - Inno Setup defaults to `UsePreviousAppDir=yes`, which queries `HKCU\...\Uninstall\<AppId>_is1\InstallLocation`. Because the AppId is distinct, it will not inherit ordinary Uoink's `%LOCALAPPDATA%\Uoink`.
  - `IsolatedValidateTargetDir` (`uoink.iss:1239–1319`) explicitly enforces:
    1. Rejection of empty or non-absolute paths (`isolated-install-app-relative`).
    2. Rejection of device or UNC paths (`isolated-path-unsupported`).
    3. Traversal guard `IsolatedGuardPath(AppDir, '/DIR')` checking ancestor reparse points and canonical handle targets (`uoink.iss:1273`).
    4. Rejection of root volumes (`uoink.iss:1277`).
    5. Rejection of protected system directories (`Windows`, `System32`, `Program Files`) (`uoink.iss:1282`).
    6. Rejection of collision with ordinary or legacy libraries via `IsolatedPathHitsLibrary` (`uoink.iss:1287`):
       - `%LOCALAPPDATA%\Uoink`
       - `%LOCALAPPDATA%\Yoink`
       - `%USERPROFILE%\Desktop\Uoink`
       - `%USERPROFILE%\Desktop\Yoink`
    7. Rejection of exact match against `{localappdata}\Uoink` (`uoink.iss:1290–1294`).
    8. Rejection of nesting or identity between `/DIR` and `/PROFILE` (`uoink.iss:1295–1299`).
    9. For existing directories:
       - If `isolated-install.json` exists, it must be well-formed and exactly match `/PROFILE` and `/PORT` (`IsolatedMarkerExact`, lines 1300–1312).
       - If `server.py` exists without `isolated-install.json`, it is refused with `isolated-install-ordinary-reuse` (lines 1313–1317), preventing an ordinary install directory from ever being treated as isolated.
  - In ordinary mode, `IsolatedValidateTargetDir` (`uoink.iss:1246–1255`) also refuses to install into a directory containing `isolated-install.json` (`isolated-install-ordinary-reuse`).
  - `PrepareToInstall` (`uoink.iss:1651–1658`) revalidates the final chosen target path before any file modification.
- **Security Assessment:** Fully contained. Impossible for an isolated setup to select or overwrite the ordinary application or profile paths without raising fatal validation errors.

### 3. Command-Line Switch Parsing and Refusal of Malformed/Contradictory Flags
- **Source Lines:** `installer/uoink.iss:388–451`, `1321–1350`, `1352–1374`; `uoink_install_isolation.py:760–840`.
- **Implementation:**
  - Token parser `IsolatedCmdToken` (`uoink.iss:388–411`) parses `/NAME` and `/NAME=VALUE` without substring matching.
  - `IsolatedSingleSwitch` (`uoink.iss:435–451`) requires that each switch appear exactly once (`IsolatedCountSwitch = 1`) with a non-empty value.
  - `InitializeSetup` (`uoink.iss:1352–1374`):
    - If any isolated parameter is present (`ISOLATED`, `PROFILE`, or `PORT`) via `IsolatedRequestPresent` (`uoink.iss:458–463`), but `/ISOLATED=1` is missing or `/ISOLATED` is repeated, it immediately aborts with `isolated-argument-invalid` (`uoink.iss:1358–1367`). It never falls back to ordinary setup.
    - Revalidates Restart Manager switches via `IsolatedCloseSwitchesValid` (`uoink.iss:1368`).
    - Validates all declared inputs via `IsolatedValidateDeclaredInputs` (`uoink.iss:1370`).
  - In `uoink_install_isolation.py`:
    - `_parse_isolation_inputs` (`lines 760–840`) flags trailing isolation flags without arguments (`isolated-argument-invalid`), flags whose value is another flag, unknown flags starting with `--isolated-`, and duplicate conflicting flags (`isolated-profile-conflict`).
    - Validates port numbers strictly (`lines 842–866`): 1–65535, rejects non-integers, and forbids production port 5179 (`isolated-port-forbidden`).
- **Security Assessment:** Robust fail-closed logic. Omitting required values, duplicating flags, or supplying conflicting arguments results in clean early termination without side effects.

### 4. Marker/Profile Containment, Path Validation, and Reparse Points
- **Source Lines:** `installer/uoink.iss:540–630`, `632–721`, `879–993`, `1042–1090`, `1129–1166`, `1762–1795`; `uoink_install_isolation.py:478–512`, `869–931`.
- **Implementation:**
  - **Reparse Point Defense:** `IsolatedExistingAncestorsHaveReparse` (`uoink.iss:661–685`) invokes `GetFileAttributesW` up the directory tree of `/PROFILE` and `/DIR`. If any existing ancestor possesses `FILE_ATTRIBUTE_REPARSE_POINT` (`$400`), it aborts with `isolated-path-reparse`.
  - **Handle Target Verification:** `IsolatedFinalPath` (`uoink.iss:687–721`) opens the nearest existing ancestor with `CreateFileW` (`FILE_FLAG_BACKUP_SEMANTICS`) and retrieves its final physical path via `GetFinalPathNameByHandleW`. This path is then verified against `IsolatedPathHitsLibrary` (`uoink.iss:1160–1164`) to guarantee no symlink or junction aliases onto `%LOCALAPPDATA%\Uoink`.
  - **Windows Naming Guards:** `IsolatedReservedName` (`uoink.iss:558–579`) and `IsolatedPathIsAmbiguous` (`uoink.iss:581–630`) block DOS reserved device names (`CON`, `PRN`, `AUX`, `NUL`, `COM1-9`, `LPT1-9`), trailing dots or spaces, invalid Win32 characters (`*?<>|"`), and misplaced colons.
  - **Bounded Marker Parsing:** `IsolatedParseMarker` (`uoink.iss:879–993`) enforces a strict JSON grammar on `isolated-install.json`:
    - Maximum buffer size: 8,192 bytes (`ISOLATED_MARKER_MAX`).
    - Rejects nested structures (`{` or `[` values).
    - Requires exactly five keys (`mode`, `profile`, `port`, `host`, `app_dir`).
    - Enforces `mode == "isolated"`, `host == "127.0.0.1"`, port != 5179, and non-empty paths.
    - Rejects duplicate keys, unexpected keys, and invalid numeric representations (e.g. leading zeros).
  - **Atomic Marker Persistence:** `WriteIsolatedMarker` (`uoink.iss:1762–1795`) writes UTF-8 JSON and immediately reads it back with `IsolatedMarkerWellFormed` and `IsolatedMarkerExact`. Any failure raises `isolated-install-marker-write-failed` (`uoink.iss:1804`).
- **Security Assessment:** Comprehensive protection against directory traversal, junction redirection, and marker tampering.

### 5. Restart Manager and Application Close Behavior
- **Source Lines:** `installer/uoink.iss:62–68`, `791–808`, `1471–1475`, `1492–1496`, `1664–1671`.
- **Implementation:**
  - Setup uses `CloseApplications=force` (`uoink.iss:68`) for ordinary upgrades.
  - However, Inno's `wpPreparing` page executes Restart Manager unconditionally (Inno never invokes `ShouldSkipPage` for `wpPreparing`, as documented in `uoink.iss:1471–1475`).
  - To eliminate Restart Manager interference, isolated mode requires command-line switches `/NOCLOSEAPPLICATIONS /NORESTARTAPPLICATIONS`.
  - `IsolatedCloseSwitchesValid` (`uoink.iss:791–808`) enforces:
    - If `/CLOSEAPPLICATIONS`, `/FORCECLOSEAPPLICATIONS`, or `/RESTARTAPPLICATIONS` is passed, abort with `isolated-close-applications-forbidden` (`lines 794–800`).
    - If either `/NOCLOSEAPPLICATIONS` or `/NORESTARTAPPLICATIONS` is missing, abort with `isolated-close-applications-required` (`lines 801–806`).
  - `RegisterExtraCloseApplicationsResources` (`uoink.iss:1492–1496`) exits immediately when `IsolatedInstall()` is true.
  - `PrepareToInstall` (`uoink.iss:1664–1671`) re-verifies these switches.
- **Security Assessment:** Restart Manager is completely suppressed. The installer cannot query, signal, or terminate external processes holding files or sockets.

### 6. Autorun Keys and Shortcut Scoping
- **Source Lines:** `installer/uoink.iss:230–304`, `305–314`, `315–323`.
- **Implementation:**
  - **Autostart Registry Key:**
    ```pascal
    Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
      ValueType: string; ValueName: "Uoink"; \
      ValueData: """{app}\python\pythonw.exe"" ""{app}\server.py"""; \
      Flags: uninsdeletevalue; \
      Check: not IsolatedInstall
    ```
    Guarded with `Check: not IsolatedInstall`. The installer never creates or modifies `HKCU\...\Run\Uoink` in isolated mode.
  - **Finish Page Post-Install Run:**
    ```pascal
    [Run]
    Filename: "{app}\python\pythonw.exe"; ... Flags: postinstall nowait skipifsilent; \
      Check: not IsolatedInstall
    ```
    Guarded with `Check: not IsolatedInstall`. The helper is never automatically launched at setup conclusion.
  - **Start Menu Shortcuts:**
    - Ordinary shortcuts are gated on `Check: not IsolatedInstall`.
    - Isolated shortcuts are gated on `Check: IsolatedInstall`:
      - `{group}\Uoink Isolated.lnk` -> runs `server.py --isolated-profile ... --isolated-port ... --show-dashboard`.
      - `{group}\Stop Uoink Isolated.lnk` -> runs `uoink_install_isolation.py --isolated-stop --isolated-from-install-dir "{app}"`.
      - `{group}\Open Uoink Isolated folder.lnk` -> opens `{app}`.
      - `{group}\Uninstall Uoink Isolated.lnk` -> runs `{uninstallexe}`.
  - **Desktop Shortcut:**
    - `{autodesktop}\Uoink Isolated.lnk` is gated on `Tasks: desktopicon; Check: IsolatedInstall`.
- **Security & Footprint Assessment:**
  - Autostart registry key is untouched.
  - **Host Footprint Leakage:** Inno expands `{group}` to `C:\Users\hello\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Uoink`. If an ordinary Uoink installation is already present, these four shortcuts are added to the user's Start Menu. On Desktop, `Uoink Isolated.lnk` is created unless tasks are suppressed.

### 7. Upgrade Preparation and Verification Safety
- **Source Lines:** `installer/uoink.iss:1662–1682`, `1726–1760`; `installer/verify_install.ps1:1–84`.
- **Implementation:**
  - In ordinary mode, `PrepareToInstall` extracts and runs `upgrade_prep.ps1` to stop port 5179 helpers and delete `%LOCALAPPDATA%\Uoink\.first-run-done`.
  - In isolated mode, `PrepareToInstall` explicitly skips this:
    ```pascal
    if IsolatedInstall() then
    begin
      ...
      Log('PrepareToInstall: isolated mode skips upgrade_prep.ps1 and ordinary sentinel delete');
      Exit;
    end;
    ```
    Ordinary helper processes and splash sentinels are completely untouched.
  - `VerifyInstalledHelper` (`uoink.iss:1726–1760`) runs `verify_install.ps1 -ExpectedVersion "3.8.0"`.
  - In `verify_install.ps1` (`lines 58–61`):
    ```powershell
    if (-not $ProbeHealth) {
        Write-VerifyLog 'files-only install verification OK; live health probe skipped'
        exit 0
    }
    ```
    Because `VerifyInstalledHelper` does not pass `-ProbeHealth`, it performs only a static bundle-presence check and does not probe `127.0.0.1:5179/health` or spawn background processes.
- **Security Assessment:** Zero execution of upgrade preparation scripts and zero network/process probes during verification.

### 8. Uninstaller Scope and Owned Process Termination
- **Source Lines:** `installer/uoink.iss:324–349`, `1477–1490`, `1505–1537`, `1539–1609`; `uoink_install_isolation.py:515–560`, `611–676`, `1156–1189`, `1225–1245`, `1359–1400`.
- **Implementation:**
  - **Uninstall Evidence Persistence:** `RegisterPreviousData` (`uoink.iss:1477–1490`) saves `Isolated=1`, `Profile`, `Port`, and `AppDir` into the Inno uninstall state file.
  - **Uninstall Gate (`InitializeUninstall`):**
    - Checks `GetPreviousData('Isolated') == '1'` and `FileExists(isolated-install.json)`.
    - If neither is isolated, it proceeds with ordinary uninstall.
    - If either signal is isolated, it enforces:
      1. Rejects ancestor reparse points, device, or UNC paths (`uoink.iss:1560–1564`).
      2. Refuses to treat an unpersisted ordinary uninstall as isolated (`uoink.iss:1566–1570`).
      3. Verifies persisted profile, port, and app directory are non-empty and match `{app}` (`uoink.iss:1572–1582`).
      4. Verifies `isolated-install.json` exists, is well-formed, and exactly matches persisted profile and port (`uoink.iss:1584–1600`).
      5. Executes `IsolatedOwnedStop(AppDir)` (`uoink.iss:1602–1606`):
         Runs `python.exe uoink_install_isolation.py --isolated-stop --isolated-from-install-dir "{app}"`.
         If this fails or returns nonzero, `InitializeUninstall` returns `False` and **aborts the entire uninstallation before any files are deleted**.
  - **Owned Process Termination (`uoink_install_isolation.py:stop_owned_helper`):**
    - Reads `<profile>\runtime-identity.json`.
    - Matches port and profile against the declared isolation binding.
    - Opens the target PID with `PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_TERMINATE | SYNCHRONIZE`.
    - Verifies via `_windows_handle_liveness`:
      1. Process exit code is `STILL_ACTIVE` (259).
      2. Process creation timestamp matches `created_ms` from `runtime-identity.json` (`GetProcessTimes`).
      3. Process image name matches `QueryFullProcessImageNameW`.
    - Only after verifying all three on the exact open handle does it invoke `TerminateProcess` (`uoink_install_isolation.py:1389`).
    - Waits up to 15 seconds for process termination.
    - Unlinks `runtime-identity.json` and `server.pid`.
  - **File Removal Scope:** `[UninstallDelete]` (`uoink.iss:340–349`) sweeps only files inside `{app}` (`server.log`, `server.pid`, `isolated-install.json`, and `python\Lib\site-packages`). It never sweeps or deletes the isolated profile folder.
- **Security Assessment:** Uninstaller termination is laser-focused on the profile-owned process handle. It cannot terminate an ordinary Uoink process or an unrelated PID. The uninstaller will never touch user data outside `{app}`.

### 9. Server Startup, Shutdown, and First-Run Migration Interlock
- **Source Lines:** `server.py:57–59`, `151`, `17140–17145`, `17160–17179`, `17188–17199`, `17258–17283`; `migrate_install.py:288–375`.
- **Implementation:**
  - Module import top:
    ```python
    import uoink_install_isolation as _install_isolation
    _install_isolation.apply_from_process()
    ```
    Validates isolation arguments before any subsystem initializes.
  - Loopback binding: `PORT = _install_isolation.listen_port(5179)`.
  - Socket options: `_YoinkHTTPServer.server_bind` (`server.py:17140–17145`) sets:
    ```python
    self.allow_reuse_address = False
    self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    ```
    This prevents port hijacking or collisions on Windows.
  - Port occupied handling: If binding fails, server logs `isolated-port-occupied` and exits with code 1 (`server.py:17195–17199`). It never falls back to 5179.
  - **Migration Interlock:** `server.py:17171–17179`:
    ```python
    if _install_isolation.current_binding() is None:
        try:
            _mig = migrate_install.run_migration(app_dir=HERE)
            log.info("install migration: %s", _mig.get("outcome"))
        except Exception as e:
            log.warning("install migration raised (non-fatal): %s", e)
    else:
        log.info("install migration: skipped_isolated_install")
    ```
    In isolated mode, `migrate_install.run_migration` is completely skipped. No files are copied from `%LOCALAPPDATA%\Yoink`, and no Windows Credential Manager keys are touched.
  - Identity recording: When the helper starts, lines 17266–17283 write `runtime-identity.json` containing the exact PID, executable path, creation timestamp, and cryptographic nonce.
- **Security Assessment:** Airtight separation between isolated server instances and the host's existing library or legacy data.

---

## Existing Test Suite Evidence and Verification

Four dedicated regression test suites verify the boundaries reviewed above:
1. `tests/test_install_isolation.py` (27 test cases):
   - Validates fail-closed behavior for missing profiles, relative profiles, missing directories, normal/legacy profile collisions, root volumes, and protected system directories.
   - Verifies forbidden production port 5179 rejection and invalid port rejection.
   - Verifies ordinary install reuse refusal (`isolated-install-ordinary-reuse`).
   - Verifies isolated helper startup, PID recording, loopback isolation, and clean owned stop.
2. `tests/test_install_isolation_repair.py` (14 test cases):
   - Validates rejection of trailing flags, flags whose value is another flag, unknown flags, and conflicting duplicate flags.
   - Verifies exact process creation timestamp checks (`_pid_liveness`, `write_runtime_identity`, incomplete identity rejection).
   - Verifies handle-bound re-verification before `TerminateProcess` (`_terminate_owned`).
   - Verifies Inno static requirements: `InitializeSetup` not using unready `{app}`, uninstaller mode persistence (`RegisterPreviousData`), exact marker matching, and isolated shortcut names.
3. `tests/test_install_isolation_integrator_review.py` (5 test cases):
   - Read-only probes testing incomplete isolation flags, missing creation identity, creation identity mismatch, and missing executable paths.
4. `tests/test_inno_final_boundary.py` (5 test cases):
   - Validates that isolated mode requires `/NOCLOSEAPPLICATIONS /NORESTARTAPPLICATIONS` and forbids positive close/restart overrides.
   - Validates that missing isolated switches fail closed rather than falling into ordinary mode.
   - Validates that `InitializeUninstall` checks persisted evidence and owned stop before deletion.
   - Validates that reparse points, device paths, and ambiguous paths are rejected before any marker read/write.
   - Validates that the Inno marker parser is bounded (<=8KB) and rejects duplicate or nested keys.

All 51 test cases directly validate the isolation invariants confirmed in this security review.

---

## Same-Account Isolated-Install Disposition

### Assessment Summary
Can supported isolated Inno mode at a fresh app/profile under checkout scratch be observed safely in the same Windows account without touching ordinary Uoink?

| Security Boundary | Status | Evidence & Source Reference |
|---|---|---|
| **Ordinary Uoink Database (`index.db`)** | **Isolated** | Protected by `IsolatedPathHitsLibrary` (`uoink.iss:1100`), `_validate_profile` (`uoink_install_isolation.py:906`), and `DATA_ROOT` redirect. |
| **Port 5179 Conflict** | **Isolated** | Gated by `IsolatedValidatePortValue` (`uoink.iss:1231`), `_validate_port` (`uoink_install_isolation.py:861`), and `SO_EXCLUSIVEADDRUSE` (`server.py:17144`). |
| **Restart Manager / Process Kills** | **Isolated** | Mandatory `/NOCLOSEAPPLICATIONS /NORESTARTAPPLICATIONS` (`uoink.iss:791`); positive close switches forbidden; `RegisterExtraCloseApplicationsResources` disabled. |
| **Legacy Data Migration** | **Isolated** | Gated by `server.py:17171`; `migrate_install.run_migration` is explicitly skipped when `current_binding()` is present. |
| **Autostart Run Key** | **Isolated** | Gated by `[Registry]` `Check: not IsolatedInstall` (`uoink.iss:313`). |
| **Finish Page Process Spawn** | **Isolated** | Gated by `[Run]` `Check: not IsolatedInstall` (`uoink.iss:322`). |
| **Uninstall Process Termination** | **Isolated** | `InitializeUninstall` runs handle-verified `stop_owned_helper` (`uoink_install_isolation.py:1359`); never touches ordinary Uoink. |
| **Host Registry Cleanliness** | **Escapes Scratch** | Inno writes to `HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\{8F3E1B27-9C6A-4E5D-A2B8-7D4C1E0F93A5}_is1`. |
| **Start Menu Cleanliness** | **Escapes Scratch** | Inno writes four `.lnk` files to `C:\Users\hello\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Uoink\`. |
| **Desktop Cleanliness** | **Escapes Scratch** | Inno writes `Uoink Isolated.lnk` to `C:\Users\hello\Desktop\` unless tasks are explicitly suppressed. |
| **Temp Directory Cleanliness** | **Escapes Scratch** | `verify_install.ps1` writes to `C:\Users\hello\AppData\Local\Temp\uoink-install-verify.log`. |
| **Runbook Gate** | **BLOCKED** | `INSTALL-RECEIPT-RUNBOOK-2026-09-09.md:34` explicitly throws if `$env:USERPROFILE -ieq 'C:\Users\hello'`. |
| **Closure Brief Rule** | **BLOCKED** | `RYAN-APPROVED-CLOSURE-BRIEF-2026-09-09.md:34` denies throwaway-account credit to any primary account execution. |

### Concrete Conditions If In-Account Execution Were Ever Attempted
If an automated evaluation harness were ever authorized to execute isolated Inno Setup in a non-production test context in this account, all of the following conditions must be satisfied:
1. **Scratch Paths:** Target app directory and profile directory must reside strictly under checkout scratch (e.g. `<worktree>\scratch\app` and `<worktree>\scratch\profile`).
2. **Profile Pre-creation:** The profile directory must exist prior to setup invocation (`uoink.iss:1206`), and the app directory must be empty or absent (`uoink.iss:1313`).
3. **Exact Command-Line Invocation:**
   ```powershell
   & ".\Uoink-Setup-3.8.0.exe" `
       /VERYSILENT /NORESTART /SUPPRESSMSGBOXES `
       /DIR="<scratch>\app" `
       /ISOLATED=1 `
       /PROFILE="<scratch>\profile" `
       /PORT=18081 `
       /NOCLOSEAPPLICATIONS /NORESTARTAPPLICATIONS `
       /MERGETASKS="" `
       /LOG="<scratch>\inno.log"
   ```
4. **Task Suppression:** `/MERGETASKS=""` (or `/TASKS=""`) is mandatory to prevent dropping `Uoink Isolated.lnk` onto `C:\Users\hello\Desktop`.
5. **Teardown Cleanup:** Upon completion, the uninstaller must be invoked (`<scratch>\app\unins000.exe /VERYSILENT /NORESTART /SUPPRESSMSGBOXES`) to cleanly purge the `HKCU` uninstall key and the Start Menu group shortcuts.

### Final Security Council Recommendation
**Do not execute Inno Setup in the primary `C:\Users\hello` account.**
Although the technical boundaries prevent interference with ordinary Uoink databases and processes, the host user profile modifications and the explicit runbook gate (`line 34`) make in-account execution invalid for release-candidate receipt credit. Astra must execute the receipt protocol in the designated throwaway Windows account as prescribed by the closure brief and runbook.
