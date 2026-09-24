# Installed Payload Classification Repair Review

**Date:** 2026-09-09  
**Reviewer:** Gemini (Worker in local multi-model control room)  
**Worktree:** `C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\73720c08-178\gemini`  
**Reference Brief:** `E:\AI\projects\uoink\checkouts\Yoink-library\docs\library\RYAN-INSTALLED-PAYLOAD-REPAIR-BRIEF-2026-09-09.md`  

---

## 1. Executive Summary and Problem Statement

Before Setup execution, source inspection revealed a C22 verifier instrument defect:
- The package's 142 source bindings represent compiler inputs.
- One compiler input is `installer/upgrade_prep.ps1`, whose Inno Setup directive is explicitly `dontcopy`. It is an ordinary-upgrade script deliberately skipped by isolated `PrepareToInstall`, and is not an installed application file.
- The verifier (`verify_installed_bindings` in `scripts/install_receipt/receipt_integrity.py`) incorrectly required all 142 compiler inputs to be present inside the installed application directory.
- Installing `upgrade_prep.ps1` solely to appease the verifier is forbidden.

Per Ryan's repair brief, Gemini was assigned to:
1. Repair `scripts/install_receipt/receipt_integrity.py` to recognize compiler-only payload roles while preserving all existing checks and 142-binding counts.
2. Add an independent test suite in `tests/test_install_receipt_payload_roles.py`.
3. Verify changes using the guarded native runner `_scratch/integrator_verify.py` with worker label `payload-role-w1`.
4. Maintain strict operational boundaries (no edits to existing tests, Inno scripts, product code, manifest defaults, helper behavior, or proof archives; no Setup execution; no port 5179 or live index access; no commits or branch merges).

---

## 2. Changes Implemented

### A. Verifier Repair: `scripts/install_receipt/receipt_integrity.py`

`verify_installed_bindings(app, sealed)` was updated with the following bounded logic:
1. **Binding Count Preservation:** Retains strict verification that `len(rows) == 142`. If the row count differs, `"expected 142 package source bindings"` is reported.
2. **Compiler-Only Role Authorization (`install_role="installer-only"`):**
   - Authorized **strictly and exclusively** for:
     - `staged_path`: `upgrade_prep.ps1`
     - `source_path`: `installer/upgrade_prep.ps1`
     - Valid 40-hex lowercase Git commit/blob (`source_git_blob`)
     - Valid 64-hex lowercase SHA-256 digest (`checkout_and_staged_sha256`)
     - Non-escaping path under app root
   - When verified, this row is recorded separately in `compiler_only_row` (and `installer_only_row`) and is **not** required to exist inside the installed app directory.
3. **Prevention of Improper Exemption:**
   - Any attempt to mark application files (such as `server.py`, `index.py`, or `uoink_tray.py`) with `install_role="installer-only"` is explicitly rejected (`"cannot mark application file as installer-only: <path>"`). The file remains an installed-file requirement.
   - Any escaping path marked `installer-only` is rejected with `"cannot exempt escaping path"` alongside `"binding escapes installed app"`.
   - Traversal attempts (`..` in path components) are rejected.
4. **Rejection of Unknown Roles and Malformed Hashes:**
   - Unknown roles (e.g. `"unknown"`, `"optional"`, `"exempt"`, `"compiler-only"`, or non-string values) are rejected with `"rejected unknown install_role"`.
   - Missing or non-64-hex digests generate `"invalid checkout_and_staged_sha256"`.
   - Malformed Git blobs generate `"invalid source_git_blob"`.
5. **Legacy Row Fidelity:**
   - Unlabelled rows (`install_role is None`) or rows with `install_role="installed"` remain strict installed-file requirements. If a legacy unlabelled `upgrade_prep.ps1` is missing from the app, `"missing installed input: upgrade_prep.ps1"` is recorded.
6. **Accurate Reporting Without False Claims:**
   - The result dictionary reports:
     - `"compiler_bindings"`: 142
     - `"installed_files_checked"`: actual count of installed files verified (141 when 1 compiler-only row is present; 142 in legacy complete installations)
     - `"files_checked"`: 141 (or 142), matching actual installed files and avoiding false claims
     - `"compiler_only_row"`: dict of the validated compiler-only row (or `None`)
     - `"problems"`: list of error descriptions
     - `"ok"`: `True` if no problems exist, else `False`
   - Clearly documented that no status constitutes a Setup or upgrade-execution receipt.

### B. Independent Test Suite: `tests/test_install_receipt_payload_roles.py`

Created an independent test suite with 34 test cases covering:
1. `test_positive_exact_compiler_only`: 142 compiler bindings, 1 compiler-only `upgrade_prep.ps1` omitted from app, 141 installed files matching hashes -> passes, reports 142 compiler bindings, 141 installed files checked, and explicit `compiler_only_row`.
2. `test_positive_legacy_installed`: 142 legacy unlabelled bindings all present in app -> passes, reports 142 installed files checked, `compiler_only_row is None`.
3. `test_legacy_upgrade_prep_missing_fails`: unlabelled `upgrade_prep.ps1` missing from app -> fails with `"missing installed input: upgrade_prep.ps1"`.
4. `test_omitted_runtime_bytes`: missing application file -> fails with `"missing installed input"`.
5. `test_changed_runtime_bytes`: modified file content on disk -> fails with `"installed input hash mismatch"`.
6. `test_attempts_to_exempt_another_file`: parameterized over `module_000.py` and `server.py` -> fails with `"cannot mark application file as installer-only"`.
7. `test_traversal_and_escaping_rejected`: path traversal / escaping -> fails with `"escapes"`.
8. `test_attempt_to_exempt_escaping_path`: escaping path marked `installer-only` -> fails with `"cannot exempt escaping path"` and `"escapes"`.
9. `test_unknown_roles_rejected`: parameterized over `"unknown"`, `"exempt"`, `"optional"`, `"compiler-only"`, `123` -> fails with `"rejected unknown install_role"`.
10. `test_invalid_sha256_rejected`: parameterized over truncated, malformed, non-hex, empty, and non-string digests -> fails with `"invalid checkout_and_staged_sha256"`.
11. `test_invalid_blob_on_compiler_only_rejected`: parameterized over missing, truncated, 64-hex, and non-hex blobs -> fails with `"invalid source_git_blob"`.
12. `test_invalid_blob_on_installed_row_rejected`: malformed blob on installed row -> fails with `"invalid source_git_blob"`.
13. `test_incomplete_binding_counts_rejected`: parameterized over 141 rows (-1), 143 rows (+1), and 0 rows (-142) -> fails with `"expected 142 package source bindings"`.
14. `test_installer_only_wrong_source_path_rejected`: `source_path != "installer/upgrade_prep.ps1"` -> fails with `"invalid compiler-only source_path"`.
15. `test_reporting_no_false_claim_of_142_installed_files`: validates exact counts: `compiler_bindings == 142`, `files_checked == 141`, `installed_files_checked == 141`, `files_checked != 142`.

---

## 3. Verification Evidence

### Guarded Native Runner Verification (`payload-role-w1`)

Executed command:
```powershell
python E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\integrator_verify.py `
    --root C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\73720c08-178\gemini `
    --label payload-role-w1 `
    tests/test_install_receipt_payload_roles.py `
    tests/test_install_receipt_c22_integrator_oracles.py::test_binding_checks_reject_missing_or_escaping_compiler_inputs
```

Output:
```text
START tests
tests exit 0 
...................................                                      [100%]
35 passed in 6.04s
```

`_scratch/payload-role-w1/results.json`:
```json
[
  {
    "name": "tests",
    "command": [
      "C:\\Python314\\python.exe",
      "-B",
      "-m",
      "pytest",
      "-q",
      "-ra",
      "--tb=short",
      "-p",
      "no:cacheprovider",
      "-p",
      "ig_paths",
      "tests/test_install_receipt_payload_roles.py",
      "tests/test_install_receipt_c22_integrator_oracles.py::test_binding_checks_reject_missing_or_escaping_compiler_inputs",
      "--basetemp=C:\\Users\\hello\\AppData\\Local\\AgentControlRoom\\worktrees\\uoink-library\\73720c08-178\\gemini\\_scratch\\payload-role-w1-0",
      "--junitxml=C:\\Users\\hello\\AppData\\Local\\AgentControlRoom\\worktrees\\uoink-library\\73720c08-178\\gemini\\_scratch\\payload-role-w1\\tests.xml"
    ],
    "exit": 0,
    "log": "C:\\Users\\hello\\AppData\\Local\\AgentControlRoom\\worktrees\\uoink-library\\73720c08-178\\gemini\\_scratch\\payload-role-w1\\tests.log"
  }
]
```

All 35 tests passed cleanly with exit code 0 under the audit guard.

---

## 4. Operational Boundaries and Invariants Observed

- **Allowed Files:** Only `scripts/install_receipt/receipt_integrity.py`, `tests/test_install_receipt_payload_roles.py`, and this review report were modified or created.
- **No Existing Test Edits:** `tests/test_install_receipt_c22_integrator_oracles.py` and all other existing tests were untouched.
- **No Inno / Product Code Edits:** No installer scripts (`.iss`), product runtime modules, manifest defaults, or proof archives were altered.
- **No Execution / Credentials:** No Setup executable, original helper, model process, live credential store, or external network calls were made.
- **Port 5179 Preserved:** Port 5179 was neither bound nor contacted.
- **Git State:** Executed strictly within the assigned Git worktree; no commits created and no branches merged.

---

## 5. Handoff to Control Room and Astra

1. **Astra Task:** Astra owns producing the new package seal entry with `install_role="installer-only"` for `upgrade_prep.ps1` from Inno's `dontcopy` entry, adapting outer observation checks, and matching the installed payload inventory against Inno's destination list.
2. **Integrator Task:** Integrator can merge worker Gemini's branch and run `payload-role-c1` on the checkout tree.
