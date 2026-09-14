# Proposed expectation correction — NOT APPLIED

The failed author invocation remains FAILED: actual 6ba3f1 / outer exit 1, eight passing and two failing cases, 102 passing and two failing subtests. The raw result is retained at _scratch/controller-custody-fake10-author01/controller-custody-fake01/stdout.json. No repeat or confirmation is authorized by this note.

The test's REFUSALS tuple contains AdapterUnavailable and LifecycleUnavailable. SessionClosed is a separate RuntimeError subclass, so neither expectation accepts it. Keep the global tuple unchanged.

Only the wrong_permit subgroup should expect SessionClosed at line 128. It copies an actual issued _NativePermit but replaces its raw identity. The actual factory checks record.permit is permit.identity at durable_lifecycle.py:562 and raises SessionClosed at :566, before capture, owner creation, attempt registration or the lower create hook. This preserves the existing stale-permit exception contract also visible in the unchanged snapshot_lifecycle.py:287–295.

Only the active subgroup should pass SessionClosed to fail_start at line 300. The fixture's transparent bind wrapper first completes the actual reservation binding, then sets the actual unpublished owner's _active to 1. The kernel's retained factory check at durable_lifecycle.py:659 reaches _require_factory_start:511–514 before the adapter pre-resume helper and before resume_owned. Its refusal of a non-idle unpublished owner is intentional. The actual cleanup path catches BaseException, attempts exact retained-worker stop and quarantine, and re-raises the original; no production error translation is needed.

The original briefs require refusal, current ownership and primary-error preservation. They do not require either subgroup to raise AdapterUnavailable or LifecycleUnavailable. These two expectations were wrong; this diagnosis identifies no product defect in the called refusal branches. It does not establish that every later retention assertion will pass.

The exception escaped each assertRaises context, so the wrong_permit assertions at lines 149–155 and active assertions at lines 301–309 did not complete in those failed subtests. They remain unchanged and unverified for these subgroups. The proposed patch changes only the two expected-type expressions; case IDs, fault setup, fixtures, global REFUSALS, guards and all behavioral assertions remain intact.

The older Ryan ruling at 58335df covered different test expectations and is not authorization here. The current brief requires a new repair decision after an admitted failure. Root must obtain approval for this exact unapplied proposal before a fresh derivative or invocation. This note grants neither.

Source inspection and JSON/text checks only. No tests, Python startup, native calls or mutation of the admitted source/run. The first combined read was truncated; focused reads 02–05 provide the relevant complete bodies and failure records. Read04's intended single test range was not rendered by its PowerShell array shape; read05 explicitly supplies lines 30–89. Both actual outputs remain preserved.
