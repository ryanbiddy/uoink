# C22 final oracle repair worker (Grok)

Worker: grok
Worktree: `C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\6a890eee-616\grok`
Branch: `control-room/6a890eee-616-grok`
Base HEAD: `3347be8822246e013aafa7283add92164ae7adcd`
(`Library: verify bundled entry and require complete C22 recovery oracles`)

Status: **source complete in this worktree**. Astra independently verifies and
integrates. This worker did not merge, commit, push, run Setup.exe, uninstall,
contact port 5179 (including negative probes), open or hash the live index,
set API keys, enable `librarian_apply_enabled`, fetch external libraries, run
a model/client, or use subagents.

No existing test, assertion, fixture, skip or parameter edits. The three
imported kit files stayed frozen:

- `tests/test_install_receipt_c22_kit.py`
- `tests/test_install_receipt_c22_kit_repair.py`
- `tests/test_install_receipt_c22_scenario_truth.py`

Every existing acceptance assertion/fixture stayed frozen. Production files
stayed unchanged. Owned only non-p4 modules under `scripts/install_receipt`,
NEW `tests/test_install_receipt_c22_final_oracles.py`, this report, and the
worker proof archive.

`IG_FORBIDDEN_LIVE` was bound to
`C:\Users\hello\AppData\Local\Uoink\index.db` before wrapper launch. Apply
remains false. Source or staged observations never earn installed credit.
Failed and unexecuted stay separate. A stub status flag is not acceptance.

## Input

- Brief: `docs/library/RYAN-C22-FINAL-ORACLE-REPAIR-BRIEF-2026-09-09.md`
- Archived third input: `docs/library/proof/ryan-c22-review-03-input-2026-09-09/`
  - `original.patch` SHA256 `60d00f827282df8f44204a0608a6921380666b92d4863c7b666c239d9fbed1db` (334499 bytes)
  - applied with `git apply --3way --whitespace=nowarn` (direct application; all paths were new)
- Sealed native runtime: `E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/ig-native/Scripts/python.exe`
  Python 3.14.6
- Committed wrapper: `docs/library/proof/ryan-corrected-01-2026-09-09/integrator_verify.py`
  SHA256 `280cfdad5ebc56a1748ce53cf9c6850335b7046ab1b9998f7cdd9a196c44e7e2`
- Sealed bindings consumed, not invented:
  `docs/library/proof/candidate-package-02-2026-09-09/source-bindings.json`
  SHA256 `da47f187ab099aaba82283b91993e7a19348eedb7cbadefdb8a168adfd871a75`
  `package-manifest.json`
  SHA256 `a41434b8c97b815bbe14f9bf4e000b406f612e7bf71545548ed2796e022fcb5e`
  installer_source_sha `8a607c37095cb4f3b66d2aee285cfb710ab5e586` (40-hex)
  package_sha256 `d024baf5e27fc15b292c17c3c7a551b41c9564378ce352e81ed25a9908bfd5b1` (64-hex)
  package_bytes `339059131`

This report was written before the guarded rerun and is completed with
measured evidence below.

## Prior evidence (original observations, not this worker's credit)

Third worker `7a3c3ae2` reports **41 passed / two frozen failures in 666.25 s**.
Those two frozen failures remain and are still the only union failures:

1. `tests/test_install_receipt_c22_kit.py::test_plan_inno_does_not_execute`
   asserts obsolete `/ISOLATEDPROFILE=`. No test edit is authorized. The agreed
   isolation interface is `/ISOLATED=1 /PROFILE=<root> /PORT=<non5179> /DIR=<app>`
   plus `/NOCLOSEAPPLICATIONS /NORESTARTAPPLICATIONS`.
2. `tests/test_install_receipt_c22_kit.py::test_synthetic_helper_scenarios_and_verdict`
   expects an all-pass stub-helper result that cannot satisfy real routes.
   Original observation was `one_off_capture` status `fail`. This union's stub
   run failed at `manual_first` (`episode_id` not found / `/podcasts/feeds`
   404). Same frozen stub-helper expectation; not a test edit.

Astra's independent original union is separate and must be preserved before
integration. No earlier status (9c866bb0 stub 19-pass, 6accc421 26-pass/2-fail,
7a3c3ae2 41-pass/2-fail) supplies installed credit.

## Product defects (named before any production-repair proposal)

Production files were not edited. These are measured or already-known product
facts, not permission to weaken oracles.

1. **Current `server.main` requires `uoink_install_isolation.current_process_executable`.**
   Overlaying the archived first isolation patch onto current `server.py`
   exits 1 (`AttributeError: ... has no attribute 'current_process_executable'`).
   That archive cannot observe original current `server.main`. This checkout
   already has the matching isolation module. The kit now keeps that checkout
   module for source-runtime and does not invoke rejected `--isolated-stop`.
   Production was not changed.
2. **Loopback RSS remains refused by `source_subscriptions`.** That product
   policy is not repaired. Capture uses `c22-fixture.invalid` rewritten only
   onto the declared loopback fixture.
3. **Helper startup migrates `taxonomy.json` to `taxonomy.json.migrated`.**
   That is not an altered-settings/pins failure. Settings and pins stayed
   unchanged with `librarian_apply_enabled=false`.
4. **Inno still requires an existing `/PROFILE` directory.** The kit now
   creates the nine profile dirs in `prepare-before-install`. This worker
   did not run Setup.exe.
5. **`_run_subprocess` does not terminate an OS child when `record_child_start`
   raises after Popen returns.** That surviving unregistered child is the
   registration-failure observation C22 must keep. Unknown liveness still
   cannot pass.

No production repair is proposed in this worktree.

## Five bounded corrections

### 1. Actual bundled guard boundary

- Canary no longer `exec`s the guard. It probes the target interpreter and
  requires automatic `sitecustomize` load. Commented or missing `_pth`
  `import site` refuses. Exact `_pth` bytes are recorded and not rewritten.
- Restore refuses conflicting or preexisting sitecustomize instead of
  deleting it. Owned bytes only. Raw original bytes are omitted from JSON.
- Restoration waits until the helper and registered plus unregistered
  descendants are affirmatively gone. Unknown liveness is a failure.
- `_with_helper` propagates cleanup errors. Prepare/spawn failures restore
  the guard if it was installed.
- Guard remains scoped to receipt DBs, declared loopback ports and synthetic
  acquisition. The live index path is never used as a canary.

### 2. Installed provenance and manifest

- `PROVENANCE_CODE` emits structured JSON (`c22-provenance-v1`): executable,
  Python version, MCP version, `sys.path`, and required module `__file__` /
  SHA-256. Import failure exits 2. Substring `ERROR` lines no longer pass.
- Files must be inside the installed/source-runtime app. Checkout and
  user-site resolution fail. Source-runtime stays `unexecuted` for installed
  credit.
- Candidate-package-02 is consumed as the seal: 40-hex Git commits, 64-hex
  package/content hashes, package bytes. No second seal is invented.

### 3. AS-7 helper/child recovery

- Registered child lifetime captures exact pid/creation/executable identity,
  terminates the owned helper while the child lives, relaunches, requires
  retained lock/claim with no duplicate launch/charge/publication, then
  waits for confirmed child exit.
- Launch interruption requires boolean `unresolved_launch`, no spawned
  child, and not unknown. Any unresolved row is not enough.
- Registration failure requires a live unregistered child, then confirmed
  death. Unknown cannot pass. Distinct from interruption.
- Ownership writers are not called as a substitute for the helper. No name
  kill.

### 4. Capture order and protected Phase 2

- `_protected` no longer copies after-state `library_work` / outbox rows
  into its allow list. Expected identities come from schema 0027
  `library_meta` defaults and admitted capture receipts. Unknown rows fail.
- All nine profiles are compared against the pre-scenario baselines.
- Added unrelated work/outbox, mutated `library_meta`, and altered pins /
  settings fail. Taxonomy file migration is not treated as a settings
  mutation.
- Manual-first drives the standing opportunity after consent and requires
  zero additional standing charge and one publication.
- Standing-first waits for actual publication before the manual action:
  one charge, one publication, unchanged prior rows.

### 5. Executable prepare/install/continue flow

- `prepare-before-install` creates the nine profile directories. CLI
  prepare also writes immutable full Phase 2 baselines once.
- `run` / `prepare_profiles` resume without regenerating or overwriting
  those baselines.
- Continue validates original user, synthetic/installed mode, package
  bytes/hash, and path bindings. Synthetic receipts cannot be promoted.
  An app that was only intended cannot skip bundled validation once it
  exists in installed mode.
- Exact stdlib-only preinstall (`python -I -S`) and bundled postinstall
  commands are recorded. Install, browser and upgrade stay unexecuted.
  Same-version reinstall is not upgrade. Marker stays installer-owned;
  profile switching is explicit CLI binding.

## Verification

Wrapper label `c22u1`. `ANTHROPIC_API_KEY` unset. Fresh short label.
`IG_FORBIDDEN_LIVE` bound before launch. Disposable
`LOCALAPPDATA`/`APPDATA`/`USERPROFILE`/`TEMP` under `_scratch/c22u1`.

```powershell
$env:IG_FORBIDDEN_LIVE = Join-Path $env:LOCALAPPDATA 'Uoink\index.db'
$env:PYTHONDONTWRITEBYTECODE = '1'
Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
& 'E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\ig-native\Scripts\python.exe' -B `
  'docs/library/proof/ryan-corrected-01-2026-09-09/integrator_verify.py' `
  --root (Get-Location).Path --label c22u1 `
  tests/test_install_receipt_c22_kit.py `
  tests/test_install_receipt_c22_kit_repair.py `
  tests/test_install_receipt_c22_scenario_truth.py `
  tests/test_install_receipt_c22_final_oracles.py
```

### Counts

| Run | Result | Seconds | Exit |
|---|---|---|---|
| Third worker original `7a3c3ae2` | 41 passed / 2 failed | 666.25 | 1 |
| This union `c22u1` | **61 passed / 2 failed** | **931.71** | 1 |
| New file only `c22f1` (fast) | 19 passed / 1 deselected | 1.59 | 0 |
| New source-runtime `c22f4` | 1 passed | 195.80 | 0 |

The two failures are the same frozen kit assertions. New oracles: 20 passed.
Failed and unexecuted remain separate in scenario receipts. Installed pass
claimed: false.

Source-runtime exercised original current `server.main` (checkout isolation
module, not the stale archive overlay). Positive measured sequences:
empty/populated replay, one-off, manual-first, standing-first, helper
relaunch, registered child lifetime with terminate-while-child-lives,
launch interruption, registration failure, protected Phase 2 across nine
profiles. Install, browser and upgrade stayed unexecuted.

## Changed paths

Kit apply (frozen tests and prior worker reports, not edited after apply):

- `scripts/install_receipt/*` as imported
- `tests/test_install_receipt_c22_kit.py`
- `tests/test_install_receipt_c22_kit_repair.py`
- `tests/test_install_receipt_c22_scenario_truth.py`
- prior C22 worker reports under `docs/library/`

Edited after apply (this worker):

| Path | SHA256 |
|---|---|
| `scripts/install_receipt/cli.py` | `52e3dad790ef2ad13335c5a25c8da9349a85c8ada1e875f4b798e825a9513e78` |
| `scripts/install_receipt/constants.py` | `802075947208183750fa7cb6752b2d8d51049ba6f347fbcc0bb0dd710f9f05c6` |
| `scripts/install_receipt/guards.py` | `b2f3ec77af68ebad532aeca44306e69a746784ea49ffb3f480345ea33b75a971` |
| `scripts/install_receipt/launcher.py` | `c381fea298769af23ab35a8bf343ce834c2ecce2134e2a854c2c6c99334f1394` |
| `scripts/install_receipt/manifest.py` | `cc14aeea2f5e5514d0e3436b79128f768bc050f97ba67c667fd8702a58e1783d` |
| `scripts/install_receipt/oracles.py` | `14cb33a9657bb1f45cab029ee67194081a1b24264b8d86c3d3179382523a083a` |
| `scripts/install_receipt/runner.py` | `c100b75d554c316d0c4e1acb85b3171bfb62aab0aba9a3416118a945d3904c18` |
| `scripts/install_receipt/scenarios.py` | `0632e61f7021c50da51ddf970412b2fc610b09155b4a4c332438a57ead6e1155` |
| `scripts/install_receipt/source_runtime.py` | `b91a1828f13f093132d21d47bdf500777a77e3dad0224a1598572af769f0e3c7` |
| `scripts/install_receipt/validation.py` | `9ab8950ee6ccb0d3b4abe08060186ae297fa5be8b6743dc5282116d4b3edee4b` |
| `tests/test_install_receipt_c22_final_oracles.py` | `556fe63aba97d2004894cb5180f06adc7035c4204a25a583c0ba677b2de3357a` |

## Evidence locations

- Raw union log/XML: `_scratch/c22u1/tests.log`, `_scratch/c22u1/tests.xml`, `_scratch/c22u1/results.json`
- Archived copy: `docs/library/proof/ryan-c22-final-oracle-2026-09-09/`
  - tests.log SHA256 `0f380461467bef019143fffc1f6dac51ef915b399b85df9620068c33ddfdb156`
  - tests.xml SHA256 `14c2c0dc8cfe0dda20faecbafd37618e20283a78b5298de171a24d81b3ecc6de`
  - results.json SHA256 `99f255c27adff09a6b75420791fa23570b63583f20c48800276df2e5e83cc51a`
- Source-runtime receipt (corrected positives): `_scratch/c22-f/f-zdy3jiiv` and later `c22f4` scratch under `_scratch/c22-f`
- Third-worker original: `docs/library/proof/ryan-c22-review-03-input-2026-09-09/`

## Remaining Ryan / Astra steps

No integration until Astra independently verifies and reviews the full diff.

Ryan's throwaway installed receipt, after Astra seals the kit against the
final isolation/package, still needs:

1. Isolated Inno with `/ISOLATED=1 /PROFILE= /PORT= /DIR=` plus
   `/NOCLOSEAPPLICATIONS /NORESTARTAPPLICATIONS`. Record argv, exit, logs.
2. Installed provenance from the bundled interpreter at the spaced path,
   checkout/user-site absent, matching candidate-package-02 bindings.
3. Empty migration replay and populated legacy replay on disposable
   profiles.
4. One-off, manual-first and standing-first capture orderings with exact
   identities, one charge, one publication.
5. Real helper terminate-while-child-lives, relaunch, launch interruption
   and registration failure, with process handles and settled state.
6. Browser image paired with persisted state (unexecuted without an image).
7. Protected Phase 2 after-state. Apply remains false.
8. Same-version reinstall labeled as such, not upgrade.

Stdlib-only preinstall and bundled postinstall argv are in
`operator_commands()` / `operator_commands.json` after
`prepare-before-install`. Marker remains installer-owned.

This worker did not execute those operator steps.
