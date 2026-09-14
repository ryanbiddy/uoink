# Cancel one owned cursor before durable journal retirement

The selected missing boundary is clean cancellation after one generated segment
through the actual ASR adapter context while its retained journal is WORKER_BOUND.
The existing owned close/join path must then observe exact child exit and an empty
job, retire read guards, confirm CLEARED and close the journal. This is a new named
case, not a relabeling of drain or a simulated storage failure.

Commit 7fba83a records native generated-facade drain and cancellation. Its cancel
case produced one segment and an acknowledged cancellation, but did not enter
the actual ASR adapter or retained journal. Writer-exclusion04 subsequently passed
actual adapter drain, physical writer exclusion and four-phase journal completion.
Keep both origins and all previous assertions/outcomes unchanged.

The production lifecycle, cancel_transcription, owned close/join, adapter finally,
journal and Windows primitives already implement the required paths. No new stop
or durability mechanism is proposed. The generated adapter constructor is explicitly
drain-only, so add one exact-string cancel branch while retaining its original
drain assertion for all other inputs. Use the existing exact port class, original
_OwnedASRStart validation, contender binding and permit; no subclass or sentinel
substitution is permitted.

Add a separately named controller_cancel_flow. Keep the original controller_flow
unchanged. The new flow uses the same real adapter context and a small separately
testable consumption helper: obtain one segment, call the actual stream.close,
require acknowledged cancellation at index 1, and require further iteration to
stop without another wire operation. Before and after cancellation, require the
same confirmed WORKER_BOUND journal bytes and a still-held gate/handle. Only the
adapter's existing finally closes/joins and exits the lease. Afterward require its
original RELEASED, child/job, guard/pipe and stale-reference checks.

The future native source derives from writer04. Retain its independent contender
and all existing process, journal, fixture and guard assertions, rather than add
a second alternate startup path. Use a fresh fixed cancel-only output and launcher;
the launcher's already-present cancel result expectations select one segment and
four exchanges. Add only the new confirmed-journal-during-cancel receipt checks.
The same 18 sources, 33 Windows function bindings, fixed process commands, call and
cleanup budgets apply. No extra Windows API or storage-failure injection is added.

Before native admission, propose focused guarded fake controls for the new mode
and consumption helper, appended to the unchanged 81-case source suite. They test
the actual new helper with inert stream/port state; they do not pretend to measure
the adapter's native finally or physical flush. Preserve source origins and all
prior cases. Root and peer review exact code before any fake or native execution.

A successful future result would establish this clean cancellation path only.
It would not prove interruption races, hung-worker recovery, hard deadlines,
power-loss persistence, crash/restart recovery, production assets or market readiness.
No execution or admission is granted by this proposal.
