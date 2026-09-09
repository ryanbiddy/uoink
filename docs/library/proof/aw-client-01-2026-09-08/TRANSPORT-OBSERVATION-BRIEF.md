# Broken-child transport observation, 2026-09-08

The ordinary explicit reconnect has completed: child 61780 was replaced by
71588, and two fresh item calls returned the earlier content. The corpus
disconnection observation is separately recorded and its files restored.

For a distinct broken-child transport case, suspend only the recorded fixture
stdio child 71588 while its recorder and real Claude Code client remain alive.
Request one fresh bounded get_library_item call. The client is configured with
a 10,000 ms per-server timeout. Retain request and actual failure timestamps;
the acceptance ceiling is 15 seconds from that request, not model start.
Do not reconnect or retry that request. A separate task-owned guard process
resumes this exact child automatically after 90 seconds or a local release
signal, whichever occurs first. Record process identity and suspend/resume
results. Resume after the observation, then exit this client cleanly.

This is a suspended-child transport-timeout observation. It does not establish
failed-launch behavior or a live service's storage-refusal latency.
