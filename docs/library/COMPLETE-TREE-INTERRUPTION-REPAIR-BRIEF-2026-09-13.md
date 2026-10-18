# Recover the interrupted combined candidate observation

The e53fe0e complete-tree attempt is partial. Collection found 2,729 cases,
but the retained main reports contain only 2,203 passes, one failure and two
skips with teardown records. BC3e's chapter_metadata case has setup only;
522 cases have no report. The media partition did not run. There is no main
XML, process exit or aggregate result. None of these counts is a full-tree pass.

At 09:33 UTC, the exec handle was missing and two process inventories found no
relevant Python process. The last event was written at 07:38:02 UTC. The host
had not rebooted during the run. The exact termination cause is unknown; do not
attribute it to a product defect or claim a normal exit. The original 24-payload
seal and synthetic interrupted fixture are preserved separately. The three
fixture database files moved into _scratch with exact hashes verified; they
are not release evidence or committed data.

Repair the observation transport by launching a separate hidden supervisor.
It must retain its PID, child PID, heartbeat, command, actual child exit and
summary hash independently of the terminal handle. First use a no-op child to
check durable output and exit recording. Then run the unchanged guarded tree
under fresh label ryan-final-partitioned-08, using the pristine 504-file NLTK
fixture and fixed original wheel. Keep all 2,729 cases, --runxfail and the sole
S21 exclusion. Compare actual membership against the last complete 2,582-case
tree, with the same 147 added cases; the partial run is not a new baseline.

Do not modify existing tests or mark the historical AT6 failure passed. A new
product failure requires its own repair brief. Do not build package 09 until
the full observation finishes and the result is reviewed. Package 08 remains
preserved. Rebind the unused package-09 observers to the new documentary source
before execution, retaining their earlier drafts and exact changes.

Control Room's separate completion-reporting repair is de06906, with 48 passes
and zero failures/skips; 8d7cc1a records local server readiness. No provider ran
for those replay checks, and neither result substitutes for Uoink qualification.
