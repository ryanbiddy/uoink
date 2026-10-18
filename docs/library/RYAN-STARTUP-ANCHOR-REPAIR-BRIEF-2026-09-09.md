# Durable default-anchor startup repair — 2026-09-09

The independent full-helper isolation run `iso-wi1` logs standing-capture
reconciliation failing because another transaction is active. The startup
sequence seeds default writing styles just before reconciliation.
`writing_studio.seed_default_anchors` performs INSERTs under the Index lock
but never commits. A lock alone is not a durable transaction boundary.

Astra will reproduce with a fresh disposable Index: seed defaults, open a
second connection to verify durability, enter the next explicit write unit,
close/reopen and confirm idempotence. A separate caller-owned transaction
must be refused without committing or rolling back that caller's work.
An invalid second row must not leave a partially seeded transaction behind.
Add these regressions in a new file; no existing fixtures/assertions change.

Repair only `seed_default_anchors` to use the Index-owned write transaction.
Retain its inactive/default flags, normalization, per-name idempotence and
custom-anchor preservation. Do not weaken Index transaction refusal or
change global SQLite isolation/autocommit behavior. Do not silence startup
reconciliation or disable background services. Preserve the failed probe
before the repair, then run the new regression file plus complete
`test_v3_2_3_anchors_lens.py`, `test_g27_style_anchor_keep.py`,
`test_writing_surface_ownership.py`, `test_writing_save_real.py`,
`test_writing_draft_endpoints.py` and `test_source_subscriptions_migration.py`.

These checks use only synthetic scratch state under the integrator guard.
No live index, port 5179, model/client runs, paid API or existing-test edits.
The supported full-helper path will be checked again after the separate
installer ownership repair. Full-tree and installed receipts remain separate.

First regression observation `anc-r1`: all three failed (0.48 seconds),
confirming the open transaction, absorbed caller work and partial-write leak.
The direct Index transaction repair then passed all three new cases, but
`anc-c1` was **18 passed / three failed** (2.41 seconds): historical
connection/lock adapters do not implement `write_transaction`.

Before the next run, add an explicit capability adapter: real Index instances
use their strict write transaction; older connection/lock adapters use an
atomic SQLite savepoint, preserving any caller-owned outer transaction.
This retains the existing module protocol without changing a test or weakening
Index's caller-ownership refusal. Rerun the same complete named union.
