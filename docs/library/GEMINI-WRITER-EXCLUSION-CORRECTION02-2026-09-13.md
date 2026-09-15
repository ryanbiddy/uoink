# Group B Source Review: Writer-Exclusion Connection Correction

## Contender Binding and Startup Authority
The contender binding and authority checks strictly precede primary worker creation. In GeneratedLifecyclePort._bind_contender at B-02:71–85, mutual identity assertions verify port and contender instances, primitives equality, unstarted port state, and null worker, read_set, and adapter_startup references before adapter entry.

In GeneratedLifecyclePort.create_suspended at B-02:228–248, adapter startup is validated against adapter_profile and generated_binding, requiring Phase.NATIVE_RESERVED and permit match before appending owned_start_validated. OwnedContender.run at B-01:112–132 enforces that the primary journal token remains in Phase.NATIVE_RESERVED with flush_successes equal to 2 and token.worker as None. The primary reservation token, raw bytes, and head are verified identical across contender execution at B-01:158–162. No ordering or identity bypass was found.

## Writer Open Attempt, Refusal Condition, and Cleanup
In ContenderObservation.run at B-01:38–67, the contender attempts an independent open against the physical journal path using CreateFileW with JOURNAL_ACCESS, zero share mode, OPEN_EXISTING, and JOURNAL_FLAGS at B-01:44–45. Line B-01:52 requires invalid handle return and Win32 error 32 (ERROR_SHARING_VIOLATION). Unexpected handle success retains the handle at B-01:51 to prevent reuse while still failing the check. Contender role restriction in NativeMonitor.call at B-04:470–471 excludes ReadFile and WriteFile, ensuring zero journal reads and writes.

Directory scopes are retired with verified handle closures at B-01:53–58. The contender worker inherits solely one passive fixture guard at B-01:135 and B-01:97–102, with child_control_handle absent. Normal exit confirms quiescence via _observe_graceful_exit at B-01:152 before releasing the guard at B-01:156. On exception, lines B-01:164–180 recover partial workers from primitives.workers, attempt _stop_partial_worker for returned creations, append notes on secondary failures, and mark worker.unconfirmed and read_set.unconfirmed without claiming release. Monitored PID, creation time, milestones, and wait states are derived from primitives and system structs rather than self-reported assertions.

## Bootstrap FFI, Budgets, and Launcher Verification
In dummy_bootstrap.py, FixedNativeDispatch at B-04:274–356 wraps thirty-three Win32 functions, validating calling thread, function pointers, and arguments under CALL_CONTEXT. Pending I/O finalization at B-04:633–635 immediately aborts the process via PROCESS_ABORT if pipe operations remain in pairs. Work budget limits of 16,384 calls and 60 seconds transition to a cleanup budget of 64 calls and 10 seconds at B-04:378–411. These cooperative call checks govern dispatch points but do not establish a hard deadline for arbitrary native work.

The launcher run_writer_exclusion04.ps1 validates exact hashes for eighteen sources, three controls, nine native support files, and five fixtures at B-05:12–54. Post-run receipt assertions at B-05:99–300 verify zero model calls, receipt schemas, milestone ordering, error 32 refusal, and exclusive post-exit journal bytes. No connected source mismatch was identified between bootstrap expectations and launcher assertions.

## Actionable Findings and Defect Scope
No actionable defect was found within the five reviewed source files B-01 through B-05. External implementations—including snapshot_reservations, windows_reservation_port, win32_worker_connection, and kernel Win32 sharing enforcement—are unreviewed.

## Unmeasured Limits
This review evaluates source text only. No execution receipts were selected. It cannot qualify native runtime outcomes, error code observations, exit timings, OS sandboxing, power-loss recovery, concurrency hazards, model execution, or release readiness.
