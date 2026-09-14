# Recover an interrupted final clear for an already retired worker

Implement one generated Windows case: finish the existing owned cancellation and
native teardown, interrupt immediately before the journal's CLEARED append, then
reconcile that same retained owner explicitly. This connects the existing recovery
service to an actual worker lifetime with the smallest additional mechanism.

This is preparation only. At this read, handoff lines 172–184 records the 89-case
qualification at 60b3bb5 and lists native cancellation next. Root must establish
that separate baseline outcome before admitting this derivative. No native run,
test, source implementation or product mutation accompanies this brief.

The current source is `_scratch/windows-journal-cancel-proposal01`; exact hashes
are in `SOURCE-BINDINGS.json` beside this file. The original six-observation plan
is `_scratch/windows-reservation-integration-brief01/BRIEF.md:114–132`.

The concrete gap has two parts. `ReservationService.reconcile_live` already
requires a revoked live token, fresh trusted observation and confirmed journal
write before gate release (`snapshot_reservations.py:432–482`). The adapter's
`confirm_live_reconciliation` can inspect its exact retired worker and guards
(`generated_adapter_flow.py:112–122,183–191`). However, the manager has no recovery
entry to change its QUARANTINED record after that service succeeds. Its failed
ordinary completion leaves that record blocked (`durable_lifecycle.py:127–141`).
The native journal observer also accepts only ordinary completion: it requires
an unrevoked token and four flushes (`generated_journal_setup.py:135–167`).

Use a fresh `_scratch/windows-retired-owner-recovery-proposal01` derivative.
Keep all existing source origins, test bodies and normal-flow assertions intact.

| File | Proposed addition |
| --- | --- |
| `durable_lifecycle.py` | Private `reconcile_retired_owner(owner)` on the exact manager. Bind the current record, token, service and worker by object identity; require QUARANTINED/revoked state, zero active work and an already verified, retired lifetime. Reserve a per-key recovery attempt under the manager lock. Call existing `reconcile_live(token)` outside that lock. Publish RELEASED only after successful confirmed clear/gate release and unchanged ownership/attempt checks. Keep the old owner revoked. Failures retain local quarantine and their actual gate state; never fabricate another release. |
| `generated_adapter_flow.py` | A fixed, single-use bootstrap probe at the end of `confirm_teardown`, after its original checks and completion-witness consumption, raises one retained `KeyboardInterrupt` object. It accepts no caller callback or wire flag. Add a separately named controller recovery flow using the exact existing port, `_OwnedASRStart`, adapter and cancel path. Catch only that expected object after the adapter context unwinds; call the new manager method with the retained owner. |
| `generated_journal_setup.py` | Separate recovery-close and completion observers. Preserve ordinary `_confirmed_phase`, `before_close` and `complete` assertions. The recovery branch binds the exact probe/attempt and retired owner, permits the deliberately still-revoked token only during this explicit clear, and verifies confirmed CLEARED bytes, unchanged handle and fourth successful flush before journal close. |
| `dummy_bootstrap.py`, new launcher | Fresh fixed run `_scratch/windows-retired-owner-recovery01`, distinct false admission template, source pins and recovery receipt. Select only the new flow/observer. Keep existing content, identity, API, process, fixture and pending-I/O finalization guards. |
| New `test_retired_owner_recovery.py` | Focused generated controls for the new manager connection, probe and observer. No OS calls. |

The manager method must accept an exact retained owner, never a path, PID,
generation string, journal head or caller evidence. Require its record's
protection already retired, `_closed_verified` true and `_active == 0`; the
existing observer additionally checks process/thread/job handles closed, pipe
retired, zero pending operations and the same worker creation identity. This
case rechecks retained evidence of completed native teardown; it cannot perform
a fresh process query after those handles have closed. Reentrant recovery and
changed ownership refuse. No lock is held across journal I/O. If a transition
wins before publication, report that state and retain the blocked record rather
than reopening a released gate or claiming atomic completion.

The interruption is injected at a Python boundary before any clear write. It is
not a failed FlushFileBuffers, torn write, controller crash or OS-delivered
interrupt. Existing `_clear` catches it and retains the gate with a revoked token;
the durable lease marks the manager record QUARANTINED. The disk still contains
INITIALIZED, RESERVED and WORKER_BOUND. Do not invent a QUARANTINED disk frame.

Add five focused controls before native admission:

1. The exact interruption propagates after teardown and before clear I/O; the
   same journal bytes, gate and handle remain held. Ordinary completion refuses.
2. Explicit manager reconciliation clears once and publishes RELEASED only after
   the service returns successfully; old owner/facade authority remains revoked.
3. Foreign/stale owner, changed record/token/head, active work, pending I/O,
   unretired guards and reentrant attempt refuse without clear or release.
4. Fake flush/identity failure and revocation during reconciliation preserve
   quarantine; repeated lease exit does not retry. Label these as fake failures.
5. The recovery observer refuses an unarmed probe, wrong attempt, premature
   journal close or stale confirmation; existing normal completion remains valid.

Use the current isolated source qualifier and its ten final guards. Alongside
these additions, select the existing affected reconciliation, failed-clear,
duplicate-exit and stale-completion controls unchanged; freeze the exact list
before root review. No unrelated model, conversion or packaging suite is needed.

The native fixture remains the five generated ASCII files, one primary owned
child and the inherited writer contender. Expected observations are: one segment
and cancel acknowledgement; exact primary child exit 0 and empty retained job;
normal guard/pipe retirement; the expected interrupt; three unchanged journal
frames and held journal gate; explicit reconciliation; then four confirmed
frames/flushes, exact closed-journal bytes and RELEASED manager state. Record the
interruption's type/identity match and fixed stage separately from native exit.
Retained facade/stream calls must remain refused without another wire operation.
Unexpected failure stays failed even if cleanup later succeeds.

No additional Windows API is needed. Derive the new call count before admission
within the existing 33 bindings, 16,384-call/60-second cooperative work limits,
64-call/10-second cleanup reserve and 1-MiB receipt cap. Keep raw streams, actual
native/tool exits, source/control hashes, journal events and post-exit byte check.
Pending OVERLAPPED ownership still triggers the existing immediate-exit guard;
this recovery method must never clear uncertainty flags or poison.

Recovery while a child is active remains separate: ordinary close refuses a
quarantined session, and pipe quarantine preserves uncertain worker/read-set
state. Controller crash/restart also needs surviving trusted lifetime evidence;
`recover_existing` does not turn recorded PID/time fields into ownership. Neither
boundary, power-loss durability, arbitrary concurrency nor writer/publication
authority follows from this case. There is no new Ryan decision for this
generated engineering; exact source, focused controls and native protocol still
need root review before execution.
