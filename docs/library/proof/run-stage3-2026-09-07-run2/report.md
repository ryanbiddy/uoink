# Living Library Product Proof Report (Run S)

**Date:** 2026-09-08 04:02:17Z  
**Run ID:** `stage3-2026-09-07-run2`  
**Client Mode:** `proof_run.py` (`mode=subscription`, `mock=False`)  
**Model:** `claude-sonnet-5`  
**Gate Verdict:** `FAIL`  

## 1. Frozen Inputs & Boundaries
- **Taxonomy Revision:** `8a1b16033eb4d6acd57c91c6a5d5e7f2af6d6f60f3adef92502b62d81ba28d04`
- **Prompt Template SHA-256:** `e4ff00598d1e58ab436d1ca31796b67776e261535849fb52d70a59d9ca413aa9`
- **Holdout Split Hash:** `855749efcaca5e985c04a9efef2decc4ee2dca3b24c8c3871f01079a9acd314c`
- **Card Profile Hash:** `6e265b0b2822ba3db6865cfa4002824d94538d2bfc0b5366e3f210504ac6bd14`
- **Source DB SHA-256:** `2765cc359805fb12f7a90aecd3dd0b34d884aa8cb3015785011bf400da3b4dfc`
- **Transport:** Pure HTTP registry (`/tools/claim_library_work`, `/tools/submit_library_result`, `/tools/apply_reshelving`).
- **Tool Invocation:** The harness drives all HTTP tool endpoints. The model executes zero tool calls.

## 2. Accuracy & Coverage Thresholds
Contract requirements: Coverage floor **0.80**, Primary-shelf precision target **0.90** per stratum.
Scoring rule: Strict mapped equality to the deepest approved taxonomy ancestor.
Abstentions (`unmapped`, `unsupported`, `rejected`) are counted against coverage and excluded from precision.

| Stratum | Total (N) | Assigned (A) | Abstentions (U) | Coverage | Coverage Floor | Correct (C) | Precision | Precision Target | Result |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **timed_evidence** | 47 | 37 | 10 | 78.7% | >= 80.0% | 28 | 75.7% | >= 90.0% | **FAIL** |
| **text_only** | 13 | 12 | 1 | 92.3% | >= 80.0% | 7 | 58.3% | >= 90.0% | **FAIL** |
| **Overall (Held-out)** | **60** | **49** | **11** | **81.7%** | >= 80.0% | **35** | **71.4%** | >= 90.0% | **FAIL** |

## 3. Evidence Grounding & Identity Checks
- Verifies evidence basis is `packet` or `fetched_full`.
- Verifies every membership quote adheres strictly to the 1 to 24 words brevity cap.
- Verifies card hash and excerpt hash bindings match frozen input records.

- **Assigned items evaluated for evidence:** 49
- **Grounded evidence valid:** 49 (100.0%)

## 4. Invariant Assertions & State Isolation
- **Librarian apply enabled:** `False` (preview only).
- **Zero applied labels before run:** `True`
- **Zero applied labels after run:** `True`
- **Projection revision identical before/after:** `True` (rev 0)
- **Active taxonomy version unchanged:** `taxonomy-v3-2026-09-07`
- **Pins preserved:** `0 pin(s)`
- **All invariant checks passed:** `True`

## 5. Usage & Resource Accounting
- **Usage Reporting Status:** `measured`
- **Wall Time:** 2136.82 s (2,136,820 ms)
- **CLI Process Calls:** 71
- **Input Tokens:** 226
- **Output Tokens:** 799,989
- **Cache Read Tokens:** 10,059,305
- **Cache Create Tokens:** 2,125,871
- **Total Tokens:** 12,985,391
- **Total Estimated Cost (USD):** $19.7169 *(Note: CLI estimate)*
