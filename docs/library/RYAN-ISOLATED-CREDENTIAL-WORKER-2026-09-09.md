# Isolated Credential Store Security Repair Worker Report

**Worker:** gemini  
**Worktree:** `C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\4c02e121-2b3\gemini`  
**Branch:** `control-room/4c02e121-2b3-gemini`  
**Date:** 2026-09-09  
**Status:** Complete in worktree. No commits created. Ready for integrator / Astra three-way integration and reseal.

---

## 1. Executive Summary

This repair addresses the isolated credential-store namespace vulnerability identified in `docs/library/RYAN-ISOLATED-CREDENTIAL-REPAIR-BRIEF-2026-09-09.md`.

Previously, `server.py` hardcoded `KEYRING_SERVICE = "Uoink"` and fallback `KEYRING_SERVICE_LEGACY = "Yoink"` for all credential operations. When running isolated helpers under explicit `--isolated-profile` and `--isolated-port`, credential queries still accessed the host machine's ordinary Uoink/Yoink OS keyring entries. An isolated helper would thus read ordinary user credentials, while key modifications or Anthropic 401 invalid-key resets would overwrite or destructively wipe the user's primary credentials.

The repair isolates credential storage in isolated mode by establishing a deterministic, bounded collision-resistant service namespace derived strictly from the canonical validated profile path. Isolated operations (read, set, delete, 401 reset, and plaintext migration) strictly operate within this isolated namespace and never fall back to ordinary or legacy services. Normal (non-isolated) mode preserves 100% existing Uoink/Yoink behavior and legacy migration.

---

## 2. Boundaries & Safety Compliance

- **Production code edits:** Exclusively in `server.py`.
- **New regression test suite:** Added `tests/test_isolated_credential_store.py`.
- **Documentation:** Updated `docs/security.md` (Threat Model and Anthropic API key storage sections).
- **Existing test edits:** Zero existing test, fixture, assertion, or skip modifications.
- **Installer & build files:** Untouched (`installer/uoink.iss`, `build.ps1`, etc.).
- **Live systems & network:**
  - Zero calls to live index or port 5179.
  - Zero real OS keyring operations performed (all tests employ an isolated `RecordingFakeKeyring`).
  - No model/client subprocesses spawned.
  - No paid API calls or environment variables (including fake `ANTHROPIC_API_KEY`).
  - Zero external network requests.
- **Integrator runner:** All test runs executed via guarded runner:
  `E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/ig-native/Scripts/python.exe -B E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/integrator_verify.py`
  with `$env:IG_FORBIDDEN_LIVE = "C:/Users/hello/AppData/Local/Uoink/index.db"`.

---

## 3. Implementation Details (`server.py`)

### 3.1 Deterministic Isolated Keyring Namespace
Added helper functions in `server.py`:
- `_isolated_binding() -> IsolationBinding | None`: Dynamically checks active isolation binding via `_install_isolation.current_binding() or _ISOLATION`.
- `_isolated_keyring_service(profile: Path | str) -> str`:
  Resolves the canonical profile path (`os.path.normcase(os.path.normpath(str(resolved)))`) and computes a 16-hex character SHA-256 digest:
  `digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]`
  Yielding deterministic service name: `Uoink-isolated-{digest}` (31 characters total, safely bounded).
- `_keyring_service_name() -> str`: Selects `_isolated_keyring_service(binding.profile)` when isolated, or `KEYRING_SERVICE` (`"Uoink"`) in normal mode.
- `_settings_path() -> Path`: Dynamically resolves settings path to `binding.profile / "settings.json"` when isolated, or global `SETTINGS_PATH` in normal mode.

### 3.2 Key Operation Hardening
- **`_get_saved_anthropic_key()`**:
  - In isolated mode: queries `_isolated_keyring_service(binding.profile)`. If absent, returns `""` immediately without fallback.
  - In normal mode: queries `KEYRING_SERVICE`, falling back to `KEYRING_SERVICE_LEGACY` ("Yoink") for install migration window compatibility.
- **`_store_saved_anthropic_key(key)`**:
  - Directs writes and deletes to `_keyring_service_name()`. In isolated mode, sets or deletes the profile-scoped entry only.
- **`_migrate_plaintext_anthropic_key()`**:
  - Reads `_settings_path()`.
  - In isolated mode, migrates plaintext `anthropic_key` into the isolated service namespace and removes it from the isolated `settings.json`.
- **`_mark_anthropic_key_invalid()`**:
  - Clears `_store_saved_anthropic_key("")` using the active service namespace, ensuring 401 resets clear only the isolated profile entry and never delete ordinary user credentials.

---

## 4. Verification Evidence

### 4.1 Negative Baseline Verification (`isolated-cred-negative-01`)
Run against unchanged `server.py` with newly authored regressions in `tests/test_isolated_credential_store.py`:
- **Command:**
  ```powershell
  $env:IG_FORBIDDEN_LIVE = "C:/Users/hello/AppData/Local/Uoink/index.db"
  E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/ig-native/Scripts/python.exe -B E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/integrator_verify.py --root C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/4c02e121-2b3/gemini --label isolated-cred-negative-01 tests/test_isolated_credential_store.py
  ```
- **Exit Code:** `1`
- **Result:** `9 failed, 1 passed in 0.77s`
- **Observed Failures:**
  - `test_isolated_read`: Failed; looked in `"Uoink"` instead of isolated namespace.
  - `test_isolated_set`: Failed; wrote to ordinary `"Uoink"` service.
  - `test_isolated_delete`: Failed; deleted ordinary `"Uoink"` service entry.
  - `test_absent_key_no_fallback`: Failed; leaked ordinary `"Uoink"` key into isolated reader.
  - `test_profile_separation_same_port`: Failed; leaked calls to ordinary `"Uoink"`.
  - `test_stable_profile_identity_different_ports`: Failed; leaked calls to ordinary `"Uoink"`.
  - `test_isolated_reset_401_path`: Failed; cleared ordinary `"Uoink"` credential.
  - `test_isolated_public_settings`: Failed; queried ordinary `"Uoink"`.
  - `test_isolated_plaintext_migration`: Failed; migrated into ordinary `"Uoink"` instead of isolated namespace.
  - `test_ordinary_legacy_compatibility`: Passed (normal mode baseline).

### 4.2 Corrected Regressions Verification (`isolated-cred-corrected-01`)
Run against repaired `server.py`:
- **Command:**
  ```powershell
  $env:IG_FORBIDDEN_LIVE = "C:/Users/hello/AppData/Local/Uoink/index.db"
  E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/ig-native/Scripts/python.exe -B E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/integrator_verify.py --root C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/4c02e121-2b3/gemini --label isolated-cred-corrected-01 tests/test_isolated_credential_store.py
  ```
- **Exit Code:** `0`
- **Result:** `10 passed in 0.66s`

### 4.3 Full Companion Suites Verification (`iso-c01`)
Run all companion test suites resolved by `git ls-files tests/ | Select-String "settings|isolation|security|credential"`:
- **Command:**
  ```powershell
  $env:IG_FORBIDDEN_LIVE = "C:/Users/hello/AppData/Local/Uoink/index.db"
  E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/ig-native/Scripts/python.exe -B E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/integrator_verify.py --root C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/4c02e121-2b3/gemini --label iso-c01 tests/test_isolated_credential_store.py tests/test_g25_settings_polish.py tests/test_install_isolation.py tests/test_install_isolation_integrator_review.py tests/test_install_isolation_repair.py tests/test_phase4_av5m3_isolation.py tests/security/test_security_findings.py tests/security/test_adversarial_fixtures.py tests/security/test_bench_local.py tests/test_mcp_slug_security.py
  ```
- **Exit Code:** `0`
- **Result:** `107 passed, 1 xfailed, 4 warnings in 14.05s`
- **Notes:** Zero failures across all 10 test files. The single expected failure `test_sec_06_fts_query_non_ascii_dropped` is a pre-existing XFAIL in `test_security_findings.py`.

### 4.4 Documentation Contract Verification (`test-doc-contracts`)
- **Command:**
  ```powershell
  $env:IG_FORBIDDEN_LIVE = "C:/Users/hello/AppData/Local/Uoink/index.db"
  E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/ig-native/Scripts/python.exe -B E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/integrator_verify.py --root C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/4c02e121-2b3/gemini --label test-doc-contracts tests/test_docs_live_contracts.py
  ```
- **Exit Code:** `0`
- **Result:** `10 passed in 1.18s`

---

## 5. Files Changed

1. `server.py`:
   - Added isolated namespace helpers (`_isolated_binding`, `_isolated_keyring_service`, `_keyring_service_name`, `_settings_path`).
   - Hardened `_get_saved_anthropic_key` to query isolated namespace and avoid ordinary/legacy fallback.
   - Hardened `_store_saved_anthropic_key` to write/delete within `_keyring_service_name()`.
   - Updated `_read_settings`, `_write_settings`, and `_migrate_plaintext_anthropic_key` to use `_settings_path()`.
2. `tests/test_isolated_credential_store.py`:
   - New suite containing 10 test cases using `RecordingFakeKeyring`.
   - Assertions enforce zero leaks into ordinary services (`"Uoink"`, `"Yoink"`) in isolated mode.
3. `docs/security.md`:
   - Documented isolated credential namespace format `Uoink-isolated-<hash>`.
   - Documented isolated mode credential CRUD, fallback prevention, port independence, and 401 reset scope.
   - Updated Threat Model table row for Anthropic API key disclosure.
4. `docs/library/RYAN-ISOLATED-CREDENTIAL-WORKER-2026-09-09.md`:
   - This worker delivery report.

---

## 6. Residual Limits & Integrator Handoff

1. **Packaging Rebuild Requirement:** Because `server.py` is bundled into Windows Inno installer builds, any packaged/installed bundle must be rebuilt and resealed before installed verification.
2. **Key Material Safety:** Tests and runtime logs do not print or persist key material.
3. **No Commits:** Worktree remains uncommitted per brief instructions. Integrator/Astra will run independent three-way verification and commit.
