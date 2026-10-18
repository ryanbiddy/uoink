# 3.8.1 release ready for owner review - 2026-09-23

Branch `release/3.8.1` in checkout `E:\AI\projects\uoink\checkouts\Yoink-release-3.8.0`,
based on the 3.8.0 release commit `c766a1c`. Draft PR #270 into `main`, draft GitHub
release `v3.8.1` (id 395313409). Nothing is published or merged, no tag exists, and
auto-merge is off. 3.8.0 (#269, draft release 389447458) was not touched.

## Commits on top of c766a1c

| Commit | What |
|---|---|
| `e9a6189`, `d31ba18` | docs: the 3.8.1 directory-ready brief |
| `563edfc` | Astra: 32 stdio tool titles + four explicit hints (HTTP registry in sync), `.mcpb` 3.8.1 with `privacy_policies`, README and bundle README Privacy sections, six version surfaces 3.8.1, `PUBLISHED_INSTALLER_VERSION` 3.8.0, non-Windows skip markers, `RUNNER~1` readiness fixtures |
| `c6e030f` | dashboard: on a fresh install the Library activity panel collapses to "Library activity appears here after your first few captures." It applies only when a rolling preset reports `no_history` for capture and the shelf journal and the item total is null. Custom intervals, errors and any library with history render as before. Three node-harness tests are in `tests/library_work_astra/test_phase5_dashboard.py` |
| `4eb7b48` | tests: `test_phase6_bc2.py` still pinned the old two-hint dict for `export_cited_range`. This was the only full-tree failure, and it failed on both CI legs |
| `215afd4` | build: `scripts/build-mcpb.ps1` wrote the staged manifest with `Set-Content -Encoding utf8`, which adds a UTF-8 BOM under Windows PowerShell 5.1. The official `mcpb validate` rejects that as invalid JSON. **The published-to-be 3.8.0 bundle has this BOM.** The manifest is now written BOM-free, and `tests/test_mcpb_manifest_no_bom.py` guards it |
| this commit | this note |

## Complete tree

`_scratch\fable_integrator_verify.py` with the `Yoink-library\_scratch\ig-native`
interpreter and `IG_FORBIDDEN_LIVE=%LOCALAPPDATA%\Uoink\index.db`, excluding
`test_phase3_s21.py` as in every recorded tree.

- `rr381-tree-01` at c6e030f: 2,704 passed, 1 failed (bc2, fixed in 4eb7b48), 127 skipped, 1 xfailed.
- **`rr381-tree-02` at 215afd4: 2,707 passed, 0 failed, 0 errors, 127 skipped, 1 xfailed (AT6), 13 subtests.**
  The skips have the same reasons as the 3.8.0 baseline (2,702 / 127 / 1).

## Package

| File | Bytes | SHA-256 |
|---|---|---|
| `build\Uoink-Setup-3.8.1.exe` (`build.ps1` under Windows PowerShell 5.1 via Start-Process, no `-Clean`; staged smoke OK; unsigned review build, `release_ready: false`) | 389,574,015 | `9e8fde36e9b33efda09af4173a0a7beb1316ae561a255c517e7e01bcecb6699d` |
| `dist\uoink-3.8.1.mcpb` (`scripts\build-mcpb.ps1`, rebuilt from current sources) | 73,684 | `6ee41ead28e91897f877b28aaa7b7d66396f45df08ae8637d4230cd444e1eaad` |
| `build\release-3.8.0\Uoink-Setup-3.8.0.exe` (backup of the shipped 3.8.0 asset, taken before building) | 389,572,901 | `a5cbdaacf99db9c165903974ae1b315991c62666cc6d2011e25cdeae29b469fc` |

The installer was built from the 4eb7b48 working tree. 215afd4 changes only
`scripts/build-mcpb.ps1`, a test and CHANGELOG, and none of those ship. The staged
`server.py`, `uoink_mcp*.py`, `VERSION`, `helper/_version.py` and dashboard HTML were
compared with the sources and are byte-identical.

`npx @anthropic-ai/mcpb validate` (CLI 2.1.2) **passes** for the staged manifest and
for the manifest unpacked from the `.mcpb`. It reports one warning: the icon should
ideally be 512x512. The bundle has five entries: manifest (byte-identical to
`.mcpb/manifest.json`, version 3.8.1, 32 tools, `privacy_policies`), both Python files,
the README and the icon, all equal to their sources. The first 3.8.1 pack, before
the fix, failed validation because of the BOM. It is kept at
`_scratch\uoink-3.8.1.bom-attempt-01.mcpb` and `build\mcpb\uoink.bom-attempt-01`.

## Isolated install receipt

`E:\AI\projects\uoink\installation-receipts\Agent Install 13`

1. `instruments\agent_install_observer05.ps1` (unchanged) with `/ISOLATED=1`, an empty
   profile and `/PORT=18081`. Exit 0. Inno post-install verification reported "bundled
   files verified for 3.8.1", and ordinary effects were unchanged.
2. `instruments\stdio_tools13.py` ran the installed `app\python\python.exe app\uoink_mcp.py`
   over stdio. serverInfo was `uoink 3.8.1` and there are **32 tools, each with a title
   and all four boolean hints**. True counts: read-only 20, destructive 6, idempotent 26,
   open-world 8 (`stdio-tools-list.json`).
3. `instruments\helper_smoke13.py`: `GET /health` returned 200 `ok:true` **version 3.8.1**,
   migration 30, in 1.5 s. `--isolated-stop` exited 0. While the helper was up,
   Playwright (headless Chromium) opened `http://127.0.0.1:18081/dashboard`. The
   Library tab showed the new empty state: the message is visible and the tiles,
   coverage, controls and sections are hidden (`dashboard-library-build-9e8fde36.png`,
   `-panel.png`, `.json`).
4. No process from the isolated app dir remained after the stop.
5. Uninstall used `instruments\uninstall_isolated_receipt13.ps1`. Attempt 01 refused,
   because the pinned `unins000.exe` hash is from the 3.8.0 builds and Inno 6.7.3
   embeds ProductVersion 3.8.1. The instrument now pins the observed 3.8.1 hash
   `06d1693e...` plus its version resource. The rerun exited 0: the isolated uninstall
   key was removed, ordinary effects were unchanged and the profile was kept.
   `app\token.txt` was left behind (it is not in `[UninstallDelete]`) and was removed
   by hand. See the note in the uninstall folder.

The live helper on port 5179 (pid 10644, started 2026-09-17) kept running. It was
touched only by one read-only `GET /health` after the uninstall.

## CI (PR #270)

At 215afd4 the four required checks (extension static, backend static, doc accuracy,
bash lint) **pass**.

- `stdlib tests (windows-latest)`: 1 failed, 2,703 passed, 5 errors. All six are
  `test_phase5_measurements{,2,3}.py`: the 548-item synthetic activity read returns
  `ok:false` on the hosted runner (2 s service deadline). These pass in both local
  trees and failed identically on #269. The `RUNNER~1` readiness failures from #269
  are gone.
- `stdlib tests (ubuntu-latest)`: the `cannot instantiate 'WindowsPath'` crash is
  fixed, and the leg now runs to completion: 2,441 passed, 167 failed, 16 errors. The
  failures are the Windows-native features (vault mirror handles and mutexes,
  install isolation, C22/P4 receipt kits, AW acceptance that drives the mirror) plus
  the same phase5 measurements. The product ships for Windows only. Gating these
  per module is follow-up work, not a 3.8.1 change.

## Owner steps

1. Publish **3.8.0 first** (draft 389447458), then merge #269.
2. Merge #270 after #269, and resolve any conflicts on `main`.
3. Before publishing 3.8.1: set the CHANGELOG `[3.8.1]` date (the release notes link
   `CHANGELOG.md#381---unreleased`, so update that anchor too). If `main` moved, point
   the draft's `target_commitish` at the commit you want tagged.
4. Publish the draft `v3.8.1`. Then bump `PUBLISHED_INSTALLER_VERSION` (`extension/setup.js`)
   and `PUBLISHED_VERSION` (`tests/test_installer_download_accuracy.py`) to 3.8.1.
5. Directory submission: compare the README Privacy section with the live
   https://uoink.app/privacy. Astra could not read the live page, so parity is unverified.
6. Optional: the 3.8.0 `.mcpb` asset fails `mcpb validate` because of the BOM. Consider
   replacing it with a BOM-free repack of the same files before publishing 3.8.0. That
   is the owner's call, and this task did not touch it.
