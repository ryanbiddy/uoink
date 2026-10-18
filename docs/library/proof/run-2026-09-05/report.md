# Living Library Product Proof Report (Run P)

**Date:** 2026-09-05 13:54:42Z  
**Run ID:** `proof-subscription-2026-09-05`  
**Client Mode:** `proof_run.py` (`mock=False`)  
**Model:** `claude-sonnet-5`  

## 1. Frozen Inputs & Boundaries
- **Taxonomy:** `docs/library/taxonomy-v1.json` (revision `2f283053bbaca2e94c2dbd340f19c62a89f529457ac40ae5b1d2d84379d22d98`)
- **Prompt Template:** `docs/library/prompt-v1.md` (sha256 `f9f17b4ecddef3b75b0223d56d35caf1f2212b9db36e81569a820ca1c646e389`)
- **Holdout Split:** `docs/library/holdout-split-2026-09-04.json` (sha256 `b3579403434952a95aec54833f473c71d0a31f9f8c4b205583ec893d9675e4a4`)
- **Card Profile:** `brief-v1` (sha256 `6e265b0b2822ba3db6865cfa4002824d94538d2bfc0b5366e3f210504ac6bd14`)
- **Source DB SHA-256:** `2765cc359805fb12f7a90aecd3dd0b34d884aa8cb3015785011bf400da3b4dfc`
- **Transport:** Pure HTTP registry (`/tools/claim_library_work`, `/tools/submit_library_result`, `/tools/apply_reshelving`).
- **Tool Invocation:** The harness drives all HTTP tool endpoints. The model executes zero tool calls.

## 2. Accuracy & Coverage Thresholds
Contract requirements: Coverage floor **0.80**, Primary-shelf precision target **0.90** per stratum.
Abstentions (`unmapped`, `unsupported`, `rejected`) are counted against coverage and excluded from precision.

| Stratum | Total (N) | Assigned (A) | Abstentions (U) | Coverage | Coverage Floor | Correct (C) | Precision | Precision Target | Result |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **timed_evidence** | 47 | 30 | 17 | 63.8% | >= 80.0% | 15 | 50.0% | >= 90.0% | **FAIL** |
| **text_only** | 13 | 4 | 9 | 30.8% | >= 80.0% | 3 | 75.0% | >= 90.0% | **FAIL** |
| **Overall (Held-out)** | **60** | **34** | **26** | **56.7%** | >= 80.0% | **18** | **52.9%** | >= 90.0% | **FAIL** |

## 3. Evidence Grounding & Identity Checks
- Verifies evidence basis is `packet`.
- Verifies evidence quote exists and adheres to the <= 25 words brevity limit.
- Verifies card hash and excerpt hash bindings match frozen input records.

- **Assigned items evaluated for evidence:** 34
- **Grounded evidence valid:** 34 (100.0%)

## 4. Invariant Assertions & State Isolation
- **Librarian apply enabled:** `False` (preview only).
- **Zero applied labels before run:** `True`
- **Zero applied labels after run:** `True`
- **Projection revision identical before/after:** `True` (rev 0)
- **Active taxonomy version unchanged:** `taxonomy-v1-2026-09-04`
- **Pins preserved:** `0 pin(s)`
- **All invariant checks passed:** `True`

## 5. Usage & Resource Accounting
- **Usage Reporting Status:** `measured`
- **Wall Time:** 2334.80 s (2,334,799 ms)
- **Input Tokens:** 214
- **Output Tokens:** 908,541
- **Cache Read Tokens:** 8,315,787
- **Cache Create Tokens:** 1,938,051
- **Total Tokens:** 11,162,593
- **Total Estimated Cost (USD):** $0.0000 *(Note: CLI estimate)*
