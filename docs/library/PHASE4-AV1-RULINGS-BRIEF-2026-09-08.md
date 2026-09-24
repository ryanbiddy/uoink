# Run AV-1r brief: Phase 4 first-increment rulings and the S21 launcher (2026-09-08)

Fable's dispatch under `ORCHESTRATION-V1-2026-09-04.md`. Codex only. You are GPT-6 Astra,
owner of contract `phase4-v1-2026-09-08` and of the S21 launcher. No model, no helper, no
port 5179, no live index, no commit.

## State

Run AV-1b (Claude worker) is integrated at `82e973a`: `library_resources.py`,
`library_prompts.py`, three read tools in the registry (85) and on stdio (29 tools, five
templates, four prompts). Gemini's AV-1a tests: 61 of 71 pass. The 10 failures are
disagreements between the tests and the implementation that need your ruling before
Gemini repairs its fixtures (run AV-1c) or the worker repairs the code (run AV-1d).

## Part 1: rule on the worker's two declared deviations

The top of `library_resources.py` lists seven rules it does not implement literally. Two
need a ruling; the other five are disclosures you may confirm or reject:

1. **Deadline baseline.** The reader measures the 2 s deadline from its construction or
   the end of its previous operation (request-scoped reader, one per stdio request), not
   from inside each call, because the P4-05 fixture advances its mock clock before calling
   `read`. Rule whether "from accepted request" is satisfied by a per-request facade.
2. **`shelf_revision` binding.** It binds definition, taxonomy/projection revisions, live
   deletion state, live displayed metadata and each member's assignment-time
   `item_shelves.source_revision`, not every member's recomputed current card revision
   (Phase 2 stores none; rebuilding cards for whole shelves cannot be guaranteed in 2 s).
   Page entries carry current bindings and a `source_changed` flag. Rule whether this
   meets "a source edit or deletion invalidates old shelf addresses".

## Part 2: rule on the six test-versus-implementation disagreements

For each, say which side the contract supports and what the exact fix is (fixture or code):

1. `tests/phase4_fixtures.py` `build_test_card` builds expected cards from the manifest
   clips (no `source_deep_link`, unmerged, un-normalized) instead of `idx.get_clips`, so
   expected `source_revision`/`card_hash` never equal the canonical card (6 failures).
2. `test_corpus_tail_edit_preserves_card_address_but_invalidates_corpus_revision` edits
   `tail_test.md`, but `seed_yoink_item` wrote the item's corpus at `<video_id>.md`, so the
   item's file is never edited and the old corpus URI legitimately still resolves.
3. `test_corpus_chunk_utf8_boundary_handling` expects raw chunk text (`startswith("Hello")`,
   `== ""`); the implementation returns the fixed fenced envelope with the chunk in its
   `text` field, per the contract's "other documents use a fixed envelope".
4. `test_source_link_validation_and_sanitization` asserts `library_cards._web_link` nulls a
   URL with a space or NUL; that function is outside AV-1 ownership and does not. The
   reader's own `safe_url` rejects them and a hostile hashed card refuses
   `invalid_source_data`.
5. Role-injection item 4 carries NUL/ESC in its title; the hostile-card rule refuses it
   (`invalid_source_data`), which conflicts with the test's expectation that it renders as
   fenced data.
6. `test_rolling_rate_limit_admissions` fails with a bare `assert False` in its loop; state
   what the contract's 60-per-rolling-60-seconds admission means at the boundary and what
   the fixture must do.

Write `docs/library/PHASE4-AV1-RULINGS-2026-09-08.md` with a table: item, ruling, owner of the
fix (Gemini fixture, Claude worker code, or contract amendment), exact change.

## Part 3: the S21 launcher's model-call accounting (your file)

`tests/library_work_astra/test_phase3_s21.py` fails its own `model_calls == 0` after every
product observation passed: `server.py` imports `whisper_runner`, whose module-level
availability probe attempts `import whisperx` once, and the launcher's `NoModels` guard
counts that import attempt as a model call (WhisperX is not installed here; the transcript
came from your synthetic injection). Evidence: `docs/library/PHASE3-S21-RECEIPT-2026-09-08.md`
and `docs/library/proof/s21-2026-09-08/`. Fable's diagnostic copy pre-imports
`whisper_runner` before installing the guard; both diagnostic runs then pass. Repair the
launcher as you see fit (pre-import, count only post-start imports, or distinguish the
probe), keeping every other guard, so that Fable can rerun S21 on the AT-3 candidate. You
may edit only that file and the rulings document.
