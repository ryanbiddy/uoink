# Review verdict — 2026-09-13

**A is ready for integrator review and synthetic qualification.** It is an
ordinary product repair that needs no new Ryan approval. `product-A.patch.txt`
changes only `whisper_runner.py`; no dependency pin, packaged dependency source,
accepted test, public default, transcript shape or model option changes.
No proposal has been applied or tested in this task.

The current source was captured by raw SHA-256 in `input-bindings.json` before
drafting the patches. The checkout HEAD observed at completion was
`099a72408f63e6cdb227322e137da428f6c3a1d7`; use the recorded file hash to check
applicability because other integrator work continued concurrently.

| Proposed API | Exact purpose |
| --- | --- |
| `is_model_downloaded(data_root, model_size=MODEL_BASE) -> bool` | Existing public signature. Read-only structural check of the expected repository's local `refs/main` snapshot and three minimum ASR files. No runtime import, fetch or directory creation. |
| `_checked_model_snapshot(data_root, model_size, snapshot) -> Path or None` | Validate snapshot layout, commit-shaped directory name, minimum nonempty files and resolved path containment. Allow ordinary Hub file links into the same repository's blobs. |
| `_prepare_model_snapshot(data_root, model_size, *, consent_given) -> Path` | Reuse a structurally ready cache; otherwise refuse without consent or run the existing downloader before validating its result. |
| `_download_model_snapshot(model_size, cache_root) -> Path` | Narrow acquisition seam using the pinned faster-whisper helper and its unchanged six supported repository identities. Called only after explicit consent. |
| `transcribe_audio(...) -> dict` | Existing public signature and output. Check the local snapshot before construction; pass its path to WhisperX with `local_files_only=True`. Preserve the original cache root separately. |

The reviewable behavior change is precise: random/partial cache contents no
longer skip consent; a downloaded snapshot without `tokenizer.json` refuses
before constructing ASR; a healthy cache is reused without an implicit remote
refresh. First-use and repair downloads remain available through the existing
explicit consent flow. The original server 412 response and standing-capture
refusal remain unchanged. Existing cache layouts are read in place; no cache
migration or deletion is proposed.

`tests-proposed.py.txt` contains **11 product cases and 6 companion cases**,
using only temporary synthetic files, AST-extracted function bodies and inert
fakes. It does not import either whole product module or any staged package.
It checks missing/partial/empty caches, all six choices, consented resolution,
invalid download results/references, a changed tokenizer before construction,
resolved blob containment, damaged-runtime refusal, and tokenizer ordering.
It preserves the constructor's real prefix through tokenizer assignment; it
does not pretend to execute the later native/feature-extraction steps.

The companion **B remains an unapproved derivative proposal**. Its exact delta
prepares a local/buffer tokenizer before CTranslate2 and refuses a missing local
tokenizer rather than taking the independent remote fallback. Non-local upstream
fallback remains for other callers. The smallest Ryan decision is review of
this exact source delta with its derivative packaging/provenance and frozen
compatibility expectations. It is not a request to approve ordinary Uoink
repairs again, and it grants no model execution or download. Do not apply B to
shared staging or present changed upstream bytes as the original pinned package.

Remaining limits must stay visible after A is integrated:

- Three nonempty files establish minimum structure, not a complete artifact
  manifest, cryptographic trust, tokenizer validity or model quality. They do
  not establish that other optional/required-by-model assets are complete.
- Path checks describe observed paths. They are not atomic protection against
  concurrent filesystem replacement. A catches stable and observed-between-step
  absence; B is needed to close the local-only tokenizer fallback itself.
- `refs/main` records the existing cache selection, not a new approved immutable
  release manifest. No remote model revisions or hashes have been invented.
- Default PyAnnote VAD still reaches unrestricted checkpoint loading. No
  speaker, alignment, native decoder or model-stack qualification is added.

Later validation can run the 11 product contracts independently of B. Preserve
all existing assertions in the podcast watch/background/durability, Phase 6,
packaged decoder and dependency-lock suites, then record the actual complete-tree
counts against the integrated commit under the integrator's guarded protocol.
No real model/native test is authorized by this proposal.

This task ran **zero tests and zero product functions**. It parsed the two
proposed sources and synthetic test body as text, verified the diffs reconstruct
those sources, and checked retained input hashes. During static review, the
reference reader was tightened to reject an overlong value before whitespace
trimming, and an overbroad error phrase was changed to describe the three
required files. The proposal generator was rerun only to incorporate those
documented text corrections; no failed measurement was relabeled.
