# Cancellation branch and control review — 2026-09-13

No additional blocking issue found. This complements the owner's source/binding review; I did not repeat its 33/18 input-map or original81 preservation checks. I read all eight new case bodies, the complete native launcher, new source branches, all launcher/qualifier deltas and the unchanged cancellation/adapter-finally paths. No tests, imports, compilation, native operations, artifacts or installed-support reads occurred.

The constructor control calls the actual exact GeneratedLifecyclePort class. It reaches both the preserved drain branch and the added cancel branch, rejects a str subclass for cancel, and rejects an unsupported mode. It does not seed a completed worker or claim runtime construction.

The five cursor-driver cases call the actual _consume_one_then_cancel helper (generated_adapter_flow.py:373–392) with an explicit inert cursor. They cover one acknowledged segment/cancel, the same close-error object with no follow-up read, missing acknowledgement, a forbidden second result and an extra wire event. These cases qualify the new driver checks; they do not exercise the actual SegmentStream cancellation or native shutdown. The unchanged real stream close at snapshot_lifecycle.py:500–517 catches BaseException and quarantines uncertain cancellation. The future native case uses that stream through the actual adapter.

The two observer cases call _bound_cancel_journal at lines395–412 against an existing fake retained journal with confirmed WORKER_BOUND bytes. The positive control establishes the intended state; twelve negative subtests change phase/revocation/pending worker, gate, attempt, handle, confirmed bytes/revision or poison state. They include the missing-key/None trap and verify no API activity during observation. The passive token/worker graph is not presented as issued native authority.

The new controller_cancel_flow at415–471 preserves exact port/facade/permit checks and places cancellation plus both journal observations inside the actual faster_whisper_session context. A cancellation or observation exception still reaches its existing BaseException-aware finally. A successful cancellation must leave the same token, raw confirmed bytes and open handle, with the session still live. RELEASED and stale-reference assertions follow adapter cleanup. These before/after observations concern the fixed serial path; they do not establish concurrent atomicity.

Native launcher lines127–131 validate exactly the eight cancellation-journal fields. Lines248–270 retain the existing one-segment, cancelled-state and four-action expectations at both endpoints. Complete process/job exit, four confirmed journal phases/flushes and exclusive postexit byte comparison remain separately required. The native bootstrap preserves its both-endpoint pending-I/O finalizer. No API or budget was added by these passive observations.

Scope remains clean acknowledged cancellation followed by shutdown. The fake cases do not qualify native adapter-finally behavior, and a future successful native observation would not establish cancellation races, timeout/forced-stop recovery, hard deadlines, restart, power-loss durability, real models or release readiness.

Observed text SHA-256 bindings:

| Input | SHA-256 |
| --- | --- |
| generated_adapter_flow.py | cc0b7ff4f445ef73b4acdc63475c1aa375b5d0cfbe461ee6c50809cd0f19b4b4 |
| dummy_bootstrap.py | ed99209c7da9bb98faf960999a38667bd5e96b75bae1e0542d69733b62cc593c |
| run_journal_cancel01.ps1 | 70ab9cc3879ed792db0f8deaec4fd343f6a96438811bad9e37977ae510fa11d6 |
| test_journal_cancel.py | b02f35091e45af10380d725de77fc84e1f3e4c42f8bd163e41c78222b4aa6b31 |
