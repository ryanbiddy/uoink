# Start failure and publication correction

Root identified two exception/lifetime defects in the unexecuted connection.
The current source and test draft are retained under `before-root-review02/`.
No test or native execution has occurred.

Local revocation can itself raise. Start cleanup must preserve the original
failure and attempt to stop the exact retained worker even if revocation failed.
That stop still requires the connection's exact retained worker/permit pair;
failure to stop is recorded as uncertainty, never release credit.

A worker can resume, return from the kernel port, and then lose publication to
lease revocation before the factory reacquires its lock. The factory will retain
the returned worker locally and stop that exact unpublished worker on this path.
It cannot rely on `owner._worker`, which is assigned only on publication.

The service will expose a trusted retained-failure lookup by physical identity.
This gives its bootstrap access to the retained token after `begin` raises. It
does not grant a public profile authority or unlock the gate. Explicit live
reconciliation still requires fresh trusted observations and a valid writable
journal. An absent or poisoned journal, incomplete first frame, or uncertain
visible tail remains deliberately held; there is no automatic truncation,
replacement-handle adoption, or unchecked release in this unit.

The existing adapter requires the exact `OwnedRuntimeFactory` class. This new
`DurableOwnedRuntimeFactory` is a generated connection unit until a separately
reviewed adapter migration connects it. No adapter or native compatibility is
claimed.

New deterministic cases will cover failed local revocation with owned stop,
revocation between returned worker and publication, and retained failure lookup.
Earlier case assertions remain unchanged. Execution requires root review.
