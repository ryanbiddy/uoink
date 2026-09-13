2026-09-13. Source review of the initial unexecuted draft found three state details to correct before qualification. Preserve the initial bytes under drafts/snapshot_lifecycle.initial-unexecuted.py. No source or test was executed.

First, close_and_join released the manager lock during the port's shutdown operation and could later overwrite a concurrent quarantine with NATIVE_STOPPED. Require the record to remain NATIVE_RUNNING before recording successful shutdown. An intervening quarantine stays terminal until a separately qualified recovery path exists.

Second, concurrent operations on one owned worker could race a native cursor. Refuse a second active operation at the state boundary; the proposed protocol is serial per owned worker. Shutdown retains its separate control path.

Third, repeated close calls on an already exhausted stream could issue unnecessary cancellation requests. Return without another port call once the stream is exhausted. The session still owns all worker/cursor resources until verified shutdown.

These changes prepare the state proposal. They alter no accepted adapter, frozen assertion, prior proof or production source.
