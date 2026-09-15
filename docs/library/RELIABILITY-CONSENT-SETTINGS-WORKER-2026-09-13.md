# Reliability consent and model settings repair

**Date:** 2026-09-13
**Worker:** grok
**Worktree:** `C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\0851b440-86a\grok`
**Base HEAD:** `6774d197646cbaa2a3e95b29d2e5bf2cff5a4d26`
**Assignment:** Continuation of `RELIABILITY-CONSENT-SETTINGS-REPAIR-BRIEF-2026-09-13.md` after Gemini run `d3d22723-6e44-488f-9de4-ded941092040` produced no patch, tests, or report. Product requirements are unchanged; this run supersedes that brief's worker name only.
**Status:** Scoped patch, new regressions, and this report are in the worktree. Not product acceptance. Named Python union not launched here. No commit or push.

---

## 1. Defects repaired

1. **Ordinary reliability execution could acquire a model.** `_load_model` defaulted `local_files_only` to false, and `detect_unreliable_spans` omitted the keyword. Default is now true. `detect_unreliable_spans` and `transcribe_media` pass `local_files_only=True`. `ensure_model` is the only caller that passes `False`, and it is the only path that creates the download root.
2. **A `.pt` consent marker alone was reported ready.** `server._reliability_model_status` now delegates to `uoink_reliability.reliability_model_status`. Ready means: in-repo consent marker plus `model.bin`, `config.json`, and `tokenizer.json` in the selected repository's bounded Hub snapshot (`refs/main` -> 40-hex snapshot, path containment, non-empty files). Internal Hub blob links remain allowed. Stale marker, incomplete snapshot, wrong repository, redirected root, or outside link stays unready. No `whisper_runner` import.
3. **Settings copy promised 150 MB for every choice and dropped turbo.** One `transcriptModelLabel(model)` covers all six choices, including `large-v3-turbo` -> `Turbo`. Status and confirmation use per-choice rounded advertised sizes. An unsaved dropdown change uses that choice's size. Missing metadata is `size unknown` / `The download size is unknown`, not a silent 150 MB. Confirmation still runs before POST of `els.whisperModel.value`.

Production faster-whisper repository mapping is unchanged, including turbo at `mobiuslabsgmbh/faster-whisper-large-v3-turbo`. dropbox-dash appears only in the September 13 advertised-byte capture used for copy estimates.

---

## 2. Changed files

| File | Role |
| --- | --- |
| `uoink_reliability.py` | Local-only default, explicit `ensure_model` acquisition, Hub-layout readiness, per-choice sizes |
| `server.py` | `_reliability_model_status` delegates to the structural helper |
| `assets/dashboard/index.html` | One label function, per-choice sizes, unsaved-selection status, named download confirm/POST |
| `tests/test_reliability_local_only_load.py` | Fake constructor: ordinary paths local-only, `ensure_model` acquires |
| `tests/test_reliability_model_readiness.py` | Marker/snapshot contracts, six sizes, server source contract (no `server` import) |
| `tests/test_reliability_settings_ui.py` | Node VM of extracted dashboard functions with fake DOM/fetch/confirm |
| `docs/library/RELIABILITY-CONSENT-SETTINGS-WORKER-2026-09-13.md` | This report |

No existing tests, fixtures, assertions, model versions, repository mapping, VAD/alignment/speaker gates, website, or marketing files were edited.

`git diff --stat` on tracked product files: `assets/dashboard/index.html` 119, `server.py` 11, `uoink_reliability.py` 172 (250 insertions / 52 deletions).

---

## 3. Intended verification (Astra)

Named union, both worktree and checkout, with existing instrumentation:

- `tests/test_c02_reliability_faster_whisper.py`
- `tests/test_cm11_asr_fallback.py`
- `tests/test_g20_humanized_copy.py`
- `tests/test_g25_settings_polish.py`
- `tests/test_whisper_cache_consent.py`
- `tests/test_reliability_local_only_load.py`
- `tests/test_reliability_model_readiness.py`
- `tests/test_reliability_settings_ui.py`

G-25 still matches `function transcriptModelLabel(model)` and `JSON.stringify({ model: els.whisperModel.value })`.

---

## 4. Worker checks that ran

Environment: `IG_FORBIDDEN_LIVE=C:\Users\hello\AppData\Local\Uoink\index.db`, `ANTHROPIC_API_KEY` unset. Interpreter: `C:\Python314\python.exe -I -S -B`.

**Did run**

1. Syntax-only `ast.parse` of owned Python text, no import: `uoink_reliability.py`, `server.py`, and the three new test files. All parsed.
2. Isolated stdlib `exec` of extracted `uoink_reliability` helpers (fake constructor, temp placeholder files). Confirmed: `_load_model` kwdefault `local_files_only=True`; omitted keyword stays local-only and does not create the root; `ensure_model` passes `False` and writes the marker; marker-only is unready; marker plus complete snapshot is ready with tiny=80; empty `tokenizer.json` is unready; wrong repository is unready; turbo size 1630; turbo repo `mobiuslabsgmbh/faster-whisper-large-v3-turbo`; unknown size is `None`.
3. Node VM tests via `tests/test_reliability_settings_ui.py` (fake DOM/fetch/confirm, `fetch` throws `network forbidden`). Output: four `ok` lines, `all green`, exit 0.

**Did not run**

- Named Python union, pytest, or any import of `server`, `whisper_runner`, `faster_whisper`, or a model package.
- `tests/test_reliability_local_only_load.py` and `tests/test_reliability_model_readiness.py` as launched tests (they import `uoink_reliability`; Astra should run them).
- Live index, port 5179, ordinary profile, paid API, model/asset fetch, install, commit, or push.

---

## 5. Notes for review

- Reliability cache layout is `RELIABILITY_MODEL_ROOT` (`DATA_ROOT/models/whisper`) plus Hugging Face `models--org--name` snapshots, not `whisper_runner`'s per-size `whisper_models/<size>/` tree. Structural policy is adapted from `whisper_runner.py` without importing it.
- Structural readiness is not artifact authenticity and is not the trusted-manifest migration.
- Size figures are conservative rounded decimal MB of advertised Hub file totals captured 2026-09-13 (model/config/tokenizer/vocabulary/preprocessor logical bytes), not observed transfers or an approved manifest: tiny 80, base 150, small 490, medium 1540, large 3100, large-v3-turbo 1630.
- A zero worker exit is not test or product acceptance.
