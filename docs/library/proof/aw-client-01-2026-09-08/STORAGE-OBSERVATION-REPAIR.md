# Storage observation setup, 2026-09-08

The first setup attempted to hash and rename only this fixture's profile/Uoink
directory while stdio child 71588 was alive. Windows denied the index-file hash
and directory rename because the child held the SQLite files open. No storage
failure request ran, no directory moved, and no product result was measured.

Repair: use the already-prepared held corpus directory as the unavailable
storage boundary. Verify containment and absence of reparse points, move only
the task-owned items directory to a fresh sibling, and request the frozen item
and excerpt through the still-running real client. Record exact domain results
and per-request times, child liveness, the unchanged index identity, and absence
of a replacement corpus. Restore the directory after the observation. This
tests unavailable corpus storage, not disappearance of an open Windows SQLite
file. The database-disappearance case remains unobserved in this client setup.
