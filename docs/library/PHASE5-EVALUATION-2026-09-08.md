# Phase 5 Evaluation Design and Labeled Counterexamples (2026-09-08)

**Document:** [`docs/library/PHASE5-EVALUATION-2026-09-08.md`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/21220777-b29/gemini/docs/library/PHASE5-EVALUATION-2026-09-08.md)  
**Author:** Gemini (Evaluation Design and Verification Worker)  
**Run:** AY (Phase 5 Evaluation Design and Counterexample Fixtures)  
**Target Implementation:** Run AZ (`library_analysis.py`, [`index.py`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/21220777-b29/gemini/index.py) query helpers, registry tool, and dashboard report)  
**Inputs:** [`docs/library/PHASE5-BRIEF-2026-09-08.md`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/21220777-b29/gemini/docs/library/PHASE5-BRIEF-2026-09-08.md), [`docs/library/ASTRA-PHASE-PLAN-2026-09-04.md`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/21220777-b29/gemini/docs/library/ASTRA-PHASE-PLAN-2026-09-04.md), [`docs/library/PHASE4-CONTRACT-2026-09-08.md`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/21220777-b29/gemini/docs/library/PHASE4-CONTRACT-2026-09-08.md), [`index.py`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/21220777-b29/gemini/index.py), [`library_work.py`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/21220777-b29/gemini/library_work.py), [`claims.py`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/21220777-b29/gemini/claims.py), and migrations [`0001`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/21220777-b29/gemini/migrations/0001_initial_schema.sql), [`0004`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/21220777-b29/gemini/migrations/0004_memory_indexes.sql), [`0006`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/21220777-b29/gemini/migrations/0006_v2_schema.sql), [`0010`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/21220777-b29/gemini/migrations/0010_podcast_feeds.sql), [`0015`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/21220777-b29/gemini/migrations/0015_universal_site.sql), [`0020`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/21220777-b29/gemini/migrations/0020_platform_author.sql), [`0024`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/21220777-b29/gemini/migrations/0024_clips.sql), [`0027`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/21220777-b29/gemini/migrations/0027_library_substrate.sql), and [`0028`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/21220777-b29/gemini/migrations/0028_source_subscriptions.sql).

---

## 1. Scope and Objective

Under Fable's dispatch in [`docs/library/PHASE5-BRIEF-2026-09-08.md`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/21220777-b29/gemini/docs/library/PHASE5-BRIEF-2026-09-08.md), Phase 5 splits into two parts:
- **Part A (Current Phase):** Descriptive activity reports over source captures and shelf journal movements. These reports require explicit distinctions between capture dates and publication dates, precise history-coverage boundaries, and deterministic invalidation when database rows change or disappear. Part A does not depend on model-extracted claims or cross-source contradiction detection.
- **Part B (Deferred):** Term bursts with confirmed observation depth, full entity resolution, and disagreement sentence extraction.

This document establishes the evaluation specification for Part A. It freezes synthetic index fixtures and exact expected reports for each gate defined in the brief:
1. Backlog import vs. steady capture rate
2. Repeated clips and cross-posts across distinct channels
3. Creator hints under multiple channel names
4. Report invalidation following a soft deletion
5. Report invalidation and journal accounting following an undo operation
6. Isolated activity within a single-source interval
7. Historical query intervals predating observation records
8. Measurable faithfulness metric for future downstream narration

No production code is added in this run. Run AZ will implement `library_analysis.py` and query helpers to satisfy these exact fixtures.

---

## 2. Activity Report Contract (`get_library_activity`)

All fixtures evaluate against the read tool `get_library_activity` exposed in the shared registry.

### 2.1 Tool Invocation Interface

```python
def get_library_activity(
    idx: Index,
    *,
    start: str,
    end: str,
    date_basis: str = "capture_time",  # "capture_time" | "publication_time"
    shelf_id: str | None = None,
    source_id: str | None = None,
) -> dict:
    ...
```

- **Interval Grammar:** UTC ISO-8601 strings representing a half-open window `[start, end)`. Query bounds check: `start < end`.
- **Date Semantics:**
  - `date_basis="capture_time"` (default): Uses [`yoinks.yoinked_at`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/21220777-b29/gemini/migrations/0001_initial_schema.sql#L29). Represents when the local library ingested the media.
  - `date_basis="publication_time"`: Uses explicit source publication timestamps where present:
    - [`podcast_episodes.published_at`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/21220777-b29/gemini/migrations/0010_podcast_feeds.sql#L41)
    - [`source_items.published_at_ms`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/21220777-b29/gemini/migrations/0028_source_subscriptions.sql#L92)
    - Sidecar publication metadata stored in [`yoinks.metadata_json`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/21220777-b29/gemini/migrations/0001_initial_schema.sql#L33) (`$.upload_date` or `$.published_at`)
  - Items without verified publication dates are recorded in `captures.publication_time_missing_count` and excluded from `date_basis="publication_time"` bucket counts.
- **Wire Budget:** Maximum 65,536 serialized UTF-8 bytes, matching Phase 4 read budgets.

### 2.2 Standard Response Structure

```json
{
  "ok": true,
  "schema_version": 1,
  "interval": {
    "start": "2026-09-01T00:00:00Z",
    "end": "2026-09-08T00:00:00Z",
    "grammar": "half_open_utc",
    "date_basis": "capture_time"
  },
  "history_coverage": {
    "earliest_recorded_ms": 1767225600000,
    "interval_covered": true,
    "coverage_status": "complete"
  },
  "provenance": {
    "source_revision_hash": "64_hex_chars",
    "projection_revision": 12,
    "last_operation_sequence": 45,
    "active_taxonomy_version": "v1"
  },
  "captures": {
    "total": 10,
    "by_source_type": {
      "video": 6,
      "episode": 4
    },
    "by_creator_hint": [
      { "hint": "Alice", "count": 6, "source_types": ["video"] },
      { "hint": "Bob", "count": 4, "source_types": ["episode"] }
    ],
    "publication_time_available_count": 4,
    "publication_time_missing_count": 6
  },
  "shelf_activity": {
    "total_operations": 2,
    "applied_operations": [
      {
        "apply_id": "app-01",
        "operation_sequence": 44,
        "kind": "apply",
        "video_id": "vid-1",
        "shelf_id": "s1"
      }
    ],
    "net_membership_changes": {
      "s1": { "added": 1, "removed": 0, "net": 1 }
    },
    "shelf_sizes": {
      "s1": 15
    },
    "churn": {
      "total_mutations": 2,
      "affected_items_count": 1,
      "churn_percent": 6
    }
  },
  "sources": {
    "active_sources_count": 2,
    "details": [
      {
        "source_id": "src-yt-01",
        "display_name": "Alice Channel",
        "adapter": "youtube_channel_rss_v1",
        "observation_window": {
          "first_seen_utc": "2026-01-01T00:00:00Z",
          "last_observed_utc": "2026-09-08T00:00:00Z"
        },
        "captures_in_interval": 6
      }
    ]
  },
  "support_level": "multi_source",
  "independent_creators_minimum_met": true,
  "counterexample_warnings": []
}
```

---

## 3. Labeled Counterexample Fixtures

Every fixture specifies:
- **Gate:** Acceptance constraint from the brief.
- **Test ID:** Test function name for Run AZ.
- **Database State:** Real SQLite schema tables, populated with exact column values.
- **Query:** Invocation parameters to `get_library_activity`.
- **Expected Report:** Canonical JSON output.
- **Acceptance Assertions:** Boolean conditions the test suite must enforce.

---

### 3.1 Fixture 1: 200-Item Backlog Import vs. Steady Capture

- **Gate:** A backlog import cannot masquerade as a current publication trend.
- **Test ID:** `test_gate1_backlog_import_vs_steady_capture`
- **Rationale:** Ingesting 200 archived RSS episodes or historical YouTube videos on a single afternoon creates a spike in capture timestamps (`yoinked_at`), but reflects historical creation dates (2022–2024). A naive count grouping by capture date reports a massive "trend burst" in September 2026. The engine must separate the capture intake rate from the publication date distribution.

#### Database State (Schema 28)

```sql
-- 1. Active taxonomy and metadata
INSERT INTO shelves(shelf_id, created_at) VALUES ('s_tech', '2026-01-01T00:00:00Z');
INSERT INTO shelf_versions(version_id, revision_hash, status, created_at)
VALUES ('v1', '1111111111111111111111111111111111111111111111111111111111111111', 'active', '2026-01-01T00:00:00Z');
INSERT INTO shelf_nodes(version_id, shelf_id, parent_shelf_id, name, path_json, definition, include_json, exclude_json, retired)
VALUES ('v1', 's_tech', NULL, 'Technology', '["Technology"]', 'Tech notes', '["tech"]', '[]', 0);
UPDATE library_meta SET active_version_id = 'v1', projection_revision = 1, last_operation_sequence = 10;

-- 2. Backlog Subscription (Podcast RSS) enrolled on 2026-09-01
INSERT INTO podcast_feeds(id, feed_url, title, poll_interval_min, enabled, added_at)
VALUES (101, 'https://feeds.example.com/backlog.xml', 'Archive Pod', 60, 1, '2026-09-01T08:00:00Z');
INSERT INTO source_subscriptions(
    source_id, kind, source_key, canonical_url, display_name, adapter, legacy_feed_id,
    detection_enabled, archived, consent_state, revision, consent_epoch, boundary,
    initial_enrollment_completed_ms, back_catalog_enrolled, poll_interval_min,
    created_at_ms, updated_at_ms
) VALUES (
    'sub_backlog_01', 'podcast_rss', 'backlog_rss_key', 'https://feeds.example.com/backlog.xml',
    'Archive Pod', 'podcast_rss_v1', 101, 1, 0, 'on', 1, 1, 'initial',
    1788259200000, 25, 60, 1788259200000, 1788259200000
);

-- 3. Steady Subscription (YouTube Channel)
INSERT INTO source_subscriptions(
    source_id, kind, source_key, canonical_url, display_name, adapter,
    detection_enabled, archived, consent_state, revision, consent_epoch, boundary,
    initial_enrollment_completed_ms, back_catalog_enrolled, poll_interval_min,
    created_at_ms, updated_at_ms
) VALUES (
    'sub_steady_02', 'youtube_channel', 'steady_yt_key', 'https://youtube.com/@steadydev',
    'Steady Dev', 'youtube_channel_rss_v1', 1, 0, 'on', 1, 1, 'none',
    1788259200000, 0, 60, 1788259200000, 1788259200000
);

-- 4. 200 Backlog Items captured on 2026-09-01 between 10:00 and 10:30 UTC
-- Publication dates are distributed across 2022 to 2024 (1788256800000 ms is 2026-09-01 10:00:00 UTC)
-- Representative slice of 200 generated rows:
-- For i in 1..200:
--   video_id = 'bk-item-' || i
--   yoinked_at = '2026-09-01T10:15:00Z'
--   published_at = '2023-05-12T08:00:00Z' (varies 2022-01-01 to 2024-12-31)
--   published_at_ms = 1683878400000
INSERT INTO yoinks (
    video_id, slug, channel, title, topic, hook_type, yoinked_at, corpus_path, sidecar_path,
    schema_version, source_type, platform, author, metadata_json
) VALUES (
    'bk-item-001', 'bk-slug-001', 'Archive Pod', 'Episode 1: The Origin', 'history', 'intro',
    '2026-09-01T10:15:00Z', 'corpus/bk-001.md', 'sidecars/bk-001.json', 2, 'episode', 'podcast', 'Host Dave',
    '{"published_at": "2022-03-10T12:00:00Z"}'
);
INSERT INTO podcast_episodes (
    id, feed_id, guid, title, published_at, status, yoink_video_id, discovered_at
) VALUES (
    5001, 101, 'guid-bk-001', 'Episode 1: The Origin', '2022-03-10T12:00:00Z', 'transcribed', 'bk-item-001', '2026-09-01T10:00:00Z'
);
INSERT INTO source_items (
    item_id, source_id, entry_id, capture_key, published_at_ms, first_seen_ms, last_seen_ms,
    first_scan_revision, metadata_json, state, video_id, committed_at_ms
) VALUES (
    'src-it-bk-001', 'sub_backlog_01', 'entry-bk-001', 'cap-bk-001', 1646913600000, 1788256800000, 1788256800000,
    1, '{"guid": "guid-bk-001"}', 'committed', 'bk-item-001', 1788257700000
);
-- (Remaining 199 rows follow this identical structure with publication dates in 2022-2024)

-- 5. Steady Items: 5 items captured daily 2026-09-01 to 2026-09-05, published same day
INSERT INTO yoinks (
    video_id, slug, channel, title, topic, hook_type, yoinked_at, corpus_path, sidecar_path,
    schema_version, source_type, platform, author, metadata_json
) VALUES (
    'std-item-01', 'std-slug-01', 'Steady Dev', 'Daily Byte 1', 'dev', 'tip',
    '2026-09-01T14:00:00Z', 'corpus/std-01.md', 'sidecars/std-01.json', 2, 'video', 'youtube', 'Steady Dev',
    '{"published_at": "2026-09-01T13:30:00Z"}'
), (
    'std-item-02', 'std-slug-02', 'Steady Dev', 'Daily Byte 2', 'dev', 'tip',
    '2026-09-02T14:00:00Z', 'corpus/std-02.md', 'sidecars/std-02.json', 2, 'video', 'youtube', 'Steady Dev',
    '{"published_at": "2026-09-02T13:30:00Z"}'
), (
    'std-item-03', 'std-slug-03', 'Steady Dev', 'Daily Byte 3', 'dev', 'tip',
    '2026-09-03T14:00:00Z', 'corpus/std-03.md', 'sidecars/std-03.json', 2, 'video', 'youtube', 'Steady Dev',
    '{"published_at": "2026-09-03T13:30:00Z"}'
), (
    'std-item-04', 'std-slug-04', 'Steady Dev', 'Daily Byte 4', 'dev', 'tip',
    '2026-09-04T14:00:00Z', 'corpus/std-04.md', 'sidecars/std-04.json', 2, 'video', 'youtube', 'Steady Dev',
    '{"published_at": "2026-09-04T13:30:00Z"}'
), (
    'std-item-05', 'std-slug-05', 'Steady Dev', 'Daily Byte 5', 'dev', 'tip',
    '2026-09-05T14:00:00Z', 'corpus/std-05.md', 'sidecars/std-05.json', 2, 'video', 'youtube', 'Steady Dev',
    '{"published_at": "2026-09-05T13:30:00Z"}'
);
```

#### Query 1A (Capture Time Basis)
`get_library_activity(idx, start="2026-09-01T00:00:00Z", end="2026-09-02T00:00:00Z", date_basis="capture_time")`

```json
{
  "ok": true,
  "schema_version": 1,
  "interval": {
    "start": "2026-09-01T00:00:00Z",
    "end": "2026-09-02T00:00:00Z",
    "grammar": "half_open_utc",
    "date_basis": "capture_time"
  },
  "history_coverage": {
    "earliest_recorded_ms": 1788220800000,
    "interval_covered": true,
    "coverage_status": "complete"
  },
  "captures": {
    "total": 201,
    "by_source_type": {
      "episode": 200,
      "video": 1
    },
    "by_creator_hint": [
      { "hint": "Host Dave", "count": 200, "source_types": ["episode"] },
      { "hint": "Steady Dev", "count": 1, "source_types": ["video"] }
    ],
    "publication_time_available_count": 201,
    "publication_time_missing_count": 0
  },
  "counterexample_warnings": [
    {
      "code": "backlog_import_cluster",
      "message": "200 items captured on 2026-09-01 carry publication dates prior to 2025-01-01. Ingestion rate does not indicate current publication velocity."
    }
  ],
  "support_level": "multi_source",
  "independent_creators_minimum_met": true
}
```

#### Query 1B (Publication Time Basis)
`get_library_activity(idx, start="2026-09-01T00:00:00Z", end="2026-09-02T00:00:00Z", date_basis="publication_time")`

```json
{
  "ok": true,
  "schema_version": 1,
  "interval": {
    "start": "2026-09-01T00:00:00Z",
    "end": "2026-09-02T00:00:00Z",
    "grammar": "half_open_utc",
    "date_basis": "publication_time"
  },
  "captures": {
    "total": 1,
    "by_source_type": {
      "video": 1
    },
    "by_creator_hint": [
      { "hint": "Steady Dev", "count": 1, "source_types": ["video"] }
    ],
    "publication_time_available_count": 1,
    "publication_time_missing_count": 0
  },
  "counterexample_warnings": [],
  "support_level": "single_source",
  "independent_creators_minimum_met": false
}
```

#### Acceptance Assertions
```python
# In test_gate1_backlog_import_vs_steady_capture:
res_cap = get_library_activity(idx, start="2026-09-01T00:00:00Z", end="2026-09-02T00:00:00Z", date_basis="capture_time")
res_pub = get_library_activity(idx, start="2026-09-01T00:00:00Z", end="2026-09-02T00:00:00Z", date_basis="publication_time")

assert res_cap["captures"]["total"] == 201
assert res_pub["captures"]["total"] == 1
assert any(w["code"] == "backlog_import_cluster" for w in res_cap["counterexample_warnings"])
assert res_pub["support_level"] == "single_source"
assert res_pub["independent_creators_minimum_met"] is False
```

---

### 3.2 Fixture 2: Same Clip Text Across Three Cross-Posts

- **Gate:** Repeated clips and cross-posts do not count as independent creators.
- **Test ID:** `test_gate2_cross_posted_clips_not_independent_creators`
- **Rationale:** Syndication accounts, short aggregators, and scraper blogs repost verbatim sentences. If three different channel names publish identical speech or prose, an analysis engine must not claim three independent creators verified or originated the statement.

#### Database State (Schema 24 & 27)

```sql
-- Three items across different platforms with identical clip text
INSERT INTO yoinks (
    video_id, slug, channel, title, topic, hook_type, yoinked_at, corpus_path, sidecar_path,
    schema_version, source_type, platform, author
) VALUES (
    'vid-x-syndicate', 'x-syndicate', 'x.com', 'Repost on X', 'systems', 'quote',
    '2026-09-03T09:00:00Z', 'corpus/x1.md', 'sidecars/x1.json', 2, 'x_thread', 'x', '@tech_repeater'
), (
    'vid-yt-syndicate', 'yt-syndicate', 'ViralShortsDaily', 'Shorts Clip', 'systems', 'quote',
    '2026-09-03T10:00:00Z', 'corpus/yt1.md', 'sidecars/yt1.json', 2, 'video', 'youtube', 'ViralShortsDaily'
), (
    'vid-web-syndicate', 'web-syndicate', 'mirrorhost.net', 'Mirror Post', 'systems', 'quote',
    '2026-09-03T11:00:00Z', 'corpus/w1.md', 'sidecars/w1.json', 2, 'page', 'web', 'mirrorhost.net'
);

-- Exact identical clip text inserted into clips table (derivable via clips.py)
INSERT INTO clips (clip_id, video_id, seq, start, end, text, cue_count)
VALUES (
    901, 'vid-x-syndicate', 0, 0.0, 15.0,
    'The core fallacy in modern systems engineering is treating network partitions as edge cases rather than permanent states.', 1
), (
    902, 'vid-yt-syndicate', 0, 0.0, 15.0,
    'The core fallacy in modern systems engineering is treating network partitions as edge cases rather than permanent states.', 1
), (
    903, 'vid-web-syndicate', 0, 0.0, 15.0,
    'The core fallacy in modern systems engineering is treating network partitions as edge cases rather than permanent states.', 1
);
```

#### Query
`get_library_activity(idx, start="2026-09-03T00:00:00Z", end="2026-09-04T00:00:00Z")`

#### Expected Report

```json
{
  "ok": true,
  "schema_version": 1,
  "interval": {
    "start": "2026-09-03T00:00:00Z",
    "end": "2026-09-04T00:00:00Z",
    "grammar": "half_open_utc",
    "date_basis": "capture_time"
  },
  "captures": {
    "total": 3,
    "by_source_type": {
      "x_thread": 1,
      "video": 1,
      "page": 1
    },
    "by_creator_hint": [
      { "hint": "@tech_repeater", "count": 1, "source_types": ["x_thread"] },
      { "hint": "ViralShortsDaily", "count": 1, "source_types": ["video"] },
      { "hint": "mirrorhost.net", "count": 1, "source_types": ["page"] }
    ],
    "publication_time_available_count": 0,
    "publication_time_missing_count": 3
  },
  "content_deduplication": {
    "total_clips_analyzed": 3,
    "unique_text_clusters": 1,
    "syndicated_clusters": [
      {
        "text_hash": "e6a4b2c1f9d8a7b6e5c4d3b2a1f0e9d8c7b6a5f4e3d2c1b0a9f8e7d6c5b4a3f2",
        "sample_text": "The core fallacy in modern systems engineering is treating network partitions as edge cases rather than permanent states.",
        "occurrences": 3,
        "items": ["vid-x-syndicate", "vid-yt-syndicate", "vid-web-syndicate"],
        "creator_hints": ["@tech_repeater", "ViralShortsDaily", "mirrorhost.net"]
      }
    ]
  },
  "support_level": "single_source",
  "independent_creators_minimum_met": false,
  "counterexample_warnings": [
    {
      "code": "cross_post_syndication",
      "message": "3 items contain verbatim identical text. Deduped to 1 content origin; fails cross-creator independence threshold."
    }
  ]
}
```

#### Acceptance Assertions
```python
# In test_gate2_cross_posted_clips_not_independent_creators:
res = get_library_activity(idx, start="2026-09-03T00:00:00Z", end="2026-09-04T00:00:00Z")

assert res["captures"]["total"] == 3
assert res["content_deduplication"]["unique_text_clusters"] == 1
assert res["support_level"] == "single_source"
assert res["independent_creators_minimum_met"] is False
assert any(w["code"] == "cross_post_syndication" for w in res["counterexample_warnings"])
```

---

### 3.3 Fixture 3: A Creator Under Two Channel Names

- **Gate:** The direction's cross-creator minimum and creator deduplication rules for Part A.
- **Test ID:** `test_gate3_creator_dual_channel_unmerged_hints`
- **Rationale:** One individual frequently operates both a primary tutorial channel and a podcast or vlog channel (e.g. "Grant Sanderson" uploading to YouTube channel `3Blue1Brown` and podcast feed `GrantSandersonPodcast`). Part A does not invent an authoritative entity graph, but must preserve unmerged observation hints while enforcing known creator links (`author` column) so a single person's accounts do not count as a multi-creator trend.

#### Database State (Schema 20 & 28)

```sql
INSERT INTO yoinks (
    video_id, slug, channel, title, topic, hook_type, yoinked_at, corpus_path, sidecar_path,
    schema_version, source_type, platform, author
) VALUES (
    'vid-3b1b-main', '3b1b-calculus', '3Blue1Brown', 'Essence of Calculus', 'math', 'visual',
    '2026-09-04T12:00:00Z', 'corpus/3b1b.md', 'sidecars/3b1b.json', 2, 'video', 'youtube', 'Grant Sanderson'
), (
    'vid-3b1b-podcast', '3b1b-audio', 'GrantSandersonPodcast', 'Neural Net Math Discussion', 'math', 'interview',
    '2026-09-04T16:00:00Z', 'corpus/pod.md', 'sidecars/pod.json', 2, 'episode', 'podcast', 'Grant Sanderson'
);
```

#### Query
`get_library_activity(idx, start="2026-09-04T00:00:00Z", end="2026-09-05T00:00:00Z")`

#### Expected Report

```json
{
  "ok": true,
  "schema_version": 1,
  "interval": {
    "start": "2026-09-04T00:00:00Z",
    "end": "2026-09-05T00:00:00Z",
    "grammar": "half_open_utc",
    "date_basis": "capture_time"
  },
  "captures": {
    "total": 2,
    "by_source_type": {
      "video": 1,
      "episode": 1
    },
    "by_channel_hint": [
      { "channel": "3Blue1Brown", "count": 1, "platform": "youtube" },
      { "channel": "GrantSandersonPodcast", "count": 1, "platform": "podcast" }
    ],
    "by_author_identity": [
      { "author": "Grant Sanderson", "count": 2, "channels": ["3Blue1Brown", "GrantSandersonPodcast"] }
    ]
  },
  "creator_deduplication": {
    "distinct_channel_hints": 2,
    "distinct_author_identities": 1,
    "author_matches": [
      {
        "author": "Grant Sanderson",
        "channels": ["3Blue1Brown", "GrantSandersonPodcast"],
        "items": ["vid-3b1b-main", "vid-3b1b-podcast"]
      }
    ]
  },
  "support_level": "single_source",
  "independent_creators_minimum_met": false,
  "counterexample_warnings": [
    {
      "code": "single_author_multi_channel",
      "message": "Activity originated from 2 channels sharing 1 verified author ('Grant Sanderson'). Fails 2-creator independence minimum."
    }
  ]
}
```

#### Acceptance Assertions
```python
# In test_gate3_creator_dual_channel_unmerged_hints:
res = get_library_activity(idx, start="2026-09-04T00:00:00Z", end="2026-09-05T00:00:00Z")

assert res["captures"]["total"] == 2
assert res["creator_deduplication"]["distinct_channel_hints"] == 2
assert res["creator_deduplication"]["distinct_author_identities"] == 1
assert res["independent_creators_minimum_met"] is False
assert res["support_level"] == "single_source"
```

---

### 3.4 Fixture 4: Deletion After a Report Was Computed

- **Gate:** Deleted or corrected inputs invalidate derived reports. Nothing cached survives a source revision change.
- **Test ID:** `test_gate4_deletion_invalidates_derived_report`
- **Rationale:** If an activity report is cached at $T_1$ over 5 items, and item 5 is soft-deleted at $T_2$ via [`yoinks.deleted_at`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/21220777-b29/gemini/migrations/0004_memory_indexes.sql#L15), the report cache key (binding `source_revision_hash`) must immediately miss. A query at $T_3$ must compute afresh over the 4 remaining items and record the deletion tombstone.

#### Database State at $T_1$ (Pre-Deletion)

```sql
INSERT INTO yoinks (
    video_id, slug, channel, title, topic, hook_type, yoinked_at, corpus_path, sidecar_path,
    schema_version, deleted_at, source_type, platform, author
) VALUES 
('vid-del-1', 'slug-del-1', 'ChanA', 'Item 1', 't', 'h', '2026-09-05T01:00:00Z', 'c1', 's1', 2, NULL, 'video', 'youtube', 'ChanA'),
('vid-del-2', 'slug-del-2', 'ChanA', 'Item 2', 't', 'h', '2026-09-05T02:00:00Z', 'c2', 's2', 2, NULL, 'video', 'youtube', 'ChanA'),
('vid-del-3', 'slug-del-3', 'ChanB', 'Item 3', 't', 'h', '2026-09-05T03:00:00Z', 'c3', 's3', 2, NULL, 'video', 'youtube', 'ChanB'),
('vid-del-4', 'slug-del-4', 'ChanB', 'Item 4', 't', 'h', '2026-09-05T04:00:00Z', 'c4', 's4', 2, NULL, 'video', 'youtube', 'ChanB'),
('vid-del-5', 'slug-del-5', 'ChanC', 'Item 5', 't', 'h', '2026-09-05T05:00:00Z', 'c5', 's5', 2, NULL, 'video', 'youtube', 'ChanC');
```

#### Report at $T_1$
`rep1 = get_library_activity(idx, start="2026-09-05T00:00:00Z", end="2026-09-06T00:00:00Z")`
- `rep1["captures"]["total"] == 5`
- `rep1["provenance"]["source_revision_hash"] == "rev_hash_5_items"`

#### Mutation at $T_2$
```sql
UPDATE yoinks 
SET deleted_at = '2026-09-05T12:00:00Z' 
WHERE video_id = 'vid-del-5';
```

#### Query at $T_3$ (Post-Deletion)
`rep2 = get_library_activity(idx, start="2026-09-05T00:00:00Z", end="2026-09-06T00:00:00Z")`

#### Expected Report at $T_3$

```json
{
  "ok": true,
  "schema_version": 1,
  "interval": {
    "start": "2026-09-05T00:00:00Z",
    "end": "2026-09-06T00:00:00Z",
    "grammar": "half_open_utc",
    "date_basis": "capture_time"
  },
  "provenance": {
    "source_revision_hash": "rev_hash_4_items_different_from_t1",
    "invalidation_detected": true,
    "prior_cache_invalidated_by": "source_item_deletion"
  },
  "captures": {
    "total": 4,
    "by_source_type": {
      "video": 4
    },
    "by_creator_hint": [
      { "hint": "ChanA", "count": 2, "source_types": ["video"] },
      { "hint": "ChanB", "count": 2, "source_types": ["video"] }
    ],
    "deleted_items_excluded_count": 1,
    "tombstones": [
      {
        "video_id": "vid-del-5",
        "deleted_at": "2026-09-05T12:00:00Z",
        "reason": "soft_deleted_in_yoinks"
      }
    ]
  },
  "support_level": "multi_source",
  "independent_creators_minimum_met": true
}
```

#### Acceptance Assertions
```python
# In test_gate4_deletion_invalidates_derived_report:
rep1 = get_library_activity(idx, start="2026-09-05T00:00:00Z", end="2026-09-06T00:00:00Z")
assert rep1["captures"]["total"] == 5

# Soft delete item 5
with idx.write_transaction() as conn:
    conn.execute("UPDATE yoinks SET deleted_at = '2026-09-05T12:00:00Z' WHERE video_id = 'vid-del-5'")

rep2 = get_library_activity(idx, start="2026-09-05T00:00:00Z", end="2026-09-06T00:00:00Z")
assert rep2["captures"]["total"] == 4
assert rep2["provenance"]["source_revision_hash"] != rep1["provenance"]["source_revision_hash"]
assert rep2["captures"]["deleted_items_excluded_count"] == 1
assert rep2["captures"]["tombstones"][0]["video_id"] == "vid-del-5"
```

---

### 3.5 Fixture 5: A Correction (Undo) After a Report Was Computed

- **Gate:** Deleted or corrected inputs invalidate derived reports.
- **Test ID:** `test_gate5_undo_correction_reverts_journal_and_invalidates`
- **Rationale:** In [`0027_library_substrate.sql`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/21220777-b29/gemini/migrations/0027_library_substrate.sql), user pins and librarian applies append to [`library_applies`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/21220777-b29/gemini/migrations/0027_library_substrate.sql#L169). An undo appends a new row with `kind='undo'`, `undo_of=<prior_apply_id>`, and increments `projection_revision` and `operation_sequence`. A shelf change report generated between the apply and the undo must invalidate; the recomputed report covering both operations must show a net membership delta of zero while faithfully recording two churn operations.

#### Database State at $T_1$ (After Initial Pin Apply)

```sql
INSERT INTO shelves(shelf_id, created_at) VALUES ('sh_alpha', '2026-09-01T00:00:00Z'), ('sh_beta', '2026-09-01T00:00:00Z');
INSERT INTO shelf_versions(version_id, revision_hash, status, created_at)
VALUES ('v1', '2222222222222222222222222222222222222222222222222222222222222222', 'active', '2026-09-01T00:00:00Z');
INSERT INTO shelf_nodes(version_id, shelf_id, parent_shelf_id, name, path_json, definition, include_json, exclude_json, retired)
VALUES ('v1', 'sh_alpha', NULL, 'Alpha', '["Alpha"]', 'Def A', '[]', '[]', 0),
       ('v1', 'sh_beta', NULL, 'Beta', '["Beta"]', 'Def B', '[]', '[]', 0);

INSERT INTO yoinks (video_id, slug, channel, title, yoinked_at, corpus_path, sidecar_path, schema_version)
VALUES ('vid-undo-01', 'undo-slug-01', 'Chan', 'Title', '2026-09-01T00:00:00Z', 'c', 's', 2);

-- State before pin: item is on sh_alpha
INSERT INTO item_shelves (video_id, shelf_id, version_id, source_revision, source, locked, is_primary, assigned_at)
VALUES ('vid-undo-01', 'sh_alpha', 'v1', 'src_rev_1', 'user', 0, 1, '2026-09-01T00:00:00Z');
UPDATE library_meta SET active_version_id = 'v1', projection_revision = 10, last_operation_sequence = 50;

-- At 2026-09-06T10:00:00Z, Operation 51: Pin move to sh_beta
INSERT INTO library_operation_receipts (operation_key, request_hash, operation_sequence, authoritative_record_hash, receipt_json)
VALUES ('opk-apply-51', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 51, 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', '{"status":"ok"}');

INSERT INTO library_applies (
    apply_id, operation_key, request_hash, kind, before_revision, after_revision,
    operation_sequence, authoritative_record_hash, forward_json, inverse_json, receipt_json,
    undo_of, created_at
) VALUES (
    'apply-51', 'opk-apply-51', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'pin',
    10, 11, 51, 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
    '{"video_id":"vid-undo-01","remove":["sh_alpha"],"add":["sh_beta"]}',
    '{"video_id":"vid-undo-01","remove":["sh_beta"],"add":["sh_alpha"]}',
    '{"status":"ok"}', NULL, '2026-09-06T10:00:00Z'
);
UPDATE item_shelves SET shelf_id = 'sh_beta', locked = 1 WHERE video_id = 'vid-undo-01';
UPDATE library_meta SET projection_revision = 11, last_operation_sequence = 51;
```

#### Intermediate Report at $T_1$
`rep_t1 = get_library_activity(idx, start="2026-09-06T00:00:00Z", end="2026-09-06T12:00:00Z")`
- Shows net change: `sh_alpha: -1`, `sh_beta: +1`.
- Bound to `projection_revision = 11`, `last_operation_sequence = 51`.

#### Undo Mutation at $T_2$ (`2026-09-06T14:00:00Z`)

```sql
INSERT INTO library_operation_receipts (operation_key, request_hash, operation_sequence, authoritative_record_hash, receipt_json)
VALUES ('opk-undo-52', 'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc', 52, 'dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd', '{"status":"ok"}');

INSERT INTO library_applies (
    apply_id, operation_key, request_hash, kind, before_revision, after_revision,
    operation_sequence, authoritative_record_hash, forward_json, inverse_json, receipt_json,
    undo_of, created_at
) VALUES (
    'apply-52', 'opk-undo-52', 'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc', 'undo',
    11, 12, 52, 'dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd',
    '{"video_id":"vid-undo-01","remove":["sh_beta"],"add":["sh_alpha"]}',
    '{"video_id":"vid-undo-01","remove":["sh_alpha"],"add":["sh_beta"]}',
    '{"status":"ok"}', 'apply-51', '2026-09-06T14:00:00Z'
);
UPDATE item_shelves SET shelf_id = 'sh_alpha', locked = 0 WHERE video_id = 'vid-undo-01';
UPDATE library_meta SET projection_revision = 12, last_operation_sequence = 52;
```

#### Query at $T_3$
`rep_t3 = get_library_activity(idx, start="2026-09-06T00:00:00Z", end="2026-09-06T18:00:00Z")`

#### Expected Report at $T_3$

```json
{
  "ok": true,
  "schema_version": 1,
  "interval": {
    "start": "2026-09-06T00:00:00Z",
    "end": "2026-09-06T18:00:00Z",
    "grammar": "half_open_utc",
    "date_basis": "capture_time"
  },
  "provenance": {
    "projection_revision": 12,
    "last_operation_sequence": 52
  },
  "shelf_activity": {
    "total_operations": 2,
    "applied_operations": [
      {
        "apply_id": "apply-51",
        "operation_sequence": 51,
        "kind": "pin",
        "created_at": "2026-09-06T10:00:00Z"
      },
      {
        "apply_id": "apply-52",
        "operation_sequence": 52,
        "kind": "undo",
        "undo_of": "apply-51",
        "created_at": "2026-09-06T14:00:00Z"
      }
    ],
    "net_membership_changes": {
      "sh_alpha": { "added": 1, "removed": 1, "net": 0 },
      "sh_beta": { "added": 1, "removed": 1, "net": 0 }
    },
    "churn": {
      "total_mutations": 2,
      "affected_items_count": 1,
      "churn_percent": 100
    }
  }
}
```

#### Acceptance Assertions
```python
# In test_gate5_undo_correction_reverts_journal_and_invalidates:
rep_t1 = get_library_activity(idx, start="2026-09-06T00:00:00Z", end="2026-09-06T12:00:00Z")
assert rep_t1["shelf_activity"]["net_membership_changes"]["sh_alpha"]["net"] == -1
assert rep_t1["shelf_activity"]["net_membership_changes"]["sh_beta"]["net"] == 1

# Execute undo transaction
# ... (insert apply-52 and bump library_meta) ...

rep_t3 = get_library_activity(idx, start="2026-09-06T00:00:00Z", end="2026-09-06T18:00:00Z")
assert rep_t3["provenance"]["projection_revision"] == 12
assert rep_t3["shelf_activity"]["total_operations"] == 2
assert rep_t3["shelf_activity"]["net_membership_changes"]["sh_alpha"]["net"] == 0
assert rep_t3["shelf_activity"]["net_membership_changes"]["sh_beta"]["net"] == 0
assert rep_t3["shelf_activity"]["churn"]["total_mutations"] == 2
```

---

### 3.6 Fixture 6: Single-Source Interval

- **Gate:** When support is too thin, show a single-source observation or no trend.
- **Test ID:** `test_gate6_single_source_interval_thin_support`
- **Rationale:** When only one feed or channel is captured during a window, reporting an "aggregate trend" or "community consensus" is invalid. The system must report `support_level="single_source"` and disallow cross-source trend claims.

#### Database State

```sql
INSERT INTO source_subscriptions (
    source_id, kind, source_key, canonical_url, display_name, adapter,
    detection_enabled, archived, consent_state, revision, consent_epoch, boundary,
    created_at_ms, updated_at_ms
) VALUES (
    'sub_solitary', 'podcast_rss', 'solitary_feed', 'https://solitary.example.com/rss',
    'Solitary Monologue', 'podcast_rss_v1', 1, 0, 'on', 1, 1, 'none',
    1788566400000, 1788566400000
);

INSERT INTO yoinks (
    video_id, slug, channel, title, topic, hook_type, yoinked_at, corpus_path, sidecar_path,
    schema_version, source_type, platform, author
) VALUES 
('sol-1', 'sol-slug-1', 'Solitary Monologue', 'Episode 40', 'ai', 'h', '2026-09-07T08:00:00Z', 'c', 's', 2, 'episode', 'podcast', 'Solo Host'),
('sol-2', 'sol-slug-2', 'Solitary Monologue', 'Episode 41', 'ai', 'h', '2026-09-07T12:00:00Z', 'c', 's', 2, 'episode', 'podcast', 'Solo Host'),
('sol-3', 'sol-slug-3', 'Solitary Monologue', 'Episode 42', 'ai', 'h', '2026-09-07T16:00:00Z', 'c', 's', 2, 'episode', 'podcast', 'Solo Host');
```

#### Query
`get_library_activity(idx, start="2026-09-07T00:00:00Z", end="2026-09-08T00:00:00Z")`

#### Expected Report

```json
{
  "ok": true,
  "schema_version": 1,
  "interval": {
    "start": "2026-09-07T00:00:00Z",
    "end": "2026-09-08T00:00:00Z",
    "grammar": "half_open_utc",
    "date_basis": "capture_time"
  },
  "captures": {
    "total": 3,
    "by_source_type": {
      "episode": 3
    },
    "by_creator_hint": [
      { "hint": "Solo Host", "count": 3, "source_types": ["episode"] }
    ]
  },
  "sources": {
    "active_sources_count": 1,
    "details": [
      {
        "source_id": "sub_solitary",
        "display_name": "Solitary Monologue",
        "adapter": "podcast_rss_v1",
        "captures_in_interval": 3
      }
    ]
  },
  "support_level": "single_source",
  "independent_creators_minimum_met": false,
  "counterexample_warnings": [
    {
      "code": "thin_support_single_source",
      "message": "Activity limited to 1 source ('Solitary Monologue'). Cross-source trend inferences are prohibited."
    }
  ]
}
```

#### Acceptance Assertions
```python
# In test_gate6_single_source_interval_thin_support:
res = get_library_activity(idx, start="2026-09-07T00:00:00Z", end="2026-09-08T00:00:00Z")

assert res["captures"]["total"] == 3
assert res["sources"]["active_sources_count"] == 1
assert res["support_level"] == "single_source"
assert res["independent_creators_minimum_met"] is False
assert any(w["code"] == "thin_support_single_source" for w in res["counterexample_warnings"])
```

---

### 3.7 Fixture 7: Interval Before Any Observation History Exists

- **Gate:** Denominators and the history-coverage rule: no inference of old changes from today's state.
- **Test ID:** `test_gate7_pre_observation_interval_coverage_gap`
- **Rationale:** If the library's earliest recorded item or subscription cursor is dated `2026-01-01`, and a client requests an activity report for June 2025 (`2025-06-01` to `2025-06-30`), returning `total_captures: 0` or "0% churn" falsely implies the library was actively monitoring the world in 2025 and observed zero publications. The system must report an explicit coverage gap.

#### Database State

```sql
-- Earliest recorded entry in index is 2026-01-01T00:00:00Z
INSERT INTO yoinks (
    video_id, slug, channel, title, yoinked_at, corpus_path, sidecar_path, schema_version
) VALUES (
    'first-ever-item', 'first-item', 'Pioneer', 'Pioneer Video', '2026-01-01T00:00:00Z', 'c', 's', 2
);
INSERT INTO source_subscriptions (
    source_id, kind, source_key, canonical_url, adapter, created_at_ms, updated_at_ms
) VALUES (
    'src_init', 'youtube_channel', 'key1', 'https://youtube.com/@init', 'youtube_channel_rss_v1',
    1767225600000, 1767225600000 -- 2026-01-01T00:00:00Z in ms
);
```

#### Query
`get_library_activity(idx, start="2025-06-01T00:00:00Z", end="2025-06-30T23:59:59Z")`

#### Expected Report

```json
{
  "ok": false,
  "schema_version": 1,
  "error": {
    "code": "history_coverage_gap",
    "message": "Requested interval precedes earliest library observation history. Cannot infer historical baseline from current state.",
    "details": {
      "requested_start": "2025-06-01T00:00:00Z",
      "requested_end": "2025-06-30T23:59:59Z",
      "earliest_recorded_observation": "2026-01-01T00:00:00Z",
      "earliest_recorded_ms": 1767225600000
    }
  },
  "history_coverage": {
    "interval_covered": false,
    "coverage_status": "no_history"
  }
}
```

#### Acceptance Assertions
```python
# In test_gate7_pre_observation_interval_coverage_gap:
res = get_library_activity(idx, start="2025-06-01T00:00:00Z", end="2025-06-30T23:59:59Z")

assert res["ok"] is False
assert res["error"]["code"] == "history_coverage_gap"
assert res["history_coverage"]["coverage_status"] == "no_history"
assert res["history_coverage"]["interval_covered"] is False
```

---

## 4. Measurable Faithfulness Check for Future Narration

The brief mandates:  
> "Narration (client-run, later) must not add facts beyond the computed packet. State the faithfulness requirement for future narration as a measurable check."

When a downstream client (such as an LLM agent or report summarizer) produces free-form narrative prose $N$ from an activity report packet $P$, the narrative must not introduce unbacked assertions, fabricate numbers, or claim broad consensus when support is thin.

### 4.1 Verification Metric Specification

The faithfulness metric is an automated evaluator $M(N, P) \in \{0, 1\}$ computed over the generated text $N$ and the input packet $P$:

$$M(N, P) = E_{\text{num}}(N, P) \land E_{\text{date}}(N, P) \land E_{\text{entity}}(N, P) \land E_{\text{trend}}(N, P) \land E_{\text{dir}}(N, P)$$

1. **Numerical Faithfulness ($E_{\text{num}}$):**
   - Extract all numbers, percentages, and cardinal counts from text $N$: $K(N)$.
   - Every number $k \in K(N)$ must exist in $P$ (under `captures.total`, `shelf_activity.churn.churn_percent`, `shelf_activity.total_operations`, `sources.active_sources_count`, etc.) or be a direct arithmetic conversion (e.g. converting fraction $1/2$ to $50\%$).
   - If any number appears in $N$ that is not present in $P$: $E_{\text{num}} = 0$.

2. **Temporal Window Faithfulness ($E_{\text{date}}$):**
   - Extract any date or month mentioned in $N$: $D(N)$.
   - All mentioned dates must fall within $[P.\text{interval.start}, P.\text{interval.end}]$.
   - If $P.\text{interval.date\_basis} == \text{"capture\_time"}$, $N$ must describe events as "captured", "ingested", or "saved", and must not assert they were "published" or "released" on those dates.
   - Violation sets $E_{\text{date}} = 0$.

3. **Entity and Shelf Faithfulness ($E_{\text{entity}}$):**
   - Extract named creators, channels, and shelves mentioned in $N$.
   - Every mentioned channel/creator must match an entry in $P.\text{captures.by\_creator\_hint}$ or $P.\text{sources.details}$.
   - Every mentioned shelf must match a key in $P.\text{shelf\_activity.net\_membership\_changes}$ or $P.\text{shelf\_activity.shelf_sizes}$.
   - Hallucinated shelves or creators set $E_{\text{entity}} = 0$.

4. **Consensus and Trend Gating ($E_{\text{trend}}$):**
   - If $P.\text{support\_level} \in \{\text{"single\_source"}, \text{"insufficient"}\}$ or $P.\text{independent\_creators\_minimum\_met} == \text{false}$:
   - $N$ must NOT contain multi-source consensus terms:
     `{"broad consensus", "creators agree", "industry-wide", "across creators", "multiple perspectives", "widespread trend", "surge across channels"}`.
   - If any forbidden token appears: $E_{\text{trend}} = 0$.

5. **Directional Faithfulness ($E_{\text{dir}}$):**
   - Extract directional verbs: "increased", "decreased", "moved", "stable".
   - If $N$ asserts a shelf "grew" or "increased", the corresponding shelf in $P.\text{shelf\_activity.net\_membership\_changes}$ must have $\text{net} > 0$.
   - If $N$ asserts net membership was "unchanged", net delta must equal 0.
   - Inconsistent direction sets $E_{\text{dir}} = 0$.

**Acceptance Threshold:** A candidate narration passes if and only if $M(N, P) == 1$ (100% precision, zero unsupported claims).

### 4.2 Labeled Narration Counterexamples

#### Case A: Compliant Narration (Pass)
- **Input Packet:** Fixture 5 report at $T_3$ (`net = 0` for both shelves, `total_operations = 2`, `affected_items = 1`).
- **Narration:**
  > "Between 00:00 and 18:00 UTC on September 6, two shelf operations were recorded for 1 item. A pin operation initially moved the item from Alpha to Beta, followed by an undo operation that returned it to Alpha. Net shelf membership across the interval remained unchanged."
- **Evaluation:**
  - Numbers: `2`, `1` (Match `total_operations` and `affected_items_count`).
  - Dates: `September 6` (Matches `2026-09-06`).
  - Entities: `Alpha`, `Beta` (Match `sh_alpha`, `sh_beta`).
  - Direction: "remained unchanged" (Matches `net: 0`).
  - Score: $M(N, P) = 1$ (**PASS**).

#### Case B: Numerical Hallucination (Fail)
- **Input Packet:** Fixture 1B (`total = 1`, `Steady Dev`).
- **Narration:**
  > "On September 1, 2026, Steady Dev published 3 videos covering developer tips."
- **Evaluation:**
  - Number `3` is not in $P$ ($P.\text{captures.total} = 1$).
  - Score: $E_{\text{num}} = 0 \implies M(N, P) = 0$ (**FAIL**).

#### Case C: Unsupported Trend Claim on Single-Source Data (Fail)
- **Input Packet:** Fixture 6 (`support_level = "single_source"`, `captures.total = 3`, `Solitary Monologue`).
- **Narration:**
  > "On September 7, creators broadly aligned around new AI topics, demonstrating widespread community agreement."
- **Evaluation:**
  - $P.\text{support\_level} == \text{"single\_source"}$, but narrative asserts "creators broadly aligned" and "widespread community agreement".
  - Score: $E_{\text{trend}} = 0 \implies M(N, P) = 0$ (**FAIL**).

#### Case D: Temporal/Date Basis Slippage (Fail)
- **Input Packet:** Fixture 1A (`date_basis = "capture_time"`, `total = 201`, warning: `backlog_import_cluster`).
- **Narration:**
  > "Podcasters published a record 200 new episodes on September 1, 2026."
- **Evaluation:**
  - Packet reflects capture time, with publication dates in 2022–2024. Stating they were *published* on September 1, 2026 violates $E_{\text{date}}$.
  - Score: $E_{\text{date}} = 0 \implies M(N, P) = 0$ (**FAIL**).

---

## 5. Verification Harness and Implementation Directives

Run AZ must implement the test suite in `tests/test_library_analysis_fixtures.py`.

### 5.1 Test Execution Matrix

| Test Function | Gate Enforced | Schema Tables Exercised | Key Verification Metric |
|---|---|---|---|
| `test_gate1_backlog_import_vs_steady_capture` | Backlog vs. publication trend | [`yoinks`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/21220777-b29/gemini/migrations/0001_initial_schema.sql#L22), [`podcast_episodes`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/21220777-b29/gemini/migrations/0010_podcast_feeds.sql#L31), [`source_items`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/21220777-b29/gemini/migrations/0028_source_subscriptions.sql#L85) | `date_basis` separation (201 capture vs 1 publication) |
| `test_gate2_cross_posted_clips_not_independent_creators` | Cross-post clip deduplication | [`yoinks`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/21220777-b29/gemini/migrations/0001_initial_schema.sql#L22), [`clips`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/21220777-b29/gemini/migrations/0024_clips.sql#L17) | Collapses 3 cross-posts to 1 cluster; `independent_creators_minimum_met: false` |
| `test_gate3_creator_dual_channel_unmerged_hints` | Dual-channel creator deduplication | [`yoinks`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/21220777-b29/gemini/migrations/0001_initial_schema.sql#L22), [`0020_platform_author`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/21220777-b29/gemini/migrations/0020_platform_author.sql#L26) | Preserves channel hints but maps to single author identity |
| `test_gate4_deletion_invalidates_derived_report` | Deletion invalidates cached report | [`yoinks.deleted_at`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/21220777-b29/gemini/migrations/0004_memory_indexes.sql#L15) | Cache key mismatch, excludes tombstone from active count |
| `test_gate5_undo_correction_reverts_journal_and_invalidates` | Undo correction journal accounting | [`library_applies`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/21220777-b29/gemini/migrations/0027_library_substrate.sql#L169), [`item_shelves`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/21220777-b29/gemini/migrations/0027_library_substrate.sql#L117) | Invalidation on projection revision bump; net delta = 0, churn = 2 |
| `test_gate6_single_source_interval_thin_support` | Thin support refusal | [`source_subscriptions`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/21220777-b29/gemini/migrations/0028_source_subscriptions.sql#L9), [`yoinks`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/21220777-b29/gemini/migrations/0001_initial_schema.sql#L22) | Sets `support_level="single_source"`; forbids multi-source claims |
| `test_gate7_pre_observation_interval_coverage_gap` | Pre-observation coverage refusal | [`source_subscriptions`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/21220777-b29/gemini/migrations/0028_source_subscriptions.sql#L9), [`yoinks`](file:///C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/21220777-b29/gemini/migrations/0001_initial_schema.sql#L22) | Returns `history_coverage_gap` error; refuses zero inference |
| `test_narration_faithfulness_metric` | Narration faithfulness evaluator | Input packet $P$ and candidate strings $N$ | Zero hallucinated numbers, dates, entities, or unsupported trends |

### 5.2 Test Execution Directives

1. Every test must run against an isolated SQLite database instantiated via `Index.open(tmp_path / "fixture.db")`.
2. All migrations through `0028_source_subscriptions.sql` must be applied. No uncommitted migrations or ad-hoc schema modifications are permitted.
3. The live user database (`%LOCALAPPDATA%\Uoink\index.db`) and port 5179 must never be opened.
4. Test assertions must compare exact canonical keys in dictionary outputs.
