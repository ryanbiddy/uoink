# Final candidate verification, 2026-09-09

Candidate `12ce8a5fbd34c3472d55ae76afa17535b43c5282`: **2,429 passed, 13 failed, 3 skipped and 1 xfailed**, 1542.35 seconds.
Result remains **FAIL**. Only `tests/library_work_astra/test_phase3_s21.py`
is excluded under the standing queue. Existing tests remain frozen. The
[complete raw proof](proof/ryan-final-kit-tree-01-2026-09-09/SHA256.json) contains commands, environment,
log, XML, every case outcome and comparison with 8fc6a40.

The original new-package C22/P4 checks and build source/hash are in the
[release notes](RELEASE-NOTES-LIVING-LIBRARY.md). They do not change any
whole-tree failure. No installed/client credit or main merge is inferred.

| Failed case | Original assertion message |
|---|---|
| `tests.library_work_astra.test_phase3_acceptance7::test_as7_c21_at6_receipt_records_process_exit_status` | AssertionError: ('Retained AT6 receipt has no explicit successful process exit status', {}) assert ({}) |
| `tests.library_work_astra.test_phase4_aw2_acceptance::test_d13_replace_syscall_cannot_complete_after_timeout` | assert (False)  +  where False = is_set()  +    where is_set = <threading.Event at 0x22abc6975f0: unset>.is_set |
| `tests.library_work_astra.test_phase4_aw3_acceptance::test_d12_retry_keeps_ownership_of_interrupted_temp` | assert (0 == 1)  +  where 0 = len([]) |
| `tests.library_work_astra.test_phase4_aw3_acceptance::test_d12_control_hard_purge_removes_unedited_recorded_temp` | assert (0 == 1)  +  where 0 = len([]) |
| `tests.library_work_astra.test_phase4_aw3_acceptance::test_d12_recorded_temp_path_does_not_authorize_deleting_user_replacement` | assert (0 == 1)  +  where 0 = len([]) |
| `tests.library_work_astra.test_phase4_aw3_acceptance::test_d13_timeout_never_publishes_or_rolls_back_over_user_bytes[visibility]` | assert (False)  +  where False = is_set()  +    where is_set = <threading.Event at 0x22abc6d1f10: unset>.is_set |
| `tests.library_work_astra.test_phase4_aw3_acceptance::test_d13_timeout_never_publishes_or_rolls_back_over_user_bytes[user_edit]` | assert (False)  +  where False = is_set()  +    where is_set = <threading.Event at 0x22abc6d1bb0: unset>.is_set |
| `tests.library_work_astra.test_phase4_aw3_acceptance::test_d13_timed_out_writer_cannot_erase_a_later_successful_sync` | assert (False)  +  where False = is_set()  +    where is_set = <threading.Event at 0x22abc6d1df0: unset>.is_set |
| `tests.library_work_astra.test_phase4_aw_acceptance::test_purge_removes_intent_owned_actual_temp_name` | assert 0 == 1  +  where 0 = len([]) |
| `tests.test_existing_index_read_open::test_read_open_does_not_migrate_then_explicit_backend_promotes` | assert <index.Index object at 0x0000022ABB317E50> is <index.Index object at 0x0000022ABB620550> |
| `tests.test_install_receipt_c22_kit::test_plan_inno_does_not_execute` | AssertionError: assert '/ISOLATEDPROFILE=' in 'E:\\AI\\projects\\uoink\\checkouts\\Yoink-library\\_scratch\\c22-kit\\t-adkqasb_\\Uoink-Setup-synthetic.exe /VERYSILE...brary\\_scratch\\c22-kit\\t-adkqasb_\\receipt\\profiles\\empty /PORT=54207 /NOCLOSEAPPLICATIONS /NORESTARTAPPLICATIONS' |
| `tests.test_install_receipt_c22_kit::test_synthetic_helper_scenarios_and_verdict` | AssertionError: ('manual_first', {'id': 'manual_first', 'status': 'fail', 'registered': {'register_source': {'ok': True, 'source': {'s...r': 'not found', '_http_status': 404}, 'episode_id': None, 'reason': 'declared episode identity not found', ...}, ...}) assert 'fail' == 'pass'      - pass   + fai |
| `tests.test_install_receipt_p4_kit::test_prepare_fixture_seeds_synthetic_items_and_keeps_apply_false` | FileNotFoundError: [Errno 2] No such file or directory: 'E:\\AI\\projects\\uoink\\checkouts\\Yoink-library\\_scratch\\final-kit-tree-01-0\\t291\\r\\p\\Uoink\\settings.json' |

The original AT6 shell wrapper did not retain its child process exit. Recovered
artifacts and the replacement AT7 cannot reconstruct it. The mirror/read
setup conflicts have two exact pending proposals; no changes were applied.
Three receipt-kit assertions retain older contracts: `/ISOLATEDPROFILE=`,
the stub lacking the current podcast feed route, and nested `Uoink/settings`
instead of the explicitly isolated profile's settings. The reviewed actual
instrument routes are measured separately. Changing these frozen assertions
or setups requires an explicit ruling; production must not regain an unsafe
or obsolete path to make them pass.

The candidate is prepared for Ryan's one throwaway-account session using
[the runbook](INSTALL-RECEIPT-RUNBOOK-2026-09-09.md). Astra then reviews actual
Inno C22 and Phase 4 client/browser receipts. Until the failures and installed
gates have a recorded disposition, the candidate is not approved for release.
Phase 6 speakers remain outside scope, Phase 5 Part B is deferred, autonomous
filing stays at 0.90 with apply false, and the X HTTP 403 stays blocked.

The three additional failures are assigned in the [receipt-test disposition brief](RYAN-FINAL-RECEIPT-CONTRACT-DISPOSITION-BRIEF-2026-09-09.md). No fixture correction is bundled with this report.
