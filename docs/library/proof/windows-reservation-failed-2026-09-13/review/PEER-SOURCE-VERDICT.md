2026-09-13. Independent source review found no remaining actionable issue in the frozen Windows journal/startup/adapter proposal. All 28 entries in PINS.json match their declared size and SHA-256. Preparation manifest: 4f5cd502c563f7dc23b3be81bffd93429eea8c30434e56da96b4d49f5cc42ee7.

The observed-uncertainty poisoning defect is corrected: failed identity queries and returned seek/read/write results latch poison before propagation. Pre-I/O argument refusals do not invent native uncertainty. The journal retains uncertain handles, requires same-handle flush/readback confirmation and refuses stale confirmation after writes or observed failures.

The split startup persists WORKER_BOUND before resume. Blocking handshake/adoption/policy acknowledgement occurs outside the manager and reservation locks; publication rechecks the current owner. Failure handling retains the exact worker and preserves the original error. The migrated adapter requires the exact durable factory. The separate no-worker witness requires actual read-set retirement and no permit, owner, startup attempt, worker or pipe; it makes no child-exit or job-empty claim.

The cache/release contract relies on the fixed private ReservationService: physical exclusion plus token pending/revision checks serialize its journal callers and reject revocation during completion. I found no reachable second journal writer in that connection. This is not a claim that arbitrary concurrent direct stream/journal calls are safe. The API note now states that limit.

All 23 new control methods were read, including direct cached-clean uncertainty, split-start failure, no-worker cleanup and actual adapter/factory migration. The original 42 test method bodies remain unchanged; their fake Kernel adds only the documented finish_start helper. The final adapter change from 8107d3f5 to b43ce233 is exactly the two-line reconciliation comment correction, independently checked by reconstructing the prior text hash.

Reviewed final source identities:

| File | SHA-256 |
| --- | --- |
| windows_reservation_port.py | 910aa472888303d29655dacc355349f7a2876c97fb593f7f0dc6f148a9ca9dc6 |
| generated_worker_flow.py | 1ab240d60ceaca130ac85f5d2e908ef5895da5297f35d78a1caba1c62e622238 |
| generated_adapter_flow.py | b43ce2335da60f7879305903b5a89bf70352acd47dc5f336bc90757f6d7873bd |
| durable_lifecycle.py | f95cc8f2c61fd1953b642669ee4027a968660e39b97d9e84782fb83ac62abacb |
| asr_loading_adapter.py | 635d2c22db75d12ffe6965fb656fdca47450ccbbaeb4d8cc8aaff9fcc79dd243 |
| test_windows_reservations.py | f94d286c85075e3832d7c84ae4e3487339a132d364cd7acff4c7285c95a83c38 |
| test_reservations.py | 604a295d5e925b9a9d7f55750bfeb1ddcda3e6a9873d6d8d7f9e98c84d9b4b9e |

This is a source verdict, not a 65-case result or native observation. I did not execute/import candidate code, tests, FFI or launchers, inspect model artifacts, or change the proposal. Root separately owns guard/launcher review. Synchronous flush/close latency, real registry creation, native qualification, crash/restart authority and production runtime activation remain outside this verdict. Real entry points remain closed.
