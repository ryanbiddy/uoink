# Phase 4 evidence-completeness worker report — 2026-09-09

Worker: grok. Worktree: `C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\1f64672e-95b\grok`.
Branch: `control-room/1f64672e-95b-grok`. HEAD at start: `12f830e Library: bind P4 correction brief to committed verification wrapper`.
No subagents, commits, push, merge, Inno, client/model, paid API, live index, or port 5179.
`ANTHROPIC_API_KEY` unset. Apply false. Astra independently verifies before integration.

This file was written **before** the first instrument edit, then completed after verification.

## Bound

- Read `docs/library/RYAN-P4-EVIDENCE-COMPLETENESS-REPAIR-BRIEF-2026-09-09.md` fully first.
- Applied `docs/library/proof/ryan-p4-kit-review-03-2026-09-09/original.patch` with `git apply --3way`. Patch sha256 `cf7b03a358bb16ead95bbf8ed8df8700925dd31956fc8248aa81b57ae898740a` (matches sealed SHA256.json). Direct application of new files; all 17 paths applied cleanly.
- Own only:
  - `scripts/install_receipt/p4_*.py` (repairs after import)
  - new `tests/test_install_receipt_p4_kit_truth.py`
  - this report
- Existing tests and assertions remain frozen, including all three imported kit suites.
- Product files were not modified.
- Verification used `E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/ig-native/Scripts/python.exe` and committed `docs/library/proof/ryan-corrected-01-2026-09-09/integrator_verify.py` (sha256 `280cfdad5ebc56a1748ce53cf9c6850335b7046ab1b9998f7cdd9a196c44e7e2`).
- `IG_FORBIDDEN_LIVE` was bound in the parent to `%LOCALAPPDATA%\Uoink\index.db` **before** invoking that interpreter (its startup sitecustomize requires the name). The wrapper then preserves it across `LOCALAPPDATA` redirect. All execution used guarded disposable profiles. API keys unset.

## Prior observation (kept unchanged)

Independent third union, sealed in `proof/ryan-p4-kit-review-03-2026-09-09/`:

- 36 passed / one frozen nested-settings-path failure, 24.86 s.
- Exact log: `p4-w3/tests.log` — `1 failed, 36 passed in 24.86s`.
- Failure: `test_prepare_fixture_seeds_synthetic_items_and_keeps_apply_false` looking for `profile/Uoink/settings.json`.
- Source-runtime: consult-library succeeded; inventory 32 tools / 5 templates / 4 prompts.
- reshelve-review returned `revision_unavailable` / `preview_invalidated` in **both** original sessions (child PIDs 63332 and 61416). Sealed in `source-runtime.json`.
- The third-kit worker labeled `packet_and_prompt_subset_complete` true despite that refusal.

**Interpretation correction (this report, not a rewrite of the old result):**
`packet_and_prompt_subset_complete == true` does **not** establish a passing valid-preview scenario. A reshelve refusal is an observed product/instrument reply, not a successful native `reshelve-review` result. Completeness credit now requires successful native consult-library **and** reshelve-review in **each** of at least two original sessions, with distinct actual child identities, complete inventories, matched frames, and no corruption. The sealed third-kit records stay as they are.

## Repair 1 — evidence inspection

`p4_inspect_evidence.py`:

- JSONL is parsed line-by-line. Corrupt records become `frame_faults`; `inspect()` no longer raises out of the inspection.
- Declared card/excerpt/corpus/brief pairs are scored **per session**. Union across sessions cannot fill another session's gaps. The aggregated `exact_packet_comparisons` list is retained so frozen status maps still work.
- `reshelve-review` success is `has_messages` and `error is None`. A `revision_unavailable` / `preview_invalidated` reply is observed (`reshelve_review_observed`) and is **not** success. `packet_and_prompt_subset_complete` requires `reshelve_review_success`.
- For `required_route="original-installed"`: at least two original sessions, each complete (pairs, consult, reshelve success, 32/5/4 inventory, child identity, no unanswered, parse ok), distinct child PIDs, no missing/unknown source labels.
- New fields: `session_reports`, `valid_preview_pair`, `each_original_session_complete`, `original_session_count`, `distinct_child_identities`, `unknown_or_missing_source_labels`.
- Generic inspect (`required_route=None`) still allows a single complete session so the first frozen inspector test remains true.

## Repair 2 — bounded transport cleanup

`p4_session.py`:

- `close()` terminates the owned job tree **before** `stdin.close()`. A writer still blocked after terminate is not followed by a synchronous close.
- `_bounded_write` uses a lock around the stream write; outbound bytes are retained to `stdin.bin` even on timeout. Large params are truncated in in-memory `retained` (`_truncated`) while the file keeps the full request.
- `query_job_process_ids` returns `{ok, pids, job_empty, error}`. `QueryInformationJobObject` failure is not an empty PID list. `ERROR_MORE_DATA` retries with a larger buffer.
- `cleaned` requires parent exit, no remaining owned descendants, **affirmative** `job_empty`, `job_query_ok`, and no drain/identity uncertainty. Query failure keeps the job handle and still closes it; foreign PIDs and process names are not targeted.
- stderr is fully logged to `stderr.bin`. In-memory join is capped at 8 MiB with file fallback so the frozen 2 MiB `stderr_bytes()` assertion still holds.

## Repair 3 — guard/provenance fail-closed before product launch

- `run_installed`: a canary that does not refuse **skips all product launches**. Restoration of receipt-owned guard/`_pth` bytes runs in `finally` after children are confirmed gone. Restoration IO failure is a product finding (`guard_restore`) and blocks installed credit. Preexisting C22 / modified guard bytes are still left, not overwritten.
- `p4_prepare_fixture.prepare`: canary is proven after writing the profile guard and **before** `_load_installed`. Failure restores env and raises `IsolationError`.
- `p4_execute_checks.execute`: canary before product import; refuse executable checks if it does not refuse.
- `p4_stdio_tap`: original-installed / fixture-attached routes refuse if `guard/sitecustomize.py` is missing. Synthetic-instrument (frozen tap test) is unchanged.
- Installed eligibility already required actual files, sealed per-file equality, missing imports, and checkout/user-site absence. Unchanged.

## Repair 4 — reshelve refusal diagnosis

Compared the real service seed to `LibraryPreviewReader` (the object original `uoink_mcp.py` uses) **without** modifying the stored preview.

Exact cause: the v1 generator constructed `LibraryWorkService(idx, profile / "prompt-store")`. Product default `store_root` is `index._path.parent / "library"`. `LibraryPreviewReader.store_root` is that default. `_recheck_preview` → `_taxonomy` looks for `store_root/taxonomies/<revision_hash>.json`. Those files were written under `prompt-store`, so the original-route recheck raised, and `library_prompts._reshelve_review` mapped it to `revision_unavailable` / `preview_invalidated` in both sessions.

This is an instrument-generator defect, not a product-code defect. Production was not edited.

Correction (`fixture_generator_version` `p4-evidence-completeness-v2-2026-09-09`):

- `LibraryWorkService(idx, librarian_apply_enabled=False)` — default store.
- Attached entry uses the same default. Attached remains a labeled extra and is **not** original-route or valid-preview credit.
- Generated artifacts in the profile: `expected.v2-default-library-store.json`, `fixture-generator-v2.json`, `preview-seed-v1-nondefault-store-archived.json`.
- Original requests/expected remain sealed in `proof/ryan-p4-kit-review-03-2026-09-09/`.
- `diagnose_preview_binding` records store roots, taxonomy files, projection, expiry, and a pure-reader recheck. The stored preview is left unmodified.

Pure-reader recheck after the correction: `ok: true`. Later prepare steps after preview are integrity check + close; projection is not mutated after minting.

## Verification

Parent bound `IG_FORBIDDEN_LIVE=%LOCALAPPDATA%\Uoink\index.db` first (the ig-native interpreter loads a sitecustomize that requires the name). Wrapper: committed `integrator_verify.py`. Fresh labels `p4ec-t3` (truth) and `p4ec-u2` (union).

Operator commands:

```powershell
$env:IG_FORBIDDEN_LIVE = Join-Path $env:LOCALAPPDATA "Uoink\index.db"
# ANTHROPIC_API_KEY / OPENAI_API_KEY / XAI_API_KEY / GOOGLE_API_KEY unset
$py = "E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/ig-native/Scripts/python.exe"
$wrap = "docs/library/proof/ryan-corrected-01-2026-09-09/integrator_verify.py"
$root = (Resolve-Path .).Path
& $py -B $wrap --root $root --label p4ec-t3 tests/test_install_receipt_p4_kit_truth.py
& $py -B $wrap --root $root --label p4ec-u2 `
  tests/test_install_receipt_p4_kit.py `
  tests/test_install_receipt_p4_kit_repair.py `
  tests/test_install_receipt_p4_kit_final.py `
  tests/test_install_receipt_p4_kit_truth.py
```

| Run | Result | Time | Log / XML |
|---|---|---|---|
| Third-kit sealed (unchanged) | 1 failed, 36 passed | 24.86 s | `proof/ryan-p4-kit-review-03-2026-09-09/p4-w3/` |
| Truth `p4ec-t3` | 11 passed | 7.60 s | `_scratch/p4ec-t3/tests.log` |
| Union `p4ec-u2` | **1 failed, 47 passed** | 65.05 s | `_scratch/p4ec-u2/tests.log` sha256 `3f196251a2e93f6935423f7b692c231c4b1079b3c747aa194d645aceb7d74c5c`; XML sha256 `eb6577857d3a1d2f17b77663feb4b64b92ba338c7cc07beb4e72384d56722680`; results sha256 `2592e692d2eaa591dacb7c38cec2a28e32e2c5a54e4710f48af8a72abd872727` |

JUnit: 48 tests, 1 failure, 0 errors, 0 skipped.

**Preserved frozen failure (do not repair):**
`tests/test_install_receipt_p4_kit.py::test_prepare_fixture_seeds_synthetic_items_and_keeps_apply_false`
`FileNotFoundError: ...\p\Uoink\settings.json`
Supported isolation root remains `<profile>/settings.json`, not `<profile>/Uoink/settings.json`.

Truth oracles (all passed): two complete original sessions; complete first / partial second; reshelve error is not valid-preview; one session is not a pair; malformed JSONL fail-closed; missing/unknown source labels; 4 MiB stdin close bounded with writer/readers exited and job-empty credit; job-query failure is not `cleaned=true`; failed canary refuses product launch; generator uses default store; prepare writes v2 artifact and pure-reader recheck succeeds.

## Original-route source observation after the documented generator correction

Frozen `test_source_runtime_original_route_against_isolation_scratch` ran against current source plus isolation overlay. Dump: `_scratch/p4kit-repair-source-runtime.json` sha256 `bde489a222366f4b3e583e5283f16e72e1d6b5b0a51a647a6e7a056d1556d785`.

- Inventory 32 / 5 / 4.
- Distinct children 72972 and 71048. Original `uoink_mcp.py`, not attached, not FAKE_CHILD.
- Unavailable storage 1.64 ms, expected `library_unavailable`, no replacement, held original restored.
- Transport failure within 15 s.
- `product_findings`: `[]`.
- `inspection_complete` / `packet_and_prompt_subset_complete`: **true** (this is now also a valid-preview pair: consult **and** reshelve succeeded in each of two original sessions).
- `installed_credit`: **false** (source-runtime; unsealed manifest). Source observation is not installed credit.
- Source copy excluded `build`, `.git`, `_scratch`, caches and dependency trees (`p4_provision_isolation._SCRATCH_EXCLUDE`).

The sealed third-kit `source-runtime.json` with `preview_invalidated` is **not** rewritten.

## File hashes (after repair)

| File | sha256 |
|---|---|
| `p4_inspect_evidence.py` | `531bb96197315a67aad2120831bfdcaee538609ea78b7a9a16b6ad49e171882f` |
| `p4_session.py` | `aff7a61909e1ed362c132670bd6f77defd037ff32a0be59fea016d29962ee441` |
| `p4_stdio_check.py` | `274431777aeb31724e887027a8872d57d34de9b0624bc3c3a40111ffa75d3a91` |
| `p4_prepare_fixture.py` | `2ed2dc871578b0ab8ae902eea59ee05d0a28381dccd7279f527ab6244623a90e` |
| `p4_common.py` | `ab478ac3594032137c447ecd815afcc32508062dd7e211f554e47b628f704c99` |
| `p4_stdio_tap.py` | `483a747d0fdb2d18fac4888bbc81fcdc1e377c273d049c129fff0d91eaaef7ff` |
| `p4_execute_checks.py` | `5d608d07396c7993b014f96568a21d97f567bbfe0bbe5ad9dde272bc451db852` |
| `p4_collect_evidence.py` (imported, not edited) | `7005c81d39db532bfc3b99f91760c6b477a2e78efe0b1935a99240b158261cf5` |
| `p4_observe_actions.py` (imported) | `c1152aa72097860324bde48268448b0c49cf9bcb46f9699d9553644d2e647198` |
| `p4_prepare_client.py` (imported) | `840782924c764b9b611e2a750a086c147b18f13f98b68a443229513ac21b0434` |
| `p4_provision_isolation.py` (imported) | `77f55b87b1a3c31110be8e940e6a2237e93b58fe3e6a52f98abbfdc07a8c4169` |
| `tests/test_install_receipt_p4_kit_truth.py` | `7db4d7941ec9697c4433300f059e7e81ea19e0c3024f29e267b8687534ba2b50` |
| Frozen `test_install_receipt_p4_kit.py` | `d42f9a4bbc1cd284f4dceaa598e50837f398dc8dcbcc2a816407abad0c9fca35` |
| Frozen `test_install_receipt_p4_kit_repair.py` | `08a89983249078f234f1f06c1efb288b43192f756d79cb9723be0adf2323cd7e` |
| Frozen `test_install_receipt_p4_kit_final.py` | `b57eab0932cec6a46f9e96eee27dd953b96dcfa10c2118ecd548deb619f79c71` |

Diff after import: 7 p4 modules, +732 / −229. No product files. No frozen-test edits. No commit.

## Open questions for Astra

1. Integrate the v2 generator (default `index.parent/library` store) and the stricter inspector. Do not treat the sealed third-kit `packet_and_prompt_subset_complete=true` with `preview_invalidated` as a valid-preview pass.
2. Installed credit remains false until Astra seals package bytes, per-file bindings, and a real Inno receipt. Source-runtime is labeled.
3. Keep the frozen nested `profile/Uoink/settings.json` assertion failed unless the contract is amended separately.
4. Real-client / Recall / screenshot observations remain unobserved. This worker started no client or model.
5. Confirm independent re-run of `p4ec-u2` commands before merging.
