# Phase 4 receipt correctness repair — 2026-09-09

Owner: one Grok subscription worker; no subagents, commits, push or Inno/client/model
execution. Write a report early. Read this brief fully first, then apply
`docs/library/proof/ryan-p4-kit-review-03-2026-09-09/original.patch` with three-way
apply. This imports the complete staged/unstaged third kit. Existing test files
and assertions remain frozen, including all three imported kit suites. Own only
`scripts/install_receipt/p4_*.py`, a new `tests/test_install_receipt_p4_kit_truth.py`,
and `docs/library/RYAN-P4-EVIDENCE-COMPLETENESS-WORKER-2026-09-09.md`.

Never open/stat/hash the actual ordinary index, contact/bind 5179, set any API key,
spend paid API, fetch library content or run diarization. Apply false. Preserve
IG_FORBIDDEN_LIVE from the parent before redirecting LOCALAPPDATA. All execution
uses guarded disposable profiles. Source observations are never installed credit.
Do not modify product files or an existing test fixture without reporting a
concrete product diagnosis to Astra first.

## Prior observation and review

Independent third union: 36 passed / one frozen nested-settings-path failure,
24.86 s. Original records and exact patch are sealed in the directory above.
The third source observation has successful consult-library and 32/5/4 inventory;
reshelve-review returns revision_unavailable / preview_invalidated in both sessions.
The worker labels packet_and_prompt_subset_complete true despite that refusal.
That flag does not establish a passing valid-preview scenario. Keep the old result
unchanged and explicitly correct this interpretation in your new report.

## Four repair groups

1. Evidence inspection must require every declared pair and successful native
   consult-library AND reshelve-review in EACH of at least two original sessions,
   with distinct actual child identities, complete inventories, matched frames and
   no corruption. A refusal is observed but not a successful valid-preview result.
   Current code aggregates matching packets/prompts across sessions and permits
   any reshelve reply; one session can fill another's gaps. Parsing corrupt JSONL
   must produce a failed inspection instead of escaping. Add meaningful negative
   cases for a successful first/partial second session, reshelve error, one session,
   malformed records and unknown/missing source labels, plus a fully passing pair.

2. Real bounded transport cleanup: current close_stdin synchronously closes the
   buffered writer while _bounded_write may hold its lock, so a large write to a
   child that never reads can hang cleanup. The existing test sends only a tiny
   initialize frame and does not exercise this. Add a multi-megabyte request and
   prove the complete close remains bounded and both writer/readers exit. Terminate
   the owned tree before any blocking stream close when needed. QueryInformationJobObject
   failure currently returns [] and may earn cleaned=true. Require affirmative
   job-empty evidence and no drain/identity uncertainty for cleanup credit. Retain
   and close the job safely even on query failure; never target foreign PIDs or
   use process names. Preserve complete raw traffic; avoid unbounded memory merely
   to keep full file logs. Existing behavior assertions remain unchanged.

3. Guard/provenance must fail closed BEFORE original product launch. In run_installed
   a failed guard canary is currently caught and product launch continues. Refuse
   instead, restore exact guard/_pth bytes after all children are confirmed gone,
   and propagate restoration failure. Review prepare/probe/client/tap entry points
   for the same requirement. Preserve any preexisting C22 guard and never overwrite
   modified guard bytes. Installed eligibility requires actual executable/module
   files and sealed per-file equality, missing imports and checkout/user-site fail.

4. Diagnose the reshelve refusal from retained exact seed and original replies.
   Compare the real service's preview binding and pure reader's recheck directly
   under the guard without modifying the stored preview or fabricating success.
   Check actual store_root/taxonomy, expiry, evidence/projection and later fixture
   operations. If a fixture generator uses a nondefault store path, stale input or
   otherwise invalidates its own preview, report the exact issue and create an
   explicitly versioned corrected generated fixture artifact; this brief permits
   instrument-generator correction, NOT edits to any existing acceptance test.
   Keep original requests/expected artifacts archived. If product behavior is wrong,
   leave production unchanged and provide a minimal real reproduction and repair
   proposal. Run complete original source entry with a fresh versioned fixture
   only after the documented correction. No attached entry credit.

## Required verification

Use `E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/ig-native/Scripts/python.exe`
and the committed `docs/library/proof/ryan-corrected-01-2026-09-09/integrator_verify.py`
wrapper, IG_FORBIDDEN_LIVE already bound,
all API keys unset. Fresh short labels. Run the three frozen kit files plus the
new truth suite, retaining exact log/XML/pass/fail counts. Source copy excludes
build, .git, _scratch, caches and dependencies. Retain exact requests, replies,
state and cleaned process evidence; report any still-failing scenarios without
turning instrument diagnostics into acceptance. Final report includes source
hashes, changed files and executable operator commands. Astra independently
verifies before integrating.

Dispatch preflight: the first attempt stopped before creating a worker because
the wrapper reference pointed to ignored scratch. The committed identical-purpose
wrapper above is the repaired required input; no measurement was rerun.
