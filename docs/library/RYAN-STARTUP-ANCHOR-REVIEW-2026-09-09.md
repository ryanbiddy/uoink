# Startup seed review — 2026-09-09

Verdict: accept the default-anchor transaction repair. The complete named
union has **21 passed, zero failed**, five warnings, 2.21 seconds. This is
a focused source result; full-helper verification follows the supported
installer integration and does not yet count as installed evidence.

On a new database, default styles previously remained in an implicit open
transaction. Standing-capture startup then correctly refused to absorb that
unrelated write. The new three-case regression reproduced the open write,
caller-transaction absorption and partial seed after an invalid row; all
three failed before repair (0.48 seconds).

The production Index now owns a complete seed transaction: commit before
return, rollback the whole seed on failure, and refuse a caller's pending
transaction without changing it. A second connection and reopen verify
durability and idempotence. Existing inactive/default flags and custom
styles remain covered by the original complete tests.

The first direct transaction repair produced 18 passes / three failures
because legacy connection/lock adapters lack Index's transaction method.
An explicit adapter uses a SQLite savepoint for that older protocol, which
keeps any caller's outer work intact. Real Index instances always use the
strict transaction API. No test or fixture was edited to resolve that failure.

The original three failures, intermediate union, final union, patch, source
hashes and guard are retained in
`proof/ryan-startup-anchor-2026-09-09/SHA256.json`. The current full tree
remains the failed `4a35316` observation until the final source is measured.
