# Review repair before a second labeled run

Attempt01 passed all 44 cases. Subsequent source review found that the writer
fallback still published a retained child without using the same live-handle
validation as ready and bind. It now calls `_record_writer_identity`.
Candidate-handle publication also gains a finally block so a failed ownership
transfer closes its candidate handle. These are product refinements, not
fixture changes or a blind repeat of the passing run.

Two new controls check that rediscovery closes only its new duplicate handle,
and that a parent without an original native handle cannot adopt children by
querying its raw PID. All 44 existing behavior assertions are unchanged.
The previous source and test bytes are retained under
`before-final-review-repair`, as well as the executed attempt01 archive.

Fresh label: `astra-authority-repair03-02`. No result claimed before execution.
