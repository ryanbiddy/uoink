**PHASE 4 NOT ACCEPTED — AW-2, 2026-09-08.**

Reviewer: codex. Contract: `phase4-v1-2026-09-08`. Reviewed candidate:
`bbf9ac3935e14ace0313b5922e7c569e0e3b0630`, containing AV-3m (`26d661a`),
AV-3r (`eb58fe1`) and AV-3s (`bbf9ac3`). The
[contract](PHASE4-CONTRACT-2026-09-08.md),
[AV-1r rulings](PHASE4-AV1-RULINGS-2026-09-08.md) and
[first acceptance review](PHASE4-ACCEPTANCE-2026-09-08.md) govern this decision.

The original AW acceptance tests now pass **32/32**. The seven supplied suites
pass **135/135**, for **167 passed in 35.48 seconds** together. I cannot reproduce
the dispatch's 208-test count from those eight files. The seven supplied files
are unchanged since `d4d99bb`; the original AW file's last change is `7115a1d`.
No assertion was weakened in this review.

Passing those cases does not close the repairs. New acceptance tests reproduce
**26 failures**, with **2 passing controls**. They show source text returned or
published after deletion, deletion of unowned temporary files and a user edit,
and a vault replacement completing after the timeout response. AW-D05's binding
repair and AW-D06's canonical hashing repair are closed. The other 14 AW items
remain open as detailed below. These are implementation blockers, so
**ACCEPTED WITH CONDITIONS is not warranted**.

The deliverable changes are this report and
[test_phase4_aw2_acceptance.py](../../tests/library_work_astra/test_phase4_aw2_acceptance.py).
Production code, prior tests and receipt evidence are unchanged.
All runtime data came from disposable SQLite indexes, corpus files and vaults
inside this dedicated worktree, under an isolated profile. No model, resident
helper, HTTP listener, port 5179, live index, other checkout, package installation,
commit or merge was used. The saved receipt's external source paths were not
followed. Python was **3.14.6**, pytest **9.1.1**, MCP SDK **1.28.1**; these runs
do not certify the packaged interpreter or requirements pin.

| Rerun file | Passed | Failed |
|---|---:|---:|
| `tests/library_work_astra/test_phase4_aw_acceptance.py` | 32 | 0 |
| `tests/test_library_resources.py` | 50 | 0 |
| `tests/test_library_resource_trust.py` | 6 | 0 |
| `tests/test_library_prompts.py` | 8 | 0 |
| `tests/test_phase4_stdio.py` | 9 | 0 |
| `tests/test_library_briefs.py` | 26 | 0 |
| `tests/test_library_mirror.py` | 25 | 0 |
| `tests/test_library_mirror_wiring.py` | 11 | 0 |
| Original AW plus seven supplied suites | **167** | **0** |
| `tests/library_work_astra/test_phase4_aw2_acceptance.py` | **2** | **26** |
| `tests/test_stdio_clip_tools.py` | 5 | 0 |
| `tests/test_c01_mcp_stdio.py` | 4 | 0 |
| `tests/test_phase0_registry_capture.py` | 4 | 0 |
| `tests/test_installer_files_complete.py` | 3 | 0 |

The final follow-up run combined AW-2 with those four inventory files:
**26 failed, 18 passed in 12.72 seconds**. No skips or xfails mask the defects.
The two new passing controls check pure preview evidence revalidation and brief
publication refusal after sampled source metadata changes. Race tests perform
real fixture mutations at identified boundaries, then inspect the result or
bytes. The timeout test releases its blocked worker and waits for completion
before inspecting the final file; it does not mistake a temporarily absent file
for successful cancellation. The SQLite test uses a second connection holding an
exclusive lock on the disposable database in DELETE journal mode.

Every test name below is in the new AW-2 file unless explicitly marked as an
original AW test. Source line numbers refer to the reviewed candidate.

| AW item | Repair review and remaining requirement | New reproducer(s) |
|---|---|---|
| AW-D01 — open | `_BoundedLock` fixes the held Index-lock case. `LibraryReader._bind_index` still calls its factory without a deadline; `server._get_existing_index` waits on `_index_open_lock` without a timeout. `_sql`/Index calls retain unbounded SQLite waits. The new measured refusals take **2.410 s** and **2.498 s** respectively. Carry the remaining deadline into backend opening, SQLite busy/query handling and I/O, and through actual adapter serialization. An after-the-fact check cannot meet the bound. (`library_resources.py:822`, `911`; `server.py:2110`.) | `test_d01_backend_open_lock_obeys_deadline`; `test_d01_sqlite_busy_wait_obeys_deadline` |
| AW-D02 — open | Card construction and shelf rechecks now compare item rows, clips and corpus signatures across members. However, `_get_item` builds/checks its card, performs full corpus admission, and returns without another source check. Deleting the item during that admission still returns its card. Recheck all served bundles after remaining I/O and before result delivery, including fan-out results. (`library_resources.py:956`, `1352`, `1774`.) | `test_d02_get_item_rechecks_after_corpus_admission` |
| AW-D03 — open | `/secret` and a simply quoted drive path are repaired. The POSIX pattern requires an ASCII letter, underscore or dot, leaving `/7secret` and `/私密` intact. A double-quoted path containing an apostrophe is partially redacted, exposing `'Brien/secret.txt`. Recognize complete explicit paths, respect the matching quote delimiter and retain full spans plus original byte/hash bindings. (`library_resources.py:288`, `310`.) | `test_d03_redacts_complete_explicit_path` (3 cases) |
| AW-D04 — open | Unknown argument, citation and usage keys now produce fixed diagnostics/counts. AV-3s adds `error: str(exc)` to the preview refusal, exposing the raw exception and its path/sentinel. Map exceptions to fixed non-source categories; do not serialize their messages. (`library_prompts.py:537`.) | `test_d04_preview_refusal_does_not_disclose_exception` |
| AW-D05 — closed for binding/purity | The real-service path calls Phase 2 `_recheck_preview`, which recomputes run, taxonomy, source, accepted submission, baseline and forward/inverse delta bindings. `_compute_preview` is a report read; it does not reap leases, approve or apply. The original changed-run test passes, and the new control checks changed evidence plus zero SQLite mutations for both successful and refused prompt reads. The error disclosure belongs to D04; deadline coverage remains D01. (`library_prompts.py:473`; `library_work.py:987`.) | Passing control: `test_d05_preview_recheck_is_pure_and_checks_evidence` |
| AW-D06 — closed | `library_briefs.canonical` now delegates to `library_cards.serialize_card`; packet, job, request, citation and artifact structured digests use that canonical function. The original hash test passes. No competing card selector or changed excerpt identity was introduced. (`library_briefs.py:124`.) | Original AW: `test_brief_hashes_use_contract_canonical_serializer` |
| AW-D07 — open | Publication revalidates source/queue/run/taxonomy/projection, and reads now check projection/taxonomy/run as well as sampled cards. But `_recheck_publication_bindings` releases the Index lock before `os.replace`: another thread can commit source deletion in that gap and publication still returns an accepted receipt. Read/discovery validation omits the bound queue digest; a changed priority leaves the old brief readable and discoverable. Keep a coherent source/report boundary through publication and validate every bound dependency on reads/discovery. Preserve receipt-before-freshness retries. (`library_briefs.py:1007`, `1034`, `1146`.) | `test_d07_publication_holds_source_lock_through_replace`; `test_d07_read_and_discovery_recheck_queue` (2 cases). Passing control: `test_d07_publication_rechecks_sampled_metadata` |
| AW-D08 — open | `_purge_trash` now invokes local brief cleanup independently of mirror consent, and ordinary cleanup failures get retry entries. If BriefStore initialization fails, the source identity is deleted without scheduling cleanup; a later pass cannot find it. `_purge` also counts interrupted directories as removed despite `rmtree(ignore_errors=True)` leaving them present. Persist cleanup intent before losing the source identity, including initialization failures; verify removal of interrupted artifacts and retain/retry incomplete work. (`server.py:9868`; `library_briefs.py:1271`.) | `test_d08_failed_store_initialization_retains_purge_retry`; `test_d08_interrupted_cleanup_cannot_report_success` |
| AW-D09 — open | Bulk events now schedule current items/shelves; successful brief publication emits a guarded event. Fresh resync creates missing items, but omits existing shelves/briefs and does not refresh an already-written item after a missed event. Scope cleanup calls `_record_purge`, which also deletes the **local** brief even though its source remains live. Reconcile all desired derivatives against authoritative revisions on resync/recovery, and separate vault scope removal from source hard purge. (`library_mirror.py:1058`, `1149`; `library_briefs.py:494`.) | `test_d09_resync_repairs_missed_refresh`; `test_d09_fresh_resync_exports_shelf_and_brief` (2 cases); `test_d09_scope_cleanup_keeps_local_brief` |
| AW-D10 — open | The real BriefStore now exposes validated dependency IDs and the mirror consumes its fenced representation. Static allowlist/deletion cases pass. However, `_build_plan` records dependency IDs on the ledger entry without copying them into the write operation. The final brief recheck sees an empty list, so a deleted dependency can still be exported. Carry the validated identities/revisions into every operation and fail closed if they cannot be revalidated at delivery. (`library_mirror.py:1384`, `1831`.) | `test_d10_brief_dependencies_rechecked_at_replace` |
| AW-D11 — open | The Mirror object retains known pending deletes while disabled and can drain them. The production `server._mirror_event` still drops **all** events while disabled, so later deletions never enter that ledger. A second failure affects enabled mirrors: the new item recheck rejects deleted items even for tombstone operations, leaving their original text in place. Deliver deletion events independently of export enablement; apply action-specific liveness checks so a valid tombstone can replace deleted source text. (`server.py:1505`; `library_mirror.py:1831`.) | `test_d11_server_delivers_deletion_events_while_disabled`; `test_d11_soft_delete_removes_item_source_text` |
| AW-D12 — open | A missing manifest after prior sync now stops replacement. Exact temporary-file ownership was not implemented: cleanup still deletes names matching a 12–24 hex suffix, and a stem `.tmp` is deleted if its bytes contain `Interrupted`. Neither establishes ownership. Record the exact allocated temp path before writing, bind it to the intent, and delete only that recorded artifact after containment/ownership checks. (`library_mirror.py:1716`, `1918`, `1941`.) | `test_d12_unowned_temps_are_never_inferred_from_name_or_text` (2 cases) |
| AW-D13 — open | Destination-derived locking and pre-replace liveness/target checks fix the original narrow cases. The worker is still an abandoned daemon thread. Blocking **inside `os.replace`**, after its callback, lets it publish after the timeout response and lock release. Purge also unlinks after a single earlier hash, deleting an intervening user edit. Implement cancellable isolated vault I/O, keep destination exclusion until termination, and recheck ownership/target bytes and action bindings for deletion as well as replacement. The module's claimed child-process prohibition remains unsupported. (`library_mirror.py:1762`, `1941`, `2108`, `2128`.) | `test_d13_replace_syscall_cannot_complete_after_timeout`; `test_d13_purge_rechecks_user_edit_before_unlink` |
| AW-D14 — open | Manifest failures now propagate with zero acknowledged syncs and retain item intents. `Library.md` is constructed later inside `_vault_work`, outside the intent-writing loop. It can be replaced with no recovery intent when the manifest fails. Give the index the same durable intent/verification/recovery path as every other owned derivative; manifest writes must also participate in cancellation. (`library_mirror.py:1230`, `1538`, `1675`.) | `test_d14_index_has_recoverable_intent_on_manifest_failure` |
| AW-D15 — open | The missing-marker check works while the ledger retains `written_generation`. Losing the ledger resets `have_synced`; a replacement empty vault at the same path is then marked and populated using the old consent. Keep durable destination-initialization state separate from a disposable delivery ledger, and require explicit reconciliation when a bound volume's marker is absent. (`library_mirror.py:1230`.) | `test_d15_bound_volume_not_readopted_after_ledger_loss` |
| AW-D16 — open | Shelf links now resolve via `../Library/...`; raw HTML in the index identity is escaped. Display labels still allow active Markdown: a shelf member title containing an image is emitted as a nested Markdown image inside the item link. Use the shared safe representation or context-appropriate complete escaping for every untrusted label/body/identity. Preserve validated link destinations separately. (`library_mirror.py:182`, `734`.) | `test_d16_shelf_title_cannot_introduce_markdown_image` |

The green tests have not been edited to lower their bar, but some repairs satisfy
only their particular inputs. D12 is the clearest example: the supplied temp
fixture writes `Interrupted partial write`; the old AW preservation test writes
`USER OWNED TEMP`. Checking for the literal word `Interrupted` makes both pass
without proving ownership. The new cases vary that content and the filename.
Likewise, the original cancellation test blocks before `_atomic_vault` performs
its recheck; the new test blocks the actual replacement after that check.
Neither passing result establishes the full repair required by AW.

The wiring review confirms post-commit apply/pin/undo hooks in
`library_work.py`, identifier-free source-refresh hooks in `server.py`, and a
brief-publication hook after persistence. These are useful additions, but the
disabled-event guard, incomplete resync and action-specific deletion failures
above prevent end-to-end delivery acceptance. The stdio adapter retains read,
resource and prompt handlers with the shared safe renderer and deadline checks;
its checks precede final SDK serialization. HTTP remains tools-only. Inventory
fixtures pass, but cannot establish storage deadlines or real-client behavior.
No server model, timer-created brief, synthetic assignment work row, correction
import or `write_user` route was introduced by these repairs.

| Gate | AW-2 disposition |
|---|---|
| P4-01 identity | Blocked by D02's final delivery coherence gap. |
| P4-02 URI validation | Supplied grammar/type tests pass. The recorded AV-1r parsed-dictionary duplicate-key limitation is unchanged; no broader waiver is inferred. |
| P4-03 bytes and limits | Supplied byte/continuation cases pass within their measured scope. |
| P4-04 provenance and trust | Blocked by D03, D04 and D16; client action evidence also remains open. |
| P4-05 failure bounds | Blocked by D01 and D02. |
| P4-06 capabilities | Supplied discovery/transport tests pass. |
| P4-07 prompts | Binding/purity repair supported; D01/D04 still affect this surface. |
| P4-08 briefs | Blocked by D07/D08. |
| P4-09 consent and paths | Blocked by D09/D10/D12/D13/D15/D16. |
| P4-10 edits and atomicity | Blocked by D09/D12/D13/D14. |
| P4-11 deletion | Blocked by D07–D15 as applicable. |
| P4-12 correction separation | Source review still supports separate correction authority; mirror rebuilding is incomplete under D09. |
| P4-13 installed compatibility | Inventory regressions pass; installed-build evidence remains open. |
| P4-14 real client | Repaired-candidate rerun required. Earlier evidence is partial and belongs to `d4d99bb`. |
| P4-15 client behavior | Full action/tool-result evidence required; saved model-authored summaries do not establish this gate. |

The [AW receipt](PHASE4-AW-RECEIPT-2026-09-08.md) remains historical supporting
evidence. I recomputed its saved proof checksums: **13/13 match**. All six
`session*.json` files are single `type:result` objects. Session 3 explicitly
reports `prompt_invoked:false`; session 6 contains an empty denial list and a
model-authored action summary. They do not become per-action transcripts by
being called transcripts in the receipt.

The first review's limits therefore still apply: comparisons of 200-character
prefixes stop before the excerpt's quote/timing fields; the expected card-text
hash is null; the text-only item's source link is null; child identity and
complete reconnect reads were not retained; storage-failure timing is a whole
12,863 ms session, not per-request service time. The 8,706 ms broken-launch
result supports that recorded transport failure within the 15-second client
bound. Empty denial lists cannot prove the absence of other authorized actions.
Recall, source-link opening and installed Inno verification remain incomplete.

**Rerunning the real-client sessions on the repaired candidate is required.**
Contract procedure step 9 explicitly invalidates affected results after code or
prompt changes. All four Phase 4 modules changed after the receipt's `d4d99bb`,
as did `server.py`; `library_work.py` is unchanged between those two candidates.
The affected retrieval, refusal, prompt, brief and mirror paths must be exercised
again after implementation blockers are repaired. This is a remaining acceptance
requirement, not an optional follow-up that makes this candidate accepted.
No model/client rerun was authorized or performed in AW-2.

The existing evidence conditions remain concrete:

1. **AW-C01:** retain actual requests, complete tool results and action records,
   invocation/configuration hashes, tool allowlist and inert sentinels. Compare
   full quotes, identities, original timing and revisions to an independently
   frozen copied-source packet. Retain child lifecycle, request byte/timing and
   storage before/after evidence.
2. **AW-C02:** demonstrate the required prompt workflow and a real returned
   public source-link opening on the selected supported client path. Record
   native attachment limitations separately. If the prompt workflow is absent,
   obtain an explicit contract ruling or supply a working supported route;
   another synthetic server probe does not close it.
3. **AW-C03:** complete isolated Recall/adversarial observations and final
   disconnected-vault/edit/deletion accounting after repair. Keep stdio-child
   reconnect distinct from any separately authorized isolated HTTP-helper test.
4. **AW-C04:** name and verify the installed Inno artifact, interpreter/SDK and
   spaced installed paths with the checkout absent; repeat affected client
   checks on that candidate. Prior source staging does not certify installation.

The proof copy manifest still contains private absolute paths. Keep it internal
or publish a separately identified redacted set. The saved cost estimates are
not invoices or measurements of paid spend.

Reproduce from this worktree with fresh short scratch directories. The fixture
override changes temporary names only; it does not alter product limits,
assertions or application code. Resolve the existing dependency directory before
redirecting the profile:

```powershell
$awTemp = Join-Path (Get-Location) '.w/p'
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
    'tests/library_work_astra/test_phase4_aw_acceptance.py',
    'tests/test_library_resources.py',
    'tests/test_library_resource_trust.py',
    'tests/test_library_prompts.py',
    'tests/test_phase4_stdio.py',
    'tests/test_library_briefs.py',
    'tests/test_library_mirror.py',
    'tests/test_library_mirror_wiring.py',
]
raise SystemExit(pytest.main(
    ['-p', 'no:cacheprovider', '--basetemp=.w/s', '--tb=short'] + files,
    plugins=[ShortPaths()]))
'@ | python -B -
# 167 passed in 35.48s; exit 0

@'
import pytest
class ShortPaths:
    @pytest.fixture
    def tmp_path(self, tmp_path_factory):
        return tmp_path_factory.mktemp('t')
files = [
    'tests/library_work_astra/test_phase4_aw2_acceptance.py',
    'tests/test_stdio_clip_tools.py',
    'tests/test_c01_mcp_stdio.py',
    'tests/test_phase0_registry_capture.py',
    'tests/test_installer_files_complete.py',
]
raise SystemExit(pytest.main(
    ['-p', 'no:cacheprovider', '--basetemp=.w/f', '-q', '--tb=line'] + files,
    plugins=[ShortPaths()]))
'@ | python -B -
# 26 failed, 18 passed in 12.72s; exit 1 (AW-2: 26 failed/2 passed;
# inventory: 16 passed). Intentional acceptance failures on this candidate.
```

Handoff: review complete; Phase 4 remains NOT ACCEPTED. Integrate the repairs for
the 14 open AW items, preserve both acceptance files, then obtain the repaired
candidate's client/installation receipts. Fable should also reconcile the
dispatch's 208 count with an exact test-file list and collected results. No
production repair or commit is included in this review dispatch.

AST parsing, test-name references, relative links, code fences and whitespace
checks passed. The untracked `.w/` directory retains the isolated fixture data
and JUnit receipts (`phase4.xml`, `final.xml`). Automatic approval review rejected
its cleanup command as "blocked by policy", with no more specific reason.
