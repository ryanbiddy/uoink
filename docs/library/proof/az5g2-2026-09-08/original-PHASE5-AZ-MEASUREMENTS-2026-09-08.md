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
| **Construction Time** | ~800–950 ms | ~350–430 ms | 2,000.00 ms (2.0 s deadline; includes reader query execution, aggregation and internal serialization) |
| **Serialization Time** | ~3.3–4.0 ms | ~0.3–0.6 ms | Sub-deadline; raw dictionary json.dumps serialization, not transport serialization |
| **Combined Query Execution** | Plans confirmed | Plans confirmed | Plans confirmed index scans (Q1: `sqlite_autoindex_yoinks_1`, Q3: `sqlite_autoindex_library_applies_3`); individual query times are not isolated from total construction time |
| **Peak Heap Memory (tracemalloc)** | 4,031.1 KiB (~3.94 MiB) | 61,131.7 KiB (~59.70 MiB) | Traced Python heap peak under tracemalloc in separate passes; not process RSS (measures Python heap allocations only) |
| **Wire Response Payload** | 58,738 bytes | 58,640 bytes | 65,536 bytes (64 KiB envelope); raw reader JSON payload bytes |
| **Actual Transport Wire Payload (stdio adapter)** | 65,252 bytes | 65,095 bytes | 65,536 bytes (64 KiB envelope); wrapped JSON-RPC response through actual shipped MCP stdio handler |
| **Combined Journal Deltas** | 209.6 KiB (214,596 bytes) | 2,760,054 bytes (~2.63 MiB) | 67,108,864 bytes (64 MiB); AZ-5c (BA-05) re-seeds both fixtures with complete service-schema membership rows (previously 74,856 and 1,050,054 bytes with abbreviated rows); sizes computed from the fixture serialization, to be re-observed by the AZ-5g regeneration |
| **Status** | Passed | Passed | Within 64 KiB wire budget; raw JSON (58,738 / 58,640 bytes) and transport wire bytes (65,252 / 65,095 bytes) both fit within 65,536 bytes; exceeds 24,576-byte dashboard target |

### Observations on Scaling
- At 548 items, full breakdown rows (joint hints, creator hints, shelf rows) fit within the 64 KiB response limit without pruning (raw JSON is 58,738 bytes; actual transport wire payload through MCP stdio adapter is 65,252 bytes).
- At 10,000 items, row shedding did not occur: all initial display pages (20 event rows, 20 creator rows, 20 joint creator rows, 1 source row, 1 shelf row) fit within the 65,536-byte wire budget (raw JSON is 58,640 bytes; actual transport wire payload through MCP stdio adapter is 65,095 bytes), so no display arrays were removed.
- In the primary 548-item and 10,000-item benchmarks, the baseline replay path was skipped because the requested interval (`2026-09-01T00:00:00.000Z` to `2026-09-02T00:00:00.000Z`) preceded the first apply (`2026-09-01T10:00:00.000Z`), producing `baseline_reason: ["interval_precedes_first_apply"]`. Baseline replay was measured separately with an interval covering the apply (see Section 1.1).
- Construction at 10,000 items completed in ~350–430 ms, well below the 2.0-second service deadline. The 548 timing includes tracemalloc profiling overhead whereas the main 10k timing was measured without tracing (a separate 10k tracing pass recorded ~61 MiB heap peak); tracemalloc measures Python heap allocations, not total process memory / RSS.
- The 24,576-byte dashboard target is missed by the primary packets (58,738 / 58,640 bytes raw JSON; 65,252 / 65,095 bytes wire payload).

---

## 1.1 Measurements of Omitted Paths

The extended test suite in `tests/test_library_analysis_fixtures.py::test_activity_cost_548_and_10000` measures paths omitted from the initial report:

| Path / Scenario | Fixture Dimensions | Observed Metric | Result & Interpretation |
| :--- | :--- | :--- | :--- |
| **Proved Baseline Replay** | 548 items, 1 apply at 10:00:00Z, interval 10:00:00Z–24:00:00Z | ~35–45 ms construction | Proved: `coverage_status = "journal_complete"`, `reasons = []`. Baseline proved across interval covering first apply. |
| **70 MiB Journal Refusal** | 1 item, 70 MiB forward/inverse deltas | ~50–95 ms refusal | `ok: False`, `error.code = "resource_too_large"`. Bounded refusal before JSON materialization. |
| **Deadline Expiry Refusal** | 548 items, expired monotonic clock | ~0.1–0.2 ms refusal | `ok: False`, `error.code = "deadline_exceeded"`, `retryable: True`. Immediate abort on expired deadline. |
| **Transport Serialization** | 548-item report packet in MCP stdio envelope | ~0.4–0.6 ms, 65,263 bytes | Full MCP transport protocol serialization with trusted document fence and text encapsulation through actual stdio adapter (65,252 bytes JSON-RPC wire payload). |
| **Three Memberships / Item** | 548 items, 3 shelves each (1,644 memberships) | ~40–50 ms construction | `ok: True`. Handles dense multi-shelf memberships efficiently (64,735 bytes transport wire). |
| **Multi-Operation Journal** | 50 items, 10 consecutive applied operations | ~5.5 ms construction | Proved: `coverage_status = "journal_complete"`, `reasons = []`. Replays sequence of 10 applies across interval covering first apply to prove state progression (35,404 bytes transport wire). |
| **100k-Observation Scale** | 1 item, 100,000 source item observations | ~750–860 ms construction | `ok: True`. Full scan across 100k observation rows completes well under the 2.0 s deadline (27,862 bytes transport wire). |


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
   - If `SUM(LENGTH(CAST(forward_json AS BLOB)) + LENGTH(CAST(inverse_json AS BLOB)))` across `library_applies` exceeds 67,108,864 bytes, `get_library_activity` refuses with `error.code = "resource_too_large"`.
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
   - **Active Read Cap:** Enforced via shared `library_resources` process guard with a limit of 2 concurrent reads. Excess concurrent requests receive `rate_limited` (`retryable: true`).
   - **Rate Limiter:** Rolling 60-second window capped at 60 admissions. Exceeding 60 calls/min raises `RateLimitExceeded` and returns `rate_limited`.
   - *Verification note (marked limitation):* `test_activity_read_has_no_side_effects` checks `total_changes` only and does not verify concurrent load or rate limit enforcement.

5. **Read Boundary Mutation Detection:**
   - Compares `PRAGMA data_version` and `total_changes` at the start and end of read operations.
   - If concurrent writes modify the database during read processing, the handler refuses with `error.code = "stale_report"`.
   - *Verification note (marked limitation):* `test_gate4_deletion_invalidates_derived_report` tests sequential deletion between requests and does not prove concurrent snapshot isolation during active read transactions.
