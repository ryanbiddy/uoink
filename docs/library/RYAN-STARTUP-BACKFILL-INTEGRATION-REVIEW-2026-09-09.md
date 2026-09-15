# Startup backfill integration review, 2026-09-09

Accept the product repair for integration. Backfill flag lookup and persistence
now use the existing Index snapshot and write transaction. The source watcher
retains its own transaction while backfill waits for the shared connection lock.
A failed flag write rolls back, records no completion and remains retryable.
The original bundled source-watch errors are retained in the first C22 archive.

Independent worker sb-w1: 22 passed / one failed, 3.26 s. Checkout sb-c1:
22 passed / one failed, 3.10 s. All six new regressions pass. Strict Phase 3:
worker sb-w2 181 passed / one failed, 36.18 s; checkout sb-c2 181 passed /
one failed, 35.96 s. S21 alone is excluded. The failures are the known getter
fixture contamination and the original AT6 receipt's absent process exit.
No existing test, fixture or assertion changed.

Worker g-sbf initially has 21 passes / two failures. Its new retry assertion
incorrectly expected one author correction after that row was already corrected
before a failed flag commit. The worker corrected only this newly authored
regression to inspect the actual preserved author/channel and persisted flag;
it did not change production counters. g-sbf and its failed assertion remain
sealed with later worker observations. This is not a correction to a frozen
acceptance test. The held-source read/write regressions use real SQLite threads;
ordinary and foreign-transaction cases cover repeat/rollback behavior.

Astra exported the original worker source, new test and report with a full-index
raw diff, then applied it by three-way apply and repeated both named groups.
The seal includes that exact patch and eight original observations:
[proof](proof/ryan-startup-backfill-integration-2026-09-09/SHA256.json).
The repaired server is packaged source, so preserve package-02 and rebuild.
The new original bundled C22 observation must contain no unexpected startup
errors. Final complete-tree and Ryan's actual installed receipts remain owed.
