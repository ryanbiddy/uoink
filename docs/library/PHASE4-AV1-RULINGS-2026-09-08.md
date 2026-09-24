# AV-1r rulings and S21 launcher repair, 2026-09-08

Owner: Astra (codex). Contract: `phase4-v1-2026-09-08`. Inspected candidate:
`9014fdf`, including AV-1b. This resolves the
[AV-1r brief](PHASE4-AV1-RULINGS-BRIEF-2026-09-08.md) against the
[Phase 4 contract](PHASE4-CONTRACT-2026-09-08.md) and
[AV implementation brief](PHASE4-AV-BRIEF-2026-09-08.md). No contract limit or
identity guarantee is relaxed.

The four unmodified Phase 4 test files reproduced **61 passed, 10 failed**.
The six fixture disputes below belong to Gemini. The deadline lifecycle and
shelf binding also need code work; fixing the ten failures alone will not
establish Phase 4 acceptance.

| Item | Ruling | Fix owner | Exact change |
|---|---|---|---|
| D1. Deadline baseline | A per-request facade can satisfy “from accepted request” if construction marks that request's admission. Completion of the previous operation cannot mark acceptance of a future request. The current reader ignores the timestamp returned by `ReadGuard.admit()` and charges idle time to the next operation. The fixture advances time before admission, so it does not test a slow read. | Claude worker code; Gemini fixture | In `LibraryReader._operation`, use the successful admission timestamp for `_Operation`'s deadline; remove the previous-completion reset as the next request's baseline. Keep one admission/deadline for `request()` fan-out. At the adapter boundary, carry that same deadline through backend acquisition and final result serialization: `make_reader` currently calls `_get_index()` before constructing the reader, and stdio rendering continues after its checks. Gemini must advance the mock clock inside a read/lock/serialization operation, then require retryable `deadline_exceeded`; add a fresh-request-after-idle success case. Do not preserve the pre-call clock trick as a timeout requirement. |
| D2. `shelf_revision` binding | Reject the deviation. Assignment-time `item_shelves.source_revision` is historical evidence, not the current source binding required by the contract. Current page entries and `source_changed` cannot repair an address that still resolves after its source changes. | Claude worker code; Gemini fixture | In `_shelf_snapshot`, obtain current canonical card source revisions for **all** ordered nondeleted members, including members outside the requested page, and hash those with the definition, taxonomy/projection revisions and displayed metadata. Preserve assignment revisions separately for display. Reuse `library_cards`; do not invent a second revision algorithm or mutate Phase 2 assignments. Construct/check a coherent snapshot and refuse concurrent change with `revision_unavailable`. If establishing it exceeds the deadline, refuse `deadline_exceeded`; never serve a partial or assignment-only binding. Add clip-only, opening-prose, off-page edit and deletion tests with unchanged projection revision; every old page URI must refuse. Unchanged rebuilds must retain addresses. A tail-only edit outside the card's bounded source inputs changes the corpus binding, not the card-derived shelf binding. |
| T1. Expected cards use manifest clips | The implementation's canonical snapshot is supported. The fixture omits stored deep links and bypasses clip merging/normalization. Its expected hashes therefore describe different inputs. | Gemini fixture | Make `build_test_card` take the index and item ID, read `idx.get_yoink(video_id)` and `idx.get_clips(video_id)` coherently, and call `library_cards.build_card(..., corpus_text=read_corpus_head(item['corpus_path']), profile='librarian')`. Update every caller. Do not obtain expected cards from `LibraryReader` itself. Keep the original manifest cues for mutation setup only. Assert that an old URI resolves before mutating clips/metadata or changing selection, so a pre-existing invalid URI cannot make a stale-address test pass. |
| T2. Corpus tail edits the wrong file | The implementation is supported. `tail_test.md` is unrelated to the stored `tail-item-01.md`. | Gemini fixture | Remove the extra file; after seeding, set `corpus_path = Path(item['corpus_path'])`. Build the card, hash, mutate and rehash that path. Assert unchanged card text, changed full-file digest, `revision_unavailable` for the old corpus URI and success for the new URI. |
| T3. Raw UTF-8 chunk expectations | The implementation's fixed fenced envelope is required. EOF is an empty **body text field**, inside a complete document. | Gemini fixture | Verify the exact preface/opening/closing fence, then JSON-decode the enclosed body. For offset 0/length 7 assert `text == 'Hello '`, byte start 0/end 6/returned 6, `boundary_adjusted`, `has_more`, and a continuation beginning at byte 6. At EOF assert `text == ''`, start/end equal total, returned 0, `complete == true`, `has_more == false` and `continuation.next_uri == null`. Keep interior-byte, beyond-EOF and too-small-next-code-point refusals. Apply excerpt code-point limits to decoded excerpt `text`, rather than the entire envelope; wire/resource byte limits still apply to the full result. |
| T4. Unsafe source links | The reader contract is supported. AV-1 must preserve hashed cards and refuse an unsafe existing link. It does not authorize changes to `library_cards._web_link`. | Gemini fixture | Test every hostile URL with `library_resources.safe_url`, expecting null, and exercise reader results using canonical cards. For links the builder already nulls, require null link fields in the successful card. For space/NUL URLs retained by the builder, require `invalid_source_data`, no successful contents and no echoed hostile input. Keep safe HTTP(S) positive cases. Remove the blanket expectation that the legacy builder nulls every URL in this list. |
| T5. Role-injection item 4 has NUL/ESC | The hostile-card refusal takes precedence over successful fenced rendering. This is zero-based `role-inject-4`, the fifth fixture, containing NUL and ESC terminal sequences. | Gemini fixture | After T1, require `invalid_source_data` for this item and verify its refusal contains no source payload. Keep successful, exactly fenced, reversibly escaped data assertions for ordinary role/directive/fence-breaking text. Preserve the separate hostile-card refusal test. Do not sanitize a card while retaining its old hash or permit terminal controls merely because JSON can escape them. |
| T6. Rolling admission boundary | The implementation's rolling-window comparison is supported. At time `t`, count admitted timestamps in `(t - 60, t]`. A timestamp exactly 60 seconds old has expired. The current test fails on its **first** read with `revision_unavailable`, not with a rate refusal or bare `assert False`. | Gemini fixture | Repair the URI via T1. Use one shared `ReadGuard` with fresh request readers and a controlled clock. At `t0`, admit exactly 60 requests; request 61 must return retryable `rate_limited`, reason `rate`, integer `retry_after_ms == 60000`. At `t0 + 59.999`, still refuse with 1 ms; at `t0 + 60`, admit. Add staggered timestamps to prove rolling expiry rather than a calendar-minute reset. Rejected admissions must not add timestamps or extend the window. An admitted request that later fails still consumes its admission. Do not spend an uncounted setup/discovery request on the tested guard. |

The source docstring actually lists eight disclosures, rather than seven. The
remaining rulings are below; number 8 overlaps T5. AV's duplicate-key reconciliation
already applies and is not a new amendment.

| Item | Ruling | Fix owner | Exact change |
|---|---|---|---|
| D3. Duplicate JSON keys | Confirm the AV brief's documented stdio limitation: parsed dictionaries cannot recover duplicate-key information. | Claude worker code (no change to this disclosure); Gemini fixture | Keep strict validation of available fields/types. Exercise duplicate rejection where raw frames/HTTP bytes are available; do not claim that a dictionary-level fixture proves raw-key rejection. Fable retains the HTTP reservation. |
| D4. Concurrency refusal code | Confirm `rate_limited`, reason `concurrency`, bounded integer retry delay and no queue. The frozen code set has no separate concurrency code. | Gemini fixture | Retain the implementation. Replace the current concurrency test's unused barrier/worker definitions and `assert reader is not None` with two held admissions, an immediately refused third, and successful admission after release. This passing stub proves no concurrency behavior. |
| D5. Excerpts outside the six selected cards | Confirm. Bounded search can identify another original clip. The six-excerpt limit bounds the card, not the excerpt address space. | Claude worker code (no change); Gemini fixture | Keep shared pre-truncation identities and drift checks. Test a search hit outside the selected six and compare its resolved identity/text with canonical stored evidence; retain per-excerpt and wire limits. |
| D6. Redaction covers only known runtime paths | Confirm the disclosure as accurate; reject it as satisfaction of the contract's broader local-path redaction requirement. `_redact` currently leaves other absolute local paths unchanged. | Claude worker code; Gemini fixture | Preserve known-path redaction and add recognition/redaction of explicit absolute drive, UNC and POSIX paths and local file URIs in corpus text, with reported spans and unchanged original-byte offsets/hash. Do not redact validated public HTTP(S) destinations as local paths. Add cases outside `data_root` and the item's known folders. Any narrower promise requires a separately recorded contract amendment; none is granted here. |
| D7. Legacy backend creates/recovers missing storage | Confirm the ownership disclosure; reject it as an acceptance exemption. The contract forbids substituting a new empty database for unavailable storage. | Claude worker code, coordinated with Fable's `server.py` reservation; Gemini fixture | Give new bounded reads a noncreating, nonrecovering storage acquisition path. Missing/corrupt/unreadable storage must return `library_unavailable` without creating/quarantining files or switching installations. Preserve legacy recovery for its existing callers. Test cold-start acquisition, not only an already-open broken connection. |
| D8. C0/C1 controls in hashed cards | Confirm refusal for the disclosed NUL/ESC case; see T5. | Gemini fixture | Preserve `invalid_source_data` assertions and unchanged hashes. Ordinary whitespace and inert role text must retain the successful fenced-data coverage. |

Verification used Python **3.14.6**, pytest **9.1.1**, MCP SDK **1.28.1**, temporary
indexes/corpora and isolated stdio child environments in this worktree. No package
was installed. The initial isolation hid user-site packages; adding the existing
package directory alone then left nine stdio failures from missing `pywintypes`.
Including its existing subdirectories produced the reproducible result below.
This tests the installed SDK version, not the requirements pin `1.27.1`.

```powershell
$av1rTemp = Join-Path (Get-Location) '_scratch/av1r-20260908'
New-Item -ItemType Directory -Path $av1rTemp -Force | Out-Null
$av1rPackages = (& python -B -c "import site; print(site.getusersitepackages())").Trim()
$env:PYTHONPATH = "$av1rPackages;$av1rPackages/win32;$av1rPackages/win32/lib;$av1rPackages/pythonwin"
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONUTF8 = '1'
$env:APPDATA = $av1rTemp
$env:LOCALAPPDATA = $av1rTemp
$env:XDG_DATA_HOME = $av1rTemp
$env:TEMP = $av1rTemp
$env:TMP = $av1rTemp
$env:UOINK_OUTPUT_DIR = $av1rTemp
python -B -m pytest -p no:cacheprovider --basetemp "$av1rTemp/pytest-complete" tests/test_library_resources.py tests/test_library_resource_trust.py tests/test_library_prompts.py tests/test_phase4_stdio.py -q --tb=short
# 10 failed, 61 passed in 16.94s; exit 1
```

The ten failures were seven `revision_unavailable` failures from mismatched
fixture cards (card stability, metadata change, excerpt identity, admission loop,
evidence kinds, fence breaking and role injection), plus wrong-file tail mutation,
raw chunk expectations and unsafe-link expectations. The brief's six card failures
exclude the admission loop. T5 is masked by the earlier mismatch in the unchanged
suite; it is not an eleventh observed failure.

Independent in-memory diagnostic assertions against disposable indexes confirmed:

- Canonical stored inputs resolve the expected card. With those inputs, role
  cases 0–3 render fenced data; case 4 and both retained space/NUL URLs refuse
  `invalid_source_data`.
- Corpus offset 0/length 7 yields body text `Hello ` ending at byte 6. EOF has an
  empty body and no continuation. Editing the stored tail file preserves the
  card and invalidates the old corpus URI.
- Sixty canonical reads are admitted; request 61 refuses. At +59.999 seconds the
  retry delay is 1 ms; a fresh reader sharing the guard succeeds at +60 seconds.
  An idle reused reader reproduces the separate `deadline_exceeded` problem.
- With a real fixture shelf, a clip-only edit invalidates the old card URI while
  the old shelf URI still succeeds and reports `source_changed: true`. Discovery
  returns that same shelf URI. Soft deletion then invalidates the shelf URI.

The S21 repair is in
[`tests/library_work_astra/test_phase3_s21.py`](../../tests/library_work_astra/test_phase3_s21.py).
It pre-imports `whisper_runner` after the environment, network, process, database
and model guards are installed. During only that import, `NoModels` raises
`ModuleNotFoundError` for `whisperx` without incrementing `model_calls`. WhisperX
never loads, even if installed. A `finally` restores normal accounting before
`server.py` imports or synthetic capture begins. The synthetic transcription
patch and all existing guard assertions remain in place.

Guard-only execution of the actual launcher definitions/import block passed:
zero startup model calls, cached `whisper_runner` reuse, all six forbidden model
imports blocked and counted, a later WhisperX probe blocked and counted, and flag
restoration after an injected import failure. AST comparison with HEAD verified
the other guard functions, their installation loop and every existing assertion
were unchanged. Syntax compilation passed. These checks imported no server and
started no helper. Pytest collection found no tests in the launcher and did not
execute it. Document links resolve, all 14 ruling rows have four columns, fences
are balanced, and both files pass whitespace checks.

All six files listed in the existing
[S21 proof manifest](proof/s21-2026-09-08/SHA256SUMS) matched their SHA-256 hashes.
The original failure receipt records one model-call count; both diagnostic
receipts record zero. This supports the launcher's accounting diagnosis in the
[S21 receipt](PHASE3-S21-RECEIPT-2026-09-08.md). It does not recertify its earlier
candidate. Fable must rerun full S21, including browser observation, on the AT-3
candidate. AV-1r launched no model or HTTP helper, touched no resident helper,
port 5179 or live index, and made no commit or merge. Only this document and the
S21 launcher are edited; Gemini/Claude fixes above remain assigned follow-up work.
