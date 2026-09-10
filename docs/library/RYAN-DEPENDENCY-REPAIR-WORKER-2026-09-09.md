# Installer Dependency Repair Worker Report

**Worker:** gemini  
**Worktree:** `C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\4d4cc9ce-a39\gemini`  
**Branch:** `control-room/4d4cc9ce-a39-gemini`  
**Date:** 2026-09-09  
**Status:** Complete in worktree. No commits created. Ready for integrator / Astra three-way apply and disposable Python 3.11 resolution.

---

## 1. Executive Summary

This report documents the implementation of the four proposed dependency pin updates in the private worktree as specified in `docs/library/RYAN-DEPENDENCY-REPAIR-BRIEF-2026-09-09.md`:

1. **Pillow**: Bumped from `10.4.0` to `12.3.0`
2. **MCP**: Bumped from `1.27.1` to `1.28.1`
3. **cryptography**: Bumped from `49.0.0` to `50.0.1`
4. **nltk**: Bumped from `3.10.0` to `3.10.3`

All four pin updates were synchronized across:
- Direct build script pins in `build.ps1` (`$PILLOW_VERSION = '12.3.0'`, `$MCP_VERSION = '1.28.1'`)
- Source requirements in `requirements.txt` (`mcp==1.28.1`, `Pillow==12.3.0`)
- Full installer runtime lock in `requirements-installer-lock.txt` (exact pins for all four packages)
- Exact-version unit assertions in `tests/test_installer_dependency_lock.py` (`locked["pillow"] == "12.3.0"` and `locked["mcp"] == "1.28.1"`, preserving strict equality assertions without relaxation)
- Current build documentation version rows in `docs/build-installer.md`
- Committed third-party notice version rows in `THIRD-PARTY-NOTICES.md`

All worktree checks pass under the guarded native runner (23/23 passed). No installer was generated, no shared environments modified, and no commits were created.

---

## 2. Safety & Operational Boundary Compliance

In strict accordance with the brief instructions:
- **No Subagents:** Executed directly in the primary agent context without spawning subagents.
- **Source Written Early:** Code and documentation changes written directly in the worktree.
- **No Commits:** Working tree left uncommitted for clean raw diff / three-way application.
- **No Build / Packaging Alterations:** Did not execute `build.ps1`, compile Inno Setup installers, or regenerate the installer package.
- **No Shared Staging/Verifier Modifications:** Did not touch shared staging or verifier environments.
- **No Network / External Downloads:** No wheels, models, media, or payloads downloaded.
- **No Credential Access:** Did not inspect or query real OS keyring credentials or Anthropic API keys.
- **No Forbidden Endpoints:** Did not access the live database index (`%LOCALAPPDATA%\Uoink\index.db`) or port 5179. Guarded runner enforced `IG_FORBIDDEN_LIVE`.
- **No Paid API Invocations:** Zero external model or paid API calls.
- **Test Integrity Preserved:** Acceptance behavior assertions untouched, no test cases skipped, lock inventory validation checks intact, and receipt fixtures unaltered.

---

## 3. Verification & Evidence

All checks were executed using the guarded native runner from the checkout:
`docs/library/proof/ryan-corrected-01-2026-09-09/integrator_verify.py`

### 3.1 Baseline Run (`baseline-check-ig2`)
Executed prior to changes:
- **Command:**
  ```powershell
  $env:IG_FORBIDDEN_LIVE = Join-Path $env:LOCALAPPDATA 'Uoink\index.db'
  $env:PYTHONDONTWRITEBYTECODE = '1'
  & 'E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\ig-native\Scripts\python.exe' -B `
    'docs/library/proof/ryan-corrected-01-2026-09-09/integrator_verify.py' `
    --root (Get-Location).Path --label baseline-check-ig2 `
    tests/test_installer_dependency_lock.py `
    tests/test_installer_files_complete.py `
    tests/test_installer_download_accuracy.py `
    tests/test_docs_live_contracts.py
  ```
- **Exit Code:** `0`
- **Result:** `23 passed in 3.35s`

### 3.2 Repaired Worktree Verification (`dep-repair-g1`)
Executed after applying the four pin updates:
- **Command:**
  ```powershell
  $env:IG_FORBIDDEN_LIVE = Join-Path $env:LOCALAPPDATA 'Uoink\index.db'
  $env:PYTHONDONTWRITEBYTECODE = '1'
  & 'E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\ig-native\Scripts\python.exe' -B `
    'docs/library/proof/ryan-corrected-01-2026-09-09/integrator_verify.py' `
    --root (Get-Location).Path --label dep-repair-g1 `
    tests/test_installer_dependency_lock.py `
    tests/test_installer_files_complete.py `
    tests/test_installer_download_accuracy.py `
    tests/test_docs_live_contracts.py
  ```
- **Exit Code:** `0`
- **Result:** `23 passed in 3.18s`

### 3.3 Test Suite Breakdown

| Test Suite | Passed | Failed | Description |
|---|---|---|---|
| `tests/test_installer_dependency_lock.py` | 4 | 0 | Verifies lock completeness, exact pins for Pillow 12.3.0 and MCP 1.28.1, notice inventory parity, range/duplicate rejection, drift detection, and build script constraint wiring. |
| `tests/test_installer_files_complete.py` | 3 | 0 | Verifies all first-party reachable imports and CLI/watchdog scripts are staged and packaged. |
| `tests/test_installer_download_accuracy.py` | 5 | 0 | Verifies published installer links, current README/docs asset names, manual install commands, and release checklists. |
| `tests/test_docs_live_contracts.py` | 11 | 0 | Verifies build.ps1 version variables match `docs/build-installer.md`, live MCP and HTTP registry counts, public probe schemas, and security model docs. |
| **Total** | **23** | **0** | **100% Passing** |

---

## 4. Remaining Risk Analysis & Non-Clean Vulnerability Audit

This update **does not declare a clean vulnerability audit**. The following residual findings and upstream architectural limits remain and require ongoing release tracking:

1. **Lightning 2.6.5 Upstream-Unfixed:**
   `lightning==2.6.5` remains pinned and has unpatched upstream CVE/GHSA advisories. The anomalous `2022.6.15` fixed-version event in advisory databases represents historical tagging noise rather than an actual resolution for 2.6.5. Upstream Lightning has not published a clean fix compatible with this dependency branch.
2. **WhisperX 3.8.6 Dependency Boundaries:**
   `whisperx==3.8.6` strictly constrains the PyTorch and HuggingFace ecosystem:
   - Pins `torch==2.8.0` (and corresponding torchaudio 2.8.0, torchvision 0.23.0, torchcodec 0.7.0).
   - Constrains `huggingface-hub < 1.0` (pinned to `0.36.2`).
   - Incompatible with `transformers >= 5.x` (pinned to `4.57.6`).
   These tight bounds prevent upgrading torch, transformers, or huggingface-hub without upstream WhisperX breaking changes or architectural redesign.
3. **PyAnnote VAD Checkpoint Loader Reachability:**
   Gemini's previous triage claim that ordinary transcription bypasses every checkpoint loader was incorrect and is explicitly retracted:
   - WhisperX 3.8.6 defaults to PyAnnote voice activity detection (VAD).
   - PyAnnote VAD loads its packaged checkpoint artifact at `assets/pytorch_model.bin`.
   - Consequently, checkpoint loading code paths *are* reachable during standard execution when VAD is engaged.
   - This path must remain in all threat models and release notes as a documented boundary.
4. **Environment Isolation Context:**
   The native verification environment (`Python 3.14.6`) executes the test harnesses and live contract guards, but does not prove binary wheel compatibility for the target Windows CPython 3.11 embeddable distribution. Astra will resolve the proposed graph using a disposable Python 3.11 environment before formal acceptance.

---

## 5. Files Changed

| File | Changes |
|---|---|
| `build.ps1` | Updated `$PILLOW_VERSION = '12.3.0'` and `$MCP_VERSION = '1.28.1'` |
| `requirements.txt` | Updated `mcp==1.28.1` and `Pillow==12.3.0` |
| `requirements-installer-lock.txt` | Updated full lock entries: `cryptography==50.0.1`, `mcp==1.28.1`, `nltk==3.10.3`, `pillow==12.3.0` |
| `tests/test_installer_dependency_lock.py` | Updated unit assertions: `assert locked["pillow"] == "12.3.0"` and `assert locked["mcp"] == "1.28.1"` |
| `docs/build-installer.md` | Updated runtime inventory table rows for Pillow (12.3.0) and MCP Python SDK (1.28.1) |
| `THIRD-PARTY-NOTICES.md` | Updated committed notice inventory rows for cryptography (50.0.1), mcp (1.28.1), nltk (3.10.3), and pillow (12.3.0) |
| `docs/library/RYAN-DEPENDENCY-REPAIR-WORKER-2026-09-09.md` | Created this worker delivery report |

---

## 6. Exact Unified Git Diff

```diff
diff --git a/THIRD-PARTY-NOTICES.md b/THIRD-PARTY-NOTICES.md
index 3073e83..6513fbe 100644
--- a/THIRD-PARTY-NOTICES.md
+++ b/THIRD-PARTY-NOTICES.md
@@ -25,7 +25,7 @@ This file is generated from the installed dependency tree (source: pip-licenses)
 | colorama | 0.4.6 | BSD License | https://github.com/tartley/colorama |
 | colorlog | 6.11.0 | MIT License | https://github.com/borntyping/python-colorlog |
 | contourpy | 1.3.3 | BSD License | https://github.com/contourpy/contourpy |
-| cryptography | 49.0.0 | UNKNOWN | https://github.com/pyca/cryptography |
+| cryptography | 50.0.1 | UNKNOWN | https://github.com/pyca/cryptography |
 | ctranslate2 | 4.8.1 | MIT | https://opennmt.net |
 | cycler | 0.12.1 | BSD License | https://matplotlib.org/cycler/ |
 | defusedxml | 0.7.1 | Python Software Foundation License | https://github.com/tiran/defusedxml |
@@ -62,14 +62,14 @@ This file is generated from the installed dependency tree (source: pip-licenses)
 | markdown-it-py | 4.2.0 | MIT License | https://github.com/executablebooks/markdown-it-py |
 | MarkupSafe | 3.0.3 | UNKNOWN | https://github.com/pallets/markupsafe/ |
 | matplotlib | 3.11.1 | Python Software Foundation License | https://matplotlib.org |
-| mcp | 1.27.1 | MIT License | https://modelcontextprotocol.io |
+| mcp | 1.28.1 | MIT License | https://modelcontextprotocol.io |
 | mdurl | 0.1.2 | MIT License | https://github.com/executablebooks/mdurl |
 | more-itertools | 11.1.0 | UNKNOWN | https://github.com/more-itertools/more-itertools |
 | mpmath | 1.3.0 | BSD License | http://mpmath.org/ |
 | multidict | 6.7.1 | Apache License 2.0 | https://github.com/aio-libs/multidict |
 | narwhals | 2.24.0 | UNKNOWN | https://github.com/narwhals-dev/narwhals |
 | networkx | 3.6.1 | UNKNOWN | https://networkx.org/ |
-| nltk | 3.10.0 | Apache Software License | https://www.nltk.org/ |
+| nltk | 3.10.3 | Apache Software License | https://www.nltk.org/ |
 | numpy | 2.4.6 | UNKNOWN | https://numpy.org |
 | omegaconf | 2.3.1 | BSD License | https://github.com/omry/omegaconf |
 | onnxruntime | 1.27.0 | MIT License | https://onnxruntime.ai |
@@ -84,7 +84,7 @@ This file is generated from the installed dependency tree (source: pip-licenses)
 | optuna | 4.9.0 | MIT License | https://optuna.org/ |
 | packaging | 26.2 | UNKNOWN | https://github.com/pypa/packaging |
 | pandas | 3.0.5 | BSD License | https://pandas.pydata.org |
-| pillow | 10.4.0 | Historical Permission Notice and Disclaimer (HPND) | https://python-pillow.org |
+| pillow | 12.3.0 | Historical Permission Notice and Disclaimer (HPND) | https://python-pillow.org |
 | primePy | 1.3 | MIT License | https://github.com/janaindrajit/primePy |
 | propcache | 0.5.2 | Apache Software License | https://github.com/aio-libs/propcache |
 | protobuf | 7.35.1 | 3-Clause BSD License | https://developers.google.com/protocol-buffers/ |
diff --git a/build.ps1 b/build.ps1
index a684a3b..727e64d 100644
--- a/build.ps1
+++ b/build.ps1
@@ -112,10 +112,10 @@ $YTDLP_VERSION  = '2026.07.04'
 # Pillow is used for the multimodal paste-corpus generator (resize +
 # JPEG-recompress + base64-encode the embedded screenshots). Pinned to
 # a recent stable; bump at release-prep time after testing.
-$PILLOW_VERSION = '10.4.0'
+$PILLOW_VERSION = '12.3.0'
 # Official Model Context Protocol Python SDK for the stdio MCP server.
 # Also pinned in requirements.txt for dev installs and docs.
-$MCP_VERSION    = '1.27.1'
+$MCP_VERSION    = '1.28.1'
 # Windows Credential Manager wrapper for Anthropic API key storage.
 # Also pinned in requirements.txt for dev installs and docs.
 $KEYRING_VERSION = '25.7.0'
diff --git a/docs/build-installer.md b/docs/build-installer.md
index a5caa45..9d80d86 100644
--- a/docs/build-installer.md
+++ b/docs/build-installer.md
@@ -112,8 +112,8 @@ installed into the embeddable Python with the exact pip versions below.
 | Python embeddable | 3.11.9 (amd64) | Locked in `build.ps1` | Current embedded runtime; any bump requires a clean installer build and smoke test. |
 | ffmpeg | n7.1 BtbN win64 LGPL | Locked in `build.ps1` | Pinned to one versioned BtbN archive and SHA256. |
 | yt-dlp | 2026.07.04 | (pip) | Pinned via `pip install yt-dlp==2026.07.04`. Bump after compatibility-testing a new release. |
-| Pillow | 10.4.0 | (pip) | Drives the multimodal paste-corpus generator (resize + JPEG-recompress + base64-encode screenshots for clipboard embedding). Pinned via `pip install Pillow==10.4.0`. |
-| MCP Python SDK | 1.27.1 | (pip) | Official Model Context Protocol Python SDK. Powers the stdio MCP server. Pinned via `pip install mcp==1.27.1` and `requirements.txt`. |
+| Pillow | 12.3.0 | (pip) | Drives the multimodal paste-corpus generator (resize + JPEG-recompress + base64-encode screenshots for clipboard embedding). Pinned via `pip install Pillow==12.3.0`. |
+| MCP Python SDK | 1.28.1 | (pip) | Official Model Context Protocol Python SDK. Powers the stdio MCP server. Pinned via `pip install mcp==1.28.1` and `requirements.txt`. |
 | keyring | 25.7.0 | (pip) | Stores the BYO Anthropic API key in Windows Credential Manager. Pinned via `pip install keyring==25.7.0` and `requirements.txt`. |
 | pystray | 0.19.5 | (pip) | Windows tray integration. |
 | pywebview | 5.4 | (pip) | Local desktop shell. |
diff --git a/requirements-installer-lock.txt b/requirements-installer-lock.txt
index 8439092..1c1bc0c 100644
--- a/requirements-installer-lock.txt
+++ b/requirements-installer-lock.txt
@@ -30,7 +30,7 @@ clr_loader==0.2.10
 colorama==0.4.6
 colorlog==6.11.0
 contourpy==1.3.3
-cryptography==49.0.0
+cryptography==50.0.1
 ctranslate2==4.8.1
 cycler==0.12.1
 defusedxml==0.7.1
@@ -67,14 +67,14 @@ Mako==1.3.12
 markdown-it-py==4.2.0
 MarkupSafe==3.0.3
 matplotlib==3.11.1
-mcp==1.27.1
+mcp==1.28.1
 mdurl==0.1.2
 more-itertools==11.1.0
 mpmath==1.3.0
 multidict==6.7.1
 narwhals==2.24.0
 networkx==3.6.1
-nltk==3.10.0
+nltk==3.10.3
 numpy==2.4.6
 omegaconf==2.3.1
 onnxruntime==1.27.0
@@ -89,7 +89,7 @@ opentelemetry-semantic-conventions==0.65b0
 optuna==4.9.0
 packaging==26.2
 pandas==3.0.5
-pillow==10.4.0
+pillow==12.3.0
 primePy==1.3
 propcache==0.5.2
 protobuf==7.35.1
diff --git a/requirements.txt b/requirements.txt
index 1b148da..f268eef 100644
--- a/requirements.txt
+++ b/requirements.txt
@@ -1,6 +1,6 @@
-mcp==1.27.1
+mcp==1.28.1
 keyring==25.7.0
-Pillow==10.4.0
+Pillow==12.3.0
 pystray==0.19.5
 pywebview==5.4
 pythonnet==3.0.5
diff --git a/tests/test_installer_dependency_lock.py b/tests/test_installer_dependency_lock.py
index 43d9af8..f5aa7a8 100644
--- a/tests/test_installer_dependency_lock.py
+++ b/tests/test_installer_dependency_lock.py
@@ -21,8 +21,8 @@ def test_installer_lock_is_complete_and_exact() -> None:
 
     assert len(locked) >= 100
     assert locked["yt-dlp"] == "2026.7.4"
-    assert locked["pillow"] == "10.4.0"
-    assert locked["mcp"] == "1.27.1"
+    assert locked["pillow"] == "12.3.0"
+    assert locked["mcp"] == "1.28.1"
     assert locked["faster-whisper"] == "1.2.1"
     assert locked["whisperx"] == "3.8.6"
     assert locked["torch"] == "2.8.0"
```
