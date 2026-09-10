# Agent Receipt Path Correction and Observation Wrapper Review

Date: 2026-09-09  
Reviewer: Gemini (Worker in local multi-model control room)  
Target wrapper: `_scratch/agent_receipt_observe.py`  
Target installer driver: `scripts/install_receipt/agent_install.ps1`  
Reference brief: `docs/library/RYAN-AGENT-RECEIPT-PATH-REPAIR-BRIEF-2026-09-09.md`  
Prior review verdict: `docs/library/ASTRA-AGENT-INSTALLATION-VERDICT-2026-09-09.md`  

---

## 1. Executive Summary and Scope

Ryan delegated this read-only review of the revised agent installation driver and its proposed observation wrapper.

During initial integration, Astra discovered that the original driver placed its receipt root inside the source repository (`_scratch`). When Phase 4's installed provenance oracle executed, it failed: the oracle asserts that installed application files, loaded modules, and `sys.path` entries do not resolve inside the forbidden checkout path (`E:\AI\projects\uoink\checkouts\Yoink-library`).

The brief directs:
1. Do not relax Phase 4's provenance oracle or narrow the forbidden checkout path.
2. Relocate the fixed allowed parent directory for installation receipts to `E:\AI\projects\uoink\installation-receipts`, outside the checkout.
3. Require a fresh child directory with spaces in its name, retaining all reparse checks, non-elevated assertions, package digest verifications, and shortcut inspections.
4. Review `_scratch/agent_receipt_observe.py` and `scripts/install_receipt/agent_install.ps1` statically before executing either.

Review boundaries observed:
- No installer executable or helper process was started.
- No Windows keyring or credential store was accessed.
- Port 5179 was not contacted.
- Production index `C:\Users\hello\AppData\Local\Uoink\index.db` was not touched.
- No network requests, external models, or paid APIs were used.
- Python and PowerShell scripts were parsed for syntax only, without runtime execution.

---

## 2. File Identification and Static Syntax Verification

Both files were read directly from their absolute paths on disk. Syntax validity was verified using standard abstract syntax tree parsing.

| Target File | Absolute Path | Size (Bytes) | SHA-256 Digest | Syntax Parse Result |
| :--- | :--- | :--- | :--- | :--- |
| Proposed Observation Wrapper | `E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\agent_receipt_observe.py` | 9,457 | `6fc78a115d443c3fb52a1764bb9ae9f8ee7024a04cf4b30ffce969ccb404146e` | Valid Python 3.11+ AST (1,938 AST nodes, 0 errors) |
| Corrected Installation Driver | `E:\AI\projects\uoink\checkouts\Yoink-library\scripts\install_receipt\agent_install.ps1` | 12,946 | `f0d8130140b7b490a99fb68e7ff890bc62de959e986a7a3ab600c8a12ea37c01` | Valid PowerShell script (0 errors via `Parser::ParseFile`) |

---

## 3. Provenance Oracle and Receipt Root Analysis

### A. Root Cause of the Original Rejection
Phase 4 enforces strict provenance through `scripts/install_receipt/p4_common.py`. In `validate_isolation`:
```python
822: if forbid_checkout is not None:
823:     forbidden = require_absolute(forbid_checkout, "--forbid-checkout")
824:     if contained_in(app, forbidden) and mode == RUNTIME_INSTALLED:
825:         raise IsolationError(
826:             "installed app resolves inside the forbidden checkout; "
827:             "use --runtime-mode source-runtime or --instrument-only"
828:         )
```
In addition, `evaluate_probe_for_installed` checks every imported module and `sys.path` entry:
```python
597: if forbid_checkout and contained_in(resolved, forbid_checkout):
598:     reasons.append(f"{name} resolved inside the checkout")
...
606: if forbid_checkout and contained_in(resolved, forbid_checkout):
607:     reasons.append("sys.path contains the checkout")
```
When `$ReceiptRoot` was configured under `_scratch`, `$taskApp` resolved to `E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\app`. Because this path is inside the forbidden checkout, the provenance oracle failed.

### B. Resolution
Relocating the root parent to `E:\AI\projects\uoink\installation-receipts` cleanly places the installed application tree outside `E:\AI\projects\uoink\checkouts\Yoink-library`. The oracle remains unmodified, maintaining full rigor:
- `forbid_checkout` remains `E:\AI\projects\uoink\checkouts\Yoink-library`.
- Installed binaries and staged files reside under `E:\AI\projects\uoink\installation-receipts\<child>\app`.
- Python imports from the installed directory no longer trip the checkout containment check.

---

## 4. Line-by-Line Review of `_scratch/agent_receipt_observe.py`

### A. Lifecycle and Stage Architecture
The wrapper manages sequential execution stages: `prepare`, `c22`, `browser`, `p4-prepare`, `p4-check`, `p4-prepare-client`, and `p4-collect`. It does not execute the Inno installer directly. The actual installation is performed separately by `agent_install.ps1` between `prepare` and `c22`.

Key implementation choices:
1. **Isolated Execution Flags (Line 7):**
   `assert sys.flags.isolated and sys.flags.no_site`
   Enforces invocation via `python -I -S`, preventing environment pollution or user-site package injection.
2. **Path Boundary Assertions (Lines 9-11):**
   Requires `root.is_relative_to(Path(r'E:\AI\projects\uoink\installation-receipts')) and ' ' in str(root)`.
   Requires `not root.is_relative_to(r)` (outside checkout).
   Requires `seal.is_relative_to(r/'docs/library/proof')`.
3. **Cryptographic Seal and Source Verification (Lines 16-23):**
   Parses `package-manifest.json` and `SHA256.json`.
   Verifies every file in the seal directory against size and digest.
   Verifies the installer package executable matches `package_sha256` and `package_bytes`.
   Verifies every source file in `package['files']` matches the file in checkout `r`.
4. **Environment Sanitization (Lines 24-26, 30-31):**
   Clears all known AI API keys and routing flags (`ANTHROPIC_*`, `CLAUDE_CODE_*`, `OPENAI_*`, `XAI_*`, `GROK_*`, `GEMINI_*`, `GOOGLE_*`, `PYTHONPATH`, `UOINK_ISOLATED_APP_DIR`).
   Redirects mutable directories (`LOCALAPPDATA`, `APPDATA`, `TEMP`, `TMP`) to `root/'environment'/<key>`.
   Pins `IG_FORBIDDEN_LIVE` to `C:\Users\hello\AppData\Local\Uoink\index.db` and sets offline flags.
   Retains actual `USERPROFILE` (`C:\Users\hello`) without falsely asserting OS-level containment.
5. **Dynamic Package Seal Binding (Line 39):**
   `manifest.CANDIDATE_PACKAGE_02_DIR = seal`
   Directs `load_candidate_package_02()` in `scripts/install_receipt/manifest.py` to load the selected seal (e.g., `candidate-package-03-2026-09-09`) while keeping all kit verification logic intact.
6. **Delegated Preparation (Lines 50-56):**
   Calls `OperatorRunner.prepare_before_install(..., skip_ordinary_user_check=True)`. This uses Ryan's authorized exception under the same Windows account, recording the exception in the receipt.
7. **Post-Execution Invariants (Lines 100-119):**
   Verifies `.pth` files match pre-run digests and ensures `sitecustomize.py` guard was removed.
   Asserts all spawned helper identities are `dead` via `liveness()`.
   Inspects helper logs in `c22/commands` to verify no unexpected `ERROR` or `CRITICAL` lines occurred.

---

## 5. Line-by-Line Review of `scripts/install_receipt/agent_install.ps1`

### A. Boundary and Driver Changes
Lines 8-11:
```powershell
$taskRepo = 'E:\AI\projects\uoink\checkouts\Yoink-library'
$taskScratch = [IO.Path]::GetFullPath('E:\AI\projects\uoink\installation-receipts').TrimEnd('\') + '\'
$taskRoot = [IO.Path]::GetFullPath($ReceiptRoot).TrimEnd('\')
if (-not $taskRoot.StartsWith($taskScratch,[StringComparison]::OrdinalIgnoreCase)) { throw 'Receipt must be inside the dedicated installation-receipts directory outside the checkout.' }
```
The driver now points its scratch base to `E:\AI\projects\uoink\installation-receipts\` and requires `$ReceiptRoot` to start with this prefix.

### B. Verification Flow
1. Asserts non-elevated execution via `WindowsPrincipal`.
2. Validates paths with `Assert-PlainPath` to block network shares, quote injections, and reparse points across all directory ancestors.
3. Checks that `$taskProfile` (`c22\profiles\empty`) exists prior to installation (ensuring `agent_receipt_observe.py prepare` was executed first).
4. Captures registry and file hashes before install, runs the Inno package with `/ISOLATED=1 /PORT=18081 /GROUP="<taskGroup>"`, and inspects post-install state.
5. Examines `uoink-install-verify.log` for files-only success markers.
6. Confirms ordinary registry keys, autorun entries, and Start Menu shortcuts were not altered.
7. Inspects the 4 isolated shortcuts (`Uoink Isolated.lnk`, `Stop Uoink Isolated.lnk`, `Open Uoink Isolated folder.lnk`, `Uninstall Uoink Isolated.lnk`), verifying target binaries, arguments, and file hashes.

---

## 6. Concrete Defects and Operational Recommendations

### Defect 1 (Wrapper): `root.mkdir(exist_ok=False)` fails when the parent directory is missing
- **Location:** `_scratch/agent_receipt_observe.py` line 28
- **Code:**
  ```python
  if a.stage=='prepare':root.mkdir(exist_ok=False)
  ```
- **Mechanism:**
  `E:\AI\projects\uoink\installation-receipts` does not currently exist on the host filesystem. In Python, `Path.mkdir()` defaults to `parents=False`. When `root` is a path like `E:\AI\projects\uoink\installation-receipts\receipt run 01`, `root.mkdir(exist_ok=False)` raises `FileNotFoundError: [WinError 3] The system cannot find the path specified`.
- **Correction:**
  Update line 28 to use `parents=True`:
  ```python
  if a.stage=='prepare':root.mkdir(parents=True, exist_ok=False)
  ```
  Alternatively, create the parent directory `E:\AI\projects\uoink\installation-receipts` prior to invoking the script.

### Defect 2 (Wrapper): Missing `operator.json` causes `p4-collect` to fail
- **Location:** `_scratch/agent_receipt_observe.py` line 88
- **Code:**
  ```python
  if stage=='collect':command+=['--operator-json',str(p4/'profile/operator.json')]
  ```
- **Mechanism:**
  `scripts/install_receipt/p4_operator.py` lines 79-80 requires:
  ```python
  if not args.operator_json or not args.operator_json.is_file():
      raise common.IsolationError("collect requires --operator-json with actual observations or explicit empty object")
  ```
  Neither `p4_prepare_fixture.py` nor `agent_receipt_observe.py` creates `operator.json`. If the operator runs `p4-collect` before creating this file, `p4_operator.py` aborts immediately with an `IsolationError`.
- **Correction:**
  Before spawning the subprocess for `stage == 'collect'`, the wrapper should verify whether `p4/'profile/operator.json'` exists. If absent, it should write an explicit empty object `{}` as authorized by the runbook:
  ```python
  if stage=='collect':
      op_json = p4/'profile/operator.json'
      if not op_json.exists():
          op_json.write_text('{}\n', encoding='utf8')
      command+=['--operator-json', str(op_json)]
  ```

### Defect 3 (Driver): `$ReceiptRoot` space-in-name requirement is not enforced in PowerShell
- **Location:** `scripts/install_receipt/agent_install.ps1` lines 10-12
- **Mechanism:**
  The brief states: *"Require a fresh child directory with spaces in its name..."*
  `agent_receipt_observe.py` checks this (`' ' in str(root)`), and `OperatorRunner` validates it (`require_space=True`). However, `agent_install.ps1` only checks that `$taskRoot` starts with `$taskScratch`. If `agent_install.ps1` is executed directly with a path lacking spaces, it will succeed, but subsequent C22 runner stages will reject the directory.
- **Correction:**
  Add an explicit check in `agent_install.ps1`:
  ```powershell
  if ($taskRoot.IndexOf(' ') -lt 0) { throw 'Receipt root must contain spaces in its name.' }
  ```

### Defect 4 (Driver): Unused `$taskRepo` assignment
- **Location:** `scripts/install_receipt/agent_install.ps1` line 8
- **Mechanism:**
  Line 8 assigns `$taskRepo = 'E:\AI\projects\uoink\checkouts\Yoink-library'`. In prior versions, line 9 used `$taskRepo` to build `$taskScratch`. After redirecting `$taskScratch` to `installation-receipts`, `$taskRepo` is unused. While harmless, keeping unreferenced path constants adds confusion.

---

## 7. Review Verdict and Sign-Off

**Status: APPROVED WITH CONDITIONS**

The structural transition to `E:\AI\projects\uoink\installation-receipts` resolves the Phase 4 provenance collision without weakening security invariants or relaxing the forbidden checkout oracle.

Before running the procedure:
1. Ensure `E:\AI\projects\uoink\installation-receipts` exists or patch line 28 of `_scratch/agent_receipt_observe.py` to specify `parents=True`.
2. Ensure `p4/'profile/operator.json'` is initialized (with `{}` or recorded observations) prior to executing `p4-collect`.
3. Add the space validation check to `agent_install.ps1` for defensive consistency.
4. Execute strictly using the newly sealed candidate package and manifest (`candidate-package-03-2026-09-09`).
