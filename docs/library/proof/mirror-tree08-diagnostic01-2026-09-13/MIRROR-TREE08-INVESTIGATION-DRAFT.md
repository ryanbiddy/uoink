# Mirror cancellation investigation, September 13

The full committed tree08 is still running at source 9dd0cfb. Do not modify it
or run a competing mirror process while it holds the shared Windows admission
gate. The first new failure is test_live_worker_lease_blocks_a_second_mirror
in test_phase4_av5m3_isolation.py, after that file's real-worker startup and
timeout/user-edit cases passed. Many later mirror cases then fail after two or
four seconds. This pattern suggests a retained gate or operation; it is not yet
a root-cause verdict. The complete result must remain failed and be sealed first.

After that run finishes, inspect its original tracebacks and source/runtime
bindings. Run the unchanged AV5m3 file once with the passive gate-state plugin
in a fresh guarded process and fresh label mirror-tree08-diagnostic01. The plugin
may record operation/owner counters, owned process identities and thread stacks,
but may not reset globals, release a gate, stop a child, change assertions or
alter any fixture. Keep the original main/media partition and all membership.

If the focused file passes, that is a narrower result. Use the captured original
failure and exact lifecycle boundary to specify a deterministic new diagnostic,
with a separate brief before execution. No blind full-tree retry. A product
repair must preserve uncertain-child exclusion, late-write refusal, alias safety
and independent user edits, and prove that admission returns after known death.

Astra owns the diagnosis, review and integration. A bounded Control Room Gemini
repair can follow once the complete failure and reproduction identify its scope.
No frozen tests, live library, port 5179, paid API, model or ordinary client use.
Package09 and all website/marketing work wait for repaired product qualification.
