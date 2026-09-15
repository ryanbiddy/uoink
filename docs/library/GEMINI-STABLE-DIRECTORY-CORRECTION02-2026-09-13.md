# Group A Source Review: Stable-Directory Identity Correction

## Directory Comparison and Call-Site Scope
The comparison function same_directory_identity at A-01:169–182 permits mutable directory byte lengths by checking that actual.size and expected.size are integers in the valid range 0 to (1 << 63) - 1. It preserves exact FileIdentity types, verifies directory is True on both sides, and requires exact equality for final_path, volume_serial, 16-byte file_id, and links.

Its call sites are strictly limited to directory contexts. In OwnedWin32Primitives.pin_exact_members at A-01:354–355, the check branches on expected.directory: directories evaluate same_directory_identity, whereas non-directories use strict FileIdentity equality. Non-directories must also have links equal to 1 at A-01:356. In _check_scope at A-02:98–100, the function checks each ancestor directory across the prefix chain and enforces case-folded final path prefix equivalence. Regular files and journals retain strict equality checks in WindowsJournalStream.identity at A-02:166–169 and WindowsGateRegistry.stage_created_handle at A-02:298–299, where size must be exactly 0.

## Refusal Integrity and Uncertainty Handling
The changes preserve refusal for reparse points, pending deletions, and invalid sizes. OwnedWin32Primitives.identity at A-01:317–330 queries FILE_ATTRIBUTE_TAG_INFO, FILE_STANDARD_INFO, and FILE_ID_INFO; it immediately raises KernelUnavailable if reparse tags or attributes are set, delete_pending is non-zero, or size is negative.

Retained-handle uncertainty semantics are preserved. When identity verification fails in pin_exact_members at A-01:360–364, the read set is marked unconfirmed without closing acquired handles. In _check_scope at A-02:101–108, comparison failures populate diagnostic state on PersistenceUnconfirmed while leaving ancestor handles unreleased. In WindowsJournalStream at A-02:171–173 and A-02:184–186, I/O exceptions poison the stream, preventing clean gate release in WindowsGateRegistry.release at A-02:377–391 without silent handle closure.

No actionable defect was found within the selected changesets A-03 and A-04. External context is absent from Group A: native entry points real_kernel_port at A-01:18–20 and real_windows_reservation_service at A-02:18–20 raise exceptions; process recovery, ctypes bindings, and external supervisor runtime are not selected.

## Verification of Test Bodies
The eleven test methods in A-05:82–244 reach the changed comparison paths and distinguish permitted directory growth from forbidden identity or regular-file alterations.

Six tests exercise _check_scope and registry gates:
- test_growth_at_each_ancestor_allows_confirmed_clear_and_release at A-05:82–111
- test_other_directory_fields_refuse_before_journal_open at A-05:112–124
- test_other_field_change_after_clean_poisons_and_retains_gate at A-05:125–140
- test_invalid_directory_size_observations_still_refuse at A-05:141–151
- test_dataclass_equality_and_refusal_diagnostic_keep_both_sizes at A-05:214–230
- test_growth_does_not_grant_release_after_flush_failure at A-05:231–244

Five tests exercise pin_exact_members directly using the local InertIdentityAPI at A-05:30–66:
- test_directory_pin_accepts_growth_and_retains_current_observation at A-05:152–163
- test_directory_pin_keeps_other_fields_strict at A-05:164–174
- test_regular_file_size_change_refuses_and_retains_handle at A-05:175–186
- test_regular_file_exact_identity_still_pins at A-05:187–193
- test_native_identity_reparse_pending_and_negative_checks_remain at A-05:194–213

Visible test bodies confirm that altering final_path, volume_serial, file_id, links, directory flag, or regular-file size causes immediate refusal. The imported fixture module test_windows_reservations is unselected, so fixture behavior is unreviewed, and none of the eleven tests were executed.

## Unmeasured Limits
This review evaluates only source text in A-01 through A-05. It does not certify execution timing, native correctness, OS sandboxing, power-loss resilience, concurrency safety, model safety, or release acceptance.
