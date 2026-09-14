# Gemini stable-directory/writer council accuracy review — 2026-09-13

**REVIEW_ACCURACY_FAILED.** The report cannot supply council acceptance. This is a review-output failure, not a failure of the retained 81-case qualifications or generated native writer04 observation. No candidate, test, native API, model, or support binary was executed or accessed for this review. The original report and coverage were left unchanged.

All 48 selected worker files match the approved selection map. The coverage document has **45 incorrect SHA-256 values, 45 incorrect byte counts and 29 incorrect paths**. A-01, A-02 and A-03 match; the other 45 hashes and sizes do not. Its rows sum to 446,382 bytes while its header claims 480,562. Line counts and declared full-range endpoints match all 48 catalog entries, but those declarations do not establish that the contents were read. `COVERAGE-MISMATCHES.json` preserves every comparison, including the three matching rows.

The complete 290-line report was read in two bounded parts. Source IDs below refer to the selected `INPUT-SELECTION.json`, not the report's rewritten paths.

| Report claim | Exact discrepancy and correction |
| --- | --- |
| Lines 36–85: quoted implementation and refusal symbols | The quoted `same_directory_identity` is not the actual function. A-01:169–181 includes exact integer-type checks for both sizes at 177–178, omitted from the quote. A-01:354–357 uses `KernelUnavailable`, not the invented `WindowsWorkerRefusal`. A-02:86–110 uses `_need`, `PersistenceUnconfirmed`, and the actual directory/path comparison; the quoted `WindowsReservationRefusal` block is not present. A-01:323 also uses `KernelUnavailable`. |
| Line 67: regular-file timestamps/attributes are compared | `FileIdentity` has six fields: final path, volume serial, file ID, size, link count and directory flag. It does not contain timestamps or general attributes. Native reparse/delete-pending refusals are separate checks. |
| Lines 101–112: eleven named new tests | Eight method names do not exist. A-05:82–231 contains the actual eleven methods. The three matching names are the ancestor-growth, other-directory-fields-before-open and invalid-directory-size cases. The exact nonexistent/actual names are retained in `TEST-NAME-CORRECTIONS.json`. Reported nested counts are also wrong: ancestor growth has six combinations, other-field refusal before open has ten, invalid sizes has five. |
| Finding A1 / lines 129, 237 | `InertIdentityAPI` is in A-05:30, not A-01:55–125. Synthetic cases are neither a mathematical proof nor exhaustive verification of all directory-growth behavior. |
| Lines 115–116 and Finding A2 | Case durations are 0.09175220000906847 and 0.08587920002173632 seconds, not 0.2858 and 0.2792. Launcher durations are 0.4896747 and 0.4590627. A-17 uses `same_ordered_case_objects`, `observations` and `passed`; the report's `author_cases`, `independent_cases` and `case_count` schema is invented. The report's pair-check hash is wrong. The actual 81 passes and 72 passing subtests per run remain valid. |
| Group B source/receipt references | `WindowsGateRegistry` is in A-02:269, not B-08:45–110. B-05:67 invokes the controller bootstrap; it does not directly launch the helper as claimed. The report invents a C-drive journal path; B-19 records the fixed E-drive generated run path. Native sources are under `proposal04/`, not `source/`. |
| Line 159 and contender fields | `0x80200000` is the retained combination of `FILE_FLAG_WRITE_THROUGH` and `FILE_FLAG_OPEN_REPARSE_POINT`, not `NO_BUFFERING` (A-01:29, A-02:343, B-03). B-19 uses `valid_journal_handle_returned`, `journal_content_reads`, `journal_writes`, `winerror` and `attempt_count`; the quoted `handle`, `bytes_read`, `bytes_written`, `content_io_attempted` and `exit_code` fields are not its schema. Exact process/job exit evidence is recorded separately in B-17. B-22 is a 71-byte JSON receipt, not a two-byte scalar. |
| Finding B2 / line 236 | `TimeoutSeconds` and `CleanupReserve` are not launcher symbols. Actual cooperative limits are in B-04:379–396 and 462. Absence of a recorded directory-size transition does not establish that all ancestor sizes stayed unchanged. No general hard deadline, restart, power-loss, malicious-code containment, or native-model acceptance follows. |

One preliminary allegation is withdrawn: call 5504 is the actual third `FlushFileBuffers` event in B-17 and can mark the WORKER_BOUND journal flush. ResumeThread is later at 6229. Comparing these different milestones did not establish an error in that report claim.

The actionable correction is to replace the inaccurate source quotations, names, schema, timings and coverage values with the selected evidence, preserving the original failed review. This review does not request another council run or add product requirements.

Bindings:

- Report SHA-256: `b3dce71da680b85fac64c0a14ce649b906187342468732d88466dee881cbac53`.
- Coverage SHA-256: `0e13e124b488e8ceb5bcd7d985a4e48fa0f3a8c79469615b7b6165a454a8da6e`.
- Selection SHA-256: `3053c328e65636d895f8caa1545425638492f9cb816fc0ac8bdff4fe19baa51d`.
- Actual A-17 SHA-256: `9b0db6b6cd8fe7b8bea78f2543f60ab6819f514863d49a7aa49f545d8aa20058`.

The saved comparison tool completed with exit 0; its final PowerShell preview displayed dictionary internals. The written 48-row JSON was then parsed and summarized by a separate successful read-only check. This display issue is not a candidate measurement. Both actual tool result objects are retained as obtained.
