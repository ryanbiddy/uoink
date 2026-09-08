**NOT ACCEPTED — Phase 4, run AW, 2026-09-08.**

Reviewer: codex (Astra). Contract: `phase4-v1-2026-09-08`.
Reviewed worktree HEAD: `5a1152e34e542d4d854ed6263d6fb468d70774a8`.
The [AW brief](PHASE4-AW-BRIEF-2026-09-08.md),
[contract](PHASE4-CONTRACT-2026-09-08.md), and
[AV-1r rulings](PHASE4-AV1-RULINGS-2026-09-08.md) govern this decision.

The seven supplied Phase 4 suites pass all **135 tests**, including the 11
mirror-wiring tests. The four inventory suites pass another **16 tests**.
Independent acceptance checks reproduce **31 failures and one passing control**.
The failures include publication after deletion, export beyond the consented
allowlist, deletion of an unowned temporary file, overwrite of a user edit, and
a vault write completing after timeout. These require repairs before acceptance;
they cannot be deferred as client-affordance conditions.

Only this document and
[test_phase4_aw_acceptance.py](../../tests/library_work_astra/test_phase4_aw_acceptance.py)
are deliverable changes. Production code and the supplied tests are unchanged.
No model, resident helper, HTTP listener, port 5179, live index, other checkout,
package installation, commit or merge was used. Runtime checks used synthetic
indexes and staged copies inside this dedicated worktree. Paths in the AW copy
manifest were read as evidence and were not followed to their source files.

The receipt names candidate `d4d99bb`. Its four Phase 4 modules and
`library_work.py` are byte-unchanged at the reviewed HEAD. `server.py`,
`uoink_mcp.py` and `uoink_mcp_tools.py` have subsequent changes, principally
capture ownership and activity-tool handling. The fresh tests below apply to
HEAD; the earlier client receipt applies to its named candidate and scope.

The rerun used Python **3.14.6**, pytest **9.1.1**, and the existing MCP SDK
**1.28.1**. It does not certify the requirements pin or an installed interpreter.

| Supplied suite | Passed |
|---|---:|
| `tests/test_library_resources.py` | 50 |
| `tests/test_library_resource_trust.py` | 6 |
| `tests/test_library_prompts.py` | 8 |
| `tests/test_phase4_stdio.py` | 9 |
| `tests/test_library_briefs.py` | 26 |
| `tests/test_library_mirror.py` | 25 |
| `tests/test_library_mirror_wiring.py` | 11 |
| Phase 4 total | **135** |
| `tests/test_stdio_clip_tools.py` | 5 |
| `tests/test_c01_mcp_stdio.py` | 4 |
| `tests/test_phase0_registry_capture.py` | 4 |
| `tests/test_installer_files_complete.py` | 3 |
| Inventory total | **16** |

The final combined supplied-suite run was **151 passed in 28.15 seconds**.
Inventories agree on **31 stdio tools, five resource templates, four prompts,
and 87 registry tools**. The 25 legacy stdio names remain present. The installer
and staging lists include all four Phase 4 modules; the client example uses
separate console-interpreter and script arguments with UTF-8 settings.

Two environment issues were resolved or separated from product defects. The
first run returned 119 passed/16 failed because the long temporary paths exceeded
the mirror's 240-byte final/temp-path policy. A shorter base still left 13 mirror
failures. The successful run overrides only pytest's temporary directory names;
it changes no assertions, path limit or application behavior. The optional
`test_installed_library_runtime.py` smoke also failed: its `-I` child computes a
user-site path under the isolated `APPDATA` and cannot find the installed SDK.
A separate `-I` staged-import check explicitly added the existing third-party
site-packages directory, kept application/profile paths isolated, excluded the
checkout from `sys.path`, imported `server`, `uoink_mcp` and all four Phase 4
modules from the stage, and discovered 31 tools. That check passed. The original
installed-runtime test is not reported as passing, and an Inno install remains
unverified.

The acceptance regressions use real disposable SQLite rows, canonical cards and
the real brief store. The control test successfully exports an owned item and
publishes/reads a valid cited brief. Race tests insert a change at a specified
read/write boundary; they do not replace the contract logic with a fake result.
The final regression run was **31 failed, 1 passed in 6.86 seconds**. Failures are
intentional contract assertions, with no `xfail` or skipped defect cases.

The following are the required repairs. Test names refer to the new file above;
each listed case failed on the reviewed HEAD.

| Defect and gates | Reproducer(s) | Finding and exact repair |
|---|---|---|
| AW-D01 — service deadline; P4-05, D1 | `test_d1_real_index_lock_obeys_service_deadline` | A held index lock delays the refusal until 2.414 seconds. `LibraryReader._operation` now starts at admission, but `_lock`/snapshot acquisition still wait without the remaining deadline. Use bounded lock/query/I/O acquisition and carry one deadline through backend acquisition and actual adapter serialization. Return by the deadline; detecting it after a blocked operation finishes is insufficient. |
| AW-D02 — snapshot coherence; P4-01, P4-05, D2 | `test_card_refuses_deletion_during_build`; `test_d2_shelf_refuses_clip_change_during_snapshot` | A card read returns source text after deletion during card construction. Shelf coherence compares item rows but discards the second snapshot's clips, so a clip change during construction also returns the old page. Recheck deletion and every canonical source input before serving; compare clips and bounded corpus inputs as well as item rows across all shelf members. Refuse concurrent change instead of returning cached old evidence. |
| AW-D03 — incomplete path redaction; P4-04, D6 | `test_d6_redacts_complete_explicit_absolute_paths` (2 cases) | `/secret` is returned unchanged; a quoted drive path containing spaces leaves ` Folder\secret.txt` visible. Recognize complete explicit absolute paths, including one-component POSIX paths and quoted paths with spaces. Preserve the original byte/hash bindings and report the full redaction span. The module's narrower disclosure is not an approved amendment. |
| AW-D04 — error disclosure; P4-04 | `test_refusal_does_not_echo_unknown_request_key` | `_strict_arguments` echoes an attacker-controlled unknown field name in `error.details.fields`. Return fixed field categories/counts or other non-source diagnostics. Apply the same rule to prompt and citation validation. Escaping the output fence does not satisfy the separate prohibition on quoted attacker input in refusals. |
| AW-D05 — stale review prompt; P4-07 | `test_reshelve_review_refuses_changed_run_binding` | A real stored preview still renders after its run revision changes. `_reshelve_review` checks expiry and projection only. Reuse/extract the Phase 2 preview-binding checks as a pure report read, covering run/taxonomy/evidence/delta bindings without minting a preview, approving, applying or reaping leases. |
| AW-D06 — brief hash contract; P4-08 | `test_brief_hashes_use_contract_canonical_serializer` | `library_briefs.canonical` uses compact unescaped JSON, whereas the frozen new structured hashes use `library_cards.serialize_card`. The same input packet therefore has a different hash. Use the contracted serialization consistently for packet, job, request, citation and artifact hashes. Do not silently keep incompatible addresses under the same contract version. |
| AW-D07 — brief freshness; P4-08, P4-11 | `test_brief_rechecks_source_before_atomic_publication`; `test_brief_read_invalidates_changed_projection` | Deletion after `_build_packet` validation but before `_write_artifact` still yields an accepted receipt. Later reads check only sampled source cards and keep serving a brief after projection changes. Build a coherent report snapshot, recheck all source/queue/run/taxonomy/projection bindings at atomic publication, and validate bound dependencies on reads/discovery. Preserve the required receipt-before-freshness idempotency behavior. |
| AW-D08 — local brief purge wiring; P4-08, P4-11 | `test_server_hard_purge_cleans_briefs_when_mirror_disabled` | `_purge_trash` removes the item but leaves its service-owned brief document and packet when the mirror is disabled. Its only new hook is guarded `_mirror_event`. Invoke local brief cleanup independently of corpus-mirror consent/availability, retain content-free receipts, and track/retry incomplete cleanup. |
| AW-D09 — rebuilding desired mirror state; P4-09–P4-12 | `test_resync_rebuilds_from_current_sources_without_prior_events`; `test_bulk_wiring_events_schedule_current_derivatives` (3 cases); `test_scope_narrowing_cleans_previously_exported_items`; `test_brief_tool_publication_emits_committed_mirror_event` | A fresh resync exports none of the two items in its preview. The identifier-free `source_refresh`, `apply` and `undo` seams schedule no affected content; narrowing scope leaves prior exports; successful brief-tool publication emits no event. Reconcile desired state from current authoritative sources on enable/resync/recovery, supply affected identities or reconcile bulk events, emit a guarded post-commit brief event, and schedule removal of excluded derivatives. Keep corrections authoritative and outside the mirror ledger. |
| AW-D10 — real brief/mirror interface; P4-09, P4-11 | `test_real_brief_dependencies_enforce_mirror_allowlist`; `test_real_brief_mirror_is_removed_when_dependency_deleted` | `BriefStore.latest_valid` returns identity metadata and `read` returns `contents`; neither returns the top-level dependency list expected by `Mirror`. The writer serializes that envelope, records empty dependencies, exports a brief citing excluded item `b`, and leaves it after deletion. Consume the real fenced brief representation or a shared validated dependency API; require every source dependency to be allowed and retain those identities for cleanup of every generated version. Unknown dependencies must fail closed. |
| AW-D11 — disabled deletion delivery; P4-11 | `test_disabled_mirror_retains_pending_deletes_and_cleans_owned_files` | Disabling hides a known pending purge (`deletion_pending` becomes zero), and `resync`/purge return early. Separate export enablement from owned-file deletion accounting. Keep prior destination/ownership state visible and permit deletion-only cleanup while disabled, including events received after disablement. Never report completed purge merely because export is off. |
| AW-D12 — manifest and temporary-file ownership; P4-09–P4-11 | `test_missing_manifest_stops_replacement_for_reconciliation`; `test_unowned_temp_named_like_item_is_preserved`; `test_purge_removes_intent_owned_actual_temp_name` | Losing the manifest still allows replacement based on ledger ownership. Cleanup deletes an unowned `<item-hash>.tmp`, but misses a real interrupted writer's 24-hex-suffix temp because `_OUR_TMP_RE` accepts 12. Stop writes for missing/corrupt-manifest reconciliation after initialization. Record exact temp ownership before writing and delete only those recorded artifacts, covering the writer's actual naming scheme. |
| AW-D13 — replacement races and cancellation; P4-09–P4-11 | `test_mirror_rechecks_authoritative_deletion_before_replace`; `test_mirror_preserves_user_edit_between_hash_and_replace`; `test_timed_out_vault_worker_cannot_publish_after_return`; `test_destination_lock_is_shared_across_local_ledgers` | Replacement rechecks only ledger generation, allowing deleted content and overwriting a newly edited target. The daemon continues writing after timeout/lock release; separate data roots do not share a destination lock. Serialize by canonical destination, retain exclusion through worker termination, enforce one bounded attempt, and recheck authoritative deletion/scope/dependencies plus target bytes immediately before replace/delete. Implement cancellable isolated vault I/O. The AV-2 brief does not forbid a child process; the module's claimed exemption is unsupported. |
| AW-D14 — durable delivery receipts; P4-10 | `test_manifest_failure_keeps_recovery_intent_and_no_success` | An injected manifest-write failure returns `synced:2` and clears the item intent; inspection found zero retained intents. Propagate manifest failure, retain recoverable intents, and acknowledge synchronization only after verifying durable file and manifest state. Give `Library.md` the same crash-recovery treatment. |
| AW-D15 — replacement volume; P4-09, P4-11 | `test_missing_volume_marker_is_not_adopted_after_prior_sync` | After a successful export, replacing the fixture vault with an empty directory at the same path causes automatic marker creation and export. Distinguish first initialization from a previously bound destination whose marker is missing; refuse the latter until explicit reconciliation/consent. Keep offline deletions pending. |
| AW-D16 — mirror rendering; P4-04, P4-09 | `test_shelf_links_resolve_to_exported_item_files`; `test_generated_index_escapes_raw_identity_markup` | Shelf links use `Library/...` relative to `Shelves/`, so they miss the generated item. `Library.md` inserts a raw stable ID into backticks; a backtick-containing ID exposes raw image HTML. Render every untrusted display field through the shared safe escaping rules, including identities, and construct links relative to the containing generated file (`../Library/...` for shelves). |

D1's admission baseline and D2's ordinary between-request source binding were
repaired, but AW-D01/D02 prevent closing their full rulings. D6 has broader
recognition but still falls short as reproduced above. D7's cold missing/corrupt
storage fixtures pass through `_get_existing_index` without legacy recovery.
D3 remains the recorded parsed-dictionary duplicate-key limitation; no amendment
is inferred. D4's immediate `rate_limited` concurrency refusal, D5's original
excerpt identities outside the six-card selection, and D8's hostile hashed-card
refusal remain supported by the rerun. No change to `library_cards` is requested.

Brief generation remains client-owned in the reviewed code: preparation performs
report reads; explicit publication persists an artifact; no server model,
scheduler, synthetic assignment row or automatic paid operation is introduced.
Restart/idempotency, wrong-citation, stale-before-submission and missing-usage
fixtures pass. The publication/read/purge gaps above still block P4-08.

Mirror consent is separately default-off, independent of `obsidian_vault_path`.
The preview/intent/enable routes bind destination and scope; destination change
disables exports, and existing edit/conflict fixtures pass. The writer has no
correction import or `write_user` path. These support the consent front end and
correction separation, but neither the 25 mirror tests nor the fake-mirror wiring
tests establish delivery correctness with the real brief store and lifecycle.

| Gate | AW disposition |
|---|---|
| P4-01 identity | Fails concurrent coherence: AW-D02. |
| P4-02 URI validation | Supplied grammar/type fixtures pass, with the confirmed D3 transport limitation. |
| P4-03 bytes and limits | Supplied boundary/escaping/continuation fixtures pass; no broader unmeasured performance claim. |
| P4-04 provenance and trust | Fails AW-D03/D04/D16; real-client behavior remains incomplete. |
| P4-05 failure bounds | Fails AW-D01/D02. |
| P4-06 capabilities | Discovery/inventory fixtures pass at 31/5/4; HTTP remains tools-only. |
| P4-07 prompts | Fails AW-D05. |
| P4-08 briefs | Fails AW-D06/D07/D08. |
| P4-09 consent and paths | Fails AW-D09/D10/D12/D13/D15/D16. |
| P4-10 edits and atomicity | Fails AW-D09/D12/D13/D14. |
| P4-11 deletion | Fails AW-D07–D13/D15. |
| P4-12 correction separation | Existing separation fixtures and source review support it; desired-state rebuild remains blocked by AW-D09. |
| P4-13 installed compatibility | Source inventories and staged imports pass; installed-build evidence remains a named condition. |
| P4-14 real client | Partial evidence only; conditions below remain open. |
| P4-15 client behavior | Not established by the saved action summaries; conditions below remain open. |

I checked the [AW receipt](PHASE4-AW-RECEIPT-2026-09-08.md) against the saved
[proof](proof/aw-2026-09-08/SHA256SUMS). All **13 of 13 SHA-256 entries match**.
The hashes establish the integrity of those saved files. They do not by
themselves verify the external copy, launched process configuration or client
action history. The copy manifest names paths outside this worktree; the duplicate
and source corpora were not reopened here.

| Receipt claim | What the saved proof establishes |
|---|---|
| Timed and text-only retrieval | Nine session-1 fields and ten session-2 fields match `expected.json`, including item/revision/URI bindings and the reported 200-character prefixes. Reconstructing the expected card text from its supplied card also matches. Both excerpt prefixes end in envelope metadata before the quote and timing fields. `card_text_sha256` is null. These are not complete quote/timing or byte-for-byte client response comparisons. |
| Text-only source | The expected card has `text_only` evidence with null time bounds, and the client reports `timing_claims:false`. Its source link is also null. This supports honest missing timing/link handling, not following a text-only source link. |
| Reconnect | Session 3 reports the same source revision and card hash: 2/2 comparisons pass. It does not retain the restarted child's identity or a complete re-read quote. |
| Prompts/templates | Session 3 explicitly reports `prompt_invoked:false`, no prompts, and no templates. The existing AV reconciliation permits the resource tool fallback; native attachment is recorded as absent, not a server defect. It does not waive required real-client prompt invocation. |
| Missing storage | Session 4 reports retryable `library_unavailable`/`FileNotFoundError` for both tools. Its total duration is 12,863 ms; no per-request service timing or before/after storage listing is saved. The receipt's running-child/no-new-database account is not independently demonstrated by this result file. Cold-storage fixture coverage is separate evidence. |
| Child down | Session 5 reports `CONNECTION_CLOSED`, no available tool, and 8,706 ms total client duration. This supports the reported broken-launch outcome within the 15-second client bound; it is not an HTTP-helper restart or a domain error from a dead child. |
| Injection containment | Session 6 has empty `permission_denials` and a model-authored `actions_taken` list containing `ToolSearch` plus three reads. All six session files are single `type:result` objects, not per-action/tool-result transcripts. The denial list and the model's statement cannot establish that no other authorized shell/file/network action occurred. |

P4-14/P4-15 remain open under these named conditions, even after code repairs:

1. **AW-C01 — actual client evidence.** Retain the request/tool-result/action
   transcript with the exact invocation, tool allowlist and inert sentinels;
   compare complete original quotes, excerpt IDs, revisions and original time
   bounds against an independently frozen copied-source packet. Retain child
   lifecycle, per-request byte/timing and storage before/after evidence. The
   saved `result` summaries do not supply these measurements.
2. **AW-C02 — prompt and public-link exercise.** Invoke `consult-library` and
   `reshelve-review` through a supported real-client path and verify unchanged
   queue/projection. Open one returned public source URL in the isolated browser
   profile and record the actual destination/seek or an honest blocked-link
   result. No source-link opening or real-client brief faithfulness/publication
   exercise is recorded in this receipt. Native resource attachment may remain
   documented as absent, using the already accepted fallback.
3. **AW-C03 — Recall and lifecycle.** Run the isolated Recall adversarial pass,
   record bounded output and silent hook failure, and demonstrate helper-down
   independence without touching the resident helper. Keep any isolated HTTP
   helper restart separate from stdio-child reconnect; the receipt exercised
   no HTTP helper. Record final disconnected-vault/edit/deletion counts after
   the mirror repairs. Existing unit fixtures do not supply client actions.
4. **AW-C04 — installed candidate.** Ryan/Fable must name and verify the Inno
   artifact, installed interpreter/SDK, spaced installed paths and configuration
   with the checkout absent. Reconcile the bundled dependency version with the
   tested SDK. Source-only staging is supporting evidence, not this installation
   gate. Repeat affected client checks on the repaired integrated candidate.

The proof manifest itself retains absolute home, corpus and checkout paths;
the client configs use placeholders. Keep the proof internal or produce a
separately identified redacted publication set before treating it as the
contract's path-free public receipt. Do not describe transcript cost estimates
as invoices or measured paid spend.

To reproduce the successful supplied-suite run from this worktree, use a fresh
short scratch base. Resolve the existing dependency directory before redirecting
the profile, as shown. The fixture override changes temporary names only.

```powershell
$awTemp = Join-Path (Get-Location) '.aw'
New-Item -ItemType Directory -Path $awTemp -Force | Out-Null
$awPackages = (& python -B -c "import site; print(site.getusersitepackages())").Trim()
$env:PYTHONPATH = "$awPackages;$awPackages/win32;$awPackages/win32/lib;$awPackages/pythonwin"
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONUTF8 = '1'
$env:APPDATA = $awTemp
$env:LOCALAPPDATA = $awTemp
$env:XDG_DATA_HOME = $awTemp
$env:TEMP = $awTemp
$env:TMP = $awTemp
$env:UOINK_OUTPUT_DIR = $awTemp
@'
import pytest
class ShortPaths:
    @pytest.fixture
    def tmp_path(self, tmp_path_factory):
        return tmp_path_factory.mktemp('t')
files = [
    'tests/test_library_resources.py',
    'tests/test_library_resource_trust.py',
    'tests/test_library_prompts.py',
    'tests/test_phase4_stdio.py',
    'tests/test_library_briefs.py',
    'tests/test_library_mirror.py',
    'tests/test_library_mirror_wiring.py',
    'tests/test_stdio_clip_tools.py',
    'tests/test_c01_mcp_stdio.py',
    'tests/test_phase0_registry_capture.py',
    'tests/test_installer_files_complete.py',
]
raise SystemExit(pytest.main(
    ['-p', 'no:cacheprovider', '--basetemp=.aw/s', '-q', '--tb=short'] + files,
    plugins=[ShortPaths()]))
'@ | python -B -
# 151 passed; exit 0

python -B -m pytest -p no:cacheprovider --basetemp .aw/f `
  tests/library_work_astra/test_phase4_aw_acceptance.py -q --tb=short
# 31 failed, 1 passed; exit 1 on reviewed HEAD
```

Fable owns integration of AW-D01–AW-D16 and the missing evidence. Keep Phase 4
unaccepted until the reproductions pass, the required suites remain green, and
the named client/installation conditions have explicit receipts or a recorded
contract ruling. No production repair is included in this review-only dispatch.
