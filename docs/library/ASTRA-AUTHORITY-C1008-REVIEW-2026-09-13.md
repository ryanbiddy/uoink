# Process repair c1008e0b needs another revision

Reject the current product patch. Astra reproduced its eleven passing synthetic
cases in 0.24 s, then observed ten failures in new inert identity-boundary cases
in 0.29 s. No real mirror or process test ran against this proposal. The accepted
owner repair ff67b84 remains unchanged in the checkout.

The proposed code still authorizes termination and job assignment when creation
timestamps differ by up to two seconds. Both effects occur for a one-millisecond
mismatch in the new probes. The same tolerance admits a child born before its
parent. Parent identity can be filled from a later raw PID query when no original
creation identity was recorded. Parent verification happens before a snapshot;
replacing either parent or child during discovery can still register a foreign
process. Finally, an exited Popen launcher with a same-PID writer whose separate
timestamp query failed remains unknown. Independent static review found the
same four groups of defects. They do not establish tree08's original cause.

The useful liveness work and effect-recorder tests should be retained for the
next revision. Worker attempts remain 2 passed/9 failed, 10 passed/1 failed, then
11 passed. The first baseline includes a broken positive-control mock and an
old two-argument assignment signature, so its nine failures are not nine proved
product defects. The revised mock retains the behavior assertion and is archived
with its original. Preserve all proposal bytes, logs and new failed boundaries.

Use stable process authority through discovery and mutation. Microsoft documents
that a process ID can be reused after its process object is freed and all handles
are closed. Retaining the original handle can protect that identity; a fresh
timestamp from an arbitrary current PID cannot establish parentage.
[PROCESS_INFORMATION documentation](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/ns-processthreadsapi-process_information).

Follow MIRROR-PROCESS-AUTHORITY-REPAIR02-BRIEF-2026-09-13.md. The next patch must
pass the unchanged boundary assertions plus positive controls for verified owned
children and unknown-child retention. Review before real process testing. No
full-tree rerun, package09 build, website or marketing work is authorized by this
failed review result.
