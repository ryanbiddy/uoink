# Phase 6 implementation brief, run BC (2026-09-08)

Fable's dispatch under `ORCHESTRATION-V1-2026-09-04.md`. Contract `phase6-v1`
([PHASE6-CONTRACT-2026-09-08.md](PHASE6-CONTRACT-2026-09-08.md), Astra) is frozen and
governs every shape, hash, projection rule, refusal and test name; it says no schema,
projection, export or identity choice is delegated to implementation. Base: the commit
this brief lands in. No worker runs a model, a transcription engine, the resident helper,
or touches port 5179 or the live index. Do not commit; Fable integrates and runs every test.

## Fable's reservations resolved

- **Shared-file edits** (contract, "BB verification and remaining dispatch decisions"):
  Fable releases the following to the Claude worker for BC only, additive and minimal:
  `migrations/0030_media_depth.sql` (the contract's DDL verbatim), `clips.py` (projection
  with labels; existing outputs byte-identical when annotations are absent), `index.py`
  (`insert_citations` carries cue labels and provenance; read helpers), `whisper_runner.py`
  (label and run provenance persistence; `transcribe_audio(..., diarize=False)` default),
  `yt_extract.py` and `podcasts.py` (chapter source from already-fetched metadata only, per
  Grok's adapter restrictions as dispositioned in the contract; no new fetch), the corpus
  and sidecar writers, and the thin `export_cited_range` adapters in `uoink_mcp_tools.py`
  (registry becomes 86) and `uoink_mcp.py` (stdio becomes 30; the canonical inventory in
  `tests/test_c01_mcp_stdio.py`, `tests/test_phase4_stdio.py`, `.mcpb/manifest.json`,
  `docs/v2-mcp.md`, `docs/v2-api.md` and the two count tests are the worker's to update in
  the same change). Dashboard wiring is Fable's after integration.
- **Two increments, one session each.** BC-1: schema, shapes and provenance, projection,
  Markdown rendering, publication/rebuild/reconstruction, deletion, diarization setting
  (P6-01 to P6-06, P6-12 to P6-15, P6-19). BC-2: `export_cited_range` with alignment,
  limits, seek equality, adapter boundaries and untrusted-metadata envelope (P6-07 to
  P6-11, P6-16 to P6-18). Gemini writes `tests/test_phase6_evaluation.py` with all 19
  contract-named tests before BC-1 (run BC-0) against the interface below; they fail on
  import until the module lands and are the acceptance target.
- **BD's measured study** needs at least ten items with real source chapters already in the
  authorized measured copy and independent annotations. Fable will inventory the copy's
  metadata for chapters after BC-1; if fewer eligible items exist, BD's navigation and
  speaker gates are recorded as blocked and a separate acquisition scope goes to Ryan. No
  fetch is authorized by this brief.

## Frozen module interface (`library_media.py`, the contract's suggested seam)

```python
CONTRACT_VERSION = "phase6-v1"
SCHEMA_MIGRATION = "0030_media_depth"

def validate_media_block(block: dict) -> dict          # sidecar media block round-trip; raises MediaError(invalid_source_data / invalid_request)
def media_revision(block: dict) -> str                  # 64-hex, per the contract's binding rules
def project_clips(cues: list[dict], item: dict, *, annotations: dict | None) -> list[dict]
    # clips.merge_cues semantics preserved byte-for-byte; adds speaker spans, chapter overlap and provenance per clip
def chapters_for(conn, video_id: str, *, revision: str | None = None) -> list[dict]
def chapter_at(chapters: list[dict], t: float) -> dict | None       # half-open point lookup
def render_markdown(item: dict, cues: list[dict], *, chapters, annotations) -> str
def export_cited_range(conn, args: dict, *, clock=None) -> dict     # BC-2; strict args; refusals per contract
def rebuild_item(conn, video_id: str, *, sidecar: dict | None) -> dict          # clip-only rebuild / reconstruct from files
def publish_transcript(conn, video_id: str, *, cues, media_block, artifacts) -> dict   # coherent snapshot publication
class MediaError(Exception): code: str; message: str; details: dict
```

Refusal codes are the contract's (`invalid_request`, `invalid_source_data`,
`revision_unavailable`, `coarse_timing`, `not_materialized`, `library_unavailable`,
`resource_not_found`, `resource_deleted`, `resource_too_large`, `rate_limited`). Budgets and
the trust envelope reuse `library_resources` where the contract says so.

## Owners

| Owner | Run | Files |
|---|---|---|
| gemini | BC-0 | `tests/test_phase6_evaluation.py` (all 19 names from the contract table; synthetic fixtures from your evaluation design as dispositioned by the contract; no inference engine, no `server` import against defaults) |
| claude (Fable 5.1 worker) | BC-1, then BC-2 | `library_media.py` and the released shared files above |
| Fable | after BC-1/BC-2 | integration, dashboard wiring, measured-copy chapter inventory for BD |
| Astra (codex) | BD | acceptance on the integrated candidate; the measured study or its blocked record |

Each worker reports observed counts and exact commands; the Claude worker also reports any
contract rule it could not implement exactly at the top of `library_media.py`.
