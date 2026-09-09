# Phase 4 receipt instrument: final repair worker — 2026-09-09

Worker: Grok. Worktree:
`C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\f3723b7a-810\grok`
branch `control-room/f3723b7a-810-grok`. Base HEAD `5162fcb` (includes Astra
`e86bc16` existing-preview / read-opening product repair). No subagents,
commits, pushes, merge, Inno, client/model, API keys, paid API, network fetch,
diarization, live index, or port 5179. Existing tests are frozen, including
`tests/test_install_receipt_p4_kit.py` and
`tests/test_install_receipt_p4_kit_repair.py`. The obsolete nested
`profile/Uoink/settings.json` assertion was not repaired. Apply false.
Source-runtime remains labeled. No worker invented package provenance.
Astra independently verifies before integration and final packaging.

## Brief opened first

`docs/library/RYAN-P4-FINAL-INSTRUMENT-REPAIR-BRIEF-2026-09-09.md` was opened
completely before owned edits. Archived second kit applied from
`docs/library/proof/ryan-p4-kit-review-02-2026-09-09/original.patch`.

Archived kit claim, preserved: **20 independent passes / one failure, 20.39 s.**

Frozen failure (unchanged assertion, unchanged error class/path shape):

```
FAILED tests/test_install_receipt_p4_kit.py::test_prepare_fixture_seeds_synthetic_items_and_keeps_apply_false
FileNotFoundError: ...\p\Uoink\settings.json
```

Initial original-route source observation (preserved, not rewritten):
32 tools / five templates / four prompts; `reshelve-review` returned
`feature_unavailable`, reason `Phase 2 work service is not attached`. Exact
replies remain in
`docs/library/proof/ryan-p4-kit-review-02-2026-09-09/prompt-observations.json`.
Requests and expected packets were not changed.

## Five bounded repair groups

Owned edits only: `scripts/install_receipt/p4_*.py`, new
`tests/test_install_receipt_p4_kit_final.py`, and this report.

### 1. Manifest and runtime provenance

- `installer_source_sha` is a real 40-hex Git commit. A 64-character SHA-256
  in that field is recorded as fabricated and is not a source commit.
- Package and per-file content digests remain SHA-256.
- Candidate-package same-purpose schema is supported
  (`staged_path`, `source_path`, `source_git_blob`,
  `checkout_and_staged_sha256`) via `--source-bindings` and
  `make_same_purpose_manifest_from_bytes` from real bytes. Git blobs and
  package SHA-256 are never invented.
- Installed eligibility compares installed module files to declared sealed
  digests. Missing binding, missing file, mismatched digest, or unverified
  import is a refusal.
- Bundled runtime probe records actual `sys.executable`, module `__file__`,
  dependency versions and `sys.path`. Installed credit still requires
  checkout and user-site absent. Source-runtime stays labeled.

### 2. Effective guard and exact restoration

- `python._pth` is parsed by active lines. Commented `#import site` is not
  treated as active.
- Original `_pth` bytes, including CRLF, are stored and restored exactly.
- Restoration runs in an outer `finally` after all children exit.
- A modified sitecustomize is not deleted merely because its prefix matches
  `# P4 receipt guard`. Conflicting C22 guards remain refused.
- `IG_FORBIDDEN_LIVE` is copied through `isolation_env` and is not recomputed
  from redirected `LOCALAPPDATA`.
- The live forbidden index is never hashed, stat'd or opened. Guard activity
  is proved with an owned disposable canary before product execution.

### 3. Actual bounded transport and owned cleanup

- Complete send+receive is deadline-bound. stdin write/flush runs on a
  worker thread and times out if the child stops reading.
- stdout is chunk-pumped (`read1`); partial live frames are retained in
  `stdout.partial.bin` before newline or exit.
- stderr is appended in full to `stderr.bin` (no 1 MB in-memory truncate).
- Readers drain before terminate; cleanup uses the owned job, not a process
  name or unverifiable foreign PID.
- Windows: create job, `CREATE_SUSPENDED` + breakaway, assign with pointer-sized
  `HANDLE` signatures, resume, then run. Assignment failure kills the
  suspended child and refuses. `cleaned` requires parent exit and descendant
  exit evidence from the owned job.

### 4. Evidence completeness

- Inspector requires every declared card/excerpt/corpus/brief pair on both
  native and fallback routes, not a nonempty equal subset.
- Original-route completeness uses only `original-installed` records.
  Synthetic/attached records cannot fill those gaps.
- Missing/corrupt/unanswered original-route records fail. A missing
  instrument input (no expected URIs) is an `instrument_diagnostic`, not a
  product defect.
- Unavailable storage must return the expected `library_unavailable`
  refusal, finish within 2 s, and create no replacement. If a replacement
  appears it is preserved as `index.db.replacement-unavail` and the held
  original is restored (the held original is no longer deleted).
- Transport failure is measured within 15 s.

### 5. Executable operator path

- `p4_execute_checks.recall_silent_unavailable` requires
  `installed-app/scripts/recall_hook.py` and refuses a staged fallback.
- Everyday retrieve checkpoints use protocol record bytes when present.
  Operator booleans without bytes stay unobserved, never passed.
- `collect()` emits `operator_sequence` with complete commands for
  preparation, original protocol observation, Ryan-only client stream
  capture, collection, and guard restoration. Missing inputs are listed
  and refused, not hypothesized.
- X remains documented HTTP 403, no retry. Chapters/cited ranges make no
  speaker claim. Phase 5 Part B stays deferred. Real-client/UI observations
  remain unobserved until Ryan supplies them.

## Verification

Interpreter:
`E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\ig-native\Scripts\python.exe`

`IG_FORBIDDEN_LIVE` bound before launch. Wrapper:
`docs/library/proof/ryan-corrected-01-2026-09-09/integrator_verify.py`.
`ANTHROPIC_API_KEY` unset.

### New regressions only (label `p4f-n1`)

```
<ig-native python> -B docs/library/proof/ryan-corrected-01-2026-09-09/integrator_verify.py
  --root <this-worktree> --label p4f-n1
  tests/test_install_receipt_p4_kit_final.py
```

**16 passed in 6.54 s, exit 0.**

Log sha256 `ff4e82df017593a34f73661e99a121b100665129c768ec3264c0ad1aea3c3046`
XML sha256 `3e2ca326917c070a1b0e37628a7ac281db1c8130243caa5fe6c78f59fda455a2`

### Frozen kits plus new regressions (label `p4f-kit`)

```
<ig-native python> -B docs/library/proof/ryan-corrected-01-2026-09-09/integrator_verify.py
  --root <this-worktree> --label p4f-kit
  tests/test_install_receipt_p4_kit.py
  tests/test_install_receipt_p4_kit_repair.py
  tests/test_install_receipt_p4_kit_final.py
```

**1 failed, 36 passed in 31.44 s, 37 tests, exit 1.**

The single failure is the frozen nested-settings assertion. Expected.

Log `_scratch/p4f-kit/tests.log`
sha256 `e4e17817ea54f307e14f6c6cdf02e491b9d06165417f76481495f6b5ac2d36fe`
XML `_scratch/p4f-kit/tests.xml`
sha256 `903f0cb59ecb169470d9e8e1b1be135393cc8fa4993e546cbe3ba99d460236d9`

Breakdown: frozen first kit 10 passed / 1 failed; frozen repair kit 10
passed; new file 16 passed.

## Original-route source-runtime against this base (`e86bc16` unchanged)

Isolation overlay copies current product source (including the preview
reader) and injects only the isolation pin. Scratch excludes build, `.git`,
`_scratch`, caches and dependency trees. Not installed credit. Stop CLI not
run. Attached entry was not used for original credit.

Dump: `_scratch/p4kit-repair-source-runtime.json`
sha256 `a72170fdb3fa2dc8a7fad3a2ed384ed4b5bb013bf50044cf606083e9da1cf36c`
elapsed 5459 ms. Records under `_scratch/p4f-kit-0/t20/r/p/records/`.

| Check | Result |
|---|---|
| tools | 32, exact frozen set |
| templates | 5 |
| prompts | 4 |
| packet/prompt subset complete | true (`inspection_complete`) |
| consult-library | successful native messages, both sessions |
| reconnect | distinct child PIDs 74396 / 65904 |
| unavailable storage | 1.89 ms, `library_unavailable`, no replacement, held original restored |
| transport failure | 0.0 ms, exit 1, within 15 s |
| installed_credit | false |

Remaining original-route product finding (exact, not hidden):

`prompts/get` name `reshelve-review`, both original-installed sessions.

Request (session a, id 26):

```json
{"jsonrpc":"2.0","id":26,"method":"prompts/get","params":{"name":"reshelve-review","arguments":{"preview_id":"2nc4B85yXOUE08PSTsKB1XA3zejDHHD9"}}}
```

Reply (both sessions a and b):

```json
{"jsonrpc":"2.0","id":26,"error":{"code":-32603,"message":"This revision is unavailable. Resolve the item again.","data":{"ok":false,"schema_version":1,"contract_version":"phase4-v1-2026-09-08","error":{"code":"revision_unavailable","message":"This revision is unavailable. Resolve the item again.","retryable":false,"details":{"reason":"preview_invalidated","next_step":"apply_reshelving mode=preview"}}}}}
```

Cause: `e86bc16` supplies `LibraryPreviewReader`, so original-route no longer
returns `feature_unavailable` / "Phase 2 work service is not attached". The
preview row is found; `_recheck_preview` then refuses `preview_invalidated`.
That is a product reply on the original `uoink_mcp.py` route, not a missing
instrument input. The initial `feature_unavailable` observation remains
archived and is not overwritten. Fixture-attached is still a separate label
and was not substituted.

## Files changed

From archived kit (applied, frozen tests not edited after import):

- `docs/library/RYAN-INSTALLED-PHASE4-KIT-WORKER-2026-09-09.md`
- `docs/library/RYAN-PHASE4-KIT-REPAIR-WORKER-2026-09-09.md`
- `tests/test_install_receipt_p4_kit.py`
- `tests/test_install_receipt_p4_kit_repair.py`
- `scripts/install_receipt/p4_*.py` (then repaired)

Repaired / new in this run:

| File | sha256 |
|---|---|
| `scripts/install_receipt/p4_common.py` | `f2088463011a04528be5d17d2278de7c0ad534ffaf2fd069bc71305671d9b28b` |
| `scripts/install_receipt/p4_session.py` | `78be7279215c919850083028a0f5133f5c61450fad1faa8889434804ec2a0b8e` |
| `scripts/install_receipt/p4_stdio_tap.py` | `3d50b2f416135c72e0055875ae576116636a6194329ece5d0d77882d78daaaa8` |
| `scripts/install_receipt/p4_stdio_check.py` | `d3fecd3f4d35f8f2a62f4ad1f89538c954e2e33e1936700f84c7445dfea1d78b` |
| `scripts/install_receipt/p4_inspect_evidence.py` | `155483e0118dbaefb7193502d53e16774aba333e872854ab12a2345bdff354a7` |
| `scripts/install_receipt/p4_collect_evidence.py` | `7005c81d39db532bfc3b99f91760c6b477a2e78efe0b1935a99240b158261cf5` |
| `scripts/install_receipt/p4_execute_checks.py` | `ee0efcd495834aea96ef2a986553caa13d8e6f99474dd995bbe07f3b8b24a6cc` |
| `scripts/install_receipt/p4_provision_isolation.py` | `77f55b87b1a3c31110be8e940e6a2237e93b58fe3e6a52f98abbfdc07a8c4169` |
| `tests/test_install_receipt_p4_kit_final.py` | `2a3aa14c2a743e6dd566cb8afcc854ecf892566799784ccee1213eba56175bef` |
| `docs/library/RYAN-P4-FINAL-INSTRUMENT-WORKER-2026-09-09.md` | this file |

Unchanged after kit apply: `p4_observe_actions.py`, `p4_prepare_client.py`,
`p4_prepare_fixture.py`. Frozen tests match the archived patch.

## Expected failing assertions and unresolved operator gates

- Frozen: `test_prepare_fixture_seeds_synthetic_items_and_keeps_apply_false`
  looking for `profile/Uoink/settings.json`.
- Original-route `reshelve-review`: exact `revision_unavailable` /
  `preview_invalidated` on current source (initial `feature_unavailable`
  preserved separately).
- Real-client/UI screenshots and Ryan stream capture: unobserved.
- Installed credit: false until Astra seals package bytes, source bindings,
  bundled interpreter provenance, and a complete original-installed route.
- Inno / live helper / port 5179: not run.
- Phase 5 Part B: deferred. X 403: no retry. No speaker claim.

No commit. Astra must independently verify before integration and final
packaging.
