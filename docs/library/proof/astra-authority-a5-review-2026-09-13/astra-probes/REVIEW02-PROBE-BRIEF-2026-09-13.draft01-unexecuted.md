# Review the unfinished Grok process-authority repair

Prepared on 2026-09-13 for the integrator. These probes are unexecuted. Run them
only after Control Room worker a5e7ba0d finishes and its final source is frozen.
They test specific paths observed in the working draft; they do not establish
the cause of tree08's fifty mirror failures or a release verdict.

The test file is `test_mirror_authority_review02.py` in this scratch directory.
Do not edit product files, the worker worktree, or committed tests during this
preparation. Preserve these first-draft bytes and a written reason before any
later revision. Astra owns copying, guarded execution, fresh labels, and the
actual pass/fail record.

The proposed boundaries are:

1. A Windows Popen handle whose creation-time query fails cannot borrow a new
   identity from its numeric PID. The raw-PID query recorder must stay empty.
   A successful original-handle query provides the positive control.
2. Drive the real `launch()` method with an inert Popen object and a ready line
   naming a distinct writer. Model that old writer as already gone: its PID now
   identifies a foreign process, and relationship discovery returns no child.
   The foreign epoch must neither enter session ownership nor reach the fake
   job-assignment effect recorder. The original launcher uses its own retained
   fake handle. A same-PID ready line supplies the launch positive control.
3. Drive real `launch()` and `terminate()` callers through a controlled thread
   interleaving. Pause fake job termination after the terminator acquires its
   handle lease. Resume launch after cancellation, so job acquisition is
   refused. The failed acquisition must not release the terminator's lease.
   Assert that the lease remains in use while the fake kernel call is paused.
   Finally release the pause and join the test thread, including on failure.

Every kernel method is an explicit inert recorder; an unrecognized method
raises. Popen, raw process observations, Toolhelp discovery, job creation,
readiness input, process streams, and owned-process mutation are mocked.
There is no `prepare()` call, exclusion gate, real process creation, native
process operation, model, network, live-index access, or port 5179 use.

The earlier same-millisecond concern is excluded from these probes. A valid
test would have to preserve Windows' original-handle lifetime and demonstrate
an actual identity collision; a sequence that reuses a PID while its original
process handle remains open would be an invalid fixture.

The tests are diagnostic proposals. Any changed fixture needs its original
bytes, exact diff, and reason retained. No result is claimed by this brief.
