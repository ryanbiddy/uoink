# 3.8.0 release qualification - 2026-09-17 (Fable)

Scope: Ryan's 2026-09-15 decisions stand (unsigned 3.8.0, AT6 disclosed,
Torch 2.8.0 / WhisperX 3.8.6 retained, Claude Desktop "tested with Claude Code"
unless Ryan completes the standard-account session). This note records what
was actually built, installed and run today on branch `release/3.8.0`
(checkout `E:\AI\projects\uoink\checkouts\Yoink-release-3.8.0`). Nothing here
approves publication or a main merge; both remain Ryan's decisions.

## Source

- Base: `5cc6366` (Sep 15, includes the two build.ps1 repairs 85349ea and
  5cc6366 and the origin/main merge 4de33f6).
- `cc5be67` build: recover PEP 639 `License-Expression` in notices generation.
  The Sep 15 build had regenerated THIRD-PARTY-NOTICES.md with 58 UNKNOWN
  licence rows (committed file: 8). pip-licenses 5.0 and the legacy `License`
  field both report UNKNOWN for wheels that declare only an SPDX expression.
  Twenty notices tests pass.
- `27c2fb5` regenerated THIRD-PARTY-NOTICES.md from the build below: every
  licence row equals the hand-reviewed file; only the preamble and the
  source-bound date differ. 8 rows remain UNKNOWN (packages with no licence
  metadata at all: primePy, pyannote-*, pytorch-metric-learning, torchcodec).

## Package

- `build\Uoink-Setup-3.8.0.exe`, 389,561,194 bytes, SHA-256
  `42c98090ee68c0600fb1274979773f01d89872b60b08a2f4533170429419879d`,
  built 2026-09-17 01:02-01:09 PDT with `build.ps1 -Clean` under Windows
  PowerShell 5.1 (no pwsh on this machine). Unsigned review build; the
  signing receipt `Uoink-Setup-3.8.0.exe.signature.json` records
  `release_ready: false`.
- Staged smoke, wizard bitmaps and ISCC completed; the dependency inventory
  matched `requirements-installer-lock.txt` exactly (this check was the one
  that failed on the developer machine before PYTHONNOUSERSITE=1).

## Installed receipts (same account, isolated namespace, never the live index)

Receipt roots under `E:\AI\projects\uoink\installation-receipts\`, produced
with the package-08 instrument `agent_install_observer05.ps1` (Inno
`/VERYSILENT /ISOLATED=1 /PROFILE=<root>\c22\profiles\empty /PORT=18081
/DIR=<root>\app /TASKS=""`) and the adapted package-07 uninstall instrument.

| Root | Package | Result |
|---|---|---|
| Agent Install 09 | candidate-checkout rehearsal build 338fd92e... (cc/living-library-candidate 25bf7c3 + uncommitted build fixes) | install exit 0, files-only verification OK; uninstalled with ordinary effects unchanged |
| Agent Install 10 | Sep 15 release build 82645b48... | install exit 0; helper smoke: /health 200 `ok:true` version 3.8.0 migration 30 in 1.5 s; stop exit 0; uninstalled with ordinary effects unchanged |
| Agent Install 11 | **42c98090...** (this build) | install exit 0, 4 isolated shortcuts verified, files-only verification OK; helper smoke `/health` and `/ping` 200 in 1.4 s, `--isolated-stop` exit 0; MCP stdio handshake: server `uoink 3.8.0`, protocol 2025-11-25, **32 tools, 5 resource templates, 4 prompts** |

Notes: the helper exits with code 1 after `--isolated-stop` because the owned
process is ended with TerminateProcess (`uoink_install_isolation._terminate_owned`);
the stop command's own exit 0 is the pass signal. Three earlier MCP receipts
show prompt_count 0 because the first instrument closed stdin before the
prompts/list response was flushed; preserved with a README. Agent Install 11
remains installed for further observations. The live index
(`%LOCALAPPDATA%\Uoink\index.db`, mtime 2026-09-15 12:39) and the live helper
(pid 18076, started 2026-09-11) were not touched.

Not done: the C22 scenario kit (Review-Kit re-seal for this package hash),
Phase 4 client drivers with Claude Code, browser observation, Claude Desktop.

## Complete tree

Launcher: Astra's `integrator_verify.py` (copied to `_scratchable_integrator_verify.py`),
interpreter `checkouts\Yoink-library\_scratch\ig-native\Scripts\python.exe` (3.14.6, pytest 9.1.1,
mcp 1.28.1), `IG_FORBIDDEN_LIVE` guard on, `tests/library_work_astra/test_phase3_s21.py` excluded as
in every recorded tree. Label `fable-tree-03c`, log and junit under
`_scratchable-tree-03c\` (gitignored). Started 01:10:52, finished 01:34:45 PDT.

**Result: 2,696 passed, 20 failed, 107 errors, 6 skipped, 1 xfailed (AT6, as decided), 13 subtests.**
The previous recorded complete tree (tree09 at 56d9d4c on the candidate) was 2,796 passed / 1 failed.
Every one of the 127 failures and errors falls into four causes; none is a new product defect
observed by the tree, and none was excused or edited:

| Cause | Count | Detail | Proposed disposition (Ryan's call) |
|---|---|---|---|
| A. Proof archive removed from the public tree (e576ec9) | 100 | `test_stage4_validator.py` (90), `test_proof_run.py` ax1 (5), `test_runtime_graph.py` (3), `test_install_receipt_c22_final_oracles.py` (1), `test_install_receipt_p4_kit_repair.py` (1) open `docs/library/proof/<run>` receipts that the release branch no longer carries | Module-level `pytest.skip` when the named proof root is absent, with the reason stated, or keep those tests on the candidate line only |
| B. NLTK backport tests read another checkout's staging | 20 | `test_nltk_pathsec_backport.py` hard-codes `checkouts\Yoink-library\installer\staging\...
ltk` as the upstream 3.10.3 source; that staging now holds the patched `3.10.3+uoink.pathsec1` after today's candidate build, so `prepare_nltk_pathsec_backport.py` refuses it | Point the staging fixture at `vendor/nltk-pathsec/original` (already used by `minimal_valid_source`) or skip when the staged VERSION is not upstream |
| C. Tests require PowerShell 7 (`pwsh`) | 7 | `test_phase4_av5m4a2_binding.py`, `av5m4b6` (2), `av5m4b7`, `aw10`, `aw4` create junctions with `pwsh -Command New-Item -ItemType Junction`; `pwsh` is not installed on this PC (Windows PowerShell 5.1 only) | Install PowerShell 7 for the receipt machine, or run `New-Item -ItemType Junction` through `powershell.exe` |
| D. Stale strict xfail | 1 | `test_sec_06_fts_query_non_ascii_dropped` is `xfail(strict=True)` for SEC-06, but the Unicode search repair (41c0d1d) fixed it: XPASS(strict) | Remove the xfail marker; the assertion now describes the shipped behaviour |

Excluding A-D there are zero failures. The candidate-line run of the same launcher on
`cc/living-library-candidate` (`fable-tree-02`, wrong interpreter) is preserved but not comparable.

## Findings for the backlog

1. The installed embeddable interpreter runs with `import site` active, so a
   user with a Python 3.13 per-user site-packages also has those packages on
   the installed app's path at runtime (package 08 too). The build is now
   immune (PYTHONNOUSERSITE=1); the runtime launchers are not.
2. `build.ps1 -Clean` deletes everything under `build\`, including retained
   review kits; the package-08 installer bytes and Review-Kit-05..08 zips were
   lost that way on the candidate checkout on 2026-09-17 (no other copies on
   disk). Keep kits outside `build\`.
3. Plain `python -m pytest` on this machine produces 16-39 spurious failures
   (children spawned with `-I` cannot see user-site jsonschema/mcp; nltk and
   whisperx are absent from the system interpreter). The only reproducible
   launcher is Astra's `integrator_verify.py` run with the `_scratch\ig-native`
   venv interpreter and `IG_FORBIDDEN_LIVE` set.
