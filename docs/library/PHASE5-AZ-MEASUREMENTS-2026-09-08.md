# Phase 5 AZ Synthetic Fixture Measurements

**Date:** 2026-09-08  
**Status:** Measured on synthetic test fixtures (`tests/test_library_analysis_fixtures.py`)  
**Scope:** Read tool `get_library_activity`, report construction, serialization, query plans, and resource limits.

All figures below are benchmarked against isolated SQLite databases populated with synthetic data fixtures. No live user index or production database was queried.

---

## 1. Cost and Scale Benchmarks

The benchmark fixture evaluates two corpus scales:
1. **548 Items:** Reflects current library size with 1–2 shelf memberships per item (822 total membership rows in synthetic fixture) and realistic creator/source distributions.
2. **10,000 Items:** 18× scale test testing scaling behavior, row-budget shedding, and memory ceiling (10,000 membership rows).

| Metric | Synthetic 548 Items | Synthetic 10,000 Items | Budget Ceiling / Interpretation |
| :--- | :--- | :--- | :--- |
| **Construction Time** | 364.57 ms (rerun ~522 ms) | 266.68 ms (rerun ~300 ms) | 2,000.00 ms (2.0 s deadline; includes reader query execution, aggregation and internal serialization) |
| **Serialization Time** | 3.09 ms | 0.38 ms | Sub-deadline; raw dictionary json.dumps serialization, not transport serialization |
| **Combined Query Execution** | < 15.00 ms | < 45.00 ms | Query plans confirmed index scans; individual queries not isolated from construction |
| **Peak Heap Memory (tracemalloc)** | 3,623.0 KiB (~3.54 MiB) | 54,465.8 KiB (~53.19 MiB) | Traced Python heap peak under tracemalloc in separate passes; not process RSS |
| **Wire Response Payload** | 59,693 bytes | 59,843 bytes | 65,536 bytes (64 KiB envelope) |
| **Combined Journal Deltas** | 73.1 KiB | 1,050,054 bytes (~1.00 MiB) | 67,108,864 bytes (64 MiB); 548 journal corrected from 54.8 KiB (74,856 bytes) |
| **Status** | Passed | Passed | Within bounds |

### Observations on Scaling
- At 548 items, full breakdown rows (joint hints, creator hints, shelf rows) fit within the 64 KiB response limit without pruning.
- At 10,000 items, row shedding did not occur: all initial display pages (20 event rows, 20 creator rows, 20 joint creator rows, 1 source row, 1 shelf row) fit within the 65,536-byte wire budget (payload is 59,843 bytes / 61,383 bytes with current serializer), so no display arrays were removed.
- In the primary 548-item and 10,000-item benchmarks, the baseline replay path was skipped because the requested interval (`2026-09-01T00:00:00.000Z` to `2026-09-02T00:00:00.000Z`) preceded the first apply (`2026-09-01T10:00:00.000Z`), producing `baseline_reason: ["interval_precedes_first_apply"]`. Baseline replay was measured separately with an interval covering the apply (see Section 1.1).
- Construction at 10,000 items completed in ~300 ms, well below the 2.0-second service deadline. The 548 timing includes tracemalloc profiling overhead whereas the main 10k timing was measured without tracing (a separate 10k tracing pass recorded ~54–56 MiB heap peak); tracemalloc measures Python heap allocations, not total process memory / RSS.

---

## 1.1 Measurements of Omitted Paths

The extended test suite in `tests/test_library_analysis_fixtures.py::test_activity_cost_548_and_10000` measures paths omitted from the initial report:

| Path / Scenario | Fixture Dimensions | Observed Metric | Result & Interpretation |
| :--- | :--- | :--- | :--- |
| **Proved Baseline Replay** | 548 items, 1 apply at 10:00:00Z, interval 10:00:00Z–24:00:00Z | 19.30 ms construction | Proved: `coverage_status = "journal_complete"`, `reasons = []`. Baseline proved across interval covering first apply. |
| **70 MiB Journal Refusal** | 1 item, 70 MiB forward/inverse deltas | 48.55 ms refusal | `ok: False`, `error.code = "resource_too_large"`. Bounded refusal before JSON materialization. |
| **Deadline Expiry Refusal** | 548 items, expired monotonic clock | 0.90 ms refusal | `ok: False`, `error.code = "deadline_exceeded"`, `retryable: True`. Immediate abort on expired deadline. |
| **Transport Serialization** | 548-item report packet in MCP stdio envelope | 0.72 ms, 67,697 bytes | Measures full MCP transport protocol serialization with trusted document fence and text encapsulation. |
| **Three Memberships / Item** | 548 items, 3 shelves each (1,644 memberships) | 23.29 ms construction | `ok: True`. Handles dense multi-shelf memberships efficiently. |
| **Multi-Operation Journal** | 50 items, 10 consecutive applied operations | 4.08 ms construction | `ok: True`. Replays sequence of 10 applies to verify state progression across interval. |
| **100k-Observation Scale** | 1 item, 100,000 source item observations | 563.23 ms construction | `ok: True`. Full scan across 100k observation rows completes well under the 2.0 s deadline. |

---

## 2. SQLite Query Plans

Queries run read-only against standard migrations (0001–0028) without creating migration 0029 or new secondary indexes.

### Q1: Yoinks Retrieval
```sql
EXPLAIN QUERY PLAN
SELECT video_id, source_type, author, channel, platform, yoinked_at, deleted_at
FROM yoinks
ORDER BY video_id ASC;
```
**Execution Plan:**
```
SCAN yoinks USING INDEX sqlite_autoindex_yoinks_1
```
- Uses the implicit primary key index on `video_id`.
- Emits rows pre-sorted in ascending order. No temporary B-tree sorting table is created in memory or on disk.

### Q3: Library Applies Journal Retrieval
```sql
EXPLAIN QUERY PLAN
SELECT apply_id, operation_key, kind, before_revision, after_revision, operation_sequence,
       authoritative_record_hash, forward_json, inverse_json, undo_of, created_at
FROM library_applies
ORDER BY operation_sequence ASC;
```
**Execution Plan:**
```
SCAN library_applies USING INDEX sqlite_autoindex_library_applies_3
```
- Uses the unique constraint index on `operation_sequence`.
- Scans strictly in operation sequence order without intermediate sorting buffers.

---

## 3. Refusal Limits and Budget Enforcement

The reader guards system availability through five explicit gates:

1. **64 MiB Journal Delta Limit:**
   - Evaluated before JSON parsing.
   - If `SUM(LENGTH(forward_json) + LENGTH(inverse_json))` across `library_applies` exceeds 67,108,864 bytes, `get_library_activity` refuses with `error.code = "resource_too_large"`.
   - Verified in `test_activity_deadline_and_work_bounds` with a 70 MiB synthetic payload.

2. **2.0-Second Service Deadline:**
   - Checked at entry and before returning responses.
   - If execution time exceeds 2.0 seconds, the handler aborts and returns `error.code = "deadline_exceeded"`, `retryable: true`.
   - Verified in `test_activity_deadline_and_work_bounds` using injected clock shifts.

3. **64 KiB Wire Budget Envelope:**
   - Maximum output size is 65,536 bytes.
   - If the initial JSON serialization exceeds 65,536 bytes, the response sheds optional rows in order:
     1. Event rows (`events.rows`)
     2. Joint creator rows (`items.by_type_creator_hint`)
     3. Creator rows (`items.by_creator_hint`)
     4. Source detail rows (`sources.details`)
     5. Shelf breakdown rows (`shelf_activity.shelves`)
   - If mandatory summary fields alone exceed 65,536 bytes, the handler refuses with `resource_too_large`.
   - Verified in `test_activity_wire_budget_and_untrusted_labels`.

4. **Concurrency and Rate Limiting:**
   - **Active Read Cap:** Enforced via `_active_reads_sem` with a limit of 2 concurrent reads. Excess concurrent requests receive `rate_limited` (`retryable: true`).
   - **Rate Limiter:** Rolling 60-second window capped at 60 admissions. Exceeding 60 calls/min raises `RateLimitExceeded` and returns `rate_limited`.
   - Verified in `test_activity_read_has_no_side_effects`.

5. **Read Boundary Mutation Detection:**
   - Compares `PRAGMA data_version` and `total_changes` at the start and end of read operations.
   - If concurrent writes modify the database during read processing, the handler refuses with `error.code = "stale_report"`.
   - Verified in `test_gate4_deletion_invalidates_derived_report`.
