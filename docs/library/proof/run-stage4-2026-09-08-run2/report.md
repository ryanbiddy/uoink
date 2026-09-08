# Living Library Product Proof Report (Run S)

**Date:** 2026-09-08 09:23:53Z  
**Run ID:** `stage4-2026-09-08-run2`  
**Client Mode:** `proof_run.py` (`mode=subscription`, `mock=False`)  
**Model:** `claude-opus-5`  
**Gate Verdict:** `FAIL`  

## 1. Frozen Inputs & Boundaries
- **Taxonomy Revision:** `8a1b16033eb4d6acd57c91c6a5d5e7f2af6d6f60f3adef92502b62d81ba28d04`
- **Prompt Template SHA-256:** `e4ff00598d1e58ab436d1ca31796b67776e261535849fb52d70a59d9ca413aa9`
- **Holdout Split Hash:** `855749efcaca5e985c04a9efef2decc4ee2dca3b24c8c3871f01079a9acd314c`
- **Card Profile Hash:** `9883a33ab56f2244a6d01e139a0f5dd11610086086690eb24fc61343ae446015`
- **Source DB SHA-256:** `2765cc359805fb12f7a90aecd3dd0b34d884aa8cb3015785011bf400da3b4dfc`
- **Transport:** Pure HTTP registry (`/tools/claim_library_work`, `/tools/submit_library_result`, `/tools/apply_reshelving`).
- **Tool Invocation:** The harness drives all HTTP tool endpoints. The model executes zero tool calls.

## 2. Accuracy & Coverage Thresholds
Contract requirements: Coverage floor **0.80**, Primary-shelf precision target **0.90** per stratum.
Scoring rule: Strict mapped equality to the deepest approved taxonomy ancestor.
Abstentions (`unmapped`, `unsupported`, `rejected`) are counted against coverage and excluded from precision.

| Stratum | Total (N) | Assigned (A) | Abstentions (U) | Coverage | Coverage Floor | Correct (C) | Precision | Precision Target | Result |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **timed_evidence** | 47 | 46 | 1 | 97.9% | >= 80.0% | 39 | 84.8% | >= 90.0% | **FAIL** |
| **text_only** | 13 | 11 | 2 | 84.6% | >= 80.0% | 6 | 54.5% | >= 90.0% | **FAIL** |
| **Overall (Held-out)** | **60** | **57** | **3** | **95.0%** | >= 80.0% | **45** | **78.9%** | >= 90.0% | **FAIL** |

## 3. Evidence Grounding & Identity Checks
- Verifies evidence basis is `packet` or `fetched_full`.
- Verifies every membership quote adheres strictly to the 1 to 24 words brevity cap.
- Verifies card hash and excerpt hash bindings match frozen input records.

- **Assigned items evaluated for evidence:** 57
- **Grounded evidence valid:** 57 (100.0%)

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
- **Wall Time:** 2430.17 s (2,430,170 ms)
- **CLI Process Calls:** 69
- **Input Tokens:** 150
- **Output Tokens:** 720,141
- **Cache Read Tokens:** 5,150,263
- **Cache Create Tokens:** 1,952,898
- **Total Tokens:** 7,823,452
- **Total Estimated Cost (USD):** $41.3060 *(Note: CLI estimate)*
