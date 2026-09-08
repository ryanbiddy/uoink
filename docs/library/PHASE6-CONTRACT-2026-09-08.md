# Phase 6 contract: chapters, local speaker labels and cited ranges

Contract version: `phase6-v1`. Date: 2026-09-08. Owner: codex (Astra).
Run: BB-codex. Implementation: BC. Acceptance: BD.

BD-0 amendment (2026-09-08): Migration 0030 now requires `IF NOT EXISTS`
on every `CREATE`, preserving the runner's replay guarantee. The wire contract
version remains `phase6-v1`; shapes and hashes are unchanged. See the
[BD-0 ruling](PHASE6-BD0-2026-09-08.md) for the amendment and BC-1 review.

BC must preserve the existing clip text, boundaries and excerpt identities while
adding revision-bound media annotations. A citation can say which local label
accompanies a passage, where that label came from, and which source chapter
overlaps it. A cited range contains stored text and actual cue bounds. Coarse
timing cannot support a precise range export.

This document freezes the implementation contract, including the SQL below. It
does not report implementation or product acceptance. BB changes only this file;
it runs no model, transcription engine, resident helper, listener on port 5179,
or live index, and makes no commit or merge. BC's shared-file reservations remain
Fable's responsibility. The brief's exclusions for Phase 2–5 services, prompts,
proof harness and tests remain in force for BB.

Inputs are the [brief](PHASE6-BRIEF-2026-09-08.md),
[Gemini evaluation](PHASE6-EVALUATION-2026-09-08.md),
[Grok restrictions](PHASE6-ADAPTER-RESTRICTIONS-2026-09-08.md),
[Phase 2 contract](PHASE2-CONTRACT-2026-09-04.md), and
[Phase 4 contract](PHASE4-CONTRACT-2026-09-08.md). The decision tables below
supersede conflicting Phase 6 proposals. Phase 2/4 identity and evidence rules
retain their authority. `phase6-v1-2026-09-08` in Gemini's examples is amended to
the exact version string `phase6-v1`.

## Inspected baseline

The brief landed in `7319cf49f5dee8a0258d478a7448b64ec8e8ae7d`.
This inspection used `2d8fd6ca946b8425628c18b907ba34aca1b33169`, which includes
Gemini's `3b0aeb7` and Grok's `7850469` inputs. References below are relative to
this checkout. Companion documents' absolute links into other workers' checkouts
are not implementation paths. Line numbers in Grok's note have drifted; a line
being in range does not establish that it still supports the claim.

| Inspected seam | Source observation and consequence |
|---|---|
| `whisper_runner.py:205–317` | `_shape_segments` retains a segment label but drops word detail. `transcribe_audio(..., diarize=False)` sets `diarization_ran` only after assignment succeeds. There is no persisted run ID. Failure is caught around the whole optional stage, not a documented partial-success stream. |
| `whisper_runner.py:111–118, 327–360` | Import probes WhisperX; inspection must not import this module in BB. Transcript writing is a direct file write; episode state stores a boolean, not label provenance. |
| `clips.py:37–45, 187–280, 300–347` | Merge uses 45/120-second thresholds, word de-overlap, short echo removal, stale-track stopping and a final short-window fold. Rebuild deletes derived rows; `speaker` is inserted as NULL. `timing_kind` derives coarse timing from duration. |
| `migrations/0024_clips.sql:16–55` | `clips.speaker` already exists. `(video_id,seq)` is unique; `clip_id` is a database key. FTS indexes only `text` and has insert/delete/update triggers. The brief's statement that no speaker field exists is corrected. |
| `yt_extract.py:128–158, 171–189, 213–234` | SRT parsing strips markup and emits three-tuples. The CLI has no chapter field and no info-JSON capture. No new CLI fetch is needed for Phase 6. |
| `server.py:2869–2886, 4103–4186, 4355–4362, 4640–4689` | The helper capture already obtains/persists metadata and renders chapters, but its main sidecar omits chapter rows and stores transcript triples. The existing chapter renderer can omit cues outside chapters and invent the fallback title `Chapter`; neither behavior is permitted in the new rendering. |
| `podcasts.py:340–434, 948–958, 1048–1084, 1136–1261` | Feeds do not parse chapters/transcript URLs. Transcript loading preserves labels; Markdown/sidecar retain them, but citation construction drops them. Source URL prefers episode page, then URL-shaped GUID/homepage/feed; it is not necessarily audio. The sidecar's OR of row/transcript diarization booleans cannot establish a run. |
| `server.py:2201–2321, 2343–2386`; `index.py:1724–1773` | Sidecar reconstruction drops labels. Citation replacement trims old tails, returns early on an empty batch and rebuilds clips in the same commit, but logs clip errors and continues. Phase 6 publication needs explicit replacement of an empty transcript and coherent metadata/projection success. |
| `provenance.py:76–145`; `migrations/0026_provenance_precedence.sql` | Explicit metadata `source_type`, `kind`, `type` precede sidecar kinds, then platform/URL fallbacks. Media annotations must not reclassify a page, note or thread as timed video. |
| `library_cards.py:32–45, 63–81, 133–160` | Excerpts hash the pre-truncation selected evidence; source revision also hashes public item fields, URL and opening prose from the bounded corpus head. Adding labels inside Markdown can change source revision even when clip text is unchanged. |
| `server.py:829, 1208, 6881–6904, 7373, 11725–11735` | `diarization_default` is already false. Explicit request value overrides the setting; standing capture reads it. Reusing a completed transcript must reuse its provenance, not claim a new run. |

These are source observations. No live chapter payload, player behavior, model
accuracy or measured-copy improvement was observed in BB.

## Identity and revision bindings

`video_id` is the exact existing item ID. No renaming, case folding or replacement
with a slug, episode number, channel or shortened capture key is allowed. Preserve
the podcast bridge's full feed/GUID/capture-key collision checks.

Freeze these distinct bindings:

| Binding | Exact meaning |
|---|---|
| Clip identity | Existing item plus existing deterministic window. Keep `seq`, `start`, `end`, `text`, `source_deep_link`, `cue_count` and computed `timing` unchanged for unchanged cue cores. `clip_id` may change on rebuild and is never a public evidence ID. |
| Timed `excerpt_id` | Existing SHA-256 of `library_cards.serialize_card([video_id, selected])`, where `selected` has exactly `start,end,text,deep_link,seq,timing`, constructed with the existing builder's normalization. No label, chapter, run or annotation key enters it. |
| Text `excerpt_id` | Existing hash of `[video_id,"opening_prose",prose]`, before excerpt truncation. Phase 6 does not relabel discovery hints or generated Markdown metadata as original prose. |
| `source_revision` | The unchanged shared card algorithm. Use the current selection `spread-longest-v2`; do not revert to Phase 2's earlier v1 selection. Do not implement an adapter-specific revision algorithm or bypass Phase 2 invalidation. |
| `cue_revision` | A new annotation binding only: hash of `["phase6-cues-v1",video_id,cores]`. `cores` is the sequence-ordered list of transcript citation objects with exactly `seq,timestamp_start,timestamp_end,text,source_url,source_deep_link`. Hash actual stored values before clip normalization; exclude row IDs and speaker fields. |
| `cue_hash` | Hash of `["phase6-cue-v1",video_id,core]` for one object from that list. A sequence alone cannot bind a label after replacement. |
| `media_revision` | Hash of the canonical `media_depth` sidecar object defined below, excluding only its own `media_revision` member. This binds source/cue revision, producer records, runs, labels, chapter rows, absence states and playback metadata. It is never substituted for `source_revision`. |
| `corpus_revision` | Phase 4's hash of the complete corpus file bytes. A rendering change changes this binding even if opening prose and all excerpts remain equal. |

All new structured hashes use the existing `library_cards.serialize_card` and
SHA-256 over its UTF-8 output. Hash strings are 64 lowercase hex digits. Reject
non-finite numbers and duplicate keys before serialization. Preserve numeric
representations as stored when calling the existing evidence builder; do not
silently change an old `0` into `0.0` in an existing hashed selection.

Phase 2 still accepts only `basis=packet` or the frozen default `fetched_full`
card. Range exports, chapter titles and label annotations add no evidence basis.
A quote validated for a shelf must still occur in one specified excerpt at the
same item/revision. An exported passage crossing two clips cannot be submitted
as one Phase 2 quote merely because export returned it together.

An unchanged rebuild preserves all bindings and labels. A label-only update
changes `media_revision`; it preserves timed excerpt IDs. If it changes corpus
opening prose or another existing card input, it also changes `source_revision`.
Never promise that hiding metadata from `selected` keeps the entire card stable.
The first 8 KiB can change through added headings as well as added prose.

Phase 4 remains a current-snapshot reader: old source/card/corpus URIs either
resolve to the same bound representation or refuse `revision_unavailable`.
Changed source text, timing, ordering or link may produce a different excerpt ID;
never remap the old ID to a same-sequence row. A known soft deletion returns
`resource_deleted`; a hard-purged identity returns `resource_not_found`. Existing
Phase 4 excerpt/card representations are not extended with mutable annotations
under their old URIs. Phase 6 export carries the additional media binding.

## Migration 0030

Reserve `migrations/0030_media_depth.sql`. `0029` remains reserved for Phase 4.
The following is the complete frozen DDL, amended in BD-0. The shipped file must
match this DDL. Apply through the existing transactional migration runner with
foreign keys enabled. Every `CREATE TABLE` and `CREATE INDEX` uses `IF NOT EXISTS`.
Keep `ALTER TABLE ... ADD COLUMN` routed through the runner's existing
`_safe_alter_add_column` helper, which skips an already-present column. If DDL
exists but its version marker is missing, replay must preserve the schema, all
populated rows and FTS results, then restore exactly one version-30 marker.
An already-recorded version 30 requires no new migration. Do not edit 0024/0026,
rebuild the clips table, change FTS text or add a
global speaker/entity table. An upgrade initializes nullable/empty annotations
and performs no network, model execution or automatic sidecar scan.

```sql
CREATE TABLE IF NOT EXISTS media_depth (
    video_id TEXT PRIMARY KEY NOT NULL,
    source_revision TEXT NOT NULL CHECK (
        length(source_revision)=64 AND source_revision NOT GLOB '*[^0-9a-f]*'),
    cue_revision TEXT NOT NULL CHECK (
        length(cue_revision)=64 AND cue_revision NOT GLOB '*[^0-9a-f]*'),
    media_revision TEXT NOT NULL CHECK (
        length(media_revision)=64 AND media_revision NOT GLOB '*[^0-9a-f]*'),
    chapter_state TEXT NOT NULL CHECK (
        chapter_state IN ('present','absent','invalid','unsupported')),
    speaker_state TEXT NOT NULL CHECK (
        speaker_state IN ('present','partial','absent','invalid','unsupported')),
    diarization_state TEXT NOT NULL CHECK (
        diarization_state IN ('not_requested','succeeded','failed','legacy_reported')),
    provenance_json TEXT NOT NULL CHECK (
        json_valid(provenance_json) AND json_type(provenance_json)='object'),
    playback_json TEXT NOT NULL CHECK (
        json_valid(playback_json) AND json_type(playback_json)='object'),
    FOREIGN KEY (video_id) REFERENCES yoinks(video_id) ON DELETE CASCADE,
    UNIQUE (video_id, source_revision)
);

CREATE TABLE IF NOT EXISTS diarization_runs (
    video_id TEXT NOT NULL,
    run_id TEXT NOT NULL CHECK (
        length(run_id) BETWEEN 1 AND 96 AND run_id NOT GLOB '*[^A-Za-z0-9_-]*'),
    cue_revision TEXT NOT NULL CHECK (
        length(cue_revision)=64 AND cue_revision NOT GLOB '*[^0-9a-f]*'),
    status TEXT NOT NULL CHECK (status IN ('succeeded','failed','legacy_reported')),
    producer TEXT NOT NULL,
    producer_version TEXT,
    model TEXT,
    generated_at TEXT,
    input_media_sha256 TEXT CHECK (input_media_sha256 IS NULL OR (
        length(input_media_sha256)=64 AND input_media_sha256 NOT GLOB '*[^0-9a-f]*')),
    artifact_sha256 TEXT NOT NULL CHECK (
        length(artifact_sha256)=64 AND artifact_sha256 NOT GLOB '*[^0-9a-f]*'),
    parameters_json TEXT NOT NULL CHECK (
        json_valid(parameters_json) AND json_type(parameters_json)='object'),
    PRIMARY KEY (video_id, run_id),
    FOREIGN KEY (video_id) REFERENCES yoinks(video_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chapters (
    video_id TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    seq INTEGER NOT NULL CHECK (seq >= 0),
    start REAL NOT NULL CHECK (start >= 0 AND start <= 31536000),
    end REAL NOT NULL CHECK (end > start AND end <= 31536000),
    title TEXT NOT NULL CHECK (length(trim(title)) > 0),
    provenance_json TEXT NOT NULL CHECK (
        json_valid(provenance_json) AND json_type(provenance_json)='object'),
    PRIMARY KEY (video_id, source_revision, seq),
    FOREIGN KEY (video_id, source_revision)
        REFERENCES media_depth(video_id, source_revision) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_chapters_video_time ON chapters(video_id, start, end);

ALTER TABLE citations ADD COLUMN speaker TEXT;
ALTER TABLE citations ADD COLUMN speaker_provenance_json TEXT CHECK (
    speaker_provenance_json IS NULL OR
    (json_valid(speaker_provenance_json) AND json_type(speaker_provenance_json)='object'));

ALTER TABLE clips ADD COLUMN media_revision TEXT CHECK (media_revision IS NULL OR (
    length(media_revision)=64 AND media_revision NOT GLOB '*[^0-9a-f]*'));
ALTER TABLE clips ADD COLUMN speaker_state TEXT NOT NULL DEFAULT 'absent'
    CHECK (speaker_state IN ('present','partial','absent','invalid','unsupported'));
ALTER TABLE clips ADD COLUMN speaker_labels_json TEXT NOT NULL DEFAULT '[]'
    CHECK (json_valid(speaker_labels_json) AND json_type(speaker_labels_json)='array');
ALTER TABLE clips ADD COLUMN speaker_spans_json TEXT NOT NULL DEFAULT '[]'
    CHECK (json_valid(speaker_spans_json) AND json_type(speaker_spans_json)='array');
ALTER TABLE clips ADD COLUMN chapter_seq INTEGER CHECK (chapter_seq IS NULL OR chapter_seq >= 0);
ALTER TABLE clips ADD COLUMN chapter_seqs_json TEXT NOT NULL DEFAULT '[]'
    CHECK (json_valid(chapter_seqs_json) AND json_type(chapter_seqs_json)='array');
CREATE INDEX IF NOT EXISTS idx_clips_chapter ON clips(video_id, chapter_seq);
CREATE INDEX IF NOT EXISTS idx_clips_speaker ON clips(video_id, speaker);
CREATE INDEX IF NOT EXISTS idx_citations_speaker ON citations(video_id, speaker);
```

SQLite enforces local shapes, keys and cascades. The common media validator must
also enforce the semantic constraints below on publication and reconstruction;
JSON columns are not permission to accept arbitrary objects. Readers validate
bindings before using an annotation. Cross-item run references, incomplete
projections, mismatched hashes and malformed persisted JSON refuse
`invalid_source_data`; stale but well-formed bindings refuse
`revision_unavailable`. Do not silently repair them during a read.

`media_depth` and `chapters` contain only the current published snapshot. Runs may
remain as local provenance while the item exists, but an old run never labels new
cues without an exact cue binding. Hard deletion cascades through these tables
and the existing citations/clips; deletion of source artifacts follows existing
purge rules. No old text-serving archive is introduced.

## Canonical data shapes and provenance

Keep the outer sidecar schema at version 2. Add one `media_depth` object with
exactly these members; persist arrays in the order specified. Existing transcript
text and timing remain the raw capture record. The sidecar is the durable input
to reconstruct these database projections, not Markdown parsed back into cues.

| Member | Shape and meaning |
|---|---|
| `schema_version`, `contract_version` | `1`, `"phase6-v1"`. |
| `video_id`, `source_revision`, `cue_revision`, `media_revision` | Bindings defined above. Hash `media_revision` after all other members are final. |
| `chapter_state`, `speaker_state`, `diarization_state` | The exact SQL enums. An absent `media_depth` block is legacy/unmaterialized, not proof that the source has no chapters. Read as absent with `reason="not_materialized"`; no migration-time guesses. |
| `provenance` | Exactly `{chapter_source,transcript_source,active_diarization_run_id,absence_reason,corpus_revision}`. Chapter source is a producer descriptor or null; transcript source is defined below; active run ID is a recorded run or null. `absence_reason` is exactly `{chapters,speakers}`, each null or a reason below. Corpus revision is Phase 4's full-file hash, null only when no corpus exists. Maps to `media_depth.provenance_json`. |
| `playback` | Exactly `{source_url,seek_url,seek_kind}`. Kind is `youtube`, `media_fragment`, or `none`. URLs are safe public HTTP(S) or null. `seek_url` is a base URL, never a precomputed range. Maps to `playback_json`. |
| `chapters` | Ordered list of `{seq,start,end,title,provenance}`; item/source revision are inherited from the containing object and copied into SQL. |
| `runs` | Current snapshot's referenced run records, sorted by `run_id`; exact SQL field names excluding inherited `video_id`, and `parameters` instead of `parameters_json`. A failed current attempt can be recorded with no cue labels. |
| `cues` | One entry per stored transcript cue in `seq` order: `{seq,cue_hash,speaker,speaker_provenance}`. Speaker is string or null; provenance is the object below or null. No screenshot annotations. |

For a legacy/unmaterialized read, construct this same object in memory with the
current item/source/cue bindings, empty chapters/runs, null cue labels and
`not_materialized` reasons. Its deterministic hash is returned without storing
anything. Text-only items use an empty cue list and unsupported annotation states.
Thus every export can return and later check a media revision, including absence.
Do not turn a legacy label into attributed evidence merely to populate this view.
Use only safe already-stored source URLs for virtual playback: a verified item
YouTube watch URL may supply kind `youtube`; all other unmaterialized playback
has kind `none` until a media path is verified.

`transcript_source` is exactly `{kind,artifact_sha256,provider,model,language}`.
Kind is `captions`, `local_asr`, `legacy_unknown`, or `none`; the other members
are recorded strings or null, with a 64-hex digest when available. It describes
transcript origin independently of speaker origin: local ASR with diarization
off is still local ASR. Use existing capture records, never infer origin from
wording. A prose-only item has kind `none`. Include this object unchanged in an
export's provenance so text origin is available even without speaker labels.

A producer descriptor is exactly
`{origin,provider,artifact_sha256,record_locator,recorded_at}`. `origin` is
`source_metadata`; `provider` is `youtube_metadata`, `embedded_transcript`, or
`supplied_metadata`. The digest hashes the exact original UTF-8 artifact bytes,
before adding the Phase 6 block; `record_locator` is an array of string keys and
nonnegative integer array indexes within that parsed artifact. `recorded_at` is
the recorded UTC timestamp or null. No URL fetch, local pathname or credential is
encoded in a locator. `supplied_metadata` is for explicitly supplied local data
and synthetic fixtures; it grants no new product import route or fetch class.

For a cue source, the locator names the ordered transcript collection; `seq`
selects its element. For an individual chapter it names that chapter object.
The source element must match the stored cue's text and times after the existing
capture parser's transformation. This makes a source label shared across cues
from one artifact without losing each cue's separate hash binding.

Persist referenced original JSON bytes under the owning item folder at
`.media-inputs/<artifact_sha256>.json` before publication, with immutable content
and verified digest. Resolve this internal path from the item folder and hash;
it never enters public provenance. For new transcription, archive the output
JSON before adding Phase 6 run/provenance fields, avoiding a self-hash cycle.
Legacy import archives the original file unchanged. Retain only artifacts needed
by the current sidecar and retained run records, subject to existing deletion
rules. Never duplicate audio for this purpose; record its digest at execution.
Admission is at most 16,777,216 bytes of referenced JSON per item snapshot and
2,048 chapters. Over-limit optional metadata is invalid with a visible reason;
preserve the original capture and transcript rather than truncate them.

Chapter provenance is a producer descriptor, always `origin=source_metadata`.
The preserved input artifact must actually supply start, end and title at the
locator. A sidecar is a storage carrier, not a new origin that erases the producer.
Production BC chapters come only from the already-obtained YouTube `chapters`
list. Podcast fixtures can exercise the generic shape with supplied metadata;
the production podcast adapter still returns unsupported chapter acquisition.

A non-null cue label has exactly one provenance object:

| Origin | Exact `speaker_provenance` shape |
|---|---|
| Source metadata | `{origin:"source_metadata",cue_revision,cue_hash,source:Producer,run_id:null}`. A structured timed voice label must be explicit in the already-held source artifact. Text prefixes, channel names and show titles do not qualify. |
| Diarization run | `{origin:"diarization_run",cue_revision,cue_hash,source:null,run_id}`. The referenced row belongs to this item and this cue revision and has status `succeeded` or `legacy_reported`. |
| Absent | `speaker:null,speaker_provenance:null`. No fabricated label or producer object. |

Labels contain 1–128 Unicode code points, at most 512 UTF-8 bytes, and no control
characters. Keep spelling, case and Unicode as supplied; reject blank labels.
`SPEAKER_00` is a permitted value. No automatic renumbering, friendly person name,
gender, host/guest role, confidence score or identity match is inferred. A label
may contain a comma, which is one reason a comma-joined scalar is not storage.

Prefer a valid structured source label for a cue; otherwise use a valid label
from the active run for that same cue. Do not fill unmatched intervals by the
nearest label. BC does not recover stripped SRT tags or add a new caption parser.
The source-label shape exists for lossless replay of already structured data and
fixture coverage. Current YouTube SRT capture supplies no such label.

For a new executed diarization run, generate a fresh UUID4 hexadecimal `run_id`
once and persist it with the transcript. Record the actual producer, package
version, diarization model identifier, UTC completion time, input audio SHA-256,
output transcript artifact SHA-256 and parameters `{language,alignment_model}`
(unknown values null). `model` means the diarization model, not Whisper's `base`
transcription setting. A transcript retry/rebuild reuses that ID. A genuinely new
execution gets a new ID even if output labels have the same spelling. Failed
optional runs have status `failed` and supply no labels. Preserve the completed
transcript, with an explicit failed state, instead of claiming success.
At most one active run supplies cue labels in a current snapshot. Mixed run IDs
in that active assignment set fail validation; rebuilding never coalesces them.

Legacy transcript JSON with `diarization_ran:true` and labels may be imported
without running a model. Its stable run ID is `legacy_` plus the SHA-256 of the
original transcript file bytes; status is `legacy_reported`, producer
`legacy_transcript`, and unavailable version/model/input hash/time are null.
Persist the original artifact digest before adding fields. This records an old
artifact's report, not a newly verified execution. Use only its own boolean;
do not OR it with a possibly stale episode-row flag. A legacy label without any
source/run provenance stays in the original artifact but is not promoted into
attributed evidence: `speaker_state=invalid`, reason `unverified_legacy_label`.

`diarization_ran` remains a compatibility projection: true only for the selected
successful or legacy-reported run, false for failed/not-requested. Consumers must
also inspect `diarization_state`. A successful run with one label remains one
label; a successful run with missing cue assignments is `speaker_state=partial`.
An exception is not evidence of usable partial diarization output. Source labels
can exist while diarization is off; the two properties are independent.

Absence reasons are `not_materialized`, `not_supplied`, `adapter_unsupported`,
`diarization_off`, `diarization_failed`, `unlabeled_cues`,
`unverified_legacy_label`, or `invalid_metadata`. `present` requires all applicable
nonempty timed cues to have valid labels; `partial` requires some but not all;
`absent` has none. `unsupported` means the adapter/item has no supported timed
annotation path. An invalid optional input is recorded as invalid with no active
rows from it. It must not destroy valid transcript text.

Chapters require finite numeric seconds, `0 <= start < end <= 31536000`, a
nonblank source title of at most 512 code points/2,048 UTF-8 bytes, contiguous
zero-based sequence and strictly increasing, nonoverlapping ranges. Gaps are
allowed. Bounds are half-open `[start,end)`. If independently known source media
duration exists, require `end <= duration`; the last transcript cue is not a
substitute for duration. Do not sort, clamp, infer an end from the next chapter,
fill a gap, or invent a title. Reject the entire invalid chapter list into
`chapter_state=invalid`, preserving the raw artifact and the reason. Empty input
means absent, zero rows. The one-year bound is an input limit, not a media fact.

## Deterministic cue-to-clip projection

Run the existing merge behavior on the same sequence-ordered cue cores. Annotate
its output without changing any core field or adding a flush at a speaker/chapter
boundary. In particular, retain its evaluation of `fresh` words before a
max-window flush and its trailing fold. Fixing those behaviors is a separate
identity-changing proposal.

Trace each contribution while the existing merger accepts, de-overlaps and folds
cues. `speaker_spans_json` contains ordered objects with exactly
`{cue_seq,cue_hash,start,end,text_start,text_end,label_index}`. Text offsets are
half-open Unicode code-point offsets in the final unchanged `clips.text`;
`start,end` are the original cue interval, never word timing. `label_index` is
an index into `speaker_labels_json` or null for an unattributed contribution.
Whitespace inserted between contributions is not assigned to a speaker.

`speaker_labels_json` is the distinct list of `{label,provenance}` in first
contributing-text order. Distinctness includes the provenance: the same spelling
from two runs is not the same label occurrence. The provenance object is the cue
shape above without `cue_hash`; individual hashes remain in spans. Multiple cues
from one producer/run and cue revision therefore share a label entry.

Dropped echoes, empty cues and stale-track tails contribute no spans or labels.
A retained cue that adds no new words can still affect legacy `cue_count`/end;
it contributes no label to the words already retained. Tail-folded windows carry
all their spans with corrected text offsets. Coarse split parts retain their
original coarse interval and offsets; no part gets more precise timing.

For each clip:

| Field | Frozen projection |
|---|---|
| `speaker_state` | `present` if every text contribution is attributed, `partial` if some are, otherwise the applicable absent/invalid/unsupported state. Multiple known speakers can still be present. |
| Existing `speaker` | Exact label only if all contributed text has the same one label/provenance pair. Otherwise NULL. Mixed or partial attribution must not look like a single speaker. |
| `speaker_labels_json` | All contributing label/provenance pairs, including multiple speakers; empty when none. Never split or filter a comma-joined string. |
| `chapter_seq` | Chapter containing the clip's start, else NULL. This is a navigation convenience, not ownership of the entire clip. |
| `chapter_seqs_json` | All chapter sequences whose ranges intersect `[clip.start,clip.end)`, in source order. Exact boundary contact without overlap is excluded. |
| `media_revision` | Current valid media snapshot hash. NULL for an unmaterialized legacy clip. |

The current merger applied to Gemini's raw fixtures has these expected windows.
These replace its Fixture 1 expectations; labels here abbreviate full provenance.

| Fixture | Clip seq | Input cue seqs contributing text | Start–end | Labels in order | `speaker` | Start chapter / all overlaps |
|---|---:|---|---|---|---|---|
| 1 | 0 | 0,1 | 0–48 | 00,01 | NULL | 0 / [0] |
| 1 | 1 | 2,3 | 48.5–95 | 00,01 | NULL | 0 / [0,1] |
| 1 | 2 | 4,5 | 95.5–175 | 01,00 | NULL | 1 / [1] |
| 1 | 3 | 6,7,8 | 180–265 | 01,00 | NULL | 2 / [2] |
| 2 | 0 | 0,1 | 0–55 | [] | NULL | 0 / [0] |
| 2 | 1 | 2,3 | 120–185 | [] | NULL | 1 / [1] |
| 2 | 2 | 4,5 | 300–375 | [] | NULL | 2 / [2] |
| 3 | 0 | 0,2 | 0–48 | 00 | SPEAKER_00 | 0 / [0] |
| 3 | 1 | 3,4 | 48.5–110 | 00 | SPEAKER_00 | 0 / [0,1] |

For Fixture 1, cue 1 already closes a sentence after 48 seconds. Cue 8 folds into
the preceding clip. Neither chapters nor labels justify changing that behavior.
The `[60,125]` export example spans parts of clips 1 and 2, not one clip.

## Markdown corpus rendering

Freeze render version `media-markdown-v1` for Phase 6-owned media sections.
Existing source prose, description, images and other corpus sections keep their
ownership. Render every raw transcript cue exactly once in sequence, including
cues outside chapter coverage. Never group by chapter using a loop that drops or
duplicates cues. No label is inserted into `citations.text` or `clips.text`.

Add a separate `## Chapters` list of source-provided title, exact start/end and
safe seek link where supported. Then render `## Transcript` with cue headings
containing timing and any local label, followed by the cue's text. A cue spanning
a chapter boundary stays intact. Add the provenance kind and run ID, if any, on
a metadata line outside the quote. For mixed clip previews list all local labels
and show their contribution spans; never attribute the full quote to the first.

Illustrative rendering for supplied fixture metadata, not an observed podcast:

```markdown
## Chapters

- [00:01:00.000–00:03:00.000](https://example.test/episode.mp3#t=60): B-Trees versus LSM Trees

## Transcript

### [00:01:00.000–00:01:35.000](https://example.test/episode.mp3#t=60) — SPEAKER_01

**Speaker provenance:** local diarization; run run-diar-20260908-01.

LSM trees write sequentially to an append log.
```

Display timestamps to milliseconds while retaining exact numeric seconds in
structured data. Display rounding never defines identity or seek arithmetic.
When chapter data is absent, show `Chapters: not supplied`; when unsupported,
show `Chapters: unavailable from this adapter`. Omit invented chapter headings.
When no labels exist, omit a cue's label suffix and show the item-level speaker
state, such as `Speaker labels: diarization off`. Source-provided labels remain
visible with `source metadata` provenance even when diarization is off.

Escape Markdown syntax in titles/labels and encode link destinations separately.
Do not render source HTML, remote images from annotations, local file links or
terminal controls. Reversible escaping must preserve the decoded quotation.
Model-facing exports use the Phase 4 untrusted-data envelope and canonical JSON
escaping, not an unfenced copy of these human-facing Markdown sections.

Re-rendering is an explicit publication step, not a side effect of clip rebuild
or range reads. Compute `source_revision` only after final corpus bytes exist;
then build the media block, which is not embedded back into the corpus head.
Do not render `source_revision`/`media_revision` into corpus text and create a
self-referential hash. If corpus re-render changes a card input, invalidate old
Phase 2 work through its existing service and let Phase 4 reject stale addresses.
An unchanged re-render must produce byte-identical media sections.

## Cited range export

BC provides one read-only domain operation `export_cited_range` and thin registry
and stdio adapters under Fable's shared-file reservation. No new Phase 4 resource
template, corpus write, saved artifact, playback launch or network call occurs on
read. A separate user save action may persist a returned export later.

Input is a strict object with required `video_id` and exactly one selector:
`start` plus `end`, or `excerpt_id`. Optional `source_revision` and
`media_revision` pin a previous result. Each supplied hash uses the 64-hex grammar;
explicit null, unknown fields, duplicate keys, booleans as numbers, non-finite
values, malformed IDs and ambiguous selectors refuse `invalid_request` before
storage access. Item IDs follow Phase 4's exact 1–512 UTF-8 byte grammar.

An unpinned request reads one coherent current snapshot and returns its bindings.
It does not assert historical label stability. A repeat intended to validate an
old export must pass both revision hashes. Mismatch or concurrent source/media
change refuses `revision_unavailable`, without old quote content. An excerpt
ID with no current match also refuses `revision_unavailable`; never fall back to
sequence, fuzzy text or the current selection's nearest clip.

Timestamp mode requires `0 <= start < end <= 31536000`, duration at most 120
seconds, at most 200 selected cues, and exact complete-cue boundaries. Select
all nonempty transcript cues with positive overlap with `[start,end)` in sequence
order. The requested start must equal the first selected cue's start; end must
equal the maximum selected end; every selected cue must fit fully inside the
request. Do not interpolate, trim words, silently snap or drop a crossing cue.
Gaps between cues are retained as gaps. Equal boundary comparisons use the stored
numeric values, with no hidden tolerance. A zero-duration cue, backward track,
invalid timing or inconsistent order makes the affected range ineligible.

Each returned cue's text is the exact stored `citations.text`, including its
whitespace and punctuation. `verbatim_text` is those strings joined with one LF;
`text_basis="stored_cues"` and `separator="\n"` disclose this assembly. `units`
preserve individual source quotations and timing. Do not run clip de-overlap on
this mode, concatenate unrelated clips into one original quote, or call raw
stored transcript text an independently verified acoustic transcript.

Excerpt mode resolves the existing pre-truncation excerpt ID using Phase 4's
identity rules. For `timed_clip`, return exactly the complete stored clip text,
original clip bounds, and `text_basis="clip_projection"`; include the cue
contribution spans above to disclose its existing whitespace/de-overlap transform.
For an eligible original `text_only` excerpt, return its complete bound opening
prose, null bounds, `timing="not_timed"`, and `text_basis="opening_prose"`.
Hints alone refuse `invalid_source_data`. Labels/chapters are never quoted as
speech. No new or truncated excerpt ID is minted.

Every selected cue and timed excerpt must have finite, valid `source_cues`
timing. A cue over 120 seconds is coarse regardless of how small the requested
slice is. Any coarse unit refuses the whole timed export, including a request for
the whole coarse interval or a coarse excerpt ID. Text-only timestamp requests
also refuse. Existing bounded Phase 4 reads can still describe a coarse excerpt
honestly; they are not a precision-export bypass.
After syntax validation and revision/deletion checks, timing eligibility takes
precedence over the 120-second duration and complete-cue boundary checks. Thus
a whole 600-second coarse cue returns `coarse_timing`, not an unrelated range
size error. A fine-timed request over the selection limits returns
`resource_too_large`; malformed numeric bounds remain `invalid_request`.

Freeze this result shape (all members required unless the table says nullable):

| Member | Value |
|---|---|
| Envelope | `ok:true,schema_version:1,contract_version:"phase6-v1"`. |
| `item` | `{video_id,title,platform,source_type,source_url,source_revision,media_revision}`; title/platform/source type may be null if unknown; safe URL nullable; both revisions are required hashes. |
| `selection` | `{mode,requested_start,requested_end,excerpt_id}`; mode is `range` or `excerpt`; unused selectors null. |
| `citation` | `{evidence_kind,timing,start,end,verbatim_text,text_basis,separator,source_deep_link,seek_link,player_seek_seconds,truncated}`. Evidence kind is `transcript_range` for range mode, otherwise the unchanged `timed_clip` or `text_only` kind. `transcript_range` is export-only, not a new Phase 2 basis. `truncated` is always false on success. Separator is LF for stored cues, null otherwise. |
| `units` | Timestamp mode: `{cue_seq,cue_hash,start,end,text,speaker,speaker_provenance}` per cue. Timed excerpt mode: `{cue_seq,cue_hash,start,end,text,text_start,text_end,speaker,speaker_provenance}` per contribution, with exact clip text slice and the contributing cue's full provenance. Text-only mode: one `{excerpt_id,text}` unit. |
| `chapters` | All overlapping chapter objects, each with item/source revision and provenance; empty for absent/invalid/unsupported or text-only. |
| `attribution` | `{speaker_state,diarization_state,diarization_ran,labels,runs,chapter_state,absence_reason}`; only runs referenced by the returned attribution, plus the current failed run if needed to explain absence. Labels are local descriptors, never identities. |
| `provenance` | `{cue_revision,transcript_source,evidence_refs,render_version}`; cue revision null for prose; transcript source as defined above; render version `media-markdown-v1`. Evidence refs are `{source_revision,excerpt_id}` for clips with a contribution from a selected cue hash, deduplicated in clip order, or the selected excerpt alone in excerpt mode. A dropped raw echo may have no clip ref; an empty list does not mint evidence. |

For Gemini Fixture 1, range `[60,125]` returns exactly cue 3 and cue 4 as two
units, joined by LF; both bear `SPEAKER_01` with their recorded run. Bounds are
60 and 125, chapter overlap is `[1]`, and evidence refs name clips 1 and 2's
unchanged excerpt IDs. Source revision/hash placeholders in the evaluation doc
are not golden hashes: BC computes and freezes them from complete fixture inputs.

The source citation and the seek target have separate meanings. `source_deep_link`
is the selected excerpt's original safe link in excerpt mode, or the first
selected cue's original safe link in range mode. It is not edited in place to
repair a legacy hash. `seek_link` is built only from validated playback metadata:

| Playback kind | `seek_link` and player command |
|---|---|
| YouTube | Valid item watch URL with exactly one `t={floor(start)}s` parameter. Player command is the same integer. Check that the video identity matches the item. |
| Direct media | Valid already-recorded enclosure/media URL, with old fragment removed and `#t={floor(start)}` added. Only an implemented, tested media-fragment/local media player path earns `seek_kind=media_fragment`. |
| Other page/provider or absent media | `seek_link:null,player_seek_seconds:null`. Preserve a valid source citation; do not invent a seek capability from a generic `#t=` fragment, including Vimeo or an episode homepage. |

For text-only items, source link is the valid original URL (including an existing
document anchor), seek fields and times are null. Do not strip legitimate anchors
or invent `#t=0`. Unsafe URLs become null; if returning an existing hashed excerpt
would require changing unsafe hashed fields, refuse `invalid_source_data` under
Phase 4's rule. Local audio paths are never public links.

For supported players, freeze `floor(citation.start) == parsed seek time ==
player command`, and `0 <= citation.start - player command < 1`. Exact cue end is
returned separately: a start-only URL does not guarantee playback stops at end.
A range player that offers stop-at-end must use the exact returned end. Physical
playback onset is a separate BD observation; correct URL arithmetic alone is not
proof of audible alignment.

Requests share Phase 4's 8,192-byte input, 65,536-byte total serialized response,
24,576-byte rendered text, 2-second service deadline, two active reads and 60
admissions per rolling minute. Both `citation.verbatim_text` and the sum of unit
text lengths must be at most 2,000 Unicode code points. Count duplicate
text/structured forms on the wire. An over-limit result refuses
`resource_too_large`; no partial export,
ellipses, clipped provenance or automatic full-corpus fallback. New modules must
use the common admission context when composed with Phase 4 reads.

Errors retain `{ok:false,schema_version:1,contract_version:"phase6-v1",
error:{code,message,retryable,details}}` and the existing transport conventions.
Freeze these selection reasons within `invalid_request.details.reason`:

| Reason | Required details; no quote text in the refusal |
|---|---|
| `coarse_timing` | `timing_kind:"coarse"`, requested range or excerpt ID, `enclosing_intervals:[{start,end}]`, `next_step:"read_library_resource"`. No purported subrange seek link. |
| `not_timed` | `timing_kind:"not_timed"`, `next_step:"get_library_item"` to obtain a prose excerpt ID. |
| `unaligned_range` | Requested range and nearest enclosing complete-cue bounds, without executing that larger selection. |
| `empty_range` | Requested range; no cue overlap. |
| `invalid_selector` | A fixed validation message; never echo hostile input. |

Use Phase 4 codes for missing/deleted items, unavailable revisions, invalid source
data, encoding/size failures and storage/deadline/rate failures. Only
`library_unavailable`, `deadline_exceeded` and `rate_limited` are retryable
unchanged. No new HTTP 200 promise overrides the existing tool transport wrapper.

## Publication, reconstruction and settings

BC uses one shared, offline media validator/projector for capture and rebuild.
Suggested implementation seam: new `library_media.py`; it must not import the
helper or an inference runtime. This name reserves no edits in another phase.
The same sidecar block must survive both `episode_to_corpus` and
`_citations_from_sidecar`, and `Index.insert_citations` must carry cue labels and
provenance into its projection transaction.

| Operation | Required behavior |
|---|---|
| Upgrade | Install DDL once through the migration ledger. Existing cue/clip core rows and FTS results remain byte/value-identical. No fabricated run rows or inferred labels. |
| Clip-only rebuild | Read current citations plus the valid media block/rows; replace clips and all annotation projections together. Preserve every core and media binding. No Markdown write, new run, fetch, transcription or generated timestamp. |
| Reconstruct from files | Verify item identity and artifact/hash bindings; recover raw transcript, chapter source, run records and annotations from the sidecar/original artifacts. Rebuild in memory, then publish one coherent snapshot. Never recover labels from rendered headings. |
| Publish changed transcript | Explicitly replace the complete transcript kind, including an empty replacement that deletes old cues/clips. Preserve screenshot rows. Validate shorter/reordered tracks; no stale tail labels or sequence reuse. Compute new bindings and trigger existing source invalidation after coherent commit. |
| Publish metadata only | Preserve cue cores and clip core tuples. Recompute media binding and, if corpus rendering changes card inputs, source binding. Old revision-bound reads refuse instead of returning relabeled data. |
| Reuse DONE transcript | Reuse its run/artifact/label provenance. If requested diarization differs, disclose reuse; enabling the setting does not silently rerun it. A new execution requires an explicit new transcription/diarization request. |
| Missing/corrupt sidecar | With a materialized DB snapshot, a missing required sidecar/artifact returns `library_unavailable`; corrupt data returns `invalid_source_data`. Only an item without a materialized snapshot/block uses the virtual `not_materialized` view. Neither case drops existing DB labels. A rebuild lacking required provenance refuses that item's publication. |
| Soft/hard delete | Respect current deletion before every read. Hard purge removes owned annotation/transcript derivatives and DB rows; no run record or delayed rebuild resurrects content. |

File and DB publication cannot be one SQLite transaction. Use unique temporary
files, flush and atomically replace each owned artifact, persist the complete
sidecar last as the file-side completion record, then commit source/citations,
chapters, runs and clips coherently in the DB. Store hashes of dependencies in
the media block; readers check them rather than trust modification times. A
crash between steps leaves an explicit incomplete/stale state; retry replays the
same durable inputs. Never mark complete after swallowing a clip projection
failure. Do not delete the last valid item snapshot before the new one validates.
Do not claim multi-file atomicity; crash tests must cover each boundary.

Before replacing files, check ownership and current input hashes under the
capture/item lock. Preserve unrelated sidecar keys and concurrent updates from
other feature owners. A user-edited corpus is a visible conflict, not permission
to overwrite it. Rebuild with a matching existing corpus leaves its bytes alone.
If regenerating a missing corpus yields different card inputs, publish a new
revision explicitly; never retain the old hash by editing the card algorithm.

Keep `diarization_default=false` as the shipped and missing-setting default.
Explicit boolean `diarize` overrides it; otherwise use the saved user setting.
Only an explicit settings action may turn that preference on. Enabling it can
affect future already-authorized captures; it grants neither source capture
consent nor a retrospective library-wide job. Changing it off affects future
runs and does not erase labels from completed runs.

Cached models and environment tokens do not imply consent. First use of the
optional alignment/diarization assets requires the existing download-consent
flow to cover those assets as well as ASR; absence/failure remains explicit.
Reads, migration, reconstruction, detection and label display never load or
download a model. BB/BC fixture tests stub execution; BD needs a separately named
scope before any real inference or media acquisition. No automatic engine swap,
paid API fallback or metered feature activation is introduced.

## Decisions on Gemini's committed evaluation

Each row identifies a proposal or assertion in the committed evaluation. Its
repeated summary/test-tree entries inherit the named ruling here.

| Input row | Ruling | Frozen result |
|---|---|---|
| §1.1 source-local labels | Adopt | Scope by item, cue revision and producer/run; no identity. |
| §1.1 evidence stability | Amend | Excerpt core hash is correct; source/card revision can also change through corpus head and item metadata. Preserve both phases' rules above. |
| §1.1 timing | Amend | >120-second cue remains coarse; unknown/invalid/nonpositive timing also cannot export precision. |
| §1.1 missing data | Adopt | Explicit states, null labels and empty lists; no generated chapter/title/person. |
| §1.1 opt-in | Amend | Saved explicit default may govern future authorized jobs; no silent background opt-in or backfill execution. |
| GATE-6-FIX / §2.1 chapters DDL | Amend | Use exact 0030 above: revision-scoped composite key, source provenance, bounds/states; no autoincrement chapter identity. |
| §2.2 citation columns/index | Amend | Keep speaker plus structured provenance; run ID alone cannot distinguish source metadata, absence or legacy report. |
| §2.3 existing clip speaker | Adopt | Reuse the existing column. |
| §2.3 chapter_seq and indexes | Amend | Keep start-chapter cache and add all-overlap array; labels/spans carry complete provenance. |
| §2.4 Markdown | Amend | Separate chapter navigation list, retain every cue, safe headings and provenance; no universal episode-page seek assumption. |
| §3.1 fixture metadata/chapters/turns | Amend | Retain as synthetic supplied inputs. Podcast feed chapter acquisition is not authorized; compute actual hashes. `base` is not a diarization model ID. |
| §3.1 expected clips 0,1,2 | Reject | Raw input yields four windows, frozen in the projection table. Do not change the merger to make the proposed three windows pass. |
| §3.2 fixture 2 inputs/windows | Adopt | Three expected windows and no speaker labels. Treat synthetic video ID as a local fixture, not a live YouTube target. |
| §3.3 echo/window/start-chapter/single speaker | Adopt | Echo is dropped; windows 0–48 and 48.5–110; second clip starts in chapter 0. Add overlap [0,1]. |
| §4.1 scalar/composite speaker rule | Reject | Mixed/partial scalar is NULL; ordered structured descriptors and spans preserve all labels without comma ambiguity. |
| §4.1 chapter start lookup/no forced flush | Adopt | `chapter_seq` is convenience only; overlap list is authoritative for coverage. |
| §4.2 hash proof / GATE-6-STAB | Amend | Test actual shared builder before/after, including text-only IDs, corpus-head shifts and stale URIs. Same text alone is insufficient. |
| §5.1 signature/selectors | Amend | Add optional source/media pins, strict limits and complete-cue boundary semantics. Preserve existing excerpt resolver. |
| §5.2 timed example / GATE-6-EXP-TIMED | Amend | Two exact cue units joined with LF; refs to two clips; production podcast page citation and audio seek are separate. Version is phase6-v1. |
| §5.3 coarse / GATE-6-EXP-COARSE | Amend | Reuse invalid_request; reason coarse_timing; refuse all precise coarse exports, including whole coarse excerpt. No claimed subinterval seek. |
| §5.4 prose / GATE-6-EXP-TEXT | Amend | Original bound prose succeeds within limits; timestamps refuse. Preserve legitimate document anchors; no hints as quotes. |
| §6.1 YouTube seek | Adopt | Floor exact source start and compare with player command. |
| §6.1 podcast/web audio seek | Amend | Only known direct media/player paths; an episode page is not evidence of support. |
| §6.1 Vimeo seek | Reject | No new provider capability from this table. Unknown support yields null seek fields. |
| §6.1 text links | Amend | No invented timing; existing non-time anchors remain. |
| §6.2–6.3 arithmetic/onset/de-overlap | Amend | Arithmetic is a deterministic gate; audible onset needs real authorized BD observation. Range mode retains raw cues; excerpt mode preserves existing de-overlap. |
| §7 no chapters | Amend | Empty rows plus explicit reason/state; export field is top-level chapters, not citation.chapter. |
| §7 diarization off | Amend | No run labels; explicit source metadata labels can still exist. |
| §7 one speaker | Adopt | Keep the one local label and successful run provenance. |
| §7 mid-stream failure | Reject | Current runner does not promise partial successful diarization. Failed run contributes no active labels; successful incomplete assignments are a separate partial case. |
| §7 out-of-bounds chapters | Amend | Validate against actual known media duration, not last cue; reject the malformed chapter list visibly. |
| §8.1 NJR | Amend | Freeze the measured paired navigation test below; do not assume baseline error >=180 seconds or force baseline starts to be failures. |
| §8.2 SCRP | Amend | Use a locally identified label, not inferred guest/host; test target words' spans. Reject LIKE on a composite scalar and invented baseline precision. Diagnostic pending separately scoped retrieval filtering. |
| §8.3 ELG | Amend | Measure words, not tokens; select whole cues and report failed/oversized tasks. The 65% figure is a diagnostic target, not an assumed result or permission to cut words. |
| §8.4 CCSD | Defer/reject for v1 | Chapter-title ranking/boosting is additional search behavior; no mandatory +25% MRR change or FTS rewrite in Phase 6. |
| GATE-6-METRIC / §9 metric test | Amend | One preregistered navigation improvement is mandatory; the other diagnostics cannot replace it or extend scope. |
| §9 test module and named fixture gates | Adopt with amendments | Use tests/test_phase6_evaluation.py and the exact required names below. A test design is not mathematical or empirical acceptance of model accuracy. |

## Decisions on Grok's committed adapter restrictions

The following tables address each distinct permission/restriction row by its
section and row order. Summary matrix (§0), frozen rules (§11), ambiguities (§12)
and sources (§13) inherit the corresponding row decision. “Adopt” freezes the
product boundary, not a claim that every external policy statement was verified
again in BB. This contract relies on inspected code and the committed policy
decisions; it makes no new vendor authorization/support claim.

| Input rows | Ruling | Decision and current-code qualification |
|---|---|---|
| §1 chapter meaning | Amend | All three fields must be supplied; invalid/missing ends are not inferred. |
| §1 speaker meaning | Adopt | Timed local label; accounts and authors are not turns. |
| §1 allow-list: standing kinds | Adopt | Current `source_subscriptions.py:96–101`, not old line 93. |
| §1 allow-list: page hosts | Adopt | `page_extractor.py:82,352–431`; no bypass for Phase 6. |
| §1 allow-list: YouTube captions | Adopt | `yt_extract.py:181–184`; unchanged English track request. |
| §1 allow-list: podcast enclosure | Adopt | Current `podcasts.py:383,1393–1399,1433–1445`. |
| §1 allow-list: X post, X article, Reddit URL, note | Adopt each | Existing URL classifiers/local note path remain unchanged; no timed annotations created from prose. |
| §1 diarization is local/default-off | Amend | Record run/artifact provenance, separate download consent, and legacy-reported state; boolean alone is insufficient. |
| §2.1 chapter availability | Amend | Reuse whatever structured chapters the existing helper blob supplies; do not assert every entry is independently verified creator authorship. |
| §2.1 speaker availability | Amend | Current SRT path has no structured output label. The broader claim that a source can never carry voice tags is too strong; no new parser/fetch is authorized. |
| §2.2 may 1: title | Adopt | Existing CLI capture only. |
| §2.2 may 2: captions/media | Adopt | Keep existing capture command, language and low-rate posture. |
| §2.2 may 3: parse captions | Adopt | Preserve current text/timing parsing. |
| §2.2 may 4: reuse metadata chapters | Adopt | `server.py:2869–2886,4355–4362`; no second chapter-specific fetch or detector call. |
| §2.2 may 5: local diarization | Amend | Existing downloaded media plus explicit opt-in; never run during rebuild to repair absent labels. |
| §2.3 must-not 1: CLI as detector | Adopt | No channel/playlist detection via capture CLI. |
| §2.3 must-not 2: Atom chapters | Adopt | Current Atom observation shape at `source_subscriptions.py:778–815` has none. |
| §2.3 must-not 3: Data API | Adopt | No new API integration; no fresh vendor-scope conclusion is needed. |
| §2.3 must-not 4: extra InnerTube/timedtext | Adopt | Freeze existing capture request set; do not reinterpret this as a claim about yt-dlp's internal requests. |
| §2.3 must-not 5: caption languages | Adopt | No Phase 6 expansion. |
| §2.3 must-not 6: comments | Adopt | Commenter is not timed speaker/chapter evidence. |
| §2.3 must-not 7: description inference | Adopt | Empty structured chapters remain empty. |
| §2.3 must-not 8: text-prefix speakers | Amend | Reject inference from `>> JOHN:`; valid source metadata need not have a diarization run ID. |
| §2.3 must-not 9: cross-video identity | Adopt | Deferred exactly as specified below. |
| §2.3 must-not 10: inaccessible content | Adopt | No access bypass to obtain media depth. |
| §2.3 must-not 11: cookie/token/sleep posture | Adopt | No capture-posture change as part of chapter work. |
| §3.1 chapters and speaker observations | Amend | No parsed chapters; labels survive transcript/Markdown/sidecar at current `podcasts.py:1048–1084,1161–1226`, but not citation writes. Chapter-bearing podcast fixtures are supplied data only. |
| §3.2 may 1: feed GET | Adopt | Existing conditional detection and 50-entry parser window; not capture consent. |
| §3.2 may 2: enclosure capture | Adopt | Enclosure-only, http(s), after consent/start reservation, with `--` and existing size cap. |
| §3.2 may 3: local transcription | Amend | Same run/provenance/default rules as above. |
| §3.2 feed validator | Adopt | Current `podcasts.py:79–119`; no new URL class. |
| §3.3 must-not 1: episode-page scrape | Adopt | Page URL can be a citation without being fetched. |
| §3.3 must-not 2: chapter JSON/psc | Amend | No chapter-file fetch; embedded XML parsing is distinct from a fetch but is also outside BC adapter scope. Do not call psc XML inherently a second URL. |
| §3.3 must-not 3: publisher transcript | Amend | No newly fetched transcript URL. Publisher text would need explicit source provenance, not necessarily local ASR; that support is deferred. |
| §3.3 must-not 4: show title as host | Adopt | `host:null` at current `podcasts.py:1213–1216`. |
| §3.3 must-not 5: YouTube as podcast | Adopt | Preserve separate capture kinds and enclosure requirement. |
| §3.3 must-not 6: unsafe enclosure/options | Adopt | Existing scheme gate and argument delimiter. |
| §3.3 must-not 7: private RSS/itunes:block | Amend | No auth/scrape workaround. Missing itunes:block parsing is an existing policy gap, not an implemented rejection or a Phase 6 repair. |
| §3.3 must-not 8: implicit diarization | Adopt | Off/failed does not infer a monologue. Source metadata labels remain a distinct origin. |
| §3.3 must-not 9: detection-time audio | Adopt | No media work in detector. |
| §4.1 X thread/posts | Adopt | Document order and author account provide no turn clock. |
| §4.2 may 1: syndication status | Adopt | On-demand existing URL capture only. |
| §4.2 may 2: ancestor chain | Amend | At most 25 parent hops after the initial post, potentially 26 posts; same-author rule stays. |
| §4.2 may 3: embedded parent | Adopt | Matching ID avoids a fetch; no new traversal. |
| §4.2 FxTwitter paragraph | Amend | Default-off is a prior policy requirement, not current code behavior (`x_extractor.py:156–157` calls enrichment). No Phase 6 dependency or unreserved repair. |
| §4.3 must-not 1: GraphQL/replies below | Adopt | No expanded authenticated capture; external penalty claims are not contract requirements. |
| §4.3 must-not 2: alternative watchers | Adopt | X watching remains deferred; no claim about a third-party service's present viability is needed. |
| §4.3 must-not 3: articles via status adapter | Adopt | Existing separate payload path. |
| §4.3 must-not 4: video bytes/HLS | Amend | This prose adapter must not fetch video. Existing regular media capture is a separate path; its timed evidence remains readable without manufacturing X author labels. |
| §4.3 must-not 5: posts/authors as annotations | Adopt | No chapters or speakers from thread structure. |
| §4.3 must-not 6: hop/author expansion | Adopt | Cap and same-author traversal unchanged. |
| §5.1–5.2 article payload/no network | Adopt | Extension-supplied DOM payload only; byline is not a speaker. |
| §5.3 must-not 1: helper article GET | Adopt | No login-wall workaround. |
| §5.3 must-not 2: syndication/FxTwitter | Adopt | No new article client or Phase 6 use. |
| §5.3 must-not 3: GraphQL/headless/watcher | Adopt | Deferred capture classes stay deferred. |
| §5.3 must-not 4: headings/byline | Adopt | No timed annotation conversion. |
| §6.1 page structure/host | Adopt | Neither supplies a turn clock. |
| §6.2 may 1: valid URL | Adopt | Existing scheme/host/userinfo validator. |
| §6.2 may 2: active host allow-list | Adopt | User-extensible list, not general web permission. |
| §6.2 may 3: local crawl/stdlib | Adopt | Existing capture only; no annotation-specific scrape. |
| §6.2 may 4: screenshot | Adopt | Existing screenshot is not chapter/speaker evidence. |
| §6.2 may 5: depth <=1 | Adopt | No expanded crawl or Writing Studio bypass. |
| §6.3 must-not 1: off-list hosts | Adopt | No Phase 6 bypass. |
| §6.3 must-not 2: unsafe URL | Adopt | Existing validation stays. |
| §6.3 must-not 3: cloud crawl | Adopt | No new API. |
| §6.3 must-not 4: depth >=2 | Adopt | No fan-out expansion. |
| §6.3 must-not 5: login wall as content | Adopt | Preserve explicit failure. |
| §6.3 must-not 6: headings/host as annotations | Adopt | No timed provenance. |
| §6.3 must-not 7: follow links for chapters | Adopt | No new acquisition. |
| §7.1 Reddit structure/authors | Adopt | Comment tree remains document structure. |
| §7.2 may 1: thread JSON | Adopt | Existing on-demand normalized URL fetch. |
| §7.2 may 2: flatten with limits | Adopt | Existing depth, score and 500-comment cap. |
| §7.3 must-not 1: OAuth/API | Adopt | No new client. |
| §7.3 must-not 2: non-thread URLs | Adopt | Existing classifier. |
| §7.3 must-not 3: morechildren | Adopt | No continuation fetch. |
| §7.3 must-not 4: removed bodies | Adopt | Existing exclusion. |
| §7.3 must-not 5: score/count bypass | Adopt | Existing exclusions. |
| §7.3 must-not 6: inaccessible threads | Adopt | Surface failure; no workaround. |
| §7.3 must-not 7: authors/depth as annotations | Adopt | No clock. |
| §7.3 must-not 8: standing watcher | Adopt | No new kind. |
| §8.1–8.2 note text/local persistence | Adopt | No timed data or network permission. |
| §8.3 must-not 1: any fetch | Adopt | Local note remains local. |
| §8.3 must-not 2: ASR | Adopt | No audio path. |
| §8.3 must-not 3: title/author inference | Adopt | No chapters or speaker identity. |
| §9.1 row 1: closed kinds | Adopt | Current enum is at line 96. No Twitch registration. |
| §9.1 row 2: 0028 CHECK | Adopt | 0030 does not expand subscription kinds. |
| §9.1 row 3: detection/capture split | Adopt | Media annotation never starts capture. |
| §9.1 row 4: no_backend default | Adopt | No implementation inferred from an injected interface. |
| §9.1 row 5: YouTube URL parser | Adopt | Do not overload it for Twitch. |
| §9.1 row 6: 25/10 caps | Adopt | Limits confer no Twitch ingestion permission. |
| §9.2 later notify-only design | Adopt as deferral | Opted-in live notices only, pending authorization/delivery design. No current Twitch implementation claim. |
| §9.3 transport/token, callback, WebSocket session | Defer each | Unresolved product designs; this contract selects no transport or OAuth flow and does not reverify vendor protocol claims. |
| §9.3 Client ID/secret, authorizing user, conduits, revocation | Defer each | Must be separately named and verified before Twitch implementation. |
| §9.4 missed events, duplicates, notification storage/surface, online/offline pairing | Defer each | Need explicit delivery/retention/dedupe design; no corpus item or capture charge. |
| §9.4 VOD expiry | Reject as implementation rationale | An expiry claim cannot justify downloading; notify-only remains. |
| §9.4 Helix polling | Adopt prohibition | No polling substitute. |
| §9.4 yt-dlp/HLS | Adopt prohibition | No capture substitute. |
| §9.5 Twitch fetch exclusions | Adopt | No VOD/clip/HLS/chat/emotes/audio, ASR, scraping, page allow-list expansion or standing detector. |
| §10 rules 1–5 | Adopt each | Existing kinds, observations only, consented capture after start, no new standing sources, no poll-time annotation fetch. |

## Named acceptance tests

All tests below are required in BC/BD unless marked diagnostic. New Phase 6 tests
belong in `tests/test_phase6_evaluation.py`; existing Phase 2–5 regressions run
unchanged through their owners. Tests use synthetic data or a separately named,
verified disposable copy. Never import `server`/`whisper_runner` against default
settings or invoke an inference engine merely to collect fixtures.

| Gate / exact test name | Required observation |
|---|---|
| P6-01 / `test_gate_6_fix_schema_migration_0030` | Apply 0030 after the existing migrations in an isolated DB; all old cue/clip values and FTS matches survive; new defaults, JSON constraints, revision-scoped chapter uniqueness, cascades and migration-ledger retry behave as specified. No 0029 collision. |
| P6-02 / `test_phase6_provenance_shapes_and_bindings` | Source labels, new runs, failed runs, legacy reports and absent data round-trip. Reject cross-item/cue hash/run references, forged states, unsafe/control-bearing labels, booleans/non-finite times and duplicate keys. Validate actual run model versus transcription model. |
| P6-03 / `test_gate_6_proj_deterministic_speaker_projection` | Exact corrected three-fixture window table, byte-identical text, partial labels, same label from different runs, commas in labels, de-overlap, zero-contribution cues, stale rewind and trailing fold. Every attributed text span has an exact contributing cue. |
| P6-04 / `test_gate_6_stab_evidence_id_invariance` | Shared builder's old/new timed and prose excerpt IDs agree for identical cores/prose; annotate without hash contamination. Card/source/corpus bindings change only when their actual inputs change. Rebuild row IDs do not enter hashes. |
| P6-05 / `test_phase6_chapter_validation_and_overlap` | Half-open point and overlap lookup, gaps, boundary-spanning clips; empty list, bad order, overlaps, missing end/title, NaN, negative/out-of-duration bounds fail visibly. No invented range or discarded outside-chapter cue. |
| P6-06 / `test_phase6_markdown_preserves_cues_and_provenance` | Every cue appears exactly once; labels/chapters/provenance render safely outside quote text; absent/source/diarization/legacy cases differ correctly. Head shifts recompute source revision; unchanged output is byte-identical. |
| P6-07 / `test_gate_6_exp_timed_source_cues` | Exact complete-cue selection, LF assembly, per-unit raw text, two-clip provenance for Fixture 1 [60,125], safe source/seek separation, and exact full excerpt mode with contribution spans. |
| P6-08 / `test_gate_6_exp_coarse_timing_refusal` | Subrange, entire coarse range, coarse excerpt ID and mixed coarse/fine request all refuse with coarse_timing; no precise text slice or seek claim leaks. |
| P6-09 / `test_gate_6_exp_text_only_citation` | Exact original bound prose by ID, null timing/seek, legitimate source anchor; timestamp request and hint-only quotation refuse. |
| P6-10 / `test_phase6_export_alignment_limits_and_errors` | Both/neither selectors, unaligned/crossing cues, empty/zero-duration ranges, stale hashes, malformed IDs, multibyte/escaping expansion and each byte/character/cue/time limit boundary. No truncation or mutation; bounded missing/corrupt/locked storage refusals. |
| P6-11 / `test_gate_6_seek_player_equality` | Parsed exported seek equals actual player command and floor(source start) for each supported path, including 22.75 -> 22; exact end retained. Unknown episode page/provider has null seek. BD separately observes onset/seek on authorized media. |
| P6-12 / `test_gate_6_miss_boundary_conditions` | No chapters, diarization off, off with source labels, succeeded one speaker, succeeded partial assignments, failure, legacy unverified labels and unknown media duration. No phantom Speaker 1/Chapter 1. |
| P6-13 / `test_phase6_rebuild_and_publication_recovery` | Same durable inputs yield identical labels, runs, chapters, span offsets, excerpt IDs and revisions after DB/clip reconstruction. Crash before/after each file replacement and DB commit; retry does not rerun ASR. Empty/shorter replacement removes tails; stale concurrent publisher and user-edited corpus refuse. |
| P6-14 / `test_phase6_stale_citation_and_delete_refusals` | Re-extraction, timing/link/source metadata change, row reorder, item swap and corpus edits inside/outside first 8 KiB retain valid IDs or produce Phase 2/4's frozen refusals; no same-sequence remap. Soft/hard deletion and delayed reconstruction cannot resurrect text. |
| P6-15 / `test_phase6_diarization_opt_in_default_off` | Missing/default false, strict explicit false/true override, saved opt-in for future capture, separate download consent, failed stage, DONE reuse and disable-with-retained-labels. Model/network/start sentinels remain untouched during read/rebuild/detection/upgrade. |
| P6-16 / `test_phase6_adapter_fetch_boundaries` | Recorded request/command sentinels show no new URL class, language, detector media or chapter-file fetch across all Grok rows. Podcast source page is not fetched for chapters. Twitch/X watcher additions absent. Existing prose adapters emit no timed annotations. |
| P6-17 / `test_phase6_untrusted_metadata_and_read_only_export` | Hostile titles/labels/links/text cannot escape the fixed data envelope; no source path/token leaks; serialized output meets budgets. Hash source artifacts, settings, queue and projections before/after reads; unchanged. Structural test does not claim observed model behavior. |
| P6-18 / `test_gate_6_metric_benchmarks` | Validate the preregistered navigation manifest and measured paired receipt below. Refuse a PASS with missing eligible data, fabricated baselines or synthetic observations reported as real. |
| P6-19 / `test_phase6_cross_video_identity_is_absent` | Two items/runs both labeled SPEAKER_00 remain unrelated; no global ID, voice embedding, entity edge, host/guest inference or cross-item speaker filter appears. |

BD must demonstrate navigation improvement on the measured copy before acceptance.
Do not hardcode the earlier 548-item inventory as today's observed count. Fable
names a candidate SHA, source-copy manifest/hash, allowed existing metadata/media
artifacts and a disposable workspace. Record source dates and eligibility before
measuring. Copy paths must be rebound inside that workspace; never follow an old
absolute path to another checkout or resident corpus.

Freeze the mandatory study as follows:

1. Before seeing Phase 6 results, identify at least ten eligible items with real
   source chapters already present in the authorized copy and 50 navigation
   targets, at most five per item. An independent annotator records target
   chapter, source start and acceptable passage/cue interval. Use chapter-start
   navigation tasks, not an inferred topic onset inside an arbitrary chapter.
   Hash the task manifest and unchanged pre-Phase 6 clip output first. If fewer
   eligible items/tasks exist, report the gate blocked; synthetic fixtures may
   not fill the measured quota or authorize new fetches.
2. For each target, baseline is its existing containing clip's seek start; where
   it lies in a gap, choose the next clip, or the preceding last clip if none.
   Phase 6 is the source chapter seek start. Both paths use the same supported
   player and rounding. Record absolute error from the annotated source start,
   then pair the two errors per task. No assumed 180-second baseline and no
   forced linear scan from zero.
3. Require mean absolute error <=15 seconds after Phase 6 and at least 80%
   reduction relative to the observed baseline mean. A zero baseline mean gives
   no improvement proof. Include every frozen task; failed or unsupported seeks
   fail the gate rather than disappear from the denominator. Report per-item and
   aggregate values, counts, raw results and exact comparison arithmetic.
4. Separately audit 30 labeled local-speaker passages across at least five items
   with already-held run output and independent human annotations. Assess the
   label attached to the target text span, not mere co-occurrence in a mixed clip.
   Require >=95% correct attribution among attributed passages and >=80% coverage
   of the 30 targets; report every abstention/failure. Arbitrary label numbering
   is matched only within that item's run using the frozen annotations. This
   tests source-local usefulness/quality, not personal identity. Missing material
   leaves this required speaker gate blocked, not implicitly passed by a model.
5. Gemini's 100-task ELG (mean word reduction target 65%), 30-query SCRP and
   40-query CCSD are diagnostics only, with their denominators, raw outcomes and
   selection method recorded if run. No new ranking/filtering implementation is
   required by a diagnostic. Do not call a word-count ratio a token measurement.

BC deterministic tests must pass before BD's measured review. BB's static SQL and
fixture checks cannot stand in for BC tests, independent annotations or a real
supported-player observation. No model/client/paid spend is authorized here.

## Exact cross-video identity deferral

`(video_id,cue_revision,run_id,label)` identifies only a label within one recording
and run. Source labels instead bind their producer artifact and item. Neither
tuple identifies a person. Even equal labels in two runs of the same item cannot
be equated automatically.

Phase 6 creates no voice embeddings, person IDs, speaker registry, alias mapping,
cross-video join, cross-source entity edge, face/voice matching, name inference,
automatic host/guest assignment or identity search filter. Existing unrelated
entity features gain no authority from Phase 6 labels. Chapter and speaker data
must not activate them.

A later proposal requires both accepted source-local usefulness results on the
measured copy and a separately frozen, human-labeled evaluation set for the
specific cross-video identity task. It must define consent, false-match and
abstention thresholds, provenance, deletion/correction behavior and an independent
review before Fable dispatches implementation. Passing Phase 6 supplies neither
identity evidence nor approval to start that work. Twitch stays notify-only and
unimplemented pending its separately verified authorization/delivery design;
encrypted sync and X watching remain deferred.

## BB verification and remaining dispatch decisions

BB verification used all 28 existing migration scripts and the exact DDL above
in SQLite `:memory:`. Old cue/clip core values survived; default annotations,
FTS search, deletion cascades and `foreign_key_check` passed. Eight malformed
SQL insert/update cases were rejected. This proves SQL syntax and those local
constraints, not the future semantic validator or migration-runner crash behavior.

The existing pure `clips` and `library_cards` modules, run with bytecode writes
disabled, confirmed all nine windows across Gemini's three synthetic fixtures.
Adding annotation fields left each full card equal. A separate synthetic corpus
head shift changed source revision while preserving timed excerpt IDs, confirming
the revision caveat. No helper or transcription module was imported.

Static checks found 19 distinct future test names, balanced Markdown fences and
five resolved relative document links. `git diff --no-index --check` reported no
whitespace errors; Git emitted only its LF-to-CRLF working-copy notice. Final
status contained only this new contract. No BC/BD runtime gate is claimed passed.

Fable must reserve BC's shared capture/index/UI/registry edits and name BD's
candidate, measured copy, eligible artifacts and independent annotator. No schema,
projection, export or identity choice above remains delegated to implementation.
If required measured material is absent, record a blocked gate and request a
separate acquisition/evaluation scope; do not broaden adapter permissions or
reduce a threshold silently.
