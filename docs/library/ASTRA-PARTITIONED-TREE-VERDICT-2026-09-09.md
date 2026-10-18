# Complete candidate tree verdict

At 9a62e8405cb891d0502860831d085f4ec37909a0, the complete two-process tree
records **2,489 passed, one failed, two skipped and one xfailed**. The result is
FAIL. All 2,493 collected cases occur exactly once across the disjoint partitions;
only S21 is absent. The three new decoder regressions are present and no prior
case is missing. Existing tests and the P4 parent guard are unchanged.

The main process exits one: 2,487 passed, one failed, two skipped, one xfailed,
with the two media cases deselected. It takes 1,463.23 seconds by pytest's printed
summary. The second process runs exactly those two media cases and exits zero:
two passed in 1.49 seconds. XML process durations total 1,464.698 seconds;
launcher time including collection is 1,477.419 seconds. Keep these different
timing definitions explicit. No monolithic pass is claimed.

The only failure is AS-7's original AT6 process-exit assertion. The old wrapper
discarded that exit, and neither a replacement run nor this observation can
recreate it. Its release disposition remains Ryan's. The skips are POSIX build
execution on Windows and unavailable symlink privilege. SEC-06 is the existing
expected failure for non-ASCII search parsing. All remain visible.

Both original media assertions pass under the reviewed execution repair. The
private GPL FFmpeg tool only supports these tests; the installer contains the
separately verified LGPL runtimes. The 43-file proof preserves collection,
membership, raw reports, XML/logs, real exits, instrument preflight and comparison:
proof/ryan-final-partitioned-01-2026-09-09/SHA256.json.

Package-05's source bindings still match this tested source. Continue the already
authorized same-account isolated Setup, reinstall, installed file comparison,
decoder checks, original C22 and Phase 4 routes. The historical evidence failure
and remaining dependency advisories are not waived. This installation observation
uses synthetic inputs and runs no model; it does not approve a public release.
