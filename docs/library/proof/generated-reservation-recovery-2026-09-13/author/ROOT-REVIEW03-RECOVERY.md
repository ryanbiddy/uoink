# Already-cleared and initialized recovery

Root identified an availability gap before any execution. Revocation during a
confirmed CLEARED append can leave the local token quarantined with a valid
CLEARED head. A failed reservation attempt can similarly leave INITIALIZED.
The earlier source is retained under `before-root-review02/`; the file port's
unchanged earlier bytes are under `before-root-review01/`.

Explicit live reconciliation will handle these heads only after fresh trusted
teardown observations and a new same-handle durability confirmation. The file
port will compare the complete expected bytes, flush, request sync, check retained
identity, and read back the same bytes. It will not append an invalid duplicate
CLEARED transition or infer durability from readable content alone. Only then may
the exact held gate publish this head as clean and release.

A previously poisoned journal still refuses. This correction does not adopt a
new handle, erase a partial tail, or treat a failed earlier sync as success.
Corrupt, absent, or poisoned state remains held for a separate physical recovery
protocol. Tests will cover revocation during a clear append, INITIALIZED after
an early reservation refusal, renewed-sync failure, and poisoned-port refusal.
These are new unexecuted synthetic controls, not repairs to measured outcomes.

The same renewed-durability rule also applies to restart reconciliation of an
already INITIALIZED/CLEARED head. The intermediate snapshot source is retained
as `before-root-review02/snapshot_reservations.before-restart-renewal.py`.
Restart reconciliation also reserves a pending operation and rechecks its local
revocation revision before release. A fresh revocation during that observer or
flush must retain the gate just as it does during live reconciliation.
