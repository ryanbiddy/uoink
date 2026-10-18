# Agent Installation Security Review: Driver and Inno Callees

Date: 2026-09-09  
Reviewer: Gemini (Worker in local multi-model control room)  
Target script: `scripts/install_receipt/agent_install.ps1` (commit `cc970a5`)  
Target installer script: `installer/uoink.iss` (commit `ddfd316`)  
Reference brief: `docs/library/RYAN-AGENT-INSTALLATION-REVIEW-BRIEF-2026-09-09.md`  

---

## 1. Executive Summary & Operational Context

Ryan delegated the installation security review for the Living Library agent installation driver. The test host is Windows 11 Home without Windows Sandbox, running under the non-elevated user account `C:\Users\hello`.

The driver under review is `scripts/install_receipt/agent_install.ps1`. It serves as a concrete, script-driven supplement to the interactive operator runbook in `docs/library/INSTALL-RECEIPT-RUNBOOK-2026-09-09.md`. The runbook had assumed a separate throwaway Windows user account. In contrast, this review evaluates the installation as what it actually is: **a per-user Inno installation executed under the same Windows user account (`C:\Users\hello`), using fresh application and data directories under `_scratch` and a profile-derived isolated credential namespace.**

This review was conducted in read-only mode:
- No existing files were modified.
- Neither the installer executable nor any helper was executed.
- No running processes were stopped.
- No Windows keyring or credential store was queried.
- Port 5179 was not contacted.
- Production index `C:\Users\hello\AppData\Local\Uoink\index.db` was not touched.
- No network requests, paid APIs, or subagents were used.

The driver contains several well-designed isolation controls, but it also contains two high-impact defects in its interaction with Inno Setup that will cause installation failures or mask verification failures during execution.

---

## 2. Containment Defects vs. Same-Account Evidence Limitations

A security review under a shared Windows account must separate code-level containment defects from unavoidable OS-level limitations.

### A. Real Containment Defects
These are concrete bugs in scripts or installer logic where the candidate code crosses boundaries it intended to respect:
1. **Shortcut pollution into the ordinary Start Menu folder:** Due to Inno Setup ignoring `/GROUP` when `DisableProgramGroupPage=yes` is set, isolated shortcuts land in `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Uoink`, altering the ordinary shortcuts and tripping the driver's own integrity check.
2. **Silent masking of verification failures:** `installer/uoink.iss` runs `verify_install.ps1` post-install but swallows non-zero exits with a suppressible message box, allowing a corrupted or incomplete installation to report exit code 0 to the driver.
3. **Hardcoded repository root:** `agent_install.ps1` hardcodes `E:\AI\projects\uoink\checkouts\Yoink-library`, breaking execution in worktree checkouts.

### B. Same-Account Evidence Limitations
These are architectural realities of running without OS-level sandboxing on Windows 11 Home under `C:\Users\hello`. They cannot be fixed by PowerShell or Inno scripts, and must be documented honestly:
1. **Shared Windows Security Token:** The installer, installed helper, test runner, and user applications run under the exact same Windows security identifier (`SID`). Any process running in this context can access files owned by `hello`.
2. **Shared DPAPI Master Key:** Windows Data Protection API (DPAPI) uses keys derived from the user's login password. Both production and isolated credentials are encrypted under the same user key. Isolation is achieved solely through service name separation (`Uoink:isolated:<profile_id>:<username>` vs `Uoink`).
3. **Shared Windows Registry Hive (`HKCU`):** Both production and isolated installations write to `HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Uninstall`. They use separate GUID keys (`{1CCDA47D-...}` vs `{8F3E1B27-...}`), but both exist in the user's hive and appear in the Windows Installed Apps list.
4. **Shared `%APPDATA%` and `%LOCALAPPDATA%`:** The user profile directories are shared. Isolation depends on the installer placing files strictly under the user-supplied `--isolated-profile` and `/DIR` arguments under `_scratch`.

---

## 3. Concrete Defects, Line Numbers, and Bounded Repairs

### Defect 1: Inno Setup Ignores `/GROUP` When `DisableProgramGroupPage=yes`
- **Files:** `installer/uoink.iss` line 45; `scripts/install_receipt/agent_install.ps1` lines 19, 42, 111, 134.
- **Mechanism:**
  In `installer/uoink.iss`:
  ```pascal
  44: DefaultGroupName=Uoink
  45: DisableProgramGroupPage=yes
  ```
  In Inno Setup's engine, when `DisableProgramGroupPage=yes` is set in the `[Setup]` section, the command-line argument `/GROUP="..."` is **completely ignored**. Inno falls back to `DefaultGroupName` (`Uoink`).
  In `scripts/install_receipt/agent_install.ps1`:
  ```powershell
  19: $taskGroup = 'Uoink Living Library Receipt ' + (Split-Path -Leaf $taskRoot)
  ...
  42: $taskGroupPath = Join-Path $env:APPDATA ('Microsoft\Windows\Start Menu\Programs\' + $taskGroup)
  ...
  111: ('/GROUP="'+$taskGroup+'"')
  ```
  The driver expects shortcuts to land in `$taskGroupPath` (`Programs\Uoink Living Library Receipt <leaf>`). But because Inno ignores `/GROUP`, Inno writes the isolated shortcuts (`Uoink Isolated.lnk`, `Stop Uoink Isolated.lnk`, `Open Uoink Isolated folder.lnk`, `Uninstall Uoink Isolated.lnk`) directly into:
  `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Uoink\`
  Next, at line 134 of `agent_install.ps1`:
  ```powershell
  134: if ($taskBefore.ordinary_autorun_hash -ne $taskAfter.ordinary_autorun_hash -or ($taskBefore.ordinary_shortcut_hashes | ConvertTo-Json -Compress) -ne ($taskAfter.ordinary_shortcut_hashes | ConvertTo-Json -Compress)) { throw 'Ordinary autorun/shortcuts changed.' }
  ```
  `$taskBefore.ordinary_shortcut_hashes` computed hashes for all `.lnk` files in `Programs\Uoink` before install. Because Inno deposited the four isolated shortcuts into `Programs\Uoink`, `$taskAfter.ordinary_shortcut_hashes` contains those four new files.
  The check fails and throws: `'Ordinary autorun/shortcuts changed.'`.
  Furthermore, the isolated shortcut group `$taskGroupPath` is never created.
- **Bounded Repair:**
  1. In `installer/uoink.iss`, change line 45 to:
     ```pascal
     DisableProgramGroupPage=no
     ```
     And in `[Code]`, add `wpSelectProgramGroup` to `ShouldSkipPage`:
     ```pascal
     function ShouldSkipPage(PageID: Integer): Boolean;
     begin
       Result := False;
       if PageID = wpWelcome then
         Result := True;
       if PageID = wpSelectProgramGroup then
         Result := True;
       if (PageID = MigratePage.ID) and ((not LegacyYoinkPresent()) or IsolatedInstall()) then
         Result := True;
     end;
     ```
     This hides the page in wizard mode while allowing Inno's command-line parser to process `/GROUP="..."`.
  2. Alternatively, set dynamic group naming in `[Setup]`:
     ```pascal
     DefaultGroupName={code:GetInstallGroupName}
     ```
     And implement `GetInstallGroupName` to check `IsolatedInstall()`.
  3. In `scripts/install_receipt/agent_install.ps1`, add an explicit post-install check verifying that `$taskGroupPath` was created and contains the four isolated `.lnk` files.

---

### Defect 2: Inno Setup Masks `verify_install.ps1` Failures with Exit Code 0
- **Files:** `installer/uoink.iss` lines 1746-1757; `scripts/install_receipt/agent_install.ps1` lines 122, 129.
- **Mechanism:**
  In `installer/uoink.iss`:
  ```pascal
  1746:   if (not VerifyOk) or (ResultCode <> 0) then
  1747:   begin
  1748:     Log('Post-install verification warning: files-only check failed with exit code ' + IntToStr(ResultCode));
  1749:     SuppressibleMsgBox(
  1750:       'Uoink is installed, but setup could not verify every bundled file.' +
  ...
  1756:     Exit;
  1757:   end;
  ```
  `VerifyInstalledHelper` runs `verify_install.ps1` during `CurStepChanged(ssPostInstall)`.
  If `verify_install.ps1` fails (for example, exit code 23 because a required file like `x_extractor.py` or `notes.py` is missing from the bundle), Inno logs a warning and calls `SuppressibleMsgBox`.
  Because `agent_install.ps1` passes `/SUPPRESSMSGBOXES` (line 109), the message box is automatically dismissed. The procedure then simply calls `Exit;`.
  Inno Setup finishes execution and exits with **code 0**.
  In `agent_install.ps1`:
  ```powershell
  122: $taskObservation.exit=$taskProcess.ExitCode
  ...
  129: if ($null -eq $taskObservation.exit -or $taskObservation.exit -ne 0) { throw 'Installer did not return exit zero; preserve all evidence.' }
  ```
  The driver only inspects `$taskProcess.ExitCode`. It never checks `$taskTemp\uoink-install-verify.log`. If bundled files are missing, the driver will record a successful installation with exit code 0.
- **Bounded Repair:**
  1. In `installer/uoink.iss`, make verification failure fatal during isolated installations:
     ```pascal
     if (not VerifyOk) or (ResultCode <> 0) then
     begin
       Log('Post-install verification failed with exit code ' + IntToStr(ResultCode));
       if IsolatedInstall() then
         RaiseException('isolated-verify-failed: verify_install.ps1 failed with exit code ' + IntToStr(ResultCode));
       ...
     ```
  2. In `scripts/install_receipt/agent_install.ps1`, add a check after line 129 to inspect `$taskTemp\uoink-install-verify.log`:
     ```powershell
     $verifyLog = Join-Path $taskTemp 'uoink-install-verify.log'
     if (-not (Test-Path -LiteralPath $verifyLog)) { throw 'Install verification log missing.' }
     $verifyContent = Get-Content -LiteralPath $verifyLog -Raw
     if ($verifyContent -notmatch 'files-only install verification OK' -or $verifyContent -match 'MISSING bundled file') {
         throw 'Post-install verification script failed in temporary log.'
     }
     ```

---

### Defect 3: Hardcoded Repository Path in Driver
- **File:** `scripts/install_receipt/agent_install.ps1` line 8.
- **Mechanism:**
  ```powershell
  8: $taskRepo = 'E:\AI\projects\uoink\checkouts\Yoink-library'
  9: $taskScratch = [IO.Path]::GetFullPath((Join-Path $taskRepo '_scratch')).TrimEnd('\') + '\'
  10: $taskRoot = [IO.Path]::GetFullPath($ReceiptRoot).TrimEnd('\')
  11: if (-not $taskRoot.StartsWith($taskScratch,[StringComparison]::OrdinalIgnoreCase)) { throw 'Receipt must be inside the checkout scratch directory.' }
  ```
  Line 8 hardcodes the path to the primary checkout. If the script is run from a Git worktree (such as `C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\...`) or if the repository is moved, line 11 throws an error unless the receipt root artificially points into `E:\AI\projects\uoink\checkouts\Yoink-library\_scratch`.
- **Bounded Repair:**
  Derive the repository root dynamically from the script location with an optional parameter override:
  ```powershell
  param(
      [Parameter(Mandatory=$true)][string]$Package,
      [Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{64}$')][string]$PackageHash,
      [Parameter(Mandatory=$true)][string]$ReceiptRoot,
      [Parameter(Mandatory=$true)][ValidateSet('install','same-version-reinstall')][string]$Stage,
      [string]$RepoRoot = $null
  )
  ...
  if (-not $RepoRoot) {
      $RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
  }
  $taskRepo = [IO.Path]::GetFullPath($RepoRoot)
  ```

---

### Defect 4: Incomplete Cloud Credential Environment Sanitization
- **File:** `scripts/install_receipt/agent_install.ps1` lines 99-101.
- **Mechanism:**
  Lines 99-101 remove common AI API keys:
  `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`, `OPENAI_API_KEY`, `XAI_API_KEY`, `GROK_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_API_KEY`.
  However, `docs/library/INSTALL-RECEIPT-RUNBOOK-2026-09-09.md` lines 50-51 also removes:
  `CLAUDE_CODE_USE_BEDROCK`, `CLAUDE_CODE_USE_VERTEX`, and `CLAUDE_CODE_USE_FOUNDRY`.
  If these variables exist in the operator's environment, child processes (such as subsequent Phase 4 Claude runs) could route calls to cloud provider credentials without explicit authorization.
- **Bounded Repair:**
  Add `'CLAUDE_CODE_USE_BEDROCK','CLAUDE_CODE_USE_VERTEX','CLAUDE_CODE_USE_FOUNDRY'` to the array in line 99.

---

### Defect 5: Missing Post-Install Verification of Isolated Shortcut Target and Group
- **File:** `scripts/install_receipt/agent_install.ps1` lines 88, 134-138.
- **Mechanism:**
  While line 88 checks that `$taskGroupPath` does not exist prior to install, the script never checks after install that `$taskGroupPath` exists or that the shortcuts inside it point to `$taskApp\python\pythonw.exe` with `--isolated-profile` and `--isolated-port`.
- **Bounded Repair:**
  After line 138, assert that `$taskGroupPath` contains the expected shortcuts:
  ```powershell
  if (-not (Test-Path -LiteralPath $taskGroupPath -PathType Container)) { throw 'Isolated Start Menu group was not created.' }
  $taskExpectedShortcuts = @('Uoink Isolated.lnk','Stop Uoink Isolated.lnk','Open Uoink Isolated folder.lnk','Uninstall Uoink Isolated.lnk')
  foreach ($taskExpected in $taskExpectedShortcuts) {
      $taskExpectedPath = Join-Path $taskGroupPath $taskExpected
      if (-not (Test-Path -LiteralPath $taskExpectedPath -PathType Leaf)) { throw ('Missing isolated shortcut: ' + $taskExpected) }
  }
  ```

---

## 4. Inno Setup Callee Analysis & Isolation Verification

### A. Parameter Parsing & Validation
In `installer/uoink.iss`, lines 388-451 and 1326-1350:
- Isolated setup requires exactly four value switches: `/ISOLATED=1`, `/PROFILE="<path>"`, `/PORT=<int>`, `/DIR="<path>"`.
- Duplicate switches or conflicting parameters immediately abort via `IsolatedAbort`.
- Port 5179 is explicitly forbidden (`IsolatedValidatePortValue`, line 1231).
- Port 18081 (specified in `agent_install.ps1` line 18) is valid.

### B. Application Close & Restart Manager Suppression
In `installer/uoink.iss`, lines 791-808:
- The script checks that `/NOCLOSEAPPLICATIONS` and `/NORESTARTAPPLICATIONS` are passed.
- It forbids `/CLOSEAPPLICATIONS`, `/FORCECLOSEAPPLICATIONS`, and `/RESTARTAPPLICATIONS`.
- `agent_install.ps1` lines 109-111 correctly passes `/NOCLOSEAPPLICATIONS` and `/NORESTARTAPPLICATIONS`.
- In `PrepareToInstall` (lines 1662-1682), when `IsolatedInstall()` is true:
  - Inno skips `upgrade_prep.ps1`.
  - Inno skips deleting `%LOCALAPPDATA%\Uoink\.first-run-done`.
  - Inno does NOT contact port 5179.
  - Inno does NOT terminate any running `python.exe` or `pythonw.exe` processes under `%LOCALAPPDATA%\Uoink` or `Yoink`.

### C. Health Probes and Network Activity
In `installer/verify_install.ps1`:
- Inno invokes `verify_install.ps1` without `-ProbeHealth` (line 1735).
- Lines 58-61 in `verify_install.ps1` exit 0 immediately after verifying file existence and the `VERSION` string:
  ```powershell
  if (-not $ProbeHealth) {
      Write-VerifyLog 'files-only install verification OK; live health probe skipped'
      exit 0
  }
  ```
- Port 5179 is not probed.
- No network requests are made.

### D. Registry Isolation
In `installer/uoink.iss`:
- AppId is dynamic:
  ```pascal
  494: function GetInstallAppId(Param: String): String;
  495: begin
  498:   if IsolatedSetupRequested() then
  499:     Result := '{8F3E1B27-9C6A-4E5D-A2B8-7D4C1E0F93A5}'
  500:   else
  501:     Result := '{1CCDA47D-2347-43D1-99F4-BD6E7C231288}';
  502: end;
  ```
- Inno automatically registers uninstall information under:
  `HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{8F3E1B27-9C6A-4E5D-A2B8-7D4C1E0F93A5}_is1`
- The ordinary registry entry `{1CCDA47D-2347-43D1-99F4-BD6E7C231288}_is1` is completely untouched.
- The `Run` key entry (`HKCU:\Software\Microsoft\Windows\CurrentVersion\Run\Uoink`) has condition `Check: not IsolatedInstall` (line 313), preventing autorun registration.
- The post-install `[Run]` command to start the server has condition `Check: not IsolatedInstall` (line 322) and `skipifsilent`. The server is not launched.

### E. Marker Generation and Verification
In `installer/uoink.iss`:
- Post-install writes `isolated-install.json` in `$taskApp` (lines 1762-1795).
- The marker records:
  ```json
  {
    "mode": "isolated",
    "profile": "<taskProfile>",
    "port": 18081,
    "host": "127.0.0.1",
    "app_dir": "<taskApp>"
  }
  ```
- `agent_install.ps1` lines 95-96 and 135-136 verify that the marker exists, is well-formed, and matches `$taskApp`, `$taskProfile`, and `$taskPort`.

### F. Same-Version Reinstall Behavior
In `agent_install.ps1`:
- When `$Stage -eq 'same-version-reinstall'`:
  - It checks that a prior `install.json` exists with exit code 0 and matching package hash (lines 93-94).
  - It checks that `isolated-install.json` exists and matches ownership (lines 95-96).
  - It records a new `same-version-reinstall.before.json`, `same-version-reinstall.inno.log`, and `same-version-reinstall.after.json`.
- In `installer/uoink.iss` (lines 1300-1312):
  - Inno reads the existing `isolated-install.json` in `$taskApp`.
  - It asserts that the marker matches the incoming `/PROFILE` and `/PORT`.
  - It checks line 1344 that no `runtime-identity.json` exists in `$taskProfile` (verifying that no isolated helper is currently running).
  - It updates the installed files and rewrites the marker.

---

## 5. Summary of Residual Host Effects Under Same-Account Execution

When executed under `C:\Users\hello`, the following residual artifacts remain on the host:
1. **Registry:** One new uninstall key at `HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{8F3E1B27-9C6A-4E5D-A2B8-7D4C1E0F93A5}_is1` (pointing to `$taskApp`).
2. **Start Menu:** One folder at `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Uoink Living Library Receipt <leaf>\` containing 4 `.lnk` files (once Defect 1 is repaired).
3. **Receipt & Scratch Files:** The `$taskRoot` tree under `checkout\_scratch\`, containing `app\`, `c22\`, `install.json`, `install.before.json`, `install.after.json`, `install.inno.log`, and temp folders.
4. **Credential Vault:** If subsequent C22/P4 scenarios store credentials, entries are written into Windows Credential Manager under names prefixed with `Uoink:isolated:...`. No production credentials (`Uoink`) are altered.

---

## 6. Antivirus / Static Check Boundaries

1. **Windows Defender / AMSI:** A clean scan from Defender or AMSI is not a security certificate. It only confirms the absence of known malicious signatures. It does not verify path containment, parameter isolation, or credential safety.
2. **Static Review vs. Execution Receipt:** This review establishes the static correctness and defects of `agent_install.ps1` and `installer/uoink.iss`. However, this report is not an execution receipt. A valid receipt requires executing the repaired script against a freshly sealed installer package, capturing the actual runtime process exit codes, registry diffs, and post-installation verification logs.

---

## 7. Next Actions for Integrator (Astra)

Before executing `agent_install.ps1`:
1. Apply the bounded repair for **Defect 1** in `installer/uoink.iss` (change `DisableProgramGroupPage=yes` to `no` and skip in `ShouldSkipPage`).
2. Apply the bounded repair for **Defect 2** in `installer/uoink.iss` (raise exception on verification failure in isolated mode) and in `agent_install.ps1` (verify `uoink-install-verify.log`).
3. Apply the bounded repair for **Defect 3** and **Defect 4** in `scripts/install_receipt/agent_install.ps1` (dynamic `$taskRepo`, environment sanitization).
4. Rebuild and seal the candidate package (`Uoink-Setup-3.8.0.exe`).
5. Prepare C22 profiles and bind the driver to the sealed installer hash.
6. Execute the driver non-elevated under `_scratch` and inspect the resulting receipts.
