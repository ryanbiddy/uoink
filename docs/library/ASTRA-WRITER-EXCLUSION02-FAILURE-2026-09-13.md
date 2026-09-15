# Windows writer-exclusion02 failed observation

The single writer-exclusion02 observation FAILED. Actual tool829f4f returned outer exit 1; the launcher records controller exit 1, receipt_valid=false and unchanged inputs. The controller reports PersistenceUnconfirmed with a null main result. No complete primary journal retirement was established.

The contender observation supplies narrower evidence. Its one exclusive OPEN_EXISTING attempt returned error 32 without a handle or content I/O. The controller records contender exit 0, an empty job and retired contender handles/read guard. Its target matches the primary physical journal, and the primary RESERVED head stayed unchanged through that contender's exit. Those observations do not satisfy the full case.

The ordinary child's local receipt records two generated segments, five operations, five released adoption handles and planned exit 0. The controller's later call tail contains primary wait/exit/job queries, nine closes and eight complete directory identity queries. It does not provide a successful main result. Do not infer complete primary cleanup from the child receipt or call names.

The controller recorded 6,425 monitored native calls and 6,461 dispatch/audit calls, valid guards, no denials, no pending pipe operations and no exhausted budget. The saved 1,566-byte journal contains INITIALIZED, RESERVED and WORKER_BOUND. There is no CLEARED frame. Its SHA-256 is 440b6e028d3ab6a63a9bdafedc7ddd4784fcd77b5cee9aa640362c6408aa9c91.

The source and passive call-tail analysis locate the likely refusal at a retained directory identity comparison. The differing field is unmeasured. A separate reporting-only proposal03 preserves the predicate and records only the already observed identity values. A future diagnostic needs its own root admission and remains a failed observation if the original assertions fail.

The proof preserves both source proposals, the actual admission and tool objects, complete generated run, two source reviews, diagnosis and fixed copy inventory. Diagnosis command/output transcriptions are labeled as transcriptions; they are not reconstructed raw tool objects. The sole model.bin is the exact 60-byte generated ASCII fixture. No real model artifact or installed support binary is copied. The source-preparation defects and documentary check failures remain distinct from this actual failed run.

No test assertion changed. No real model, recovery after restart, storage-failure behavior, production runtime, installation or release was accepted.
