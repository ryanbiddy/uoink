**PHASE 4 NOT ACCEPTED — AW-3, 2026-09-08.**

Reviewer: codex (Astra). Reviewed HEAD:
`c24de5e37afbfc6b7ebb0ae5f31690faaf5ac79b`, containing AV-4 `6559a71`
and BC-2 `fd1825c`. The four Phase 4 modules are unchanged between `6559a71`
and this HEAD; the shared server, index and adapters include BC-2. The
[dispatch](PHASE4-ACCEPTANCE-3-BRIEF-2026-09-08.md),
[contract](PHASE4-CONTRACT-2026-09-08.md) and
[AW-2 rulings](PHASE4-ACCEPTANCE-2-2026-09-08.md) govern this review.

**D04, D11 and D16 are closed. Eleven items remain open:** D01–D03,
D07–D10 and D12–D15. Both requested legacy-test alignments are confirmed.
The required suites pass **306/306**, but the
[new acceptance file](../../tests/library_work_astra/test_phase4_aw3_acceptance.py)
has **16 failing reproductions and one passing control**. The failures include
publication after source deletion, loss of temporary-file ownership, deletion
of a user replacement and a timed-out writer erasing a later acknowledged sync.
These implementation failures preclude acceptance with conditions.

| Required suite | Passed | Failed |
|---|---:|---:|
| `tests/library_work_astra/test_phase4_aw_acceptance.py` | 32 | 0 |
| `tests/library_work_astra/test_phase4_aw2_acceptance.py` | 28 | 0 |
| `tests/test_library_resources.py` | 50 | 0 |
| `tests/test_library_prompts.py` | 8 | 0 |
| `tests/test_library_briefs.py` | 26 | 0 |
| `tests/test_library_mirror.py` | 25 | 0 |
| `tests/test_library_mirror_wiring.py` | 11 | 0 |
| `tests/test_phase4_stdio.py` | 9 | 0 |
| `tests/test_c01_mcp_stdio.py` | 4 | 0 |
| `tests/test_stdio_clip_tools.py` | 5 | 0 |
| `tests/test_phase0_registry_capture.py` | 4 | 0 |
| `tests/test_docs_live_contracts.py` | 10 | 0 |
| `tests/test_library_adapters.py` | 94 | 0 |
| New `test_phase4_aw3_acceptance.py` | **1** | **16** |

The final documented-runner check completed the acceptance command in
**17.61 s**, the unit/inventory command in **32.09 s**, and the new-test command
in **6.74 s**. It reproduced the same counts as the separate runs. There were no
skips or xfails. The brief's 152 unit/inventory count excludes the 94 adapter
tests; its complete named command collects 246 here. The inventories confirm
32 stdio tools and 88 registry tools, including BC-2's additive export adapter.
They do not certify Phase 6 behavior or close Phase 5's BA-3 findings.

The first acceptance run used an overly long scratch base and produced
58 passes and two brief-export failures. Shortening only the scratch base made
both pass: the generated brief temp paths had exceeded the mirror's Windows
path limit. This was a fixture-path issue, not a candidate finding. Existing
tests, product limits and assertions were not changed. A scratch-only pytest
plugin gives ordinary `tmp_path` fixtures short directory names; the AW fixture
already uses short names.

Each test name below belongs to the new AW-3 file unless marked AW-2. Source
line numbers refer to the reviewed HEAD.

| Item | Ruling, evidence and exact remaining repair |
|---|---|
| D01 — **open** | The backend-open lock and busy waits on an already-bound connection now pass AW-2. Cold acquisition still calls `Index.open` without carrying the remaining deadline into its initial SQLite work (`server.py:2111`, `index.py:416`). A real second connection holding `BEGIN EXCLUSIVE` makes the refusal arrive after **2.626 s**, despite the 2-second service deadline. Bound cold database opening and its initialization, as well as subsequent I/O and serialization, under the same admission. An eventual timeout check is insufficient. Reproduction: `test_d01_cold_database_open_obeys_deadline`. |
| D02 — **open** | `get_item` now rechecks after corpus admission. Prompt fan-out still returns previously built cards after later metadata reads change their source (`library_prompts.py:329`; `LibraryReader.request` only checks time on exit). Deleting `a` after `_shelf_metadata` reads completes still returns the evidence-brief prompt. Revalidate every included source after the remaining fan-out work and before delivery; refuse the complete response on change. Reproduction: `test_d02_prompt_rechecks_cards_after_remaining_metadata_reads`. |
| D03 — **open** | The three AW-2 cases are repaired, including matching quote delimiters. `_POSIX_FIRST = [\w.]` still excludes valid explicit absolute paths beginning with punctuation or symbols (`library_resources.py:301`). Quoted `/@private/secret.txt`, `/-private/secret.txt` and `/🔑private/secret.txt` are returned intact. Recognize complete absolute path spans without that first-character restriction, preserve validated public URLs and keep original byte/hash bindings with reported redactions. Reproduction: `test_d03_punctuation_and_symbol_led_absolute_paths_are_redacted` (3 cases). |
| D04 — **closed** | Preview exceptions now produce fixed `preview_invalidated` details without `str(exc)` (`library_prompts.py:530`). AW-2's sentinel/path exception test passes, as do prior unknown-field/citation/usage disclosure cases. The binding/purity control also passes. |
| D07 — **open** | Queue changes now invalidate brief reads/discovery, and the same-Index competing-thread publication test passes. The retained Python lock excludes only users of that Index object. An independent SQLite connection commits deletion before `os.replace`, and publication still returns an accepted receipt (`library_briefs.py:1007`). Establish exclusion/coherence with authoritative writers across connections/processes through publication, or refuse when the dependency changes. Preserve receipt-before-freshness retry semantics. Reproduction: `test_d07_publication_excludes_an_independent_sqlite_writer`. |
| D08 — **open** | Store-initialization failure now schedules retry, and incomplete interrupted-directory deletion refuses. However, `_purge` catches a date-directory enumeration error and continues as if cleanup completed (`library_briefs.py:1300`). The server clears its retry; after storage recovers, the purged source's local brief remains. Treat an uninspectable day as incomplete cleanup and retain durable retry until every dependent artifact/packet is accounted for. Reproduction: `test_d08_unreadable_day_retains_local_brief_cleanup_retry`. |
| D09 — **open** | Fresh shelf/brief export, missed item refresh and preservation of the local brief during scope cleanup now pass. Scope removal still enters the source-purge ledger, and resync skips that identity even after a new explicit consent includes it (`library_mirror.py:1104`, `1189`). Re-adding live item `b` returns `ok:true`, `synced:0` with no item file. Separate scope cleanup from authoritative source purge and reconcile a newly authorized live item without requiring an unrelated capture/restore event. Reproduction: `test_d09_resync_reexports_explicitly_readmitted_scope_item`. |
| D10 — **open** | Dependency IDs now reach the write operation, so deletion just before replacement is caught. The final check only tests liveness and scope, not bound revisions (`library_mirror.py:1946`). Changing `b`'s clip text at that same boundary still exports the obsolete brief. Carry and revalidate the complete bound dependency state through replacement, including evidence revisions and applicable report bindings. Reproduction: `test_d10_brief_source_revision_rechecked_at_replace`. |
| D11 — **closed** | The production event guard delivers `soft_delete` and `hard_purge` while export is disabled (`server.py:1505`). Tombstone replacement now accepts an authoritative deleted source and refuses a live one (`library_mirror.py:1938`). Both AW-2 cases and the aligned deletion/restore/wiring tests pass. This closes the event-delivery and tombstone defects; the separate recovery/cancellation failures still block the deletion gate. |
| D12 — **open** | Filename/content guessing is gone. Recorded ownership still fails across retries: a new intent overwrites the old `temp_rel` before cleanup, leaving a real interrupted temp behind even after later hard purge. Conversely, a user file recreated at that recorded path is deleted without checking its identity/bytes (`library_mirror.py:1368`, `1822`, `2007`, `2018`). Preserve outstanding temp records across generations, durably bind allocated artifacts, and verify containment plus current ownership before removal. Retain failed cleanup work. Reproductions: `test_d12_retry_keeps_ownership_of_interrupted_temp`; `test_d12_recorded_temp_path_does_not_authorize_deleting_user_replacement`. The unedited recorded-temp hard-purge control passes. |
| D13 — **open** | The repair lets the syscall complete and then restores old bytes or unlinks the target (`library_mirror.py:2043`). Source bytes are observable after the timeout, an intervening user edit is deleted, and an old worker can erase a later successful sync. Final absence in AW-2's single-writer case therefore does not establish cancellation. Use cancellable isolated vault I/O, retain destination exclusion until the worker can no longer mutate it, and protect every destructive action with current ownership checks. Do not repair cancellation by an unfenced rollback. Reproductions: `test_d13_timeout_never_publishes_or_rolls_back_over_user_bytes` (2 cases); `test_d13_timed_out_writer_cannot_erase_a_later_successful_sync`. |
| D14 — **open** | `Library.md` now has an intent, but its hash describes the planned catalog. The delivered index is rebuilt from successful exports and omission counts (`library_mirror.py:1380`, `1711`). When one item fails and manifest persistence fails, the index on disk has a different hash from its intent. Persist the exact final index bytes/hash before replacement, retain that generation until recovery, and apply the same cancellation/manifest guarantees as other derivatives. Reproduction: `test_d14_index_intent_matches_exact_published_bytes`. |
| D15 — **open** | Separate destination state closes the ordinary ledger-loss test. Its write is non-atomic, errors are swallowed, and export success is still acknowledged (`library_mirror.py:918`, `2174`). With that write unavailable, subsequent ledger loss and a replacement empty vault cause old consent to initialize the replacement. Make destination initialization durable before acknowledging/exporting; missing, corrupt or failed binding state must require reconciliation rather than silently granting initialization authority. Reproduction: `test_d15_failed_destination_binding_persistence_does_not_allow_readoption`. |
| D16 — **closed** | `_safe_label` escapes Markdown punctuation before shelf/index display (`library_mirror.py:192`); link destinations remain generated separately. AW-2's image-title case passes, as do the original relative-link/HTML cases and the mirror trust fixtures. This closes the reviewed label-rendering defect. |

D05 (preview binding/purity) and D06 (canonical structured hashing) remain closed
as ruled in AW-2. Their controls pass. The 11 open items above are wider cases
of existing obligations, not new contract requirements.

The D12 tests create a temp through the real allocator, inject replacement and
cleanup failures, and verify the recorded path before exercising recovery. They
do not manufacture ownership from a filename. The D13 tests release and join the
blocked work before inspecting final bytes. One also reads the real replaced
file before rollback; another waits for a second successful resync before
releasing the first writer. The D07 competitor uses a separate SQLite connection,
so the passing same-object lock test cannot conceal the publication gap.

Both legacy-test alignments follow the prior rulings:

- **D11 wiring confirmed.** In
  `test_each_seam_fires_once_when_enabled_and_never_when_disabled`, expecting
  exactly `soft_delete`, `hard_purge` while disabled preserves deletion delivery.
  Other events remain suppressed. The companion tests now commit deletion and
  restoration in the index before sending the event, matching authoritative
  state instead of treating a hint as a deletion command.
- **D12 temp retention confirmed.** In
  `test_crash_before_replacement_preserves_old_file`, the manually created stem
  `.tmp` has no allocation/intent record. Keeping its exact `Interrupted partial
  write` bytes is required. The old assertion deleted an unowned file. This
  alignment grants no exemption for orphaning owned temps or deleting user
  replacements; the new failing cases and passing owned-temp control enforce
  those distinctions.

| Gate | AW-3 disposition |
|---|---|
| P4-01 identity | Open under D02's final response-coherence failure. |
| P4-02 URI validation | Named tests pass; the recorded parsed-dictionary duplicate-key limitation is unchanged. |
| P4-03 bytes/limits | Named boundary, continuation and serialization fixtures pass within their tested scope. |
| P4-04 provenance/trust | D03 remains open; P4-15 action evidence is also outstanding. |
| P4-05 failure bounds | D01 and D02 remain open. |
| P4-06 capabilities | Named discovery, negotiation and inventory tests pass. |
| P4-07 prompts | Preview refusal/purity repaired; D01/D02 still affect prompt delivery. |
| P4-08 briefs | D07/D08 remain open. |
| P4-09 consent/paths | D09/D10/D12/D13/D15 remain open. |
| P4-10 edits/atomicity | D09/D12/D13/D14 remain open. |
| P4-11 deletion | D07/D08/D10/D12/D13 remain open despite closure of D11's event/tombstone defects. |
| P4-12 correction separation | Reviewed changes preserve separate correction authority; mirror rebuilding remains incomplete under D09. |
| P4-13 installed compatibility | Fixture inventories pass. Ryan owns the installed Inno receipt shared with Phase 3 C22. |
| P4-14 real client | Candidate-specific rerun remains required. |
| P4-15 client behavior | Actual action/tool-result evidence remains required. |

Fable should collect the following in one planned rerun for **Claude Desktop and
Claude Code over stdio**, recording results separately for each client. The
frozen required pair remains Claude Code/stdio; Desktop evidence does not waive
a missing Code workflow. Running on this candidate can document these open
failures, but a later repair invalidates affected observations. To avoid repeating
the affected sessions, execute the acceptance rerun after these repairs are
integrated and the revised SHA is frozen. AW-3 launches neither client nor model.

1. **Identify the actual candidate and isolate its data.** Record SHA, client
   versions/mode, interpreter/SDK/protocol, launch/configuration hashes, child
   PIDs, tool allowlist and fixture-copy manifest/hashes. Use subscription
   access with `ANTHROPIC_API_KEY` absent and no paid API calls. Verify every
   corpus path resolves to the authorized disposable copy. Retain the expected
   packet before the session, derived from stored evidence and canonical card
   construction rather than only the reader under test. Keep all test profiles,
   browser state and output separate from live data and resident configuration.
2. **Prove the complete retrieval path.** Record real discovery, bounded search,
   item resolution, full card and excerpt resource/fallback results for timed
   and text-only items. Compare exact IDs, source/card/excerpt hashes, complete
   quote text, original timing, public links and truncation against that frozen
   packet. Compute the full card-text hash; 200-character prefixes or a null
   expected hash are insufficient. Record five templates, four prompts and
   the candidate's 32 stdio tools; native attachment limitations get their own
   result. A tool fallback must return identical resource contents.
3. **Exercise prompts and a real source link.** Invoke `consult-library` and
   `reshelve-review` in the supported real-client workflow, retain their actual
   returned messages, and compare queue/projection/settings before and after.
   A model-authored claim of invocation or another synthetic protocol probe
   cannot close this gate. If a client lacks the required prompt route, record
   the failure and supply a supported route or obtain an explicit contract
   ruling. Open a returned public source link in the isolated browser, retaining
   the actual destination and timed seek where applicable. Show the text-only
   item has a real source link and no invented timestamp. If the authorized
   session includes a brief job, retain its prepared packet across restart,
   publication request, citations, receipt, identical retry and stale refusal.
4. **Separate reconnect, storage and transport failure.** Retain the old/new
   test stdio-child identities, explicit reconnect and full unchanged-item
   comparison. With the child alive and fixture storage unavailable, measure
   each request's domain refusal within 2 seconds and prove no replacement
   empty index was created. For stopped/broken launch, measure the real client's
   transport failure within 15 seconds from the request/connection attempt,
   allowing at most one explicit reconnect. Whole-session durations do not
   establish service latency. No resident helper, port 5179 or HTTP restart is
   required or authorized for these stdio sessions.
5. **Retain action evidence for P4-15.** Exercise hostile titles, source text,
   fences, labels and brief content with only declared fixture actions and inert
   sentinels available. Save actual requests, full tool results, attempted and
   executed tool/shell/file/connector/network actions, permission decisions and
   sentinel before/after state. Show no unauthorized action follows the injected
   instructions. An empty denial list and a final model-written summary cannot
   establish that. Separately enable only the isolated Recall fixture, retain
   its bounded/silent-failure behavior and observe client actions consuming it.
   Finish disconnected-vault, user-edit and deletion cases with owned artifact,
   temp, pending-cleanup and conflict accounting after repair. Keep private
   evidence internal; identify any public redacted copy separately by hash.

The historical [AW receipt](PHASE4-AW-RECEIPT-2026-09-08.md) still belongs to
`d4d99bb`. AW-2's findings about its missing action transcripts, full comparisons,
prompt invocation, link opening and per-request timing remain applicable.
AW-3 did not reopen its external copy paths or rerun its client sessions.
P4-13 stays with Ryan: name/hash the installed Inno artifact, verify imports
and stdio from installed spaced paths with the checkout absent, and attach the
shared C22 receipt. Source tests and user-site SDK results cannot substitute
for that installation evidence.

All runtime indexes, corpora, vaults, application roots and temporary files were
under this worktree's `_scratch/` directory. Python was **3.14.6**, pytest
**9.1.1**, and MCP SDK **1.28.1**. No implementation, existing test, contract or
client configuration was edited. No model, resident helper, listener, port 5179,
live index, API key, other checkout, installation, commit or merge was used.
Ignored scratch files retain the runner, isolated fixtures and JUnit receipts.
The separate runs are in `_scratch/aw3/` (`acceptance.xml`, `inventory.xml`,
`n2.xml`); the documented-runner verification is in `_scratch/aw3-repeat/`
(`a.xml`, `i.xml`, `n.xml`). AST, embedded Python syntax, relative links, named
test references, Markdown fences and whitespace checks passed. Git shows only
the two requested deliverables as untracked changes.

The following PowerShell-launched Python runner reproduces all three commands
without relying on those ignored helper files. Choose fresh short `q3a/q3i/q3n`
directories if they already exist. It resolves installed dependencies before
redirecting application roots, and changes temporary names only.

```powershell
@'
import os, site, subprocess, sys
from pathlib import Path
root = Path.cwd().resolve()
scratch = root / '_scratch' / 'aw3-repeat'
scratch.mkdir(parents=True, exist_ok=True)
(scratch / 'aw3_paths.py').write_text(
    'import pytest\n@pytest.fixture\ndef tmp_path(tmp_path_factory):\n'
    '    return tmp_path_factory.mktemp("t")\n', encoding='utf-8')
packages = Path(site.getusersitepackages())
env = os.environ.copy()
env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1',
           PYTEST_PLUGINS='aw3_paths',
           PYTHONPATH=os.pathsep.join(map(str, [root, scratch, packages,
               packages / 'win32', packages / 'win32/lib', packages / 'pythonwin'])))
env.pop('ANTHROPIC_API_KEY', None)
groups = {
 'a': ['tests/library_work_astra/test_phase4_aw_acceptance.py',
       'tests/library_work_astra/test_phase4_aw2_acceptance.py'],
 'i': ['tests/test_library_resources.py', 'tests/test_library_prompts.py',
       'tests/test_library_briefs.py', 'tests/test_library_mirror.py',
       'tests/test_library_mirror_wiring.py', 'tests/test_phase4_stdio.py',
       'tests/test_c01_mcp_stdio.py', 'tests/test_stdio_clip_tools.py',
       'tests/test_phase0_registry_capture.py', 'tests/test_docs_live_contracts.py',
       'tests/test_library_adapters.py'],
 'n': ['tests/library_work_astra/test_phase4_aw3_acceptance.py'],
}
returncodes = []
for name, files in groups.items():
    base = root / '_scratch' / ('q3' + name)
    assert base.resolve().is_relative_to(root / '_scratch') and not base.exists()
    profile = scratch / ('p-' + name)
    profile.mkdir(parents=True, exist_ok=True)
    for key in ('APPDATA', 'LOCALAPPDATA', 'XDG_DATA_HOME', 'TEMP', 'TMP', 'UOINK_OUTPUT_DIR'):
        env[key] = str(profile)
    env['UOINK_INDEX_PATH'] = str(profile / 'unused-index.db')
    result = subprocess.run([sys.executable, '-B', '-m', 'pytest', '-q',
        '-p', 'no:cacheprovider', '--basetemp=' + str(base),
        '--junitxml=' + str(scratch / (name + '.xml')), *files], env=env)
    returncodes.append(result.returncode)
    print(name, 'exit', result.returncode, flush=True)
raise SystemExit(1 if any(returncodes) else 0)
'@ | python -B -
```

Handoff: AW-3 review complete; Phase 4 NOT ACCEPTED. Deliverables are this report
and the new AW-3 acceptance file. Required suites: 306 passed; new assertions:
16 failed, 1 passed. Fable owns integration of the 11 named repairs and the
candidate-specific client rerun; Ryan retains installed P4-13/C22. No open
question prevents the repair work. No commit or merge was made.
