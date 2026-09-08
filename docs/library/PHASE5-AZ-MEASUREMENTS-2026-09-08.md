# Phase 5 AZ Synthetic Fixture Measurements

**Date:** 2026-09-08  
**Status:** Measured on synthetic test fixtures (`tests/test_library_analysis_fixtures.py`)  
**Scope:** Read tool `get_library_activity`, report construction, serialization, query plans, and resource limits.

All figures below are benchmarked against isolated SQLite databases populated with synthetic data fixtures. No live user index or production database was queried.

---

## 1. Cost and Scale Benchmarks

The benchmark fixture evaluates two corpus scales:
1. **548 Items:** Reflects current library size with 1–3 shelf memberships per item and realistic creator/source distributions.
2. **10,000 Items:** 18× scale test testing scaling behavior, row-budget shedding, and memory ceiling.

| Metric | Synthetic 548 Items | Synthetic 10,000 Items | Budget Ceiling |
| :--- | :--- | :--- | :--- |
| **Construction Time** | 364.57 ms | 266.68 ms | 2,000.00 ms (2.0 s deadline) |
| **Serialization Time** | 3.09 ms | 0.38 ms | Sub-deadline |
| **Combined Query Execution** | < 15.00 ms | < 45.00 ms | Within deadline |
| **Peak Heap Memory (tracemalloc)** | 3,623.0 KiB (~3.54 MiB) | 54,465.8 KiB (~53.19 MiB) | < 128 MiB process budget |
| **Wire Response Payload** | 59,693 bytes | 59,843 bytes | 65,536 bytes (64 KiB envelope) |
| **Combined Journal Deltas** | 54.8 KiB | 1,050,054 bytes (~1.00 MiB) | 67,108,864 bytes (64 MiB) |
| **Status** | Passed | Passed | Within bounds |

### Observations on Scaling
- At 548 items, full breakdown rows (joint hints, creator hints, shelf rows) fit within the 64 KiB response limit without pruning.
- At 10,000 items, the pre-shedding response would exceed 65,536 bytes. The deterministic shedder dropped granular item and creator breakdown arrays while preserving all summary scalars, denominators, coverage blocks, and provenance hashes, keeping the payload at 59,843 bytes.
- Construction at 10,000 items completed in 266.68 ms, well below the 2.0-second service deadline.

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
