# Fixed cancellation driver qualification proposal

This unexecuted fake qualification targets the new generated adapter cancel mode,
consumption helper and passive journal observer in windows-journal-cancel-proposal01.
It preserves the four original test files and ordered 81 cases from the committed
stable-directory qualification. Append eight focused cases; no existing assertion
or accepted result is changed.

The new cases construct the actual exact port class with inert services, exercise
the actual new consumption helper with a fixed passive stream, and exercise the
actual journal observer with the existing fake retained journal. They cover a
successful single-segment cancellation, mode refusal, missing acknowledgement,
preservation of a close error, forbidden second result or extra wire event, and
retained journal/gate identity checks including missing-key/None refusal.

These are driver and observation checks. They do not simulate a passed native
adapter shutdown or Windows flush. Production cancellation/stop/adapter-finally
methods remain unchanged and the separately reviewed native case must measure
their connection to the retained journal.

Reuse the fixed C:\Python314\python.exe -I -S -B source guard and launcher. Add only
the two existing writer helper modules required by the exact adapter import and
the new test module, plus changed membership/input counts and fresh label. Retain
all ten final guard checks, explicit startup environment binding, closed content
reads, metadata/registry traps, immediate native exit and before/after hashes.
Root review and distinct admission are required before any run. No execution is
authorized by writing this proposal.
