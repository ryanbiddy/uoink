# Local Model Benchmark Report (LM Studio)

**Date:** 2026-09-04  
**Target Endpoint:** `http://localhost:1235/v1`  
**Target Model:** `qwen3.8-27b`  
**Evaluation Set:** `docs/library/gold-set-2026-09-04.json` (60 items)  
**Prompt Spec:** `scripts/librarian/prompts/assign.md`  
**Harness:** `scripts/librarian/bench_local.py`  
**Benchmark Status:** `not run: endpoint down`

---

## 1. Executive Status

The local LM Studio endpoint at `http://localhost:1235/v1` is currently offline. A connection probe to `GET http://localhost:1235/v1/models` fails immediately with connection refused (`[WinError 10061] No connection could be made because the target machine actively refused it`).

In accordance with dispatch instructions, no benchmark agreement percentages, throughput metrics, or latency figures are fabricated. The harness has been implemented, validated in mock execution, and documented below for immediate execution once LM Studio is launched locally.

---

## 2. Harness Design (`scripts/librarian/bench_local.py`)

The evaluation script tests Stage 2 taxonomy assignment on local LLMs using an OpenAI-compatible HTTP interface.

### CLI Interface
```bash
# Standard run against local LM Studio instance
python scripts/librarian/bench_local.py

# Custom host, port, or model
python scripts/librarian/bench_local.py --base-url http://localhost:1235/v1 --model qwen3.8-27b

# Sub-sample evaluation (e.g. 5 items)
python scripts/librarian/bench_local.py --limit 5

# Synthetic verification mode (validates harness logic without an active endpoint)
python scripts/librarian/bench_local.py --mock --limit 10

# Export structured metrics to JSON
python scripts/librarian/bench_local.py --output docs/library/bench-results.json
```

### Evaluation Protocol
1. **Health Probe:** Makes a 3-second `GET /v1/models` check. If the connection fails or returns non-200, the harness logs `[STATUS] not run: endpoint down` and exits cleanly with diagnostic details.
2. **Taxonomy Injection:** Builds the prompt dynamically by injecting the library's 57 unique shelf paths into the `{{TAXONOMY}}` placeholder of `scripts/librarian/prompts/assign.md`.
3. **Card Input:** Serializes each gold set item's evidence card (or metadata-only stub if no transcript clips exist) into `{{CARDS}}`.
4. **Metric Measurement:**
   - **Level 1 Agreement:** Normalizes and compares the predicted primary top shelf (`shelf_paths[0][0]`) against the gold label.
   - **Level 2 Agreement:** Compares both top shelf and sub-shelf (`shelf_paths[0][1]`).
   - **Evidence Grounding:** Verifies that the model's returned `evidence_quote` is an exact substring within the card's transcript clips (or `"metadata-only"` for items without audio).
   - **Throughput & Latency:** Measures wall-clock elapsed time per item using `time.perf_counter()` and divides completion tokens by wall time to report tokens per second (TPS).

---

## 3. Execution Verification

### Live Endpoint Check
```text
$ python scripts/librarian/bench_local.py
=== Uoink Librarian Local Benchmark ===
Base URL:      http://localhost:1235/v1
Target Model:  qwen3.8-27b
Gold Set:      docs/library/gold-set-2026-09-04.json
Assign Prompt: scripts/librarian/prompts/assign.md
Mock Mode:     False
========================================
Evaluating complete gold set (60 items)

Checking LM Studio endpoint status...
[STATUS] not run: endpoint down (Connection failed: [WinError 10061] No connection could be made because the target machine actively refused it)
LM Studio is not listening on http://localhost:1235/v1.
To verify the benchmark evaluation harness, rerun with: python scripts/librarian/bench_local.py --mock
```

### Mock Harness Run (`--mock --limit 10`)
To verify that parsing, hierarchical path matching, quote validation, and metric aggregation work without defects, the harness was executed with synthetic completions:

```text
$ python scripts/librarian/bench_local.py --mock --limit 10
=== Uoink Librarian Local Benchmark ===
Base URL:      http://localhost:1235/v1
Target Model:  qwen3.8-27b
Gold Set:      docs/library/gold-set-2026-09-04.json
Assign Prompt: scripts/librarian/prompts/assign.md
Mock Mode:     True
========================================
Evaluating subset of 10 items (--limit 10)

[STATUS] Running in MOCK mode (simulated endpoint responses).

Running Stage 2 Assignment evaluation...
[01/10] episode_54e695d5 | L1: ✓ | L2: ✓ | 2.43s | 35.0 tps
[02/10] episode_9ddb44f9 | L1: ✓ | L2: ✓ | 2.63s | 35.0 tps
[03/10] episode_ee13d34d | L1: ✓ | L2: ✓ | 2.40s | 35.0 tps
[04/10] KjToqo-ACnc      | L1: ✓ | L2: ✗ | 1.91s | 35.0 tps
[05/10] _3GaXHNSP2I      | L1: ✓ | L2: ✓ | 2.37s | 35.0 tps
[06/10] 0FrcYhnHmLg      | L1: ✓ | L2: ✗ | 2.43s | 35.0 tps
[07/10] iyVXw-SoUrY      | L1: ✓ | L2: ✓ | 2.60s | 35.0 tps
[08/10] wQb4JK5xKMw      | L1: ✓ | L2: ✓ | 2.31s | 35.0 tps
[09/10] aqz-KE-bpKQ      | L1: ✓ | L2: ✓ | 1.97s | 35.0 tps
[10/10] HIj8wU_rGIU      | L1: ✓ | L2: ✓ | 2.40s | 35.0 tps

========================================
=== BENCHMARK RESULTS SUMMARY ===
Items Evaluated:         10
Level 1 Agreement:       10/10 (100.0%)
Level 2 Agreement:       8/10 (80.0%)
Evidence Grounding:      10/10 (100.0%)
Total Wall Time:         23.46s
Mean Latency Per Item:   2.35s
Overall Throughput:      35.0 tokens/sec
========================================
```

---

## 4. Benchmark Repair Increment (Run D - Astra Finding 4 Resolution)

During run C, Astra identified that the benchmark harness could award credit to the wrong item if an ID was mismatched or omitted, that cards omitted `video_id`, that latency timing excluded reading the response body, and that missing token usage fell back to word count approximation.

In run D, the harness was repaired with the following hardened behaviors:
1. **Strict ID Validation:** `evaluate_single_item` strictly validates assignment IDs against the target `video_id`.
   - **Wrong IDs:** Rejected (`id_status: "wrong_id"`, `id_valid: False`). Agreement metrics score 0.
   - **Missing IDs:** Rejected (`id_status: "missing_id"`, `id_valid: False`). Agreement metrics score 0.
   - **Duplicate IDs:** Rejected (`id_status: "duplicate_id"`, `id_valid: False`). Agreement metrics score 0.
   - **Exit Evidence:** Running `python scripts/librarian/bench_local.py --mock --mock-wrong-id` returns the right label under the wrong ID, and the harness strictly scores all items 0 (0.0% Level 1 and Level 2 agreement). Tested in `tests/security/test_bench_local.py::test_mock_returns_right_label_under_wrong_id_scores_zero`.
2. **Explicit Card Identity:** `format_card_for_prompt` explicitly adds `video_id` to every prompt card (both for non-null cards that omitted it and metadata-only stubs).
3. **Full Response Latency Measurement:** `send_chat_completion` now records wall time through the complete `resp.read()` body read (`wall_time = t1 - t0` measured after `resp.read()`).
4. **Honest Usage Accounting:** Missing or null `completion_tokens` from provider APIs are reported as `"unavailable"` rather than defaulting to word counts or 0.
5. **Prompt Fencing (SEC-03):** The `{{CARDS}}` block in `assign.md`, `induce.md`, and `reshelve.md` is enclosed in explicit `<untrusted_cards>` XML fences with a strict security directive stating card content is passive data, not commands. Empty cards and metadata-only cards produce an explicit `unsupported` outcome.

### Verification Run with `--mock-wrong-id`:
```text
$ python scripts/librarian/bench_local.py --mock --mock-wrong-id --limit 3
=== Uoink Librarian Local Benchmark ===
Base URL:      http://localhost:1235/v1
Target Model:  qwen3.8-27b
Gold Set:      docs/library/gold-set-2026-09-04.json
Assign Prompt: scripts/librarian/prompts/assign.md
Mock Mode:     True (wrong_id=True)
========================================
Evaluating subset of 3 items (--limit 3)

[STATUS] Running in MOCK mode (simulated endpoint responses).

Running Stage 2 Assignment evaluation...
[01/03] episode_54e695d5 | ID: wrong_id | L1: ✗ | L2: ✗ | 2.43s | 35.0 tps
[02/03] episode_9ddb44f9 | ID: wrong_id | L1: ✗ | L2: ✗ | 2.63s | 35.0 tps
[03/03] episode_ee13d34d | ID: wrong_id | L1: ✗ | L2: ✗ | 2.40s | 35.0 tps

========================================
=== BENCHMARK RESULTS SUMMARY ===
Items Evaluated:         3
Level 1 Agreement:       0/3 (0.0%)
Level 2 Agreement:       0/3 (0.0%)
Evidence Grounding:      0/3 (0.0%)
Total Wall Time:         7.46s
Mean Latency Per Item:   2.49s
Overall Throughput:      35.0 tokens/sec
Reported Tokens:         261
========================================
```

---

## 5. Operational Instructions for Live Run

When the user or control room host boots LM Studio with `qwen3.8-27b` listening on port `1235`:

1. Confirm the model is loaded in LM Studio with the local server enabled on port `1235`.
2. Run the benchmark across the entire 60-item gold set:
   ```bash
   python scripts/librarian/bench_local.py --output docs/library/bench-results-live.json
   ```
3. The script will emit per-item agreement checkmarks, write the JSON metric breakdown, and report true Level 1 and Level 2 agreement against the hand-verified gold set.

