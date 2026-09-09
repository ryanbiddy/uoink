# Phase 5 AZ Synthetic Fixture Measurements

- **Date:** 2026-09-08
- **Status:** Measured on synthetic test fixtures (`tests/test_library_analysis_fixtures.py`) after AZ-5h2
- **Scope:** Read tool `get_library_activity`, report construction, serialization, query plans, resource limits, and the actual shipped stdio entry (`bounded_stdio_server` / `run_bounded_stdio_async`).
- **Source commit:** `d1d5fb8b3eca802f14ae53de3d6562df30b9129d`
- **Source tree:** `079170c1f70f4addcfaed15006a51f751ae60f67`
- **Harness:** `scripts/measure_phase5_az5g2.py`
- **Proof:** `docs/library/proof/az5g2-2026-09-08/`

All figures below are benchmarked against isolated SQLite databases populated with synthetic data fixtures. No live user index or production database was queried. Tracing passes are labelled separately and are not compared with untraced times as equivalent. Returned display-array lengths are samples, not population totals.

---

## 1. Cost and Scale Benchmarks

The benchmark fixture evaluates two corpus scales:
1. **548 Items:** Reflects current library size with 1–2 shelf memberships per item (822 total membership rows in synthetic fixture) and realistic creator/source distributions.
2. **10,000 Items:** 18× scale test testing scaling behavior, row-budget shedding, and memory ceiling (10,000 membership rows).

| Metric | Synthetic 548 Items | Synthetic 10,000 Items | Budget Ceiling / Interpretation |
| :--- | :--- | :--- | :--- |
| **Construction Time** | 61.22 ms untraced / 1004.96 ms traced diagnostic | 641.30 ms untraced / 16057.02 ms traced diagnostic | 2,000.00 ms fixed service deadline. Traced times include tracemalloc and are not equivalent to untraced times. 10k traced pass uses a 30.0 s diagnostic deadline. |
| **Serialization Time** | 0.38 ms | 0.44 ms | Sub-deadline; raw dictionary json.dumps serialization, not transport serialization |
| **Combined Query Execution** | Plans measured on this 548 fixture | Plans measured on this 10k fixture | Q1: `SCAN yoinks USING INDEX sqlite_autoindex_yoinks_1`; Q3: `SCAN library_applies USING INDEX sqlite_autoindex_library_applies_3`; individual query times are not isolated from total construction time |
| **Peak Heap Memory (tracemalloc)** | 5253.9 KiB | 78388.7 KiB | Traced Python heap peak under tracemalloc in separately labelled diagnostic passes; not process RSS. 10k heap used a relaxed 30.0 s diagnostic deadline. |
| **Wire Response Payload** | 58,035 bytes | 57,968 bytes | 65,536 bytes (64 KiB envelope); raw reader JSON payload bytes (legacy table label 'Wire Response Payload' verified by test; distinguished from actual transport wire bytes below) |
| **Actual Transport Wire Payload (stdio adapter)** | 64,732 bytes | 64,601 bytes | 65,536 bytes completed JSON-RPC UTF-8 before newline, measured through the actual shipped `bounded_stdio_server` writer (`JSONRPCMessage.model_dump_json`); trailing newline is retained in the proof frames and is not counted in this row |
| **Combined Journal Deltas** | 209.6 KiB (214,596 bytes) | 2,760,054 bytes (~2.63 MiB) | 67,108,864 bytes (64 MiB) fixed journal gate; sizes from `SUM(LENGTH(CAST(forward_json AS BLOB))+LENGTH(CAST(inverse_json AS BLOB)))` on the live fixture databases |
| **Status** | Measured | Measured | Within the 64 KiB completed-frame cap; raw JSON and shipped JSON-RPC both fit 65,536 bytes; exceeds the 24,576-byte dashboard target (a target, not an acceptance-blocking hard limit) |

Handler-only serialization of the same captured packets (not the shipped entry; `JSONRPCResponse` id=1, no newline): 64,732 / 64,601 bytes.

### Observations on Scaling
- At 548 items, row shedding occurred to satisfy the 64 KiB wire budget: events returned 0 of total 550 (omitted 550; events.total metric=550); joint returned 12 of total 20 (omitted 8); creators returned 20 of total 20 (omitted 0); sources returned 1 of total 1 (omitted 0); shelves returned 2 of total 2 (omitted 0). Raw JSON is 58,035 bytes; shipped stdio JSON-RPC is 64,732 bytes (`isError`=False).
- At 10,000 items, row shedding occurred: events returned 0 of total 10002 (omitted 10002; events.total metric=10002); joint returned 13 of total 50 (omitted 37); creators returned 20 of total 50 (omitted 30); sources returned 1 of total 1 (omitted 0); shelves returned 1 of total 1 (omitted 0). Raw JSON is 57,968 bytes; shipped stdio JSON-RPC is 64,601 bytes (`isError`=False).
- Baseline replay was not skipped on the primary 548-item and 10,000-item intervals. `_execute_activity` populated replay projection state (observed=True) before returning `coverage_status=partial` with reasons `['interval_precedes_first_apply']`. The interval `2026-09-01T00:00:00.000Z`–`2026-09-02T00:00:00.000Z` precedes the first apply at `2026-09-01T10:00:00.000Z`. A separate interval covering that apply proved `journal_complete` with empty reasons.
- Untraced 548 construction completed in 61.22 ms. The cost fixture's first 548 call is a traced pass (1004.96 ms diagnostic heap including tracemalloc). Untraced 10,000-item construction completed in 641.30 ms. A separate 10k tracing pass with a 30.0 s diagnostic deadline recorded 78388.7 KiB peak Python heap. Tracemalloc measures Python heap allocations, not total process memory / RSS.
- The 24,576-byte dashboard target is missed by the primary packets (58,035 / 57,968 bytes raw JSON; 64,732 / 64,601 bytes shipped JSON-RPC). That target is aspirational, not a fixed acceptance-blocking limit. The fixed enforced envelope is 65,536 completed UTF-8 bytes.

Population dimensions (not display-array lengths):

| Fixture | items | memberships | observations | applies | journal bytes | items.total metric |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| 548 primary | 548 | 822 | 548 | 1 | 214,596 | 548 |
| 10,000 primary | 10000 | 10000 | 10000 | 1 | 2,760,054 | 10000 |

---

## 1.1 Measurements of Omitted Paths

The extended test suite in `tests/test_library_analysis_fixtures.py::test_activity_cost_548_and_10000` measures paths omitted from the initial report. Extra shipped-entry and tracing passes are labelled by scope.

| Path / Scenario | Fixture Dimensions | Observed Metric | Result & Interpretation |
| :--- | :--- | :--- | :--- |
| **Proved Baseline Replay** | 548 items, 1 apply, interval 10:00:00Z–24:00:00Z | 68.64 ms untraced construction, 57,894 bytes raw JSON | Proved: `coverage_status = "journal_complete"`, `reasons = []`. events returned 0 of total 549 (omitted 549; events.total metric=549); joint returned 11 of total 20 (omitted 9); creators returned 20 of total 20 (omitted 0); sources returned 1 of total 1 (omitted 0); shelves returned 2 of total 2 (omitted 0). Shipped JSON-RPC 64,595 bytes. |
| **70 MiB Journal Refusal** | 1 item, 73,400,398 bytes forward/inverse deltas | 52.03 ms untraced refusal, 221 bytes raw JSON | `ok: False`, `error.code = "resource_too_large"`, `retryable: False`. Bounded refusal before JSON materialization. Shipped entry frame 329 bytes, `isError`=True. Diagnostic traced heap 18.7 KiB (not a normal timing result). |
| **Deadline Expiry Refusal** | 548 items, expired monotonic clock | 0.10 ms reader refusal, 190 bytes raw JSON | `ok: False`, `error.code = "deadline_exceeded"`, `retryable: True`. Message: `Service deadline exceeded before lock acquisition`. Diagnostic traced heap 5.9 KiB. A separately labelled shipped-entry inbound-expiry refusal is retained in the proof (`shipped_expired_inbound`). |
| **Transport Serialization** | 548-item report packet in hand-built envelope | 0.47 ms, 64,743 bytes | Hand-built JSON-RPC synthetic envelope with preface and document fences; isolates serialization timing and does not invoke the stdio handler. |
| **Actual shipped stdio entry** | 548-item live reader through `bounded_stdio_server` | 69.16 ms session (includes initialize + reader + writer), 64,732 bytes JSON-RPC | Actual shipped transport: SDK `JSONRPCMessage.model_dump_json`, completed-frame cap, trailing newline retained in proof. `isError`=False. This is a harness transcript, not a real-client log. |
| **Three Memberships / Item** | 548 items, 1644 memberships | 67.85 ms untraced, 57,671 bytes raw JSON | `ok: True`. events returned 0 of total 550 (omitted 550; events.total metric=550); joint returned 10 of total 20 (omitted 10); creators returned 20 of total 20 (omitted 0); sources returned 1 of total 1 (omitted 0); shelves returned 3 of total 3 (omitted 0). Journal 405,026 bytes. Shipped JSON-RPC 64,362 bytes. |
| **Multi-Operation Journal** | 50 items, 10 consecutive applied operations | 12.27 ms untraced, 34,917 bytes raw JSON | Proved: `coverage_status = "journal_complete"`, `reasons = []`. events returned 20 of total 60 (omitted 40; events.total metric=60); joint returned 1 of total 1 (omitted 0); creators returned 1 of total 1 (omitted 0); sources returned 1 of total 1 (omitted 0); shelves returned 2 of total 2 (omitted 0). Journal 234,590 bytes. Shipped JSON-RPC 39,378 bytes. |
| **100k-Observation Scale** | 1 item, 100,000 source item observations | 1127.19 ms untraced, 28,790 bytes raw JSON | `ok: True`. Coverage `no_history`. events returned 1 of total 1 (omitted 0; events.total metric=1); joint returned 1 of total 1 (omitted 0); creators returned 1 of total 1 (omitted 0); sources returned 2 of total 2 (omitted 0); shelves returned 0 of total 0 (omitted 0). No journal. Shipped JSON-RPC 32,351 bytes. |

---

## 2. SQLite Query Plans

Queries run read-only against standard migrations (0001–0028) without creating migration 0029 or new secondary indexes. Plans below were measured on the actual 548-item cost fixture; the 10,000-item plans are retained in the proof JSON.

### Q1: Yoinks Retrieval
```sql
SELECT video_id, source_type, author, channel, platform, yoinked_at, deleted_at FROM yoinks ORDER BY video_id ASC
```
**Execution Plan:**
```
SCAN yoinks USING INDEX sqlite_autoindex_yoinks_1
```
- Measured on the 548-item fixture, not inferred from an empty database.
- Individual query times were not isolated from total construction time.

### Q3: Library Applies Journal Retrieval
```sql
SELECT apply_id, operation_key, kind, before_revision, after_revision, operation_sequence, authoritative_record_hash, forward_json, inverse_json, undo_of, created_at FROM library_applies ORDER BY operation_sequence ASC
```
**Execution Plan:**
```
SCAN library_applies USING INDEX sqlite_autoindex_library_applies_3
```
- Measured on the 548-item fixture.
- Individual query times were not isolated from total construction time.

---

## 3. Refusal Limits and Budget Enforcement

Fixed implemented limits (not the same thing as a measured guarantee that every untested path meets them):

1. **64 MiB Journal Delta Limit (fixed):**
   - Evaluated before JSON parsing.
   - If `SUM(LENGTH(CAST(forward_json AS BLOB)) + LENGTH(CAST(inverse_json AS BLOB)))` across `library_applies` exceeds 67,108,864 bytes, `get_library_activity` refuses with `error.code = "resource_too_large"`.
   - Measured here with a 73,400,398-byte synthetic payload; refusal envelope 221 raw bytes.

2. **2.0-Second Service Deadline (fixed):**
   - Checked at entry and through the shipped writer's final `JSONRPCMessage.model_dump_json`.
   - AZ-5h2 uses the original inbound `admitted_at` when a transport scope is bound.
   - Injected expired-clock reader refusal measured at 0.10 ms, 190 raw bytes, `retryable: True`.
   - This is not a blocked-lock measurement; remaining-budget SQLite waits are covered by AZ-5h2 tests, not by this timing row.

3. **64 KiB Completed-Frame Envelope (fixed):**
   - Maximum completed outbound UTF-8 JSON-RPC size is 65,536 bytes before the terminating newline.
   - Display-row shedding order: events, joint creator hints, creator hints, source details, shelf rows.
   - If mandatory summary fields alone exceed the cap, the handler refuses with `resource_too_large`.
   - Primary packets shed optional rows and remain under the cap, as measured.

4. **Concurrency and Rate Limiting (fixed):**
   - Active read cap 2; rolling 60-second window of 60 admissions.
   - *Verification note (marked limitation):* `test_activity_read_has_no_side_effects` checks `total_changes` only and does not verify concurrent load or rate limit enforcement. This measurement run does not claim an unmeasured concurrency path passes.

5. **Read Boundary Mutation Detection (fixed):**
   - Compares `PRAGMA data_version` and `total_changes`.
   - *Verification note (marked limitation):* sequential deletion tests do not prove concurrent snapshot isolation during an active read. Unmeasured here.

---

## 4. Provenance and scope labels

- Git commit `d1d5fb8b3eca802f14ae53de3d6562df30b9129d`, tree `079170c1f70f4addcfaed15006a51f751ae60f67`.
- Interpreter `3.14.6 (tags/v3.14.6:c63aec6, Jun 10 2026, 10:26:10) [MSC v.1944 64 bit (AMD64)]`; installed mcp `1.28.1`; pin `mcp==1.27.1`.
- `uoink_mcp.mcp.run_stdio_async is uoink_mcp.run_bounded_stdio_async` = `True`.
- Pre-refresh document archive SHA-256 `4745bd1db6efcd14e9b0aeb930ba0193981e4024b0ec91f4ad27a1f96da20ea0` (git blob `c3c8e1b72d3354bdfe85b1ce881e1e765aa28ea0`).
- Rejected AZ-5g Gemini partial is not this record: `docs/library/patches/az5g-gemini-partial-rejected-2026-09-08.patch` SHA-256 `88a91ef8f62839f7f180683bcc03dc17105d6771d37b597fc6dec56bc91148b8`.
- Complete packets and frames live under `docs/library/proof/az5g2-2026-09-08/packets/`.
- Handler-only dumps, hand-built envelopes, and shipped frames are separate files with distinct scope labels.
- Normal construction times are untraced. Heap figures are diagnostic tracing only.
- A handler transcript is not a real MCP client log. No model, live index, or port 5179 was used.
