# Five-record metadata graph result, 2026-09-13

The complete candidate03 metadata graph passes with 144 pinned packages and 287 active dependency edges. It reports no missing packages, conflicting constraints, wheel failures, incomplete evidence, manifest errors, marker errors, direct-URL errors or selection errors. This closes the two wheel-evidence gaps in the preceding graph by using the exact inspected local artifacts; no package version or public capture changed.

| Measurement | Actual result | Elapsed |
| --- | --- | --- |
| Author checker qualification, tool 468c4b | 68 passed; 0 failed/errors/skips/subtests; native/outer 0 | 6.1413821000023745 s |
| Independent root qualification, tool 36df84 | Same 68 ordered observations; all other counts 0; native/outer 0 | 6.037034900014987 s |
| Full graph, tool e8f43c | PASS, 144 pins / 287 active edges; native/outer 0 | 3.4340338000038173 s in driver; 3.9960709 s outer |

Both qualifications retain valid guards, no violations and unchanged 367-input preparations. The full graph retains valid guards, no violations, identical filesystem identities and all 313 captures/47 preparation records unchanged before and after. The original selection hash is `e9e6917fce8021173309790589ed79e71a5e43d891b7d31d2b7f7a7e412405aa`.

All five local entries retain null public URLs, `public_release_record=false` and `artifact_verified_in_this_invocation=false`. ANTLR 4.9.3 and proxy-tools 0.1.0 retain `requires_python=null`. The graph reads previously captured METADATA; it does not read or install their wheels. The separate proxy-tools MIT/BSD inconsistency and final notice packaging remain outside this result.

The source plan maps 1,050 files. It stores 63 new unique text payloads (2,050,594 bytes) and references 415 existing payloads (123,950,800 bytes) in the archive committed at `4827288`. That archive is required to reconstruct the complete preparations. It retains the original five-cap failure, the invalid 51/11 qualification and the valid three-record graph FAIL; none is relabeled. Current prose-write refusal and the full-graph preparation reader's basename-filter error remain in the new mapping. They did not run or alter the graph.

Root also reported compact rereads ce490d, 43ab38 and 3c2dcc of the final graph/guards. No separate raw tool objects were saved for those reads; this paragraph is a transcribed observation. The original e8f43c tool object is retained exactly.

This result supports the fixed Windows CPython 3.13 metadata dependency plan. Native import behavior, runtime compatibility, owned loader/session integration, durable recovery, model assets and release readiness still require their own evidence.
