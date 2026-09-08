# Phase 6 BD study inputs (Fable, 2026-09-08)

Disposable study workspace for Astra's BD measured navigation study (contract
`phase6-v1`, "Freeze the mandatory study"). Built by Fable from the authorized measured
copy only:

- `study-inputs-manifest.json`: candidate SHA, the read-only measured index copy's path and
  hash, the eligibility rule, and per item: video id, source type, title, corpus-relative
  path, `metadata.json` hash, chapter count and chapter starts, `yoinked_at`, clip count and
  pre-Phase 6 clip seek starts, and the hash of the unchanged pre-Phase 6 clip rows.
- `items/<video_id>/chapters.json`: the source chapters and identity fields extracted from the held `metadata.json` (its sha256 and size are recorded inside as `_provenance`; the caption and format tables are not copied).
- `items/<video_id>/clips-pre-phase6.json`: the unchanged pre-Phase 6 clip output from the
  measured index copy (baseline material for step 2 of the study).

Counts: 35 items with >= 2 real source chapters under the corpus root; 25 of them are in
the measured index copy with at least one pre-Phase 6 clip and are eligible. No media, no
transcripts and no new fetches are included; the study may not fetch. The speaker gate's
material (already-held diarization run output with human annotations) does not exist in
the copy, so that gate is expected to report blocked.

Rebinding: all paths in the manifest are relative to this directory or recorded as
provenance only; the study must not follow absolute paths to another checkout or the
resident corpus. `SHA256SUMS` seals the workspace before any annotation.
