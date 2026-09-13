# Concrete integration ports and remaining work

The generated bootstrap constructs one gate registry for all approved snapshot
bindings. Its physical key is the exact volume/file identity of the snapshot
directory. A real binding must retain that directory's identity/lifetime before
registration; path spellings, store aliases, revision, manifest, and generation
cannot create separate physical gates. The current registry provides in-process
exclusion only. The Windows writer gate and durable storage port are not present.

`RetainedJournal` accepts one retained stream plus trusted identity and sync
services. It implements bounded reads, complete short writes, flush, sync,
identity checks, and exact readback. Its generated sync returns a test-controlled
boolean; this does not measure filesystem durability. Failed persistence poisons
the port and retains the gate. Neither readable CLEARED bytes nor a completed
later join repairs that uncertainty.

`ReservationService` receives fixed journal, worker-observation, normal teardown,
and fresh reconciliation ports from the trusted bootstrap. Worker observation
uses a retained ownership object; PID/time is only recorded descriptive data.
Normal teardown must establish exact process/job exit, no pending I/O or active
operations, and retired member guards before it confirms. The separate live
reconciliation port must make fresh observations bound to the exact worker,
physical identity, generation, journal head, and unique attempt. `None` worker
requires confirmation that no child was created and all acquired guards retired.
A retained failed token is accessible through the trusted service, not IPC.

Restart reconciliation has no live owner and cannot turn recorded PID/time into
kill authority. Its trusted observer must supply current independent lifetime
evidence for the physical snapshot, journal head, and old generation. The current
unit only exercises an opaque generated observer. If the real system cannot
establish that evidence, restart remains blocked. Corrupt/poisoned/absent state
requires a separately reviewed physical recovery protocol; there is no truncate
or automatic force-clear path here.

The lifecycle connection requires separate `create_suspended`, nonblocking
`resume`, exact `stop_start_failure`, and `completion_evidence` services. It
persists the reservation before creation and the retained-worker observation
before resume. Failure stops the exact retained worker even if local revocation
raises, and publication failure stops a returned worker that was never attached
to the facade. Stop uncertainty never retires guards or releases the gate.

A short semantic entry slot prevents replacing an active lifecycle record's
physical token while journal I/O occurs outside its manager lock. Finalization
is one-shot. Quarantine and ordinary completion remain separate paths. The
unchanged base lifecycle still serializes its existing kernel calls as documented;
this unit only moves the added journal operations outside the manager lock.

The existing adapter accepts the exact original `OwnedRuntimeFactory` class.
This distinct generated factory is not connected to that adapter. Adapter
migration, actual Windows gate/durability implementation, trusted observer
bootstrap, and generated native failure/restart checks are still required.
No new Ryan decision is needed to make these conservative engineering changes;
his existing real-asset/runtime/release gates still apply.
