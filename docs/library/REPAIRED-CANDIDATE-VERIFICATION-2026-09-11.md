# Repaired candidate: complete-tree verdict

Source `6697dffc30c98e97b22ecc9a5a35dfd3e8a91f5d` records **2,535 passed,
one failed and two skipped** across 2,538 cases. The aggregate remains FAIL.
The only failure is the unchanged AS7/C21 assertion requiring the unavailable
original AT6 child exit. No new product failure appeared in this run.

The guarded observation finished at 2026-09-11T18:09:32.491403Z. Main tests took
1,448.233 seconds and the two original media cases took 4.079 seconds:
1,452.312 test-process seconds, or 1,465.893 seconds including collection and
launcher overhead. This is a complete two-process partitioned tree, not a
monolithic pytest invocation. The private GPL FFmpeg test tools do not ship.

Collection, execution reports and XML agree on every case exactly once. All
2,497 prior cases remain; 41 new regressions cover Unicode retrieval, capture
display semantics and required runtime notices. Only the previously prohibited
S21 real-client file is absent. No existing test, behavior assertion, expected-
failure marker or P4 guard was edited.

This run explicitly uses `--runxfail`. The original SEC-06 assertions now pass
with the Unicode repair, while their strict expected-failure marker remains
unchanged. The earlier normal focused run's strict XPASS failure and the older
complete run's xfail stay archived; this new result does not rewrite them.

The source contains search repair `41c0d1d`, capture display `15e3f7e`, Lightning
2.6.6 pins `63f7de9`, and setuptools runtime/notice repair `9ea755b`. Their named
suites were independently executed in worktree and checkout before integration.
The complete tree qualifies their combined source for the authorized replacement
candidate build. It does not establish installed-browser, real-client or security
acceptance; those observations and retained release decisions are separate.

Proof: [complete membership, raw results and instruments](proof/ryan-final-partitioned-03-2026-09-11/SHA256.json).
The missing AT6 exit remains Ryan's release disposition. Do not manufacture a
historical exit or relabel the aggregate as passed.
