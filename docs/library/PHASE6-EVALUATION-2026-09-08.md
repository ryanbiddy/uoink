# Phase 6 Evaluation Design: Media Depth and Cited Range Export (2026-09-08)

**Document:** [`docs/library/PHASE6-EVALUATION-2026-09-08.md`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/479b2aba-48a/gemini/docs/library/PHASE6-EVALUATION-2026-09-08.md)  
**Author:** Gemini (Evaluation Design and Verification Worker)  
**Run:** BB (Phase 6 Evaluation Design and Export Verification)  
**Target Implementation:** Run BC (`0030` schema migration, cue-to-clip projection, `export_cited_range`, corpus/sidecar update)  
**Acceptance Review:** Run BD (Astra review and acceptance against pre-defined metrics)  
**Inputs:** [`docs/library/PHASE6-BRIEF-2026-09-08.md`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/479b2aba-48a/gemini/docs/library/PHASE6-BRIEF-2026-09-08.md), [`docs/library/ASTRA-PHASE-PLAN-2026-09-04.md`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/479b2aba-48a/gemini/docs/library/ASTRA-PHASE-PLAN-2026-09-04.md), [`whisper_runner.py`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/479b2aba-48a/gemini/whisper_runner.py), [`clips.py`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/479b2aba-48a/gemini/clips.py), [`yt_extract.py`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/479b2aba-48a/gemini/yt_extract.py), [`library_cards.py`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/479b2aba-48a/gemini/library_cards.py), [`migrations/0024_clips.sql`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/479b2aba-48a/gemini/migrations/0024_clips.sql), and [`migrations/0022_podcast_corpus.sql`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/479b2aba-48a/gemini/migrations/0022_podcast_corpus.sql).

---

## 1. Scope, Invariants, and Acceptance Gates

Under Fable's dispatch in [`docs/library/PHASE6-BRIEF-2026-09-08.md`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/479b2aba-48a/gemini/docs/library/PHASE6-BRIEF-2026-09-08.md), Phase 6 introduces structured media depth where it directly alters library retrieval and evidence citation:
1. Chapter rows bound to item and source revision.
2. Source-local speaker labels on transcript cues, projected deterministically to clips and Markdown corpus files.
3. Cited range export producing verbatim text with seek-accurate deep links for timed media, while cleanly refusing coarse media.

This design document freezes the evaluation framework, synthetic fixtures, projection rules, refusal envelopes, and verification formulas before implementation begins in Run BC.

### 1.1 Non-Negotiable Architectural Invariants

Implementation in Run BC must satisfy five structural invariants:

1. **Source-Local Speaker Labels, Never Cross-Source Identity:**
   Speaker turns emitted by WhisperX (`SPEAKER_00`, `SPEAKER_01`) or source transcripts are local to one recording and one diarization execution. No global entity resolution, speaker table across items, or name guessing is permitted in Phase 6. A label is a source-local stream partition, nothing more.
2. **Evidence ID and Clip Stability:**
   Phase 2 evidence IDs and Phase 4 excerpt IDs rely on `_hash([card["video_id"], selected])` in [`library_cards.py`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/479b2aba-48a/gemini/library_cards.py#L150). The `selected` dict keys are `(start, end, text, deep_link, seq, timing)`. Adding speaker labels and chapter metadata must not change clip window boundary math (`start`, `end`, `seq`) or inject label strings into raw clip `text`. Existing citations must continue resolving without churn.
3. **Honest Timing and Player-Seek Equality:**
   Player seek targets and exported deep links must resolve to the identical source timeline second ($\lfloor T_{\text{export}} \rfloor = T_{\text{seek}}$). Where cue timing is coarse (> 120s single cue), the system must explicitly refuse sub-interval precision rather than inventing word-level seek targets.
4. **Explicit Missing Data:**
   Missing chapters or unrun diarization must produce explicit empty lists or `NULL` database values. The system must never fabricate a chapter titled "Chapter 1" or a speaker named "Speaker 1".
5. **Diarization Remains Opt-In and Default-Off:**
   In line with local compute budgets, diarization runs only on explicit user request. Automated background processes must never trigger pyannote or download diarization models without direct consent.

### 1.2 Summary of Acceptance Gates

| Gate ID | Target Capability | Verification Method | Pass Criteria |
|---|---|---|---|
| **GATE-6-FIX** | Fixture Schema Conformance | Ingestion of Fixtures 1, 2, 3 into `0030` schema | Zero constraint violations; foreign keys cascade cleanly; correct column populations in `chapters`, `citations`, `clips`. |
| **GATE-6-PROJ** | Deterministic Label Projection | Projection via `clips.py:merge_cues` across mixed turns | Single-speaker clips retain exact speaker label; mixed turns assign canonical ordered composite (`SPEAKER_00, SPEAKER_01`); `clips.text` is byte-identical to pre-Phase 6 text. |
| **GATE-6-STAB** | Evidence ID Invariance | SHA-256 excerpt ID recalculation | Excerpt hashes for identical cue text match pre-Phase 6 hashes across all test cards. |
| **GATE-6-EXP-TIMED** | Timed Cited Range Export | `export_cited_range` on `source_cues` items | Exact verbatim text slice, exact deep link `#t=N`, chapter metadata attached, speaker attribution present. |
| **GATE-6-EXP-COARSE**| Coarse Range Refusal | `export_cited_range` on `coarse` items | Refuses with frozen code `invalid_request`, `details.timing = "coarse"`, enclosing interval returned, no fabricated seek points. |
| **GATE-6-EXP-TEXT**  | Text-Only Citation | `export_cited_range` on `not_timed` items | Excerpt ID query succeeds with `deep_link` (no hash fragment), `seek_link: null`; timestamp query refuses `invalid_request`. |
| **GATE-6-SEEK** | Player Seek Parity | Round-trip comparison between export URL and player seek | $|T_{\text{export\_start}} - T_{\text{player\_seek}}| < 1.0\text{s}$; deep link opens to ground truth speech onset. |
| **GATE-6-MISS** | Missing-Data Boundaries | Execution against items lacking chapters, diarization off, and single speaker | Explicit `NULL` / `[]` returned; single speaker preserves `"SPEAKER_00"` without flattening to `NULL`. |
| **GATE-6-METRIC** | Measurable Improvement | Navigation resolution and speaker precision benchmarks | $\ge 65\%$ evidence locality gain, $\ge 95\%$ speaker attribution precision, mean jump offset $\le 1$ clip. |

---

## 2. Schema Shapes and Data Models (`0030_media_depth.sql`)

Phase 6 allocates migration `0030_media_depth.sql`. This section specifies the exact column definitions and provenance bindings evaluated by the test suite.

### 2.1 The `chapters` Table

Chapters represent structured timeline segments provided by source metadata (such as YouTube description timestamps or podcast RSS chapter marks).

```sql
CREATE TABLE IF NOT EXISTS chapters (
    chapter_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id         TEXT NOT NULL,
    seq              INTEGER NOT NULL,          -- 0-indexed order within item
    start            REAL NOT NULL,             -- seconds from start of media
    end              REAL NOT NULL,             -- seconds from start of media
    title            TEXT NOT NULL,             -- verbatim chapter title from source
    source_revision  TEXT NOT NULL,             -- binding to item source revision
    source_kind      TEXT NOT NULL,             -- 'youtube_metadata' | 'podcast_feed' | 'sidecar'
    FOREIGN KEY (video_id) REFERENCES yoinks(video_id) ON DELETE CASCADE,
    UNIQUE (video_id, seq),
    CHECK (start >= 0.0),
    CHECK (end > start)
);

CREATE INDEX IF NOT EXISTS idx_chapters_video_time 
    ON chapters(video_id, start, end);
```

### 2.2 Citations Schema Extension (`citations`)

The `citations` table (updated in migration `0022_podcast_corpus.sql`) stores raw cues of kind `transcript_chunk`. In migration `0030`, it stores source-local speaker labels and diarization run bindings:

```sql
ALTER TABLE citations ADD COLUMN speaker TEXT DEFAULT NULL;
ALTER TABLE citations ADD COLUMN diarization_run_id TEXT DEFAULT NULL;

CREATE INDEX IF NOT EXISTS idx_citations_speaker 
    ON citations(video_id, speaker);
```

### 2.3 Clips Schema Extension (`clips`)

In [`migrations/0024_clips.sql`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/479b2aba-48a/gemini/migrations/0024_clips.sql#L24), the `speaker` column is already defined (`speaker TEXT, -- reserved; NULL in phase 1`). Migration `0030` ensures `clips` stores the projected speaker label and adds an explicit chapter association:

```sql
ALTER TABLE clips ADD COLUMN chapter_seq INTEGER DEFAULT NULL;

CREATE INDEX IF NOT EXISTS idx_clips_chapter 
    ON clips(video_id, chapter_seq);
CREATE INDEX IF NOT EXISTS idx_clips_speaker 
    ON clips(video_id, speaker);
```

### 2.4 Markdown Corpus Format

The rendered Markdown corpus file (e.g., `folder/slug.md`) incorporates chapters as level-2 headers and speaker trailers on cue links:

```markdown
# Episode Title

**Podcast:** Show Name  
**Source:** https://podcast.example.com/ep42  
**Published:** 2026-09-08T00:00:00Z  

## Chapter: Introduction and Architecture

### [00:00:05](https://podcast.example.com/ep42#t=5) — SPEAKER_00
Welcome back to the studio. Today we examine storage engines.

### [00:00:22](https://podcast.example.com/ep42#t=22) — SPEAKER_01
Thanks for having me on.
```

---

## 3. Evaluation Fixtures with Ground-Truth Annotations

Three synthetic fixtures represent the target operational matrix. Each fixture provides raw inputs, intermediate cue records, and ground-truth expectation assertions.

### 3.1 Fixture 1: Multi-Speaker, Multi-Chapter Podcast (`fixture_podcast_multiturn`)

- **Item Metadata:**
  - `video_id`: `pod-phase6-001`
  - `slug`: `systems-deep-dive-ep42`
  - `title`: `Episode 42: Storage Engines and Query Boundaries`
  - `channel`: `Systems Deep Dive`
  - `platform`: `podcast`
  - `source_type`: `episode`
  - `url`: `https://systems.example.fm/ep42.mp3`
  - `source_revision`: `f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2`
- **Diarization State:**
  - `diarization_ran`: `true`
  - `model`: `base`
  - `diarization_run_id`: `run-diar-20260908-01`
- **Known Chapter Boundaries:**
  - Chapter 0 (`seq: 0`): `[0.0, 60.0)` — "Intro and Welcome"
  - Chapter 1 (`seq: 1`): `[60.0, 180.0)` — "B-Trees versus LSM Trees"
  - Chapter 2 (`seq: 2`): `[180.0, 270.0)` — "Wrap-up and Conclusions"

#### Raw Cue Sequence (Citations)

| Seq | Start (s) | End (s) | Speaker | Text | Ends Sentence | Expected Clip Seq |
|---|---|---|---|---|---|---|
| 0 | 0.0 | 22.0 | `SPEAKER_00` | Welcome to Systems Deep Dive episode forty two. | Yes | Clip 0 |
| 1 | 22.5 | 48.0 | `SPEAKER_01` | Glad to be here to discuss disk storage engines. | Yes | Clip 0 |
| 2 | 48.5 | 58.0 | `SPEAKER_00` | Let us dive right into the primary differences. | Yes | Clip 0 |
| 3 | 60.0 | 95.0 | `SPEAKER_01` | LSM trees write sequentially to an append log. | Yes | Clip 1 |
| 4 | 95.5 | 125.0 | `SPEAKER_01` | In contrast B-Trees update disk pages in place. | Yes | Clip 1 |
| 5 | 126.0 | 175.0 | `SPEAKER_00` | That creates write amplification on random updates. | Yes | Clip 1 |
| 6 | 180.0 | 215.0 | `SPEAKER_01` | Exactly which is why compaction tuning matters. | Yes | Clip 2 |
| 7 | 216.0 | 240.0 | `SPEAKER_00` | Thanks everyone for listening to this episode. | Yes | Clip 2 |
| 8 | 240.5 | 265.0 | `SPEAKER_01` | Goodbye. | Yes | Clip 2 |

#### Expected Projection Assertions

1. **Clip 0:**
   - `seq`: 0, `start`: 0.0, `end`: 58.0, `cue_count`: 3
   - `speaker`: `"SPEAKER_00, SPEAKER_01"` (multi-speaker window)
   - `chapter_seq`: 0
   - `text`: `"Welcome to Systems Deep Dive episode forty two. Glad to be here to discuss disk storage engines. Let us dive right into the primary differences."`
2. **Clip 1:**
   - `seq`: 1, `start`: 60.0, `end`: 175.0, `cue_count`: 3
   - `speaker`: `"SPEAKER_01, SPEAKER_00"` (order of first appearance in clip)
   - `chapter_seq`: 1
   - `text`: `"LSM trees write sequentially to an append log. In contrast B-Trees update disk pages in place. That creates write amplification on random updates."`
3. **Clip 2:**
   - `seq`: 2, `start`: 180.0, `end`: 265.0, `cue_count`: 3
   - `speaker`: `"SPEAKER_01, SPEAKER_00"`
   - `chapter_seq`: 2
   - `text`: `"Exactly which is why compaction tuning matters. Thanks everyone for listening to this episode. Goodbye."`

---

### 3.2 Fixture 2: YouTube Video with Chapters, Diarization Off (`fixture_youtube_chapters_nodiar`)

- **Item Metadata:**
  - `video_id`: `yt-phase6-002`
  - `slug`: `distributed-consensus-explained`
  - `title`: `Distributed Consensus in 10 Minutes`
  - `channel`: `Tech Explainers`
  - `platform`: `youtube`
  - `source_type`: `video`
  - `url`: `https://youtube.com/watch?v=yt-phase6-002`
  - `source_revision`: `a9b8c7d6e5f4a3b2c1d0e9f8a7b6c5d4e3f2a1b0c9d8e7f6a5b4c3d2e1f0a9b8`
- **Diarization State:**
  - `diarization_ran`: `false`
  - `model`: `none`
  - `diarization_run_id`: `null`
- **Known Chapter Boundaries:**
  - Chapter 0 (`seq: 0`): `[0.0, 120.0)` — "The Two Generals Problem"
  - Chapter 1 (`seq: 1`): `[120.0, 300.0)` — "Raft Leader Election"
  - Chapter 2 (`seq: 2`): `[300.0, 600.0)` — "Log Replication and Safety"

#### Raw Cue Sequence (Citations)

| Seq | Start (s) | End (s) | Speaker | Text | Ends Sentence | Expected Clip Seq |
|---|---|---|---|---|---|---|
| 0 | 0.0 | 25.0 | `NULL` | Two generals must agree on when to attack. | Yes | Clip 0 |
| 1 | 25.2 | 55.0 | `NULL` | Unreliable messengers make total certainty impossible. | Yes | Clip 0 |
| 2 | 120.0 | 150.0 | `NULL` | Raft breaks consensus into three clear subproblems. | Yes | Clip 1 |
| 3 | 150.5 | 185.0 | `NULL` | The first subproblem is leader election using heartbeats. | Yes | Clip 1 |
| 4 | 300.0 | 340.0 | `NULL` | Log replication requires leader commit confirmation. | Yes | Clip 2 |
| 5 | 340.5 | 375.0 | `NULL` | Followers write entries to disk before responding. | Yes | Clip 2 |

#### Expected Projection Assertions

1. **All Clips:** `speaker` column in `clips` table must evaluate to `NULL`.
2. **Chapter Alignment:**
   - Clip 0 (`start: 0.0, end: 55.0`): `chapter_seq = 0`
   - Clip 1 (`start: 120.0, end: 185.0`): `chapter_seq = 1`
   - Clip 2 (`start: 300.0, end: 375.0`): `chapter_seq = 2`
3. **No Phantom Speaker Data:** `SELECT COUNT(*) FROM clips WHERE video_id = 'yt-phase6-002' AND speaker IS NOT NULL` must return `0`.

---

### 3.3 Fixture 3: Boundary Collisions and Single-Speaker Monologue (`fixture_boundary_collisions`)

This fixture isolates boundary edge cases: chapter transitions mid-sentence, single-speaker diarization runs, and echo cue handling.

- **Item Metadata:**
  - `video_id`: `pod-phase6-003`
  - `slug`: `solo-monologue-lecture`
  - `title`: `Lecture: Formal Methods in Practice`
  - `channel`: `Academic Monologues`
  - `platform`: `podcast`
  - `source_type`: `episode`
  - `url`: `https://lecture.example.edu/fm.mp3`
  - `source_revision`: `0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef`
- **Diarization State:**
  - `diarization_ran`: `true`
  - `model`: `base`
  - `diarization_run_id`: `run-diar-20260908-03`
  - **Identified Speakers:** `["SPEAKER_00"]` (Single speaker detected across all turns)
- **Known Chapter Boundaries:**
  - Chapter 0 (`seq: 0`): `[0.0, 50.0)` — "Specification Basics"
  - Chapter 1 (`seq: 1`): `[50.0, 150.0)` — "Temporal Logic Assertions"

#### Raw Cue Sequence (Citations)

| Seq | Start (s) | End (s) | Speaker | Text | Ends Sentence | Edge Condition |
|---|---|---|---|---|---|---|
| 0 | 0.0 | 25.0 | `SPEAKER_00` | Formal specifications describe allowable behaviors. | Yes | Normal start |
| 1 | 25.0 | 25.02 | `SPEAKER_00` | allowable behaviors. | Yes | 20ms echo cue: must drop |
| 2 | 25.02 | 48.0 | `SPEAKER_00` | We define state invariants first. | Yes | Reaches 48s (>45s sentence close) |
| 3 | 48.5 | 55.0 | `SPEAKER_00` | Temporal logic handles state changes across time. | Yes | Spans chapter boundary at 50.0s |
| 4 | 55.5 | 110.0 | `SPEAKER_00` | Liveness guarantees something good eventually happens. | Yes | Inside Chapter 1 |

#### Expected Projection Assertions

1. **Echo Dropping:** Cue 1 is dropped per [`clips.py:237`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/479b2aba-48a/gemini/clips.py#L237) (`(end - start) < 0.05` with repeated tail words).
2. **Window Flush on Sentence Close:** Clip 0 closes at Cue 2 (duration $48.0 - 0.0 = 48.0\text{s} \ge 45.0\text{s}$ with sentence ending).
3. **Clip 0 Properties:** `start: 0.0`, `end: 48.0`, `speaker: "SPEAKER_00"`, `chapter_seq: 0`.
4. **Boundary Spanning Cue (Cue 3):** Cue 3 starts at `48.5` (Chapter 0) and ends at `55.0` (Chapter 1). Clip 1 starts at `48.5`.
5. **Chapter Attribution Rule:** Clip 1 has `start = 48.5`. Because $48.5 \in [0.0, 50.0)$, Clip 1 is assigned `chapter_seq = 0`.
6. **Single-Speaker Retention:** Single speaker `"SPEAKER_00"` is preserved on all clips. It must not be flattened to `NULL`.

---

## 4. Deterministic Projection and Evidence ID Stability

### 4.1 Cue-to-Clip Projection Rules

When [`clips.py:merge_cues`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/479b2aba-48a/gemini/clips.py#L187) aggregates citations into clip windows:

1. **Speaker Aggregation:**
   - Let $S = [c_1.\text{speaker}, c_2.\text{speaker}, \dots, c_m.\text{speaker}]$ be the non-null speaker values of the cues merged into the clip.
   - If $S$ is empty (diarization off or missing labels): `clip.speaker = NULL`.
   - If all elements in $S$ are equal to $s_0$: `clip.speaker = s_0`.
   - If $S$ contains multiple distinct values: `clip.speaker = ", ".join(\text{distinct}(S))` preserving the order of first appearance in the clip window. Example: `["SPEAKER_01", "SPEAKER_00"]` becomes `"SPEAKER_01, SPEAKER_00"`.
2. **Chapter Association:**
   - `clip.chapter_seq` is resolved by point lookup on the clip start time:
     $$\text{chapter\_seq} = \text{chapter.seq} \quad \text{where} \quad \text{chapter.start} \le \text{clip.start} < \text{chapter.end}$$
   - If no chapter encloses `clip.start`: `clip.chapter_seq = NULL`.
   - Chapter boundaries do not force premature flushes of clip windows. This preserves window sizing invariants ($45\text{s} \le \text{window} \le 120\text{s}$) and prevents clip boundary jitter.

### 4.2 Mathematical Invariance of Phase 2 and Phase 4 Evidence IDs

In [`library_cards.py`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/479b2aba-48a/gemini/library_cards.py#L136-L153), excerpt identity is computed as:

$$\text{excerpt\_id} = \text{SHA-256}(\text{JSON}(\text{video\_id}, \text{selected}))$$

where `selected` contains strictly:
```python
selected = {
    "start": clip["start"],
    "end": clip["end"],
    "text": clip["text"],
    "deep_link": clip["source_deep_link"],
    "seq": clip["seq"],
    "timing": clip["timing"]
}
```

Because `speaker` and `chapter_seq` are stored as distinct relational columns on `clips` and are **not** serialized into `selected`, and because raw cue text is merged without prepending speaker prefixes, the resulting hash remains mathematically invariant:

$$\text{excerpt\_id}_{\text{Phase 6}} \equiv \text{excerpt\_id}_{\text{Phase 4}}$$

**Verification Gate `GATE-6-STAB` Assertion:**
For each clip in Fixture 1, compute `excerpt_id` using the pre-Phase 6 card builder and the Phase 6 card builder. The hashes must match byte-for-byte:
$$\text{assert } \text{hash}_{\text{v4}}(c) == \text{hash}_{\text{v6}}(c) \quad \forall c \in \text{Clips}$$

---

## 5. Expected Cited-Range Export Output

The read tool `export_cited_range` allows clients to extract a bounded, verifiable passage with playback-ready seek links and provenance metadata.

### 5.1 Tool Signature

```python
def export_cited_range(
    idx: Index,
    video_id: str,
    *,
    start: float | None = None,
    end: float | None = None,
    excerpt_id: str | None = None,
) -> dict:
    ...
```

- **Query Modes:**
  - Mode A (Timestamp Range): `start` and `end` specified ($0.0 \le \text{start} < \text{end}$).
  - Mode B (Excerpt Identifier): `excerpt_id` specified (64-character lowercase hexadecimal string).
  - Calling with both or neither raises `invalid_request`.

---

### 5.2 Case 1: Timed Media Item (`source_cues`)

**Request (Timestamp Mode):**
```json
{
  "video_id": "pod-phase6-001",
  "start": 60.0,
  "end": 125.0
}
```

**Expected Response (`200 OK`):**
```json
{
  "ok": true,
  "schema_version": 1,
  "contract_version": "phase6-v1-2026-09-08",
  "item": {
    "video_id": "pod-phase6-001",
    "title": "Episode 42: Storage Engines and Query Boundaries",
    "platform": "podcast",
    "source_type": "episode",
    "source_url": "https://systems.example.fm/ep42.mp3",
    "source_revision": "f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2"
  },
  "citation": {
    "timing": "source_cues",
    "start": 60.0,
    "end": 125.0,
    "verbatim_text": "LSM trees write sequentially to an append log. In contrast B-Trees update disk pages in place.",
    "word_count": 16,
    "source_deep_link": "https://systems.example.fm/ep42.mp3#t=60",
    "player_seek_seconds": 60
  },
  "attribution": {
    "diarization_ran": true,
    "diarization_run_id": "run-diar-20260908-01",
    "speakers": ["SPEAKER_01"],
    "turns": [
      {
        "start": 60.0,
        "end": 95.0,
        "speaker": "SPEAKER_01",
        "text": "LSM trees write sequentially to an append log."
      },
      {
        "start": 95.5,
        "end": 125.0,
        "speaker": "SPEAKER_01",
        "text": "In contrast B-Trees update disk pages in place."
      }
    ]
  },
  "chapter": {
    "seq": 1,
    "title": "B-Trees versus LSM Trees",
    "start": 60.0,
    "end": 180.0
  },
  "provenance": {
    "enclosing_clip_seq": 1,
    "exported_at": "2026-09-08T10:00:00Z"
  }
}
```

---

### 5.3 Case 2: Coarse Timing Item (Refusal Contract)

When cues have duration $> 120\text{s}$ (e.g., audio transcribed without segment alignment), [`clips.py:39`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/479b2aba-48a/gemini/clips.py#L39) marks them `coarse`. Sub-interval seeking within a coarse block cannot be guaranteed against source media.

**Request:**
```json
{
  "video_id": "legacy-coarse-item-009",
  "start": 150.0,
  "end": 180.0
}
```

**Expected Response (`Refusal`):**
```json
{
  "ok": false,
  "schema_version": 1,
  "contract_version": "phase6-v1-2026-09-08",
  "error": {
    "code": "invalid_request",
    "message": "Sub-interval citation refused: item timing is coarse. Word-level timestamps do not exist for this source.",
    "retryable": false,
    "details": {
      "timing_kind": "coarse",
      "requested_range": {"start": 150.0, "end": 180.0},
      "enclosing_interval": {"start": 0.0, "end": 600.0},
      "coarse_source_deep_link": "https://podcast.example.com/coarse-ep#t=0",
      "next_step": "read_library_resource"
    }
  }
}
```

---

### 5.4 Case 3: Text-Only Item (`not_timed`)

Text-only items (articles, notes, PDF papers) have no audio/video timeline.

**Request by `excerpt_id` (`200 OK`):**
```json
{
  "video_id": "page-sqlite-arch-2026",
  "excerpt_id": "7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c"
}
```

**Expected Response:**
```json
{
  "ok": true,
  "schema_version": 1,
  "contract_version": "phase6-v1-2026-09-08",
  "item": {
    "video_id": "page-sqlite-arch-2026",
    "title": "Architecture of SQLite",
    "platform": "web",
    "source_type": "page",
    "source_url": "https://sqlite.org/arch.html",
    "source_revision": "c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1"
  },
  "citation": {
    "timing": "not_timed",
    "start": null,
    "end": null,
    "verbatim_text": "SQLite implements an in-process, serverless, zero-configuration SQL database engine.",
    "word_count": 10,
    "source_deep_link": "https://sqlite.org/arch.html",
    "player_seek_seconds": null
  },
  "attribution": {
    "diarization_ran": false,
    "diarization_run_id": null,
    "speakers": [],
    "turns": []
  },
  "chapter": null,
  "provenance": {
    "evidence_kind": "text_only",
    "exported_at": "2026-09-08T10:00:00Z"
  }
}
```

**Request by `start`/`end` on Text-Only Item (`Refusal`):**
```json
{
  "ok": false,
  "schema_version": 1,
  "contract_version": "phase6-v1-2026-09-08",
  "error": {
    "code": "invalid_request",
    "message": "Timestamp range citation refused: item has no media timeline. Use excerpt_id.",
    "retryable": false,
    "details": {
      "timing_kind": "not_timed",
      "video_id": "page-sqlite-arch-2026"
    }
  }
}
```

---

## 6. Player-Seek Versus Exported-Range Equality Checks

A critical evaluation gate in the phase plan is:  
> *"Player seeking and exported ranges match source timing."*

### 6.1 Timestamp Arithmetic and Deep Link Mechanics

Players in the web dashboard, desktop shell, and external browser tabs rely on specific platform syntax to seek. The exported range must align exactly with the player's seek target:

| Platform | Syntactic Scheme | Canonical Link Format | Player Seek Extraction |
|---|---|---|---|
| YouTube | Query parameter `t` | `https://youtube.com/watch?v={id}&t={T}s` | `int(T)` seconds |
| Podcast / Web Audio | Media fragment hash | `https://example.com/audio.mp3#t={T}` | `float(T)` or `int(T)` |
| Video / Vimeo | Time hash | `https://vimeo.com/{id}#t={T}s` | `int(T)` seconds |
| Text Page / Note | No timeline fragment | `https://example.com/doc` | `null` |

### 6.2 Equality Invariant Formulation

Let:
- $T_{\text{start}}$ be the exact float timestamp of the first cue in the exported citation.
- $L_{\text{export}}$ be the URI emitted in `citation.source_deep_link`.
- $T_{\text{seek}}$ be the integer seek point parsed from $L_{\text{export}}$.
- $T_{\text{player}}$ be the player's internal seek command issued by the frontend audio controller.

The test suite enforces:

$$\lfloor T_{\text{start}} \rfloor = T_{\text{seek}} = T_{\text{player}}$$

$$\text{and} \quad 0 \le T_{\text{start}} - T_{\text{seek}} < 1.0\text{s}$$

### 6.3 Test Verification Scenarios

1. **Sub-second Start Offset:**
   - Cue starts at $t = 22.75\text{s}$.
   - Exported link: `https://systems.example.fm/ep42.mp3#t=22`.
   - Player seek parameter: `22`.
   - The test asserts that audio playback started at $22\text{s}$ contains the leading acoustic syllable of the first word (which began at $22.75\text{s}$), ensuring speech onset is never clipped.
2. **Trailing Fragment De-overlap:**
   - Where YouTube auto-captions overlap (e.g., Cue $N$ starts at $19.91\text{s}$ repeating words from Cue $N-1$), [`clips.py`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/479b2aba-48a/gemini/clips.py#L130) computes `new_words`.
   - The test asserts that the seek link points to the start of the window, not an intermediate overlapping cue timestamp that would repeat audio.

---

## 7. Missing-Data Boundary Test Matrix

To prevent hallucinated structures, missing metadata must produce strict null values.

| Scenario | Database State | Cues State | Clips State | Markdown Rendering | Cited Range Export Output |
|---|---|---|---|---|---|
| **No Chapters** | No rows in `chapters` for `video_id` | `citations.kind = 'transcript_chunk'` | `clips.chapter_seq = NULL` | No `## Chapter` headings | `citation.chapter = null` |
| **Diarization Off** | `podcast_episodes.diarization_ran = 0` | `citations.speaker = NULL` | `clips.speaker = NULL` | Cue links omit `— SPEAKER_XX` | `attribution.diarization_ran = false`, `speakers = []`, `turns = []` |
| **Diarization Ran: 1 Speaker** | `podcast_episodes.diarization_ran = 1` | All `citations.speaker = 'SPEAKER_00'` | All `clips.speaker = 'SPEAKER_00'` | Cue links include `— SPEAKER_00` | `attribution.diarization_ran = true`, `speakers = ["SPEAKER_00"]` |
| **Mid-Stream Diarization Failure** | WhisperX logs warning, degrades to transcript-only | First $k$ cues have speaker; remaining cues `NULL` | Early clips have speaker; later clips `NULL` | Mixed trailers matching cue state | `attribution.diarization_ran = false`, Partial turns recorded |
| **Chapter Timestamps Out of Bounds** | Source metadata has chapter starting past audio end | Cues end at $300\text{s}$; chapter claims start at $450\text{s}$ | Clip point lookup yields no match; `chapter_seq = NULL` | Out-of-bounds chapter ignored | Refuses chapter association; does not emit phantom chapter |

---

## 8. Measurable Retrieval and Navigation Improvement Specification

The phase plan states:
> *"A retrieval or navigation improvement is demonstrated on the measured copy before any cross-source entity work is proposed."*

This section establishes four pre-implementation benchmarks and acceptance criteria evaluated on the 548-item copy.

### 8.1 Metric 1: Navigation Jump Resolution (NJR)

- **Problem Statement:** In long-form audio/video (> 30 minutes), finding a targeted discussion topic requires navigating dozens of sequential clips.
- **Evaluation Task:** Given 50 target conceptual queries with human-annotated ground-truth chapter locations:
  - **Baseline Navigation:** Linear scan through sequential clips from $t = 0$.
  - **Phase 6 Navigation:** Direct jump using the `chapters` table index.
- **Metric Formula:** Mean Absolute Temporal Error (MATE) in seconds from true topic onset:
  $$\text{MATE} = \frac{1}{N} \sum_{i=1}^N |T_{\text{jump}}^{(i)} - T_{\text{true\_onset}}^{(i)}|$$
- **Target Improvement:**
  - Baseline MATE: $\ge 180\text{s}$ (skimming across 3+ clips).
  - Phase 6 Chapter Jump MATE: $\le 15.0\text{s}$ (direct alignment to chapter start).
  - **Pass Threshold:** MATE reduction of at least $80\%$.

---

### 8.2 Metric 2: Speaker-Constrained Retrieval Precision (SCRP)

- **Problem Statement:** In multi-speaker interviews, searching for statements made specifically by the guest (e.g., "guest explanation of LSM compaction") returns false positives where the host asked the question or mentioned the term.
- **Evaluation Task:** 30 speaker-attributed queries evaluated on the dual-speaker podcast benchmark:
  - **Baseline Retrieval:** Full-text search on `clips_fts` matching query terms across any clip text.
  - **Phase 6 Retrieval:** Full-text search filtered by source-local speaker:
    ```sql
    SELECT c.* FROM clips c 
    JOIN clips_fts f ON c.clip_id = f.rowid 
    WHERE clips_fts MATCH :query AND c.speaker LIKE :speaker_pattern;
    ```
- **Metric Formula:** Precision at Rank 1 ($P@1$) and Rank 3 ($P@3$) on speaker correctness:
  $$P@k = \frac{\text{Count of top-}k\text{ hits spoken by target speaker}}{k}$$
- **Target Improvement:**
  - Baseline $P@1$: $\approx 0.52$ (unconstrained dialogue ambiguity).
  - Phase 6 $P@1$: $\ge 0.95$.
  - **Pass Threshold:** $P@1 \ge 0.90$ across all evaluated queries.

---

### 8.3 Metric 3: Evidence Locality Gain (ELG)

- **Problem Statement:** Phase 1 clips return 45–120 seconds of text (~250 words). Passing entire clips into agent reasoning budgets clutters context windows with extraneous dialogue.
- **Evaluation Task:** 100 quote verification tasks across the test copy.
- **Metric Formula:** Token reduction ratio of the cited range compared to the enclosing clip:
  $$\text{ELG} = 1 - \frac{\text{WordCount}(\text{cited\_range})}{\text{WordCount}(\text{enclosing\_clip})}$$
- **Target Improvement:**
  - Baseline (Full Clip): $\text{ELG} = 0.0$ (entire clip returned).
  - Phase 6 Cited Range: Verbatim sentence slice (15–40 words vs. 250 words).
  - **Pass Threshold:** Mean $\text{ELG} \ge 0.65$ (at least a $65\%$ reduction in non-essential token context).

---

### 8.4 Metric 4: Chapter-Contextual Search Disambiguation (CCSD)

- **Problem Statement:** Generic terms like "installation", "performance", or "costs" match multiple irrelevant parts of an episode.
- **Evaluation Task:** 40 multi-intent queries evaluated with chapter title boosting.
- **Metric Formula:** Mean Reciprocal Rank (MRR) of the first relevant passage:
  $$\text{MRR} = \frac{1}{Q} \sum_{q=1}^Q \frac{1}{\text{rank}_q}$$
- **Target Improvement:**
  - Baseline MRR: $\le 0.45$.
  - Phase 6 MRR: $\ge 0.70$.
  - **Pass Threshold:** Relative MRR improvement $\ge +25\%$.

---

## 9. Verification Test Suite Architecture (Run BC / Run BD)

Implementation in Run BC will be verified by a dedicated test module: [`tests/test_phase6_evaluation.py`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/479b2aba-48a/gemini/tests/test_phase6_evaluation.py).

```
tests/test_phase6_evaluation.py
├── test_gate_6_fix_schema_migration_0030()
│   └── Validates 0030 table creation, foreign key cascade, unique constraints
├── test_gate_6_proj_deterministic_speaker_projection()
│   └── Verifies single vs. mixed-speaker projection on Fixture 1 and Fixture 3
├── test_gate_6_stab_evidence_id_invariance()
│   └── Asserts Phase 4 excerpt_id matches Phase 6 excerpt_id across all clips
├── test_gate_6_exp_timed_source_cues()
│   └── Asserts JSON envelope, seek calculation, and turns on Fixture 1
├── test_gate_6_exp_coarse_timing_refusal()
│   └── Asserts invalid_request code and enclosing interval on coarse cues
├── test_gate_6_exp_text_only_citation()
│   └── Asserts excerpt_id success and timestamp query refusal on web pages
├── test_gate_6_seek_player_equality()
│   └── Verifies floor(start) == seek_seconds across all fixture cues
├── test_gate_6_miss_boundary_conditions()
│   └── Validates explicit NULLs for no-chapters, diarization-off, single-speaker
└── test_gate_6_metric_benchmarks()
    └── Evaluates NJR, SCRP, ELG, and CCSD on evaluation set
```

Execution of this suite in Run BD will provide the mathematical proof required by Astra before any cross-video entity work is scheduled.
