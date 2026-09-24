# Product proof execution plan, run P

Run P builds and tests the proof machinery with fixtures. It does not execute a
model. Fable must integrate Gemini's runner and scorer, then have Astra review
that integrated tree before the subscription pass. This document implements the
codex section of [the dispatch](PROOF-BRIEF-2026-09-05.md) and the proof section of
[contract v1.2](PHASE2-CONTRACT-2026-09-04.md).

The input freeze is currently **blocked**. The named database was verified and
upgraded in this worktree, but ten referenced Markdown heads are under
`C:/Users/hello/AppData/Local/Uoink`. Fable's isolated-helper decision forbids
touching that directory. A clarification about reading only those source
documents is pending. Those ten targets remain in the manifest with a null
revision and an explicit blocker; none was excluded or replaced with empty
evidence. The validator refuses this provisional manifest for any proof.

There is also a quality constraint to resolve before spending subscription time:
four of the declared 13 text-only holdout items have `source_type=video`, only
text-only excerpts, and no timed evidence. The service's existing
`unsupported_evidence` rule rejects description prose for such videos. These
IDs are `2046008958511702016`, `KjToqo-ACnc`, `aqz-KE-bpKQ`, and `h6YLDi2gnMM`.
Even nine assignments out of that declared stratum would give coverage
`9/13 = 0.6923`, below `0.80`. Preserve the frozen denominator and report the
failure; do not relax evidence validation, replace items, or tune the taxonomy
using their labels. Completing the ten heads will permit a full remeasurement.

## Commands for the orchestrator

Run these from the integrated project worktree. Every command below the first
block depends on a complete freeze and the next-run integration review. This
run executed no runner, scorer, helper, or subscription client. The runner and
scorer paths below are Gemini's assigned interfaces, not a claim that they
already exist in this worker's checkout.

```powershell
$ErrorActionPreference = 'Stop'
$proofRoot = (Get-Location).Path
$proofSource = 'C:/Users/hello/AppData/Local/AgentControlRoom/uoink-index-copy-2026-09-04-upgraded.db'
$proofExpected = '2765cc359805fb12f7a90aecd3dd0b34d884aa8cb3015785011bf400da3b4dfc'
if (Test-Path Env:ANTHROPIC_API_KEY) { throw 'ANTHROPIC_API_KEY must be unset, including empty values' }
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $proofSource).Hash.ToLowerInvariant() -ne $proofExpected) {
    throw 'Named source hash mismatch'
}
$proofTestRoot = Join-Path $proofRoot '_scratch/proof/orchestrator-tests'
New-Item -ItemType Directory -Path $proofTestRoot -Force | Out-Null
$env:LOCALAPPDATA = $proofTestRoot
$env:APPDATA = $proofTestRoot
$env:TEMP = $proofTestRoot
$env:TMP = $proofTestRoot
$env:UOINK_OUTPUT_DIR = Join-Path $proofTestRoot 'output'
$env:PYTHONPATH = '.'
$env:PYTHONIOENCODING = 'utf-8'
python tests/validate_proof_receipts.py --self-test --mock
if ($LASTEXITCODE -ne 0) { throw 'Receipt self-tests failed' }
python -m pytest -q tests/ -p no:cacheprovider --basetemp "$proofTestRoot/pytest"
if ($LASTEXITCODE -ne 0) { throw 'Suite failed or pytest is unavailable' }
python tests/validate_proof_receipts.py --verify-inputs --mock
if ($LASTEXITCODE -ne 0) { throw 'Freeze incomplete or frozen inputs changed' }
```

The unresolved source-document decision must be settled before that last command
can succeed. To reproduce the current conservative freeze:

```powershell
python tests/validate_proof_receipts.py --freeze --mock --source $proofSource
```

It currently returns exit 1 and writes `freeze_status=blocked`. If Fable confirms
read-only access to the ten explicit Markdown references, the complete-freeze
command is:

```powershell
python tests/validate_proof_receipts.py --freeze --mock --source $proofSource --allow-install-corpus
if ($LASTEXITCODE -ne 0) { throw 'Full freeze failed' }
python tests/validate_proof_receipts.py --check-source --mock --source $proofSource --allow-install-corpus
if ($LASTEXITCODE -ne 0) { throw 'Frozen source evidence changed' }
```

`--allow-install-corpus` reads only bounded `.md` heads explicitly referenced by
the named copy. It never opens the resident index, token, settings, or helper.
Without that decision, supply a separately authorized corpus snapshot and adapt
the freeze input mapping in a later dispatch. Do not claim a complete freeze.
Review the regenerated manifest before execution; `--freeze` is an intentional
replacement of this artifact, whereas `--check-source` does not rewrite it.

After integration, first run the fixture smoke pass, then the complete mock pass:

```powershell
python scripts/librarian/proof_run.py --source $proofSource --out _scratch/proof/mock-12 --mock --limit 12 --concurrency 4
if ($LASTEXITCODE -ne 0) { throw 'Mock smoke run failed' }
python tests/validate_proof_receipts.py --receipts _scratch/proof/mock-12/receipts.json --mock
if ($LASTEXITCODE -ne 0) { throw 'Mock smoke receipts invalid' }
python scripts/librarian/proof_run.py --source $proofSource --out _scratch/proof/mock-all --mock --concurrency 4
if ($LASTEXITCODE -ne 0) { throw 'Full mock run failed' }
python tests/validate_proof_receipts.py --receipts _scratch/proof/mock-all/receipts.json --mock
if ($LASTEXITCODE -ne 0) { throw 'Full mock receipts invalid' }
python scripts/librarian/proof_score.py --receipts _scratch/proof/mock-all/receipts.json --holdout docs/library/holdout-split-2026-09-04.json
if ($LASTEXITCODE -ne 0) { throw 'Mock scoring failed' }
```

Fixture runs must remain labeled fixtures in both receipts and `report.md`.
Their measured quality denominator is zero. A gold fixture assignment rejected
by the production evidence validator must remain rejected in the receipts.

The following is the **future orchestrator subscription sequence**, after the
integration review and the blockers above have been resolved. It is not a run-P
execution instruction. Use one fresh output directory; never resume by dropping
failed attempts or rerun subsets to improve the score.

```powershell
if (Test-Path Env:ANTHROPIC_API_KEY) { throw 'ANTHROPIC_API_KEY must be unset' }
if (Test-Path -LiteralPath '_scratch/proof/subscription-2026-09-05') { throw 'Proof output already exists' }
python tests/validate_proof_receipts.py --check-source --mock --source $proofSource --allow-install-corpus
if ($LASTEXITCODE -ne 0) { throw 'Preflight source verification failed' }
python scripts/librarian/proof_run.py --source $proofSource --out _scratch/proof/subscription-2026-09-05 --model claude-sonnet-5 --concurrency 4
if ($LASTEXITCODE -ne 0) { throw 'Proof stopped; preserve and audit partial receipts' }
python tests/validate_proof_receipts.py --receipts _scratch/proof/subscription-2026-09-05/receipts.json --require-real
if ($LASTEXITCODE -ne 0) { throw 'Real receipts invalid; no quality acceptance' }
python scripts/librarian/proof_score.py --receipts _scratch/proof/subscription-2026-09-05/receipts.json --holdout docs/library/holdout-split-2026-09-04.json
if ($LASTEXITCODE -ne 0) { throw 'Scoring failed' }
python tests/validate_proof_receipts.py --check-source --mock --source $proofSource --allow-install-corpus
if ($LASTEXITCODE -ne 0) { throw 'Source evidence changed during proof' }
```

Archive the output directory, report, freeze, validator version, integrated Git
SHA, commands, exit codes, and before/after snapshots together. Never merge or
push from this dispatch. Changing `--model` is permitted by Fable's decision;
record the requested value and the identity actually reported by the CLI.

## Frozen inputs and hash definitions

The machine-readable freeze is
[`proof/manifest-2026-09-05.json`](proof/manifest-2026-09-05.json). Its `files`
map hashes the raw on-disk bytes of the taxonomy, assign prompt, card builder,
holdout, gold labels, index/clip/provenance/service code, and migrations 26/27.
`implementation_hash` binds that entire map. `hashes` contains the exact fields
that every receipt must copy into `inputs`.

The named source is 71,733,248 bytes, with the dispatch's SHA-256. Its measured
schema is **25**. The current `Index.open(explicit_worktree_duplicate)` upgrades
the duplicate to **27**, including the existing clip repair. The source is
hashed before copying and after measurement; SQLite opens only the local
duplicate. The manifest uses the upgraded evidence. `upgrade.sha256` records
this measurement's duplicate, whose migration timestamps make the file hash
specific to the run. A subsequent upgrade must reproduce the semantic input
hashes and schema, not that file hash. Actual execution records its own pre/post
upgrade hashes.

`canonical(x)` means Python JSON with `ensure_ascii=False`, `sort_keys=True`,
`separators=(',', ':')`, `allow_nan=False`, encoded as UTF-8. No trailing newline
enters a canonical hash. SHA-256 hashes bytes directly.

| Field | Definition |
|---|---|
| `items` | Every target as `[video_id, source_revision]`, ordered by `video_id`; 548 rows, including unresolved targets |
| `exclusions` | Explicit ID-to-reason object; currently `{}`. Unresolved heads are blockers, not exclusions |
| `manifest_hash` | SHA-256 of canonical `{"items": items, "exclusions": exclusions}`; same formula as `LibraryWorkService._manifest_hash` |
| `target_manifest_hash` | The same formula for receipt `target_ids`; only mock runs may use an ordered subset |
| `taxonomy_revision_hash` | Hash of normalized, sorted service nodes; `2f283053bbaca2e94c2dbd340f19c62a89f529457ac40ae5b1d2d84379d22d98` |
| `prompt_file_sha256` | Raw file bytes, including checkout line endings |
| `prompt_sha256` | UTF-8 of `read_text(encoding='utf-8')`, with universal newline conversion; pass this hash to `prepare_run` |
| `card_profile_hash` | Canonical hash of the explicit `card_profile` object |
| `holdout_ids_hash` | Canonical hash of all 60 unique IDs sorted by `video_id`; labels do not enter this list |
| `cards_hash` | Canonical hash of the per-item source revision, card hash, size, stratum, source type and evidence status |
| `corpus_heads_hash` | Canonical hash of per-item raw/decoded head hashes and actual bytes read; at most 8,192 source bytes per item |

The provisional `manifest_hash_kind=provisional-unresolved-heads` is not a
service manifest hash. Ten null revisions make it unusable for `prepare_run`.
Current partial measurements are 209 timed cards and 329 text-only cards, with
44 timed and eight text-only heldout cards resolved. These are counts of the
538 verified heads, not a remeasurement of the full library.

The taxonomy file's `canonical_hash` is not the service revision. Convert each
`retired` integer to a boolean, normalize path strings to NFC, set the name from
the last path segment, infer the parent ID from the prefix, and sort nodes by
`(len(path), path, shelf_id)`. Submit only `version_id`, `nodes`, and optional
`parent_version_id` to `approve_taxonomy`. Verify its returned revision against
the frozen normalized taxonomy. `normalized_taxonomy()` implements the exact
conversion in the validator.

Card-profile parameters are schema 1, `librarian`, `spread-longest-v1`, six
excerpts, 240 characters per excerpt, and 8,192 UTF-8 bytes including the
`library_cards.card_text()` wrapper. Card and excerpt hashes use the existing
card serializer, which differs from the compact service canonical JSON. Do not
substitute one serialization for the other. The card index freezes the actual
hash and byte count per item; the runner must compare every claimed card to it.

Freeze source heads before reasoning. The freeze command preserves bounded raw
heads in ignored `_scratch/proof/freeze/heads/`, named by SHA-256 of the item ID.
The isolated launcher should copy them into its own disposable corpus directory
and rewrite only its duplicate's `corpus_path` values before preparing work.
Compare raw and decoded head hashes first. Paths do not enter source revisions.
This permits helper execution without reading the resident install directory.
Archive these private heads with the receipts; do not commit corpus text.

## Helper and client boundary

The harness is the subscription client. It owns claim, reasoning, and submit.
The model receives no tools and never calls the registry. The reasoning process
uses `claude -p --json-schema <schema> --output-format json --tools ""` with the
selected model and the frozen prompt on standard input. Construct arguments as
an array; use no shell interpolation. Record the exact output schema text and
hash before launching the first process.

Before importing `server`, the launcher assigns `LOCALAPPDATA`, `APPDATA`,
`TEMP`, `TMP`, and `UOINK_OUTPUT_DIR` to paths inside one fresh directory under
`_scratch/proof/`. Verify and copy the named database to `<root>/Uoink/index.db`,
stage the frozen source heads, import `server`, set `server.PORT=5180`, and
start `main()` in a thread. Read the per-install token only through the isolated
`server.TOKEN_PATH`; record its path, never its contents. Verify all resolved
roots before startup. Refuse port 5179 rather than probing it. If 5180 is
occupied, abort instead of connecting to the existing listener. Tests use an
ephemeral port and an isolated fixture copy.

Approve the taxonomy on this disposable helper. Because public activation is
part of apply, seed the already approved taxonomy's active status during
isolated setup, before opening the proof's measurement interval: update
`shelf_versions.status` and `library_meta.active_version_id` in one local setup
transaction. Record that setup separately. Do not call apply, create an apply
journal entry, or increment the proof projection revision for setup. This is a
fixture/bootstrap action on the duplicate, not permission to activate the live
library. The integration review must check this implementation.

Take the `before` snapshot after setup and before `prepare_run`/claims. Keep
`librarian_apply_enabled=false`. Prepare work in frozen manifest order, with no
policy overrides. Send claim requests to `/tools/claim_library_work`, submit to
`/tools/submit_library_result`, and preview to `/tools/apply_reshelving` with
`mode=preview`, `activate_version=false`. Take the `after` snapshot after the
last request. No labels, pins, projection revision, policies, or activation may
change across that interval, and the proof apply journal count must be zero.

## Receipt JSON contract

The authoritative Draft 2020-12 JSON Schema is `RECEIPT_SCHEMA` in
[`tests/validate_proof_receipts.py`](../../tests/validate_proof_receipts.py).
To inspect or export it without running anything:

```powershell
python tests/validate_proof_receipts.py --schema
```

Root fields are required and reject unknown properties. Use `audit_extensions`
for additional observations. This is the wire contract for integration; adapt
the runner to it during the next run. The current work does not review or edit
Gemini's independently developed schema.

| Object | Required content |
|---|---|
| Root | Schema/contract versions, run ID, `mode` (`mock` or `subscription`), completed/aborted status and abort reason |
| `inputs` | Every named hash from the freeze's `hashes` object |
| `target_ids`, `target_manifest_hash` | Ordered attempted scope and bound target/exclusion hash |
| `config` | Client/transport/model, loopback URL, isolation/index/token paths, five environment roots, API-key-unset assertion, empty tools, concurrency/retry/time/error bounds, exact output schema and hash |
| `database` | Copied bytes before upgrade, copied bytes after upgrade, final original-source hash, schema before and after |
| `before`, `after` | Projection revision, full memberships, pins and item policies, active version/revision, apply-enabled flag, applied-label and proof-apply counts |
| `attempts` | Every reasoning attempt in per-item attempt order, including rejected/failed attempts |
| `transport_failures` | Every failed claim/reason/submit/preview exchange, including failures before a work ID exists |
| `targets` | One ordered terminal disposition per target, explicit nonassignment reason, work ID and last attempt ID where available |
| `preview` | Exact preview request and successful response for completed runs |
| `totals` | Input/card/prompt/response bytes, end-to-end wall milliseconds, retries, actual model-process count, rejected-attempt count and transport-failure count |

An attempt contains `attempt_id`, `video_id`, `work_id`, `attempt_token`,
`attempt_number`, `packet_hash`, the complete claimed `packet`, `card_text`,
`prompt_text`, `response_text`, their byte counts, `serialized_input_bytes`,
`wall_ms`, outcome, nullable `rejection_reason`, submitted `result`, raw
`submit_response`, `usage`, and `estimates`. Keep attempt tokens private with the
receipts. Never include the helper authentication token.

Preserve raw stdout in `response_text`, even when invalid JSON or empty. For a
successful result, mock JSON is `{"results":[{"video_id":id,"result":result}]}`;
the real CLI envelope contains that same object in `structured_output`. Save
the CLI envelope intact, including its usage data. A service outcome `error`
maps to receipt outcome `rejected`, while the raw result and response retain
the original `error`. Transport failures use a rejected attempt when a claim
was already obtained, plus a linked failure event. A claim failure before an
item is identified uses null `video_id`/`attempt_id` in the failure event.

Byte definitions are literal UTF-8 sizes. `prompt_text` is exactly
`render_prompt(template, normalized_taxonomy, card)`: the assign template,
safe `serialize_card(taxonomy)` at `{{TAXONOMY}}`, and one wrapped `card_text(card)`
at `{{CARDS}}`. No holdout labels, gold rationales, examples from the heldout
set, retry feedback, or extra instructions may be appended. Retry with the
same frozen prompt. `serialized_input_bytes` equals prompt bytes plus exact
output-schema bytes per reasoning attempt; it measures those client inputs,
not hidden provider system prompts or billable tokens. Attempt byte totals sum
all reasoning attempts. Transport events separately retain request/response
bytes, including identical-payload resends, so they are not double-counted as
new reasoning. Run wall time includes startup, claims, failures, retries,
preview, and final snapshots; it is not the sum of overlapping process times.

`usage.status=reported` requires CLI JSON provenance for the model and all four
counters: input, output, cache read, and cache creation. The validator maps the
last two to CLI `cache_read_input_tokens` and `cache_creation_input_tokens`.
If any required counter or model identity is absent, use
`{"status":"unavailable","reason":"..."}` and keep the raw stdout for audit.
Only CLI-supplied usage may be described as measured. Mock usage is unavailable.
`estimates.total_cost_usd` contains the CLI's estimate, with
`source=claude_cli_estimate`, or null with `source=unavailable`. It is never an
invoice-confirmed payment. Put any separately obtained invoice evidence in
`audit_extensions`; missing usage cannot establish a dollar-cost gate.

The validator checks successful accepted assignments against the frozen card:
item/source/card/excerpt identities, approved shelf ID/path, confidence at least
0.60, packet basis, matching evidence kind, and a verbatim quote under 25 words.
It also enforces the service's original-prose source-type restriction. Receipt
validation exits 0 as `FIXTURE_VALID` or `RECEIPTS_VALID_AUDIT_REQUIRED`; neither
is a product-quality PASS. `--require-real` rejects mock evidence. Aborted or
malformed receipts exit 1 and remain audit artifacts.

## Abort conditions

Stop launching work, terminate owned reasoning children, stop the owned helper,
and persist partial receipts on any abort. Preserve all completed and in-flight
attempt records; use explicit interruption/transport reasons. Never delete
receipts or repair the live library as part of cleanup.

- Reject startup for an API key present even with an empty value, a source/hash
  mismatch, incomplete freeze, changed heads/prompt/taxonomy/profile, unsafe
  root, occupied port 5180, port 5179, or enabled apply.
- End the run at two hours measured from process start. Child timeouts must
  respect the remaining budget. Never exceed four concurrent `claude -p`
  processes or one new reasoning retry per rejected result. An ambiguous
  submit may resend the identical payload/submission key to recover its
  idempotent receipt; it must not obtain an extra reasoning attempt.
- Astra's operational error guard is greater than 10% after at least 20
  completed reasoning attempts. Numerator: rejected attempt records plus
  transport-failure events; denominator: completed reasoning attempts. This
  deliberately counts a rejected attempt and its transport event separately.
  Evaluate continuously; the final validator also rejects an exceeded ratio.
  This guard is an execution-plan choice, not a quality threshold from Fable.
- Abort immediately for an applied label or proof-created apply record, changed
  projection/membership/pin/policy/activation, a changed/deleted/pinned target,
  invalid evidence accepted by the service, missing attempt records, or an
  unreconciled claim/submit response. Never refill the manifest with replacements.
- A missing heldout item, empty stratum, zero assignments, invalid evidence,
  precision below 0.90, or coverage below 0.80 blocks quality acceptance after
  scoring. Retain the failed result as the one proof run; do not tune and rerun.

## Run-Q audit checklist

1. Review the integrated runner/scorer against this contract, including
   ephemeral-port fixture coverage, key/port refusals, CLI timeout/child cleanup,
   bootstrap activation, and recovery of failed HTTP submissions. This review
   is deferred to the next run as dispatched.
2. Match all receipt hashes to the complete frozen manifest. Recompute the
   548 ordered source pairs, exclusions, card hashes, corpus heads and 60-ID
   split. Verify both source file hashes and the actual upgrade receipt.
3. Reconcile every registry work/attempt/submission record with the receipt
   history and every terminal target. Inspect raw transport failures, preview
   request/response, helper logs, and the independent database snapshot. A
   self-consistent JSON file alone does not prove that HTTP calls happened.
4. Recompute every accepted membership's identity and quote checks independently.
   Inspect text-only source origins. Compare exact rendered prompts and output
   schema against the recorded process invocation; heldout labels stay outside
   the model boundary. A real result must not originate from the mock fixture.
5. Remeasure strata from actual frozen excerpts. Use the gold labels only for
   scoring, with their frozen file hash. Map a gold path to the longest matching
   prefix in the approved taxonomy (for example, Security/Agent Guardrails maps
   to the approved Security shelf). An unmappable or ambiguous gold label needs
   adjudication; never silently remove it from the denominator.
6. For each stratum report correct primary assignments, all valid evaluated
   assignments, total heldout targets, and abstentions broken down by outcome.
   Precision is correct/assigned; coverage is assigned/total. Abstentions count
   against coverage. No assignments or an empty stratum cannot pass. Fixture
   observations and measured model observations use separate denominators.
7. Recompute byte/retry/error totals and end-to-end duration. Compare reported
   usage with raw CLI JSON and preserve unavailable counters. Keep CLI cost
   estimates separate from any invoice evidence. Audit the error guard at each
   completion boundary, not only the final ratio.
8. Compare complete before/after state and apply journal records. Check pins and
   item policies even when empty in this copy. Record recovery-gate acceptance
   from the integrated service review; receipt validation does not re-prove it.
   Apply remains disabled until all P2-0 through P2-7 gates are accepted.

## Run-P validation evidence

The offline validator self-test currently passes 39 positive/adversarial cases,
with zero helper calls and zero model calls. It covers fixture/real separation,
identity and prompt tampering, Unicode byte accounting, retries, state changes,
forbidden ports, missing receipts, and unavailable usage/cost. The freeze
command verified the named source hash and upgraded only a worktree duplicate.
It retained ten unresolved heads and exits 1 rather than accepting them.

The requested full suite could not start: this environment's
`C:/Python314/python.exe` reports `No module named pytest`. An installation
attempt targeted only `_scratch/proof/python-deps`; the restricted network
rejected the PyPI connection. The baseline of 931 tests is inherited evidence,
not a test result from run P. Re-run the exact suite command in the integrated
environment before proceeding.

Static checks also passed for all recorded file hashes, 548 unique ordered
targets, the provisional manifest hash, 538 archived raw/decoded corpus-head
hashes, normalized taxonomy, and the holdout ID hash. The original source hash
remained unchanged. Python compilation passed. `--verify-inputs --mock` exits 1
with `Input freeze is incomplete`, as required while ten heads remain unresolved.

Git staging was attempted for exactly the three assigned files. It failed with
`index.lock: Permission denied` in the shared Git administrative directory.
The files remain unstaged in this worktree; no commit, merge, or push occurred.
