# Exact startup and adapter delta

The derived factory adds one `finish_start(worker, permit, profile)` call after
confirmed binding and nonblocking resume, outside the manager state lock. It
requires exactly True before publication. The generated adoption port splits its
old combined start into suspended preparation, resume, and handshake/adoption;
the adapter bridge keeps its exact startup validation before preparation and its
policy acknowledgement in finish_start. The old combined entry refuses.

The migrated adapter requires the exact durable factory and manager identity.
OwnedSession, OperationFacade, resolver binding, lease permit, cleanup and passive
segments retain their existing checks. The generated bridge receives one trusted
Windows registry and physical binding before any lease, and constructs its fixed
reservation observer callbacks itself. No runtime profile supplies callbacks or
permission.

Normal completion evidence is an opaque local witness issued only after the
observed clean process/job exit, no pending pipe work, and confirmed guard/handle
retirement. A consumed witness cannot be reused for ordinary completion. Fresh
live reconciliation can confirm only this already-retired exact lifetime by
checking its permanent observed-death witness and current retired state for a new
attempt; it cannot clear an unconfirmed process/pipe or invent new native proof.
General crash/restart reconciliation remains closed pending its protocol.

The original 42 test bodies stay unchanged. Their fake Kernel gains only a
finish_start helper returning an explicit fake success; new focused controls
cover finish failure and publication refusal. No test is executed here.
