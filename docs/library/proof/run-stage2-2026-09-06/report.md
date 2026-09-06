# Living Library Product Proof Report (Run S)

**Date:** 2026-09-06 06:57:25Z  
**Run ID:** `stage2-2026-09-06`  
**Client Mode:** `proof_run.py` (`mode=subscription`, `mock=False`)  
**Model:** `claude-sonnet-5`  
**Gate Verdict:** `FAIL`  

## 1. Frozen Inputs & Boundaries
- **Taxonomy Revision:** `bd9e7f9d572a709a9e0f939b5433932fb36840278929946c2c6870ac0158dd97`
- **Prompt Template SHA-256:** `662e8ee8133110beefb59b948e4dcebf9e64104c1e6f97deb08aee4000221ae1`
- **Holdout Split Hash:** `0d5be9a11c8589dcbde79a7b2bbb08a23ad6e9e299a6da2f224439583772b309`
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
| **timed_evidence** | 47 | 41 | 6 | 87.2% | >= 80.0% | 31 | 75.6% | >= 90.0% | **FAIL** |
| **text_only** | 13 | 12 | 1 | 92.3% | >= 80.0% | 11 | 91.7% | >= 90.0% | **PASS** |
| **Overall (Held-out)** | **60** | **53** | **7** | **88.3%** | >= 80.0% | **42** | **79.2%** | >= 90.0% | **FAIL** |

## 3. Evidence Grounding & Identity Checks
- Verifies evidence basis is `packet` or `fetched_full`.
- Verifies every membership quote adheres strictly to the 1 to 24 words brevity cap.
- Verifies card hash and excerpt hash bindings match frozen input records.

- **Assigned items evaluated for evidence:** 53
- **Grounded evidence valid:** 53 (100.0%)

## 4. Invariant Assertions & State Isolation
- **Librarian apply enabled:** `False` (preview only).
- **Zero applied labels before run:** `True`
- **Zero applied labels after run:** `True`
- **Projection revision identical before/after:** `True` (rev 0)
- **Active taxonomy version unchanged:** `taxonomy-v2-2026-09-05`
- **Pins preserved:** `0 pin(s)`
- **All invariant checks passed:** `True`

## 5. Usage & Resource Accounting
- **Usage Reporting Status:** `measured`
- **Wall Time:** 2628.28 s (2,628,284 ms)
- **CLI Process Calls:** 71
- **Input Tokens:** 222
- **Output Tokens:** 1,034,756
- **Cache Read Tokens:** 9,260,888
- **Cache Create Tokens:** 2,478,488
- **Total Tokens:** 12,774,354
- **Total Estimated Cost (USD):** $23.2390 *(Note: CLI estimate)*
