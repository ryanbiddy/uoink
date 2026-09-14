# Avoid journal reads during final gate release

The first unexecuted port draft read the complete journal in `release`, which
ReservationService calls under its transition lock. That would add blocking
journal I/O to the final publication section. Preserve the first draft under
`before-release-review01/`.

The native journal will retain the exact bytes returned by a successful
append/renewal and the stream's write revision. Any later write attempt or failed
append/renewal invalidates that confirmation. Final release validates this
bounded retained confirmation and its clean head without rereading or flushing.
The exclusive non-inherited handle prevents another process from changing that
file during ownership. Native CloseHandle remains the actual final release and
must return successfully before local clean credit is published. This is not a
claim that CloseHandle latency is bounded. All blocking journal confirmation
remains outside the reservation publication and manager locks.
