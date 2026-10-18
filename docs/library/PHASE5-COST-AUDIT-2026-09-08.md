# Phase 5 Part A cost audit (2026-09-08)

**Author:** grok · **Run:** AY · **Owner of this file:** grok (Fable reservation in `PHASE5-BRIEF-2026-09-08.md`).
**Not code. No model. No helper. No port 5179. No live index. No commit.**

This audit names the SQL the Part A activity reports need, what the existing indexes in `migrations/*.sql` actually cover, expected cost at the measured 548-item library and at 10,000 items, which indexes are missing, and the dashboard display budget. It does not freeze report definitions; that is Astra's contract. It does not implement queries; that is run AZ.

## Method and limits of this forecast

- **Schema source:** `migrations/0001_initial_schema.sql` through `migrations/0028_source_subscriptions.sql` as they stand in this worktree. Line citations are to those files.
- **Applied-journal shape (read only):** `library_work.py` `_delta` / `_project_record` (forward `items` keyed by `video_id`; `created_at` written from `_stamp()`).
- **Existing capture-time reader:** `index.py` `search_yoinks_for_memory` (inclusive `YYYY-MM-DD` on `yoinked_at`, default page 50, clamp 200). Part A intervals are half-open UTC; do not copy the inclusive `date_to` trick without labelling it.
- **Scale 548:** observed item count on the 2026-09-04 upgraded copy (`COST-MODEL-2026-09-04.md`: 548 cards, 3,216 clip rows). Not re-opened here.
- **Scale 10,000:** arithmetic projection of *items*. Journal rows, `source_items`, and `engagement_events` do not grow 1:1 with items.
- **Planner:** SQLite 3 B-tree, WAL (`index.py` `PRAGMA journal_mode=WAL`), default 4 KiB pages. This run did **not** `EXPLAIN QUERY PLAN` against any index file. Costs are schema-based forecasts, labelled as such. Migration `0004` already ran EXPLAIN on memory-page filters and omitted compound `(yoinked_at DESC, <filter>)` indexes because the planner did not pick them.
- **Deadline inherited from Phase 4:** 2.0 seconds from accepted request through result construction (`PHASE4-CONTRACT-2026-09-08.md` service deadline). Part A is pure aggregation: the budget is SQLite + JSON parse + serialization, not tokens. Paid spend is $0.

A number that requires reading `forward_json` / `inverse_json` / `evidence_json` / `metadata_json` is a different cost class from a number that reads integer and short-text columns. The rest of this note is mostly that distinction.

## Part A reports this audit prices

From the frozen brief, not from a later contract draft:

| ID | Report | Default clock | Must not do |
|---|---|---|---|
| A1 | Captures per interval by `source_type` and creator hint (`author`, else `channel`) | `yoinks.yoinked_at` (capture) | Treat capture as publication |
| A2 | Same counts on publication time, **only** where a source carries it, labelled as publication | `podcast_episodes.published_at`; `source_items.published_at_ms`; not sidecar files | Infer missing publication time from `yoinked_at` |
| A3 | Shelf membership changes per interval from the applied journal | `library_applies.created_at` | Infer old membership from today's `item_shelves` |
| A4 | Current shelf size; interval churn from the journal (Phase 2 churn definition) | Size: now. Churn: applies in the interval | Use today's sizes as a time series |
| A5 | Sources with activity, with the observation window each source actually has | `source_subscriptions.last_observed_ms`; cursor `coverage` / `observed_count`; `source_items` first/last seen and published | Present a 15- or 50-entry feed window as a complete catalog |
| A6 | Per-item engagement in the interval (table is named in the brief; keep it a count, not a trend claim) | `engagement_events.ts_utc` | Reuse `Index.top_engaged` (Python N+1 over all events) |

Supporting reads, not reports: active taxonomy and projection (`shelf_versions`, `library_meta`, `library_runs`); deletion/undo invalidation (`yoinks.deleted_at`, `library_applies.undo_of`).

## Scale model (what 548 and 10,000 actually mean)

| Relation | Grows with | 548-item library (order) | 10,000-item library (order) |
|---|---|---|---|
| `yoinks` | items | 548 | 10,000 |
| `item_shelves` | items × memberships (1–3) | 0.5k–1.6k | 10k–30k |
| `shelf_versions` / `shelf_nodes` | taxonomy revisions × ~11 shelves (v3 has 11 `shelf_id`s) | tens | tens to low hundreds |
| `library_runs` | assignment runs | small | small |
| `library_applies` | projection-changing operations, **not** items | handful after one reshelve + pins | still handful of *rows* after one reshelve; each row's JSON may hold 10k item keys |
| `source_subscriptions` | feeds/channels/playlists | tens | tens to low hundreds |
| `source_items` | observed entries, including never-captured | can exceed yoinks (RSS windows accumulate) | 10k–100k plausible |
| `podcast_episodes` | feed length, captured or not | hundreds per feed | thousands across feeds |
| `engagement_events` | opens/clicks over time | low thousands (comment in `index.py` `top_engaged`) | 10^5–10^6 if the 10k library is old |

The expensive 10k case is not “10,000 integer primary keys.” It is one `library_applies` row whose `forward_json` embeds 10,000 membership records including `evidence_json`, or a publication-time pass that parses 10,000 `metadata_json` blobs / sidecar files.

## Schema inventory (cite these lines)

### `yoinks` — capture clock, type, creator hint, deletion

`migrations/0001_initial_schema.sql:22-34` — `video_id` PK, `channel`, `title`, `yoinked_at TEXT NOT NULL`, `metadata_json`.
`migrations/0001_initial_schema.sql:86-88` — `idx_yoinks_yoinked_at ON yoinks(yoinked_at DESC)`; `idx_yoinks_channel ON yoinks(channel)`; `idx_yoinks_hook_type`.
`migrations/0004_memory_indexes.sql:15-16` — `deleted_at TEXT`; `idx_yoinks_deleted_at ON yoinks(deleted_at)`. Lines 6–13 record that compound `(yoinked_at DESC, filter)` indexes were **omitted** after EXPLAIN: a leading DESC sort column does not seed an equality seek on the second column.
`migrations/0015_universal_site.sql:11-13` — `source_type TEXT`; `idx_yoinks_source_type ON yoinks(source_type)`.
`migrations/0020_platform_author.sql:26-30` — `platform TEXT`; `author TEXT`; `idx_yoinks_platform`; `idx_yoinks_author`.
`migrations/0001_initial_schema.sql:33` and `index.py:83-84` — `metadata_json` / `health_score_json` live on the row. `SELECT *` is a different cost from `SELECT video_id, source_type, author, channel, yoinked_at, deleted_at`.

Capture time is `yoinked_at`. Publication time is **not** a yoinks column.
`index.py:99-100` — `_now_iso()` formats `yoinked_at` as local naive `YYYY-MM-DDTHH:MM:SS` (no `Z`). Part A intervals are half-open UTC. Cost of conversion is O(1) per bind; mixing UTC bounds with local-naive stored strings is a **correctness** bug, not a planner issue. Astra owns the interval grammar.

### `library_applies` — membership journal

`migrations/0027_library_substrate.sql:169-183` — `apply_id` PK; unique `operation_key`; `kind` in `apply|activate|pin|undo`; `before_revision` / `after_revision`; unique `operation_sequence`; `forward_json` / `inverse_json` / `receipt_json`; unique `undo_of`; `created_at TEXT NOT NULL`.
No `CREATE INDEX` on `created_at` or `kind`. The unique `operation_sequence` is the only time-ordered access path that is indexed, and it is sequence, not UTC.
`library_work.py:224` — default `clock` is `lambda: int(time.time() * 1000)`.
`library_work.py:238-241` — `_now()` is `int(self.clock())`; `_stamp()` is `str(self._now())`. Apply timestamps are millisecond epoch as text, **not** ISO-8601. `yoinks.yoinked_at` is ISO text (`index.py` `_now_iso`). Interval binds must convert. Lexicographic compare of 13-digit millisecond strings works until year 2286; do not mix the two encodings in one `WHERE`.
`library_work.py:851-864` — forward `items` is a dict keyed by `video_id`; values are full `item_shelves` rows (including `evidence_json`).
`library_work.py:1295-1299` — only projection-changing operations land in `library_applies`. No-change receipts stay in `library_operation_receipts` (`0027:154-160`).
`PHASE2-CONTRACT-2026-09-04.md` — churn numerator/denominator are defined on a preview baseline, not on today's `item_shelves`. Preview `summary_json` (`0027:138-151`, `library_work.py:937-942`) is **not** the durable interval journal; previews expire.

### `item_shelves` — current size only

`migrations/0027_library_substrate.sql:117-133` — PK `(video_id, shelf_id)`; `library_one_primary ON item_shelves(video_id) WHERE is_primary=1`.
No index on `shelf_id`, `assigned_at`, or `version_id`. `GROUP BY shelf_id` is a table scan. `ON DELETE CASCADE` from `yoinks` (`0027:118`).

### `shelf_versions` / `library_runs` / `library_meta`

`migrations/0027_library_substrate.sql:11-19` — `shelf_versions`: PK `version_id`; unique `revision_hash`; `status`; `created_at`.
`migrations/0027_library_substrate.sql:20` — `library_one_active_taxonomy ON shelf_versions(status) WHERE status='active'`.
`migrations/0027_library_substrate.sql:21-34` — `shelf_nodes` PK `(version_id, shelf_id)`.
`migrations/0027_library_substrate.sql:35-41` — `library_meta` singleton: `projection_revision`, `active_version_id`, `last_operation_sequence`.
`migrations/0027_library_substrate.sql:43-51` — `library_runs`: PK `run_id`; `version_id` FK; `run_revision`; `state`; `created_at`. No index on `created_at`, `version_id`, or `state`.

These tables are tiny at both scales. Full scans are the right plan.

### `engagement_events`

`migrations/0006_v2_schema.sql:45-53` — `id` INTEGER PK; `video_id`; `event_type`; `ts_utc TEXT NOT NULL`; `source`; `idx_engagement_video ON engagement_events(video_id)`; `idx_engagement_ts ON engagement_events(ts_utc)`.
`migrations/0021_suite_engagement.sql:4-7` — `event_id TEXT`; unique `idx_engagement_event_id` where not null.
No FK to `yoinks`. Deleted items leave events. No index on `event_type`. No covering `(ts_utc, video_id, event_type)`.

### `podcast_episodes`

`migrations/0010_podcast_feeds.sql:31-52` — `published_at TEXT`; `yoink_video_id TEXT`; `discovered_at TEXT NOT NULL`; unique `(feed_id, guid)`.
`migrations/0010_podcast_feeds.sql:53-58` — `idx_podcast_episodes_feed`; `idx_podcast_episodes_status`; `idx_podcast_episodes_published ON podcast_episodes(published_at)`.
`migrations/0023_podcast_watch.sql:14-15` — `idx_podcast_episodes_auto_ingest ON podcast_episodes(feed_id, auto_ingest_requested, yoink_video_id)`. Third column does **not** serve `WHERE yoink_video_id = ?`.
No dedicated index on `yoink_video_id`. No index on `discovered_at`.

### `source_subscriptions` and the observation tables the reports actually need

`migrations/0028_source_subscriptions.sql:9-40` — PK `source_id`; `kind`; `last_observed_ms INTEGER NOT NULL DEFAULT 0`; `created_at_ms`; unique `(kind, source_key)`. No index on `last_observed_ms`, `archived`, or `consent_state`.
`migrations/0028_source_subscriptions.sql:64-84` — `source_detection_cursors`: PK `source_id`; `coverage` in `window|complete|partial|unknown`; `observed_count`; `truncated`; `last_poll_success_ms`; `source_detection_due ON (next_poll_at_ms)`.
`migrations/0028_source_subscriptions.sql:85-116` — `source_items`: `published_at_ms INTEGER`; `first_seen_ms`; `last_seen_ms`; `video_id`; `state`; unique `(source_id, entry_id)`; `source_items_capture_key ON (capture_key)`; `source_items_ready ON (source_id, state, retry_at_ms, first_seen_ms)`.
No index on `published_at_ms`, `last_seen_ms`, or `video_id`. `first_seen_ms` is the fourth column of `source_items_ready`, so `MIN(first_seen_ms) GROUP BY source_id` cannot use it as a leftmost prefix.

`complete` coverage describes that poll's enumeration, not historical completeness (`PHASE3-CONTRACT-2026-09-07.md`; YouTube Atom window 15, podcast parser first 50 — `PHASE3-ADAPTER-LIMITS-2026-09-07.md` §3.1).

## Existing indexes that Part A can use

| Index | File:line | Serves |
|---|---|---|
| `idx_yoinks_yoinked_at` `(yoinked_at DESC)` | `0001:86` | A1 capture-time range and newest-first samples |
| `idx_yoinks_deleted_at` | `0004:16` | Deletion invalidation; **not** a substitute for `WHERE deleted_at IS NULL` on a date range |
| `idx_yoinks_source_type` | `0015:12-13` | Equality on type without a date predicate |
| `idx_yoinks_author` / `idx_yoinks_channel` | `0020:30` / `0001:87` | Creator-hint equality; not a date range |
| `library_applies.operation_sequence` UNIQUE | `0027:176` | Ordered journal walk by sequence |
| `library_applies.undo_of` UNIQUE | `0027:181` | “Was this apply undone?” |
| `library_one_active_taxonomy` | `0027:20` | Active taxonomy, O(1) |
| `library_one_primary` | `0027:133` | Primary membership per item, not size-by-shelf |
| `idx_engagement_ts` | `0006:53` | A6 interval |
| `idx_engagement_video` | `0006:52` | Per-item engagement, not an interval |
| `idx_podcast_episodes_published` | `0010:57-58` | A2 podcast publication range |
| `source_items_ready` `(source_id, state, …)` | `0028:116` | Per-source state counts (already used by `list_sources` `_summary`) |
| `source_detection_due` | `0028:84` | Poller, not reports |

## Named queries

Placeholders `:start` / `:end` are half-open UTC. Bind ISO-8601 for `yoinked_at` / `ts_utc` / RSS `published_at`; bind millisecond integers (or the 13-digit text form) for `library_applies.created_at` and `source_items.*_ms`. Never `SELECT *` on `yoinks`, `library_applies`, `item_shelves`, or `source_items` for these reports.

Tables the brief named, and where each is read:

| Table | Queries | Role |
|---|---|---|
| `yoinks` | Q1, Q2a, Q4, Q7 | Capture clock, type, creator hint, live-row filter |
| `library_applies` | Q3, Q4 churn, Q7 | Membership journal |
| `shelf_versions` | Q8 | Taxonomy revision in the interval; active hash |
| `library_runs` | Q8 | Projection/run revisions in the interval |
| `engagement_events` | Q6 | Per-item engagement counts |
| `podcast_episodes` | Q2a | Publication clock for captured episodes |
| `source_subscriptions` | Q2b, Q5 | Source identity, `last_observed_ms`, kind |
| `source_items` (join target of 0028, not a named brief table) | Q2b, Q5 | `published_at_ms`, observation window |
| `item_shelves` (0027, current projection only) | Q4 size | Current shelf size; **not** history |
| `library_meta` | Q8 | `projection_revision`, `last_operation_sequence` |

### Q1 — A1 captures by type and creator hint (capture time)

```sql
SELECT source_type,
       COALESCE(NULLIF(author, ''), channel) AS creator_hint,
       COUNT(*) AS n
FROM yoinks
WHERE deleted_at IS NULL
  AND yoinked_at >= :start AND yoinked_at < :end
GROUP BY 1, 2
ORDER BY n DESC;
```

**Plan with existing indexes:** range on `idx_yoinks_yoinked_at`, filter `deleted_at IS NULL` (most rows are live, so the deleted_at index is the wrong leading choice), group in a temp table.

**548:** ~548 rows in an all-history window, tens in a 7-day window. Forecast **< 2 ms**. Table scan of thin columns is also acceptable; `0004` already preferred single-column indexes at this size.

**10,000:** 7-day window: index range, likely tens–hundreds of rows, **< 5 ms**. All-history `GROUP BY`: 10k-row scan of five thin columns, forecast **1–10 ms**. Still inside the 2 s deadline by two orders of magnitude.

**Do not** add `(yoinked_at DESC, source_type)` to chase this. `0004:6-13` measured that shape and the planner ignored it.

**Sample evidence rows** (for the 20-event list, not the count):

```sql
SELECT video_id, source_type,
       COALESCE(NULLIF(author, ''), channel) AS creator_hint,
       yoinked_at
FROM yoinks
WHERE deleted_at IS NULL
  AND yoinked_at >= :start AND yoinked_at < :end
ORDER BY yoinked_at DESC, video_id
LIMIT 20;
```

Uses `idx_yoinks_yoinked_at`. Same cost class as today's memory page (`index.py:1475-1478`).

### Q2 — A2 publication-time captures (labelled)

Publication time exists in SQL in two places. YouTube upload dates in sidecar files are **not** a third SQL clock.

**Q2a podcast, captured episodes**

```sql
SELECT y.source_type,
       COALESCE(NULLIF(y.author, ''), y.channel) AS creator_hint,
       COUNT(*) AS n
FROM podcast_episodes e
JOIN yoinks y ON y.video_id = e.yoink_video_id
WHERE y.deleted_at IS NULL
  AND e.yoink_video_id IS NOT NULL
  AND e.published_at >= :start AND e.published_at < :end
GROUP BY 1, 2;
```

`idx_podcast_episodes_published` serves the range. The join is `ON yoink_video_id` with **no** dedicated index (`0023:14-15` only helps when `feed_id` is already bound). Nested-loop from the published range into `yoinks` PK is fine while the range is small; a long publication window that hits thousands of episodes will look up `yoinks` by PK (cheap) after scanning the published index.

**548:** **< 5 ms**. **10,000 captured items** with several large feeds: still **< 20 ms** if the join stays PK lookups.

**Q2b subscribed observations (includes not-yet-captured)**

```sql
SELECT s.kind, s.source_id, COUNT(*) AS n
FROM source_items i
JOIN source_subscriptions s ON s.source_id = i.source_id
WHERE i.published_at_ms >= :start_ms AND i.published_at_ms < :end_ms
  AND i.state != 'deleted'
GROUP BY s.kind, s.source_id;
```

**Missing index:** `published_at_ms`. This is a full scan of `source_items` plus a PK join to `source_subscriptions`.

**548:** if `source_items` is ~1k–5k, forecast **< 10 ms**.
**10,000 items** with accumulated RSS identities (10k–100k `source_items`): forecast **20–200 ms** for a full scan of thin columns. Still inside 2 s. Becomes a problem only if the query also selects `metadata_json` (`0028:97`).

**Q2c YouTube upload_date in sidecar / `metadata_json` — do not price as a report query.** `json_extract(metadata_json, '$.upload_date')` is a full `yoinks` scan plus JSON parse of every blob. Opening `sidecar_path` is 548 or 10,000 file reads and will miss a 2 s deadline at 10k. If the item was observed through a subscription, use Q2b. If it was not, publication time is **unavailable**; say so. Do not backfill from `yoinked_at`.

### Q3 — A3 membership changes from the journal

**Header pass (counts and the 20-event list). Do not select JSON columns.**

```sql
SELECT apply_id, kind, operation_sequence, created_at,
       before_revision, after_revision, undo_of
FROM library_applies
WHERE created_at >= :start AND created_at < :end
ORDER BY operation_sequence;
```

**Missing index:** `created_at`. Access path today is a table scan, or a walk of `operation_sequence` with a residual time filter. Row count is operations, not items.

**548:** handful of rows. Forecast **< 1 ms** if JSON columns are not loaded.
**10,000:** still likely tens–hundreds of *rows*. Scan of scalar columns **< 5 ms**. The unique `operation_sequence` does not help a UTC window unless the implementation maps the window onto sequence bounds via `library_meta.last_operation_sequence` (wrong: sequence is not time).

**Item-change counts for those rows.** `receipt_json` is the apply receipt (`operation_key`, revisions, `delta_hash`, `no_change`, sequence) — **not** `changed_items` / `baseline_items`. Those live on expired `library_previews.summary_json`. Completeness therefore requires JSON:

```sql
SELECT a.apply_id, a.kind, a.operation_sequence, a.created_at,
       j.key AS video_id
FROM library_applies a,
     json_each(a.forward_json, '$.items') AS j
WHERE a.created_at >= :start AND a.created_at < :end;
```

`json_each` parses the whole `forward_json` document. Values under `$.items` are full membership rows including `evidence_json` (`library_work.py:857`, `0027:126`). SQLite still tokenizes those bytes even if the SELECT list only takes `j.key`.

| Apply shape | JSON bytes (order) | Parse forecast |
|---|---|---|
| Pin/undo of 1–3 memberships, small evidence | KiB | **< 1 ms** |
| Full reshelve of 548 items, evidence hundreds of bytes × 1–3 shelves | 0.5–3 MiB | **5–40 ms** |
| Full reshelve of 10,000 items, same evidence density | 10–40 MiB | **80–400 ms** per such apply |

One 10k-item apply in the window is still inside 2 s. Several full-library applies in one window, parsed in Python after `SELECT forward_json`, plus the process lock (`Index._lock`), is the first real miss risk. **Do not call `LibraryWorkService._snapshot` (`SELECT * FROM item_shelves`) to reconstruct history.**

For the displayed 20 events: run the header pass, then `json_each` only those 20 `apply_id`s (or the latest 20). Complete “how many items changed” over the interval either (a) parses every apply in the window, or (b) needs a thin integer on the apply row (see 0029).

### Q4 — A4 current shelf size; interval churn from the journal

**Current size (now, not a time series):**

```sql
SELECT s.shelf_id, COUNT(*) AS members
FROM item_shelves s
JOIN yoinks y ON y.video_id = s.video_id
WHERE y.deleted_at IS NULL
GROUP BY s.shelf_id;
```

PK `(video_id, shelf_id)` does not help `GROUP BY shelf_id`. Table scan of 548–30,000 memberships.

**548:** **< 2 ms**. **10,000:** 10k–30k thin rows, forecast **2–15 ms**. Select only `shelf_id, video_id`. `evidence_json` on `item_shelves` (`0027:126`) is the blob to avoid.

Join `shelf_nodes` on the active `version_id` (`library_one_active_taxonomy`) for names. Eleven v3 shelves fit in the display budget without paging.

**Interval churn:** Phase 2 definition (`PHASE2-CONTRACT-2026-09-04.md`; `library_work.py:916-940`): distinct previously assigned, nondeleted items whose shelf-set or primary changed, over the **then** baseline, not over today's `item_shelves`. For an interval that is not “this preview,” recompute from Q3's `json_each` of `forward_json` and `inverse_json` `$.items` (compare shelf-id sets and primary). Same JSON-cost class as Q3. Do not emit a churn percentage from current sizes.

### Q5 — A5 sources with activity and actual observation windows

```sql
SELECT s.source_id, s.kind, s.display_name, s.last_observed_ms,
       s.consent_state, s.archived,
       c.coverage, c.observed_count, c.truncated,
       c.last_poll_success_ms, c.last_poll_attempt_ms
FROM source_subscriptions s
LEFT JOIN source_detection_cursors c ON c.source_id = s.source_id
WHERE s.archived = 0
ORDER BY s.source_id;
```

Subscriptions are tens to low hundreds. PK joins. Forecast **< 2 ms** at both scales. This is the window the adapter **reported** (`coverage`, `observed_count`, `truncated`).

**Actual first/last observation per source** (do not run unbounded on every source in the same way `list_sources` N+1s `GROUP BY state`):

```sql
SELECT source_id,
       MIN(first_seen_ms) AS window_start_ms,
       MAX(last_seen_ms) AS window_end_ms,
       MIN(published_at_ms) AS published_min_ms,
       MAX(published_at_ms) AS published_max_ms,
       COUNT(*) AS observed_rows
FROM source_items
WHERE source_id = :source_id AND state != 'deleted'
GROUP BY source_id;
```

`source_items_ready` does not serve `MIN/MAX(published_at_ms)` or `MAX(last_seen_ms)`. Per-source scan of that source's items is fine (YouTube window ~15; a podcast feed may be hundreds). **Do not** `GROUP BY source_id` across 100k items while also selecting `metadata_json`. Cap displayed sources at the `list_sources` page (default 50, max 100; `source_subscriptions.py:319`, dashboard `limit: 100`).

**548:** **< 10 ms** for ~50 sources. **10,000 items / many feeds:** per-source aggregations for 50 displayed sources, forecast **< 50 ms**. A single `GROUP BY source_id` over 100k thin rows: **20–100 ms**.

### Q6 — A6 engagement in the interval

```sql
SELECT video_id, event_type, COUNT(*) AS n
FROM engagement_events
WHERE ts_utc >= :start AND ts_utc < :end
GROUP BY video_id, event_type;
```

Uses `idx_engagement_ts`. Cost tracks **events in the window**, not library size.

**548, quiet library:** **< 5 ms**. **10,000 items, years of dashboard use, 10^5–10^6 events, 7-day window:** range scan of that week's events, forecast **< 50 ms**. All-history `GROUP BY` on a million events: **100 ms–1 s** — still usually inside 2 s; the miss is reusing `Index.top_engaged` (`index.py:1179-1188`), which `SELECT DISTINCT video_id` then runs `engagement_signal` (all events for that id, Python decay) per id. That is O(distinct videos × events) and is **not** a Part A plan.

Join to `yoinks` only for the displayed sample, and only to read `deleted_at` / title. Events for deleted items remain (no FK).

### Q7 — invalidation (deleted or corrected inputs)

```sql
SELECT video_id, deleted_at
FROM yoinks
WHERE deleted_at IS NOT NULL
  AND deleted_at >= :start AND deleted_at < :end;
```

`idx_yoinks_deleted_at`. Cheap at both scales.

```sql
SELECT apply_id, undo_of, created_at, operation_sequence
FROM library_applies
WHERE undo_of IS NOT NULL
  AND created_at >= :start AND created_at < :end;
```

`undo_of` unique helps lookup by target apply, not by time. Residual on `created_at`. Tiny.

**No report cache.** The brief: a deleted or corrected input marks dependent reports stale and they recompute. Recompute-on-read is the cheap invalidation story at 10k if Q1–Q6 stay on thin columns. A materialized report table would itself be invalidated on every apply, delete, and undo — more writes than it saves.

### Q8 — provenance bindings (every number)

```sql
SELECT projection_revision, active_version_id, last_operation_sequence
FROM library_meta WHERE singleton = 1;

SELECT version_id, revision_hash, created_at
FROM shelf_versions WHERE status = 'active';

SELECT run_id, version_id, run_revision, state, created_at
FROM library_runs
WHERE created_at >= :start AND created_at < :end;
```

O(1) / tiny scans. Attach `query` name, interval, `projection_revision`, `revision_hash`, `last_operation_sequence` to every displayed count. Bytes: hundreds, not kilobytes.

## Expected cost, rolled up

Forecasts assume SSD-local SQLite, WAL, thin column lists, one process lock, no `ANALYZE` requirement.

| Packet | 548 items | 10,000 items | Inside 2 s? |
|---|---|---|---|
| Q1 counts + 20 capture events | < 5 ms | < 15 ms (7-day); < 20 ms all-history | yes |
| Q2a + Q2b publication counts | < 15 ms | < 200 ms if `source_items` is large and unindexed on `published_at_ms` | yes |
| Q2c sidecar / `metadata_json` upload_date | do not run | **miss** at 10k file reads | no — forbidden path |
| Q3 headers only | < 1 ms | < 5 ms | yes |
| Q3 `json_each` of one full-library apply | 5–40 ms | 80–400 ms | yes for one apply |
| Q3 Python `json.loads` of several 10k-item `forward_json`s under the lock | n/a | **risk** | maybe not |
| Q4 current sizes | < 2 ms | < 15 ms | yes |
| Q5 50 sources + per-source MIN/MAX | < 10 ms | < 50 ms | yes |
| Q6 7-day engagement | < 5 ms | < 50 ms typical; all-history on 10^6 events up to ~1 s | yes if not `top_engaged` |
| **Whole Part A dashboard packet, recommended plan** | **< 50 ms** | **< 300 ms** typical; **< 1 s** with one 10k-item apply parse | yes |
| Same packet if it `SELECT`s `forward_json` + `metadata_json` for every row | still ok at 548 | **can miss 2 s and blow the wire budget** | no |

Memory: a 40 MiB apply blob in RAM once is acceptable. Holding every historical full-library apply in RAM is not. Stream `json_each` per apply, or parse only the 20 displayed events plus integer counts.

## Missing indexes

None of these are required to meet 2 s at 548 items. They are the 10,000-item and large-`source_items` list. Do **not** add a report table.

| Priority | Proposed index | Why | Why not at 548 |
|---|---|---|---|
| P1 | `library_applies(created_at, operation_sequence)` | Q3 UTC window; today only `operation_sequence` is unique and it is not time | Few apply rows; scan is free |
| P1 | `source_items(published_at_ms)` | Q2b publication-time reports; no index exists (`0028:92` column, no `CREATE INDEX`) | Small `source_items` |
| P1 | `podcast_episodes(yoink_video_id)` | Q2a join to `yoinks`; `0023:14-15` does not lead with `yoink_video_id` | Range is small; PK lookups after published index |
| P2 | `source_items(video_id)` | Join observation → captured yoink; column `0028:107`, no index | Small |
| P2 | `source_items(source_id, last_seen_ms)` | Q5 observation-window `MAX(last_seen_ms)` | Per-source scans are tiny |
| P3 | `item_shelves(shelf_id)` | Q4 `GROUP BY shelf_id`; PK is `(video_id, shelf_id)` (`0027:128`) | 548–1.6k rows |
| P3 | covering `engagement_events(ts_utc, video_id, event_type)` | Q6 avoids table lookups if events reach 10^6 | `idx_engagement_ts` already exists (`0006:53`) |
| skip | compound `(yoinked_at DESC, source_type)` or `(yoinked_at DESC, author)` | `0004:6-13` EXPLAIN: not picked | already measured |
| skip | `source_subscriptions(last_observed_ms)` | table is tiny | full scan is the right plan |
| skip | `shelf_versions(created_at)` / `library_runs(created_at)` | tiny | full scan |

Partial `yoinks(yoinked_at) WHERE deleted_at IS NULL` would make Q1 covering. Not justified until EXPLAIN on a 10k copy shows a full scan; `0004` found the opposite at the then-current size.

## Migration 0029

The brief: no report table is reserved; if one is needed, **0029** must be named and justified.

**Part A does not need a report table.** Recompute-on-read matches invalidation (delete, undo, apply) and stays inside 2 s if JSON blobs are not loaded for counts.

**0029 is justified only as DDL for the P1 indexes above**, and only if run AZ's EXPLAIN on a 10k fixture shows a full scan that matters. Optional extra, still not a report table: `ALTER TABLE library_applies ADD COLUMN changed_item_count INTEGER` (and maybe `added_item_count` / `removed_item_count`) written at apply time from `len(forward["items"])`. That makes interval `SUM(changed_item_count)` O(applies) without `json_each`. Justify it only if a 10k-item `forward_json` parse misses the deadline in AZ tests.

Do not allocate 0029 to a cached `library_activity` snapshot. It would be stale on every `deleted_at` and every apply, and it would duplicate `library_applies`.

## Dashboard display budget

The dashboard is `assets/dashboard/index.html`, a single HTML app (`docs/surface-maps/dashboard-layout.md`). Phase 5 surface is **read-only, no new capability**. It should consume the same packet as `get_library_activity`, not a second unbounded dump.

### Bind to budgets that already exist

| Budget | Value | Source | Part A use |
|---|---|---|---|
| MCP / registry response | 65,536 UTF-8 bytes | `PHASE4-CONTRACT-2026-09-08.md:115` | Hard cap for `get_library_activity` and for the dashboard JSON if it is the same packet |
| Resource / brief-input body | 24,576 UTF-8 bytes | Phase 4 resource text; `get_library_brief_input` packet | Prefer this size for the dashboard fragment |
| Card | 8,192 UTF-8 bytes | Phase 4; `library_cards` librarian profile | Do not embed cards in the activity report |
| Service deadline | 2.0 s | Phase 4 | All Q1–Q8 plus serialization |
| `whats-new` events | 20; `days` 1–30, default 7; half-open UTC | `PHASE4-CONTRACT-2026-09-08.md:267` | Phase 5 must agree or supersede explicitly. **Agree:** complete counts, 20 evidence events, same interval grammar |
| Library page | 24 rows, infinite scroll | `assets/dashboard/index.html` `state.limit: 24` | Do **not** infinite-scroll 10,000 capture rows in the report. Link “open Library with this date filter” instead |
| Shelf page | 20 members | Phase 4 | Size table is per-shelf counts (11 v3 shelves), not member lists |
| `list_sources` | default 50, max 100, cursor | `source_subscriptions.py:319-320` | Observation-window rows |
| Engagement scores fetch | 24 | dashboard `/engagement/scores?limit=24` | Sample only; counts are complete |
| `list_work` | default 25 | `library_work.py:509` | Not a report reader (`list_work` reaps leases) |

### Frozen display packet (recommended)

One JSON object, schema version 1, no HTML, no `forward_json`, no `inverse_json`, no `evidence_json`, no `metadata_json`, no `packet_json`.

| Field | Completeness | Cap | Notes |
|---|---|---|---|
| Interval, clock label (`capture` vs `publication`), `as_of`, `projection_revision`, `taxonomy_revision_hash`, `last_operation_sequence`, query names | always | O(1) | Provenance. Hundreds of bytes |
| A1 counts by `source_type` × creator hint | complete integers | **top 20 rows + `other` remainder** | 10k items can have hundreds of authors. 20 matches `whats-new` / resource list density |
| A2 publication counts | complete integers, plus `unavailable_publication_time` count | same 20 + other | Labelled publication; never fill from capture |
| A3 apply headers in interval | complete `apply_count`, `items_changed` if cheap | **20 event rows** | Row: `apply_id`, `kind`, `operation_sequence`, `created_at`, `before_revision`, `after_revision`, `undo_of`, `item_change_count`, up to 5 `video_id`s |
| A4 shelf sizes | complete for the active taxonomy | all current shelves (11 now; page at 20 if a later taxonomy exceeds that) | Integers + `shelf_id` + name |
| A4 interval churn | complete numerator/denominator or explicit `uncomputed` if JSON parse skipped | O(1) plus up to 20 `changed_item_ids` | History from journal only |
| A5 sources | complete `source_count`; windows for the page | **50 default / 100 max**, cursor | `coverage`, `observed_count`, `truncated`, `window_start_ms`, `window_end_ms`, `published_min_ms`, `published_max_ms` |
| A6 engagement | complete event count in interval | **24** item samples (dashboard scores limit) | Not a value_score ranking |
| Time buckets for charts | complete | **≤ 30** buckets (match max `whats-new` days) or 24 hourly for a 1-day view | Pre-aggregate in SQL. No 10k DOM nodes |
| Deleted / undone in interval | complete counts | 20 ids | Invalidation evidence |

**Wire overflow:** drop whole sections in this order, never truncate a count: A6 samples, A3 extra `video_id`s, A5 page (keep cursor), A1/A2 creator rows beyond 20 (keep `other`), chart buckets (keep totals). Same “drop whole entries” rule as `resources/list` (`PHASE4-CONTRACT-2026-09-08.md:99-101`).

**DOM:** one report panel, not a new Library grid. Charts from the ≤30 bucket array (canvas/SVG). Creator-hint table 20 rows. Source cards reuse the existing Sources card density, not one DOM node per `source_items` row.

**Byte budget check (order):** 20 events × ~200 bytes + 20 creator rows × ~80 + 11 shelf sizes × ~60 + 50 source windows × ~250 + provenance ~400 ≈ **20 KiB**, under 24,576. Headroom is the `other` remainder and cursors, not more rows. If AZ adds Librarian cards, omit them; cards alone are 8,192 each and will blow both budgets.

**`whats-new` agreement:** counts and 20 events for captures, recorded shelf revisions (`shelf_versions` / `library_runs` in the interval), and applied membership changes. Identify event kind and history coverage. Never infer old changes from today's `item_shelves`. Phase 5 may add A2/A5/A6 fields inside the same 65,536 cap; it must not raise the event list without a recorded amendment.

## What run AZ must not do (cost)

1. `SELECT *` / `SELECT forward_json, inverse_json` for the dashboard or MCP packet.
2. `LibraryWorkService._snapshot` or `SELECT * FROM item_shelves` to build a time series.
3. `Index.top_engaged` for A6.
4. Sidecar walks or `json_extract` on every `yoinks.metadata_json` for publication time.
5. Unbounded creator-hint or source-item lists in HTML.
6. A cache table that survives `deleted_at`, undo, or apply.
7. Calling `list_work` (lease maintenance) from a report reader.
8. Treating YouTube's 15-entry Atom window or the podcast parser's first 50 entries as a complete back catalog (`PHASE3-ADAPTER-LIMITS-2026-09-07.md`, `PHASE3-CONTRACT-2026-09-07.md:119-126`).

## Ambiguities this audit does not freeze

Astra's contract owns these; they change cost only at the edges:

1. Whether A6 engagement is in Part A or deferred with term bursts. The brief named the table, so the query is priced. If deferred, drop Q6.
2. Exact creator-hint merge rules (Part A: `author` else `channel`, no dedup). Dedup would be a later, more expensive pass.
3. Whether `get_library_activity` is allowed to return `items_changed: null` when it skips JSON parse, vs always parsing.
4. Clock conversion: `library_applies.created_at` is epoch-ms text (`library_work.py:224,238-241`); `yoinks.yoinked_at` is local-naive ISO (`index.py:99-100`); `source_items` clocks are INTEGER ms; `podcast_episodes.published_at` is RSS date text. Three encodings, one half-open UTC interval.
5. Whether 0029 lands in AZ or waits for a measured 10k EXPLAIN.

## Verdict

Part A is cheap at 548 items with the indexes that already exist. It stays cheap at 10,000 items if the implementation aggregates thin columns, samples 20 events, and does not ship journal JSON to the dashboard. The only structural gaps are **no `library_applies(created_at)` index**, **no `source_items(published_at_ms)` index**, **no `podcast_episodes(yoink_video_id)` index**, and the **JSON size of a full-library apply**. Display must reuse Phase 4's 65,536 / 20-event / 2 s envelope and the dashboard's 24-row page size, not invent a 10,000-row report view.
