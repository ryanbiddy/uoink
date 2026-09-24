Use this specification to assemble the stage 4 artifacts without changing the
original v3 identity freeze. The validator implementation is
[`tests/validate_proof_receipts.py`](../../tests/validate_proof_receipts.py).
All paths below are relative to `docs/library/proof/`; use the actual freeze
date. AP creates the validation route and specification, not production cards,
labels or execution receipts.

| Manifest `files` key | Default artifact name |
|---|---|
| `holdout` | `holdout-v3-2026-09-07.json`, immutable original |
| `bindings` | `holdout-v3-stage4-bindings-<date>.json` |
| `packet` | `holdout-v3-stage4-labelling-packet-<date>.json` |
| `diff` | `card-contract-v2-diff-<date>.json` |
| `labels_gemini` | `labels/holdout-v3-stage4-labels-gemini-<date>.json` |
| `labels_grok` | `labels/holdout-v3-stage4-labels-grok-<date>.json` |
| `adjudication` | `labels/holdout-v3-stage4-labels-adjudicated-<date>.json` |
| `gold` | `labels/holdout-v3-stage4-gold-<date>.json` |
| `mapping` | `labels/holdout-v3-stage4-mapping-<date>.json` |

Keep the taxonomy, both parent-taxonomy entries, prompt, card builder, service
and other implementation-file records in `files`. Each record has `path` and
the SHA-256 of exact file bytes. The final `implementation_hash` binds the
complete file-record object. Protect JSON bytes from EOL conversion at
integration; do not rewrite an archived file to make its hash agree.

The new manifest is `manifest-stage4-<date>.json`. It adds `stage: 4`,
`card_payloads` (an object keyed by all 548 IDs), and `probe` to the existing
manifest format. `cards` remains the per-ID index with `source_revision`,
`card_hash`, `card_bytes`, `stratum`, `source_type` and `status`. Each index
entry must match its complete payload. The payload's card hash uses
`library_cards._hash` over the card with `card_hash` removed; byte counts use
`library_cards.card_text(card).encode('utf-8')`, including the wrapper.

The exact profile is:

```json
{
  "profile": "librarian",
  "schema_version": 1,
  "selection_version": "spread-longest-v2",
  "n_clips": 6,
  "clip_chars": 240,
  "byte_budget": 8192,
  "corpus_read_bytes": 8192,
  "serialization": "library_cards.card_text UTF-8"
}
```

Keep `manifest_hash` as the historical identity/exclusion hash. It cannot
identify the new cards by itself. `stage4_freeze_hash(manifest)` supplies the
additional manifest-content binding needed before labels exist. It hashes the
object containing `stage`, `source`, `items`, `exclusions`, `cards`,
`corpus_heads`, `card_profile`, `taxonomy`, `execution`, `probe`, plus
`prompt_file_sha256`, `prompt_sha256` and `card_builder_sha256` from `hashes`.
Structured hashes use the validator's `digest`: sorted-key UTF-8 JSON,
`ensure_ascii=False`, separators `(',', ':')`, no nonfinite values or newline.
This differs from the card serializer; use the named helpers.

The content binding excludes label-file hashes. That avoids a cycle in which
the manifest hashes the bindings and the bindings hash the manifest's entire
file. The final manifest's exact byte hash belongs in the execution record and
checksum inventory after every seal is complete. A content hash must never be
presented as that exact file hash.

Adapters can call
`freeze_inputs(staged_source, stage=4, stage4_sealed=False)` after the v2 builder
is integrated. This reads the named source staged inside the current checkout
and archived heads; it does not read original corpus paths. The returned status
is `awaiting-stage4-seal`, with a provisional zero gold hash, so receipt
validation refuses it. Use its cards, profile, probe and content binding to
build the packet and seal. The normal `freeze_inputs(..., stage=4)` then
rebuilds the same cards and binds all completed files. Its content hash must
match the prepared candidate. The CLI `--stage4 --freeze --mock --source <copy>`
requires the completed seal and validates before writing the assigned manifest.
An existing differing manifest is never overwritten.

`stage4_bindings(manifest, original_v3, original_file_sha256)` returns the
binding document. Verify the original file bytes before passing them. The
required shape is:

```text
schema_version: 1
kind: "holdout-v3-stage4-bindings"
target_count: 60
original_holdout_sha256: exact original v3 file hash
stage4_freeze_hash: stage4_freeze_hash(manifest)
manifest_hash: manifest.manifest_hash
cards_hash: manifest.cards_hash
card_profile_hash: manifest.hashes.card_profile_hash
strata:
  timed_evidence: 47 rows in original v3 order
  text_only: 13 rows in original v3 order
```

Every row contains exactly `video_id`, `stratum`, `source_revision`,
`old_card_hash` and `new_card_hash`. The first four values come from the original
v3 row; the new hash comes from the new card index. The original v3 file hash
is `855749efcaca5e985c04a9efef2decc4ee2dca3b24c8c3871f01079a9acd314c`.
Validation compares the entire document to the expected binding, preserving
order, both hashes and the original stratum. Adding prose never moves a timed
identity into another denominator.

The packet contains `kind: "holdout-v3-stage4-labelling-packet"`,
`bindings_sha256`, `stage4_freeze_hash`, `card_profile_hash`, the complete
normalized `taxonomy` object, `subject_rule: "admissible-excerpts-only"`, and
`cards`: 60 distinct rows containing `video_id`, `stratum`, and the complete
`card`. Each packet card must equal its manifest payload. The packet must
contain no previous labels, outcomes, predictions or rationales.

Both original label documents and the adjudication contain `packet_sha256`,
`bindings_sha256`, `taxonomy_revision_hash`,
`subject_rule: "admissible-excerpts-only"`, a nonempty `prior_v3_exposure`
declaration, and `items`. Each of the 60 rows contains `video_id`, original
`stratum`, unchanged `source_revision`, new `card_hash`, `outcome`,
`shelf_path`, and `evidence: {excerpt_id, quote}`, along with the labelling
workflow's shelf IDs, confidence and rationale fields. Every quote must occur
in one admissible excerpt and satisfy the unchanged 1-to-24-word rule. Preserve
unmappable and unsupported rows. Human review checks the subject judgement;
quote matching alone cannot establish that judgement.

The adjudication also contains `label_file_sha256`, an object with
`labels_gemini` and `labels_grok` hashes, and a nonempty `sealed_at` timestamp.
Retain disagreements and reasons in its rows. Gold remains a list of 60 rows
for scorer compatibility; each row preserves all adjudicated fields and adds
`sealed: true`. The execution record and independent audit must establish that
the seal predates the first probe process.

The mapping document contains `scoring_version: "strict-mapped-primary-v2"`,
`bindings_sha256`, `gold_sha256`, `adjudicated_sha256`,
`taxonomy_revision_hash`, and `items`, an object with exactly the 60 selected
IDs. Every item carries `source_revision`, new `card_hash`, original
`stratum`, `gold_path`, `outcome`, `mapped_path`, `mapped_shelf_id` and
`scorable`. Use null mapped fields and `scorable: false` where no unambiguous
approved ancestor exists. The validator checks the row references and derives
the strict ancestor mapping independently. Scorer adapters must use these new
bindings and gold while retaining full-manifest validation and the strict rule.

The diff ledger binds `stage4_freeze_hash` and `card_profile_hash`; its `items`
list has exactly 548 rows, each with `video_id`, unchanged `source_revision`,
`old_card_hash` and `new_card_hash`. Include Gemini's change classifications
and displaced/truncated excerpt details in each row. The validator checks the
complete identity/hash ledger. Independent review of Gemini's helper and the
source replay must check the classifications and timed selection.

The manifest's exact `execution` object is:

```json
{
  "model": "claude-opus-5",
  "effort": null,
  "batch_size": 8,
  "concurrency": 4,
  "max_retries": 1,
  "wall_budget_ms": 7200000,
  "error_rate_limit": 0.1,
  "error_rate_min_attempts": 20,
  "guard_rule": "distinct-failed-completed-attempts-plus-anonymous-v2",
  "guard_parameters": {
    "min_completed_attempts": 20,
    "numerator_multiplier": 10,
    "denominator_multiplier": 1,
    "comparison": "strictly-greater"
  }
}
```

The runner's receipt `config` must carry the same model, effort, concurrency,
retry and guard fields. Record batch size 8; every process has at most eight
attempts. Assignment argv names `claude-opus-5` and has no effort flag. Probe
receipts use 900,000 ms; full receipts use 7,200,000 ms. Grok and Fable must
reconcile this interface with the runner and execution-record adapters before
freezing. These declarations do not substitute for observed client provenance.

`stage4_probe()` produces the deterministic development selection and its
900,000 ms budget, batch 8, concurrency 4 and retry cap 1. Record the returned
object unchanged in `manifest.probe`. `validate_probe_receipts()` invokes
`validate_receipts(require_real=True, require_whole_manifest=False)`, still
requiring completed receipts and all original artifacts. Its additional
criteria are exactly sixteen first-attempt terminal outcomes, two calls of
eight, and zero rejected/errored completions or transport failures. Legitimate
unmapped/unsupported outcomes may pass. The full validator defaults to
`require_whole_manifest=True`; the scorer must preserve that default and
refuse probe-only status. No probe result establishes P2-7.
