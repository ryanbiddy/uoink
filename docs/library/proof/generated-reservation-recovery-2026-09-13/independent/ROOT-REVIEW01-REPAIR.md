# Reservation source review correction

Root identified three defects in the unexecuted draft. The exact source, tests,
and brief are retained under `before-root-review01/`. No measurement failed and
no test has run.

An absent gate and a `None` token compared equal through `dict.get`. The guard
will require membership and a non-None identical token before any mutation,
including publishing a clean journal head.

Ordinary completion previously admitted quarantine and ignored an existing
revocation. It will admit only a non-revoked reservation or bound worker. A
separate `reconcile_live` entry will require the retained live token and a fixed
trusted reconciliation port. That port must make fresh observations of the exact
retained owner and completed guard retirement for the physical snapshot,
generation, current journal head, and unique reconciliation attempt. A recorded
PID, old completion receipt, or late ordinary join cannot clear quarantine. The
port is fixed when the service is constructed; clients cannot supply it through
a profile or a reconciliation argument. Its real implementation is still absent.

Every transition and successful publication will recheck live-token and gate
identity after acquiring the token lock. A check before waiting is insufficient.
Blocking journal and observation calls remain outside this lock. Pending
transitions prevent competing writes; revocation can still refuse publication.

Focused new cases will check missing/None gate refusal without clean-head side
effects, rejection of ordinary completion after revocation or quarantine, the
separate reconciliation path, and stale ownership at the lock boundary. Existing
draft assertions remain unchanged. These additions need source review before
execution.
