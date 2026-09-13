# Partition subtest receipt review — 2026-09-13

The extended receipt contract preserves top-level membership and every failed subtest. **116 synthetic checks passed**: the unchanged 53 helper cases, 48 new cases and the unchanged 15 mirror-observer cases. This qualifies the scratch instruments for parent review. No product suite or complete tree09 ran.

Installed native Python 3.14 uses pytest **9.1.1**. Its captured `subtests.py`, `unittest.py`, `main.py`, `terminal.py` and `junitxml.py` explain the measured behavior. A `SubtestReport` shares its parent's node ID and reports `when=call`. Passing subtests increment JUnit's suite `tests` counter without adding testcase elements. Failed/skipped subtests add failure/skip elements inside the parent's testcase. A failed teardown after any failed call report can split that parent into a second testcase. The counters must therefore be reconciled against reports, not equated with selected cases or XML element counts.

Pytest's fixture-based subtests can also promote an otherwise passing parent to failed during terminal status processing. Session failure counting occurs before that mutation; JUnit sees the final failure. Unittest subtests do not make that same promotion. The receipts now retain report type/class, sequence index, subtest ordinal/context, outcome before hooks, final outcome and any transition reason. The contract accepts only the observed passing-parent-to-failed transition with matching preceding failed subtests and pytest's exact reason. It never changes a raw report.

| Completed evidence | Top-level outcome | Subtest outcome | Native receipts |
| --- | --- | --- | --- |
| unit01 | 93 passed | None | Original 53 plus first 40 new cases; exit 0. |
| unit03, final unit selection | **116 passed** | None | Includes eight guard-receipt cases and 15 unchanged observer cases; exit 0. |
| native04, final deliberate failure smoke | **5 passed, 6 failed, 3 error** across 14 cases | **8 passed, 8 failed, 2 skipped** | 60 reports; raw session failures 14, final failed reports 16, two promoted parents. JUnit `tests=34`, failures 13, errors 3, skips 3 across 16 testcase elements. Exit 1 remains a failure. |
| pass01 | **3 passed** | **4 passed** | 13 reports; JUnit `tests=7` across three testcase elements; exit 0. |
| collect01 | 13 selected; no tests executed | None | Zero reports/failures; exit 0. |

Native01 and native02 preserve the earlier 13-case deliberate experiment. Native01's untyped reports still refuse as duplicate phases; no guessed conversion is allowed. Native03 records the first combined observer/import-guard smoke before the later stream repair. All intentional failures and original drafts remain retained.

**Unit02 is incomplete.** A pre-existing observer test replaces `Path.open`; the receipt callback attempted to reopen its JSONL during that test's call report and failed. Raw pytest and outer verifier exited 1, and no partition session receipt was produced. There is no completed case count for this attempt. The documented repair opens the partition and probe streams once at startup, then writes/flushes through those handles. Unit03 and native04 use fresh labels after that repair. No fixture or assertion was changed.

Top-level `counts` now classify any case with a failed subtest as failed, unless a setup/teardown failure makes it error. Its original parent phase outcomes remain available. Added result fields distinguish `subtest_counts`, `failed_subtests`, raw failed phases/reports, final failed reports and promoted parents. Legacy untyped ordinary receipts retain the earlier strict phase contract. Duplicate/missing sequence indices or ordinals, unknown report types, incomplete phases, unexplained outcome changes, missing failure tags, extra XML elements, contradictory counts and abnormal exits still refuse.

The full-tree runner and sealer carry and independently check these fields. They load the explicit heavy-import guard for collection, main and media pytest processes, each with a separate receipt, and require empty startup imports, an installed guard at finish and the matching raw pytest exit. The guard covers those pytest processes; it makes no claim about child subprocesses. Native04 and pass01 each denied all ten named heavy roots before discovery. No heavy package code ran in those checks.

The mirror observer now uses `trylast=True` for its passive report callback so native terminal promotion happens first. Native04 captured all **16** final failure reports, including both promoted parents, with **zero observer errors**. Pass01 captured zero reports and finished cleanly. Product state capture code is unchanged; the existing 15 observer tests remain unchanged.

`FINAL-VERIFICATION.json` reconciles the actual raw receipts, records final hashes and verifies the 19-payload before snapshot plus the unchanged prior 92-payload partition-exit seal. `before/`, `integration-before/`, launch input snapshots, raw results/XML/logs, `after/` and diffs preserve the whole instrument change. The root manifest seals these documentary bytes. Parent review remains required before tree09.
