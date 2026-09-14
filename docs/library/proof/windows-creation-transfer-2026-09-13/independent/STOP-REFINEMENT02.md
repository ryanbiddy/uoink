# Preserve the pipe port's one forced-stop attempt

The first split-start draft called the primitive stop again after pipe quarantine
had already attempted it. Preserve that unexecuted draft under
`before-stop-refinement02/`. The adapter now requires the exact controller pair
and worker, invokes its existing idempotent quarantine path, and consumes that
path's retained process-wait observation. It queries exit/job state without
issuing a second termination. Failed/unknown stop remains failed; pending pipe
work still prevents a confirmed stop result and no logical quarantine is cleared.
