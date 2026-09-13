# Independent Review: Optional Installer Signing Path (commit d24cc33)

**Date**: 2026-09-12  
**Reviewer**: Gemini (worktree worker `gemini`)  
**Commit Reviewed**: `d24cc33` ("feat(build): verify optional installer signing [Astra]")  
**Scope & Boundary**: Focused independent review of optional release signing implementation across `build.ps1`, `installer/uoink.iss`, `scripts/installer_signing.ps1`, `scripts/sign_installer.ps1`, `tests/test_installer_signing.py`, `docs/build-installer.md`, and proof archive `docs/library/proof/signing-repair-01-2026-09-12/`.

> [!IMPORTANT]
> This review evaluates an optional build mode introduced in commit `d24cc33`. It is not a security certification, release approval, or signed release candidate. The real signed success path remains unobserved: no publisher certificate exists in the standard host stores (`CurrentUser\My` and `LocalMachine\My`), SignTool is absent from PATH, and no real signer or timestamp service was invoked.

---

## 1. Executive Summary & Test Evidence

All standing rules were strictly enforced during this review:
- Zero test or production code in existing files was altered.
- No certificates were created or imported; trust stores remained untouched.
- No real code signer was called; no release was compiled or installed.
- No clients were launched; live index `%LOCALAPPDATA%\Uoink\index.db` was not opened.
- Helper port `5179` was not contacted; no paid APIs were called; no models or checkpoints were loaded.
- Provider credentials (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_API_KEY`, `GROQ_API_KEY`, `MISTRAL_API_KEY`, `DEEPSEEK_API_KEY`) were scrubbed from child test execution environments.

### Observed Test Counts

1. **Existing Baseline Suites (34 passed in 10.00s)**:
   - `tests/test_installer_signing.py`: 26 passed
   - `tests/test_installer_dependency_lock.py`: 5 passed
   - `tests/test_build_guide_accuracy.py`: 3 passed
2. **New Reproduction Suite (5 passed in 1.68s)**:
   - `tests/test_installer_signing_review.py`: 5 passed
3. **Combined Suite (39 passed in 11.43s)**:
   - All 39 tests passed cleanly under isolated environment execution.

---

## 2. Review of Retained Inno Refusal Evidence

The proof directory `docs/library/proof/signing-repair-01-2026-09-12/` contains three retained synthetic wiring attempts (`signing12-inno-wiring01`, `wiring02`, `wiring03`). Inspection of these attempts confirms the following mechanical behaviors:

### Attempt 01: `signing12-inno-wiring01` (Incomplete execution)
- **Observed Artifacts**: `compiler.log` (0 bytes), `fixture.txt` (34 bytes), `synthetic.iss` (323 bytes), no `result.json`.
- **Cause**: Line 1 of `check_inno_signing_wiring01.ps1` set `$ErrorActionPreference = 'Stop'`. When Inno Setup (`ISCC.exe`) ran, native stderr from the failing callback or compiler triggered a terminating script error in PowerShell under stream redirection `*>`. The wrapper aborted before writing `result.json` or recording compiler exit.

### Attempt 02: `signing12-inno-wiring02` (Failed observation assertions)
- **Observed Artifacts**: `compiler.log` (1,134 bytes), `result.json` (971 bytes), `compiler_exit: 2`.
- **Result Details**: `callback_invoked: false`, `missing_certificate_refused: false`, `installer_created: false`.
- **Cause**: While the compiler exited with code 2 and did not create an installer, Inno Setup's `ISCC.exe /Q` does not forward callback stdout or stderr into `compiler.log`. The script asserted that `compiler.log` must contain `sign_installer.ps1` and `Cannot find path`, which failed because ISCC swallowed child process output.

### Attempt 03: `signing12-inno-wiring03` (Refusal confirmed via forwarder)
- **Observed Artifacts**: `callback-arguments.json` (419 bytes), `callback.log` (1,272 bytes), `compiler.log` (1,134 bytes), `observed callback.ps1` (527 bytes), `result.json` (998 bytes).
- **Result Details**: `compiler_exit: 2`, `callback_invoked: true`, `missing_certificate_refused: true`, `installer_created: false`.
- **Significance**: Inno compiler invoked the custom `observed callback.ps1`, which forwarded arguments to `sign_installer.ps1` and redirected child stderr to `callback.log`. The missing certificate (`0000000000000000000000000000000000000000`) was refused, Inno stopped at the uninstaller stage, and compilation aborted with exit code 2.
- **Limitation**: The successful observation relied on `observed callback.ps1` capturing stderr to an external log. In production (`build.ps1`), Inno directly invokes `sign_installer.ps1` without output capture, leaving operators with no callback error output on build failure.

---

## 3. Detailed Findings and Defects

### Finding 1 (Defect): Unquoted Target File Parameter in Inno SignTool Command
- **Source**: [scripts/installer_signing.ps1](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/e922b3bf-3d8/gemini/scripts/installer_signing.ps1#L122-L123)
- **Test Codification**: [tests/test_installer_signing.py](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/e922b3bf-3d8/gemini/tests/test_installer_signing.py#L53)
- **Reproduction**: `test_repro_inno_command_lacks_quotes_around_filepath_token` and `test_repro_unquoted_filepath_with_spaces_fails_powershell_binding` in [tests/test_installer_signing_review.py](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/e922b3bf-3d8/gemini/tests/test_installer_signing_review.py#L38-L70).
- **Detail**:
  `Get-UoinkInnoSignCommand` constructs the `/Suoinkrelease=...` parameter passed to ISCC:
  ```powershell
  return ('/Suoinkrelease=$q{0}$q -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $q{1}$q -FilePath $f -CertificateThumbprint {2} -TimestampUrl {3} -SignToolPath $q{4}$q' -f
      $PowerShellPath, $CallbackPath, $CertificateThumbprint, $TimestampUrl, $SignToolPath)
  ```
  Notice that `$PowerShellPath`, `$CallbackPath`, and `$SignToolPath` are wrapped in `$q` (Inno's quote substitution), but `$f` is unquoted (`-FilePath $f`).
  When Inno signs the uninstaller or installer, Inno expands `$f` into the literal file path. If the build directory, checkout directory, or uninstaller cache directory contains spaces (e.g., `C:\Users\John Doe\...` or `C:\Build Outputs\...`), Inno executes:
  `powershell.exe ... -File "...\sign_installer.ps1" -FilePath C:\Build Outputs\signed-uninstallers\...`
  PowerShell's parameter binder assigns `C:\Build` to `-FilePath`. The remaining unquoted tokens (`Outputs\...`) are treated as positional arguments, binding to `$CertificateThumbprint`. When PowerShell encounters the literal `-CertificateThumbprint` flag later in the argument string, it fails with:
  `A parameter cannot be found that matches parameter name 'CertificateThumbprint'` or throws positional binding conflicts.
  Existing test `test_inno_command_quotes_paths_and_uses_fixed_callback` asserted this exact broken behavior (`assert ' -FilePath $f ' in command`).
- **Required Fix**: Change `-FilePath $f` to `-FilePath $q$f$q`.

---

### Finding 2 (Defect): PowerShell 7 (`pwsh`) Preflight Failure via Incompatible Executable Path
- **Source**: [build.ps1](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/e922b3bf-3d8/gemini/build.ps1#L60)
- **Reproduction**: `test_repro_pwsh_pshome_resolution_fails_in_powershell_7` in [tests/test_installer_signing_review.py](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/e922b3bf-3d8/gemini/tests/test_installer_signing_review.py#L73-L78).
- **Detail**:
  In `build.ps1`, the sign command is configured with:
  ```powershell
  -PowerShellPath (Join-Path $PSHOME 'powershell.exe')
  ```
  When `build.ps1` runs under PowerShell 7 (`pwsh`), `$PSHOME` points to `C:\Program Files\PowerShell\7`. In PowerShell 7, the executable is `pwsh.exe`; `powershell.exe` does not exist in `$PSHOME`.
  `Get-UoinkInnoSignCommand` validates line 116 of `scripts/installer_signing.ps1`:
  ```powershell
  if ($path -notmatch '^[A-Za-z]:[\\/]' -or -not (Test-Path -LiteralPath $path -PathType Leaf)) {
      throw 'Signing callback and PowerShell must be existing absolute files'
  }
  ```
  Running `build.ps1 -ReleaseSigned` from `pwsh` immediately throws `Signing callback and PowerShell must be existing absolute files`.
- **Required Fix**: Resolve the current PowerShell binary dynamically:
  ```powershell
  $psExe = (Get-Process -Id $PID).Path
  if (-not $psExe -or -not (Test-Path $psExe)) { $psExe = Join-Path $PSHOME 'powershell.exe' }
  ```
  or fallback to `(Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe')`.

---

### Finding 3 (Defect): Residual `Get-FileHash` Dependency in Unsigned Build Flow
- **Source**: [build.ps1](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/e922b3bf-3d8/gemini/build.ps1#L210), [build.ps1](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/e922b3bf-3d8/gemini/build.ps1#L831)
- **Detail**:
  In `signing12-checkout01`, Astra documented two test failures caused by `Get-FileHash` failing to resolve in isolated child PowerShell processes. Astra repaired `scripts/installer_signing.ps1` by implementing `Get-UoinkFileSha256` using .NET's `[Security.Cryptography.SHA256]::Create()`.
  However, `build.ps1` was not fully converted:
  - Line 210 (`Confirm-Hash`): `$actual = (Get-FileHash -Path $path -Algorithm SHA256).Hash.ToLower()`
  - Line 831 (unsigned receipt generation):
    `sha256 = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant()`
  If an unsigned review build or preflight cache validation runs in an environment where `Microsoft.PowerShell.Utility` autoloading fails, `build.ps1` aborts after compilation when attempting to hash the generated executable.
- **Required Fix**: Replace calls to `Get-FileHash` in `build.ps1` with `.NET` SHA256 streams or import `Get-UoinkFileSha256`.

---

### Finding 4 (Defect): Missing SHA256 Digest Verification in `Assert-UoinkSignedFile`
- **Source**: [scripts/installer_signing.ps1](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/e922b3bf-3d8/gemini/scripts/installer_signing.ps1#L70-L76)
- **Reproduction**: `test_repro_assert_signed_file_does_not_verify_sha256_algorithm` in [tests/test_installer_signing_review.py](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/e922b3bf-3d8/gemini/tests/test_installer_signing_review.py#L81-L110).
- **Detail**:
  The brief requires: "require SHA256 and an RFC 3161 timestamp, then verify publisher identity, trust and timestamp."
  In `Invoke-UoinkSignFile`, signing explicitly passes `/fd SHA256` and `/td SHA256`.
  However, `Assert-UoinkSignedFile` only checks:
  1. `Invoke-UoinkSignTool $SignToolPath @('verify', '/pa', '/all', '/tw', $FilePath)`
  2. `Get-AuthenticodeSignature -LiteralPath $FilePath` status equals `'Valid'`
  3. Certificate thumbprint matches `$CertificateThumbprint`
  4. `$signature.TimeStamperCertificate` is not null.
  It never inspects the digest algorithm of either the file signature or the timestamp counter-signature. Windows Authenticode and SignTool `/pa` verify legacy SHA-1 signatures if permitted by certificate policy or catalog roots. An artifact signed with SHA-1 would be reported with `signature_verified: true`.
- **Required Fix**: Verify `$signature.SignerCertificate.SignatureAlgorithm.FriendlyName` matches SHA256 and assert timestamp hash algorithm.

---

### Finding 5 (Defect): Stale Receipt Retention on Failed Builds and Missing Uninstaller Receipt
- **Source**: [build.ps1](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/e922b3bf-3d8/gemini/build.ps1#L813-L835)
- **Detail**:
  `build.ps1` writes `$exe.signature.json` only after compilation succeeds. If a signed build succeeded previously, and a subsequent build (signed or unsigned) fails midway during compilation or signing:
  - The previous `$exe.signature.json` remains untouched on disk with `signature_verified: true`.
  - The previous `$exe` may remain on disk if not cleaned.
  - The documentation claims: "An unsigned build writes an explicitly unverified receipt, replacing any old signed receipt." This replacement only occurs if the unsigned build completes successfully; it does not protect against failed builds.
  Additionally, while Inno compiles and signs the uninstaller into a fresh GUID folder under `build\signed-uninstallers\`, no receipt or record of the uninstaller's hash, timestamp, or signature is saved into the build receipt or manifest.
- **Required Fix**: Delete `$exe` and `$exe.signature.json` immediately before calling `$iscc`, and capture the uninstaller receipt alongside the installer receipt.

---

### Finding 6 (Operational Defect): Inno Compiler Swallows Callback Error Details
- **Source**: [build.ps1](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/e922b3bf-3d8/gemini/build.ps1#L814)
- **Observed Proof**: `signing12-inno-wiring02` vs `signing12-inno-wiring03` in [docs/library/proof/signing-repair-01-2026-09-12/review.json](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/e922b3bf-3d8/gemini/docs/library/proof/signing-repair-01-2026-09-12/review.json#L24-L36).
- **Detail**:
  In `build.ps1`:
  ```powershell
  & $iscc /Q @signingArgs $issGenerated
  if ($LASTEXITCODE -ne 0) { throw 'ISCC compilation failed' }
  ```
  `ISCC.exe /Q` does not pipe the SignTool callback's standard error to the console. If signing fails (due to a certificate error, network timeout to the RFC 3161 endpoint, Smart Card PIN prompt timeout, or the path quoting bug in Finding 1), ISCC terminates with exit code 2 and outputs nothing about the cause. The operator sees only `ISCC compilation failed`.
- **Required Fix**: Wrap the callback invocation or log callback stdout/stderr to a dedicated build log (`build\signing.log`) so failures are diagnosable.

---

### Finding 7 (Design Limitation): Preflight Does Not Verify Certificate Trust Chain
- **Source**: [scripts/installer_signing.ps1](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/e922b3bf-3d8/gemini/scripts/installer_signing.ps1#L30-L42)
- **Reproduction**: `test_repro_assert_certificate_accepts_untrusted_certificate` in [tests/test_installer_signing_review.py](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/e922b3bf-3d8/gemini/tests/test_installer_signing_review.py#L113-L132).
- **Detail**:
  `Assert-UoinkSigningCertificate` checks:
  1. Thumbprint exists in `Cert:\CurrentUser\My\`
  2. `HasPrivateKey` is `$true`
  3. `NotBefore` <= UtcNow < `NotAfter`
  4. EnhancedKeyUsage contains code-signing OID `1.3.6.1.5.5.7.3.3`.
  It does not check if the certificate is trusted or chains to a valid root (e.g. `$certificate.Verify()`). If a self-signed or untrusted certificate is supplied, preflight succeeds, downloads and stages all components, and only fails at the uninstaller compilation step at the very end of the build.
  Furthermore, `Assert-UoinkSigningToken` permits spaces but its character ban regex `[\x00-\x1f"%!?&|<>$`^]` does not include semicolon (`;`) or single quote (`'`), despite semicolons acting as command separators in PowerShell.

---

### Finding 8 (Documentation): Launch Checklist Directs Unsigned Release Builds
- **Source**: [docs/build-installer.md](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/e922b3bf-3d8/gemini/docs/build-installer.md#L277-L286)
- **Detail**:
  Under "Launch checklist", Step 1 instructs:
  `1. Build a release artifact: .\build.ps1 -> produces build\Uoink-Setup-<VERSION>.exe.`
  Step 4 instructs:
  `Attach build\Uoink-Setup-$version.exe to the GitHub draft release.`
  If a release engineer executes this checklist verbatim, it builds an unsigned review build and attaches it to the release. The checklist makes no reference to `-ReleaseSigned`, `-SigningCertificateThumbprint`, `-TimestampUrl`, or `-SignToolPath`.
- **Required Fix**: Update the Launch checklist with the signing command syntax and prerequisites.

---

## 4. Observed Behavior vs. Hypotheses

| Area | Observed Behavior | Hypothesis / Unobserved Path |
|---|---|---|
| **Signing verification logic** | Passed 34 mock tests. Mock objects correctly simulate SignTool failure codes (1, 2) and certificate properties. | Real SignTool verification behavior with production RFC 3161 timestamps remains unobserved. |
| **Path quoting with spaces** | Inno callback command emits unquoted `-FilePath $f`. PowerShell fails parameter binding when simulated path contains spaces. | Exact Inno behavior on NTFS paths with commas or semicolons was not observed under real compiler. |
| **Inno compiler logging** | ISCC swallows callback stderr (`wiring02`); forwarder script was required to capture logs (`wiring03`). | Behavior of non-quiet mode (`ISCC` without `/Q`) under PowerShell redirection in CI was not measured. |
| **PowerShell versioning** | PowerShell 7 lacks `powershell.exe` in `$PSHOME`. | Execution under Windows PowerShell 5.1 in standard developer shell succeeds because `powershell.exe` exists in `$PSHOME`. |
| **Preflight side effects** | Preflight stops before downloads/staging if thumbprint is invalid format or absent from `CurrentUser\My`. | Preflight with an untrusted or expired-chain certificate was verified by mock to pass preflight and defer failure. |

---

## 5. Summary Table of Defect Classifications

| Defect ID | Severity | File | Lines | Description |
|---|---|---|---|---|
| **DEF-01** | High | `scripts/installer_signing.ps1` | 122–123 | `-FilePath $f` unquoted in Inno callback; breaks on paths with spaces |
| **DEF-02** | High | `build.ps1` | 60 | Hardcoded `Join-Path $PSHOME 'powershell.exe'` breaks PowerShell 7 |
| **DEF-03** | Medium | `build.ps1` | 210, 831 | Unsigned receipt and hash check retain fragile `Get-FileHash` dependency |
| **DEF-04** | Medium | `scripts/installer_signing.ps1` | 70–76 | `Assert-UoinkSignedFile` does not verify SHA256 digest algorithm |
| **DEF-05** | Medium | `build.ps1` | 813–835 | Stale `$exe.signature.json` not deleted before compile; no uninstaller receipt |
| **DEF-06** | Low | `build.ps1` | 814 | ISCC swallows signing callback error output; leaves failure undiagnosable |
| **DEF-07** | Low | `scripts/installer_signing.ps1` | 30–42 | Preflight accepts untrusted certificates without verifying trust chain |
| **DEF-08** | Low | `docs/build-installer.md` | 277–286 | Launch checklist omits `-ReleaseSigned` invocation |

---

## 6. Recommended Action Plan for Integrator

1. **Do not modify production code in this review task** (per brief mandate).
2. **Open a repair brief** covering DEF-01, DEF-02, DEF-03, DEF-04, DEF-05, and DEF-08.
3. Keep the 5 reproduction tests in [tests/test_installer_signing_review.py](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/e922b3bf-3d8/gemini/tests/test_installer_signing_review.py) as regression anchors.
4. Maintain `release_ready: false` until Ryan selects the production signing certificate and timestamp endpoint.
