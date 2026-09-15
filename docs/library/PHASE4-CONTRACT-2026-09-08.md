# Phase 4 contract: bounded library access, 2026-09-08

Contract: `phase4-v1-2026-09-08`. Owner: Astra (codex). Integrator: Fable.
Base inspected: `42481e532b95879d2230d74644f13dadcbc25b42`, the commit containing
[the AU brief](PHASE4-BRIEF-2026-09-08.md). This freezes implementation decisions
for AV. It records no implementation or client acceptance result.

The supported pair is Claude Code over stdio through `uoink_mcp.py`. Success means
that client can discover a saved item, retrieve a bounded quotation with its
identity and revision, open its source link, reconnect after a process restart,
and distinguish unavailable storage from an empty library. Resources, prompts,
briefs and the optional mirror use the same evidence identities.

The [orchestration contract](ORCHESTRATION-V1-2026-09-04.md) governs ownership and
acceptance. The [phase plan](ASTRA-PHASE-PLAN-2026-09-04.md),
[reach memo](MCP-REACH-2026-09-04.md) and current
[Phase 2 contract](PHASE2-CONTRACT-2026-09-04.md), including its amendments, are
inputs. Decisions below supersede the reach memo where they differ. Grok's AU
protocol-limits note supplies current client/specification evidence; Gemini's AU
test plan supplies independent fixtures. Fable must reconcile both against these
gate IDs before AV. Neither companion file was present in this worktree during
this review; their contents have not been assumed.

No model, helper, live index, listener, port 5179, migration, package installation,
commit or merge is part of AU. AV must preserve the separately owned Phase 2/3
services, card selection, prompts and proof tests. No database migration is needed
for this design. `0029` remains reserved to Fable if a demonstrated implementation
need requires an amendment; workers must not allocate a different number.

## Baseline and implementation seams

These are source observations at the base, not runtime measurements:

| Surface | Observed behavior and consequence |
|---|---|
| `uoink_mcp.py` | 25 explicit tools; imports `server` in-process with logging redirected to stderr. No resource or prompt registrations. It does not proxy requests through the resident HTTP helper. |
| `server.py` | `_mcp_initialize_result` advertises tools only. `_handle_mcp_post` handles initialization, ping and tools. `/tools/<name>` uses `uoink_mcp_tools.TOOL_REGISTRY`. HTTP and stdio are distinct adapters. |
| `uoink_mcp_tools.py` | `search_clips` defaults to 20 hits, caps at 50, and returns full clip text without source revisions. `get_evidence_card` uses the shared builder, default profile `full`; `get_uoink_corpus` reads the whole file. These are not the new bounded contract. |
| `library_cards.py` | Schema 1, selection `spread-longest-v2`; `librarian` is at most 6 excerpts of 240 characters and 8,192 UTF-8 bytes including `card_text`. Full defaults remain 10 clips. Source revision hashes supplied evidence and bounded opening prose, not the complete corpus file. |
| `scripts/recall_hook.py` | Read-only SQLite, explicit untrusted-data fence, 1.5-second budget, at most 5 hits, 160 quote characters and 1,200 total context characters. It reads storage directly and can work with the HTTP helper stopped. |
| `memory_layer.py` | Taste/user mirroring is best effort. `_atomic_write` uses a shared `.tmp` name; `_maybe_mirror` replaces destinations without checking user edits. Neither is sufficient for the corpus mirror. |
| Phase 2 | Six registry tools are HTTP-only at this base. Work rows bind one item to an assignment run; there is no brief work kind. `list_work` can reap leases, so it is not a pure report reader. |
| Client assets | `.mcpb/manifest.json` declares manifest 0.4 and an installed-Python thin launcher. `skills/uoink/SKILL.md` still requires an Anthropic key and assumes YouTube/timestamps. `source_manifest.py` describes several clients without per-client acceptance evidence. |

AV's adapter owner implements a shared `library_resources.py` for URI validation,
bounded reads and safe rendering, with thin stdio registrations. Fable separately
reserves any needed edits to `server.py`, `uoink_mcp_tools.py`, `memory_layer.py`,
build/install manifests and client assets. Do not create another card selector,
revision algorithm, queue validator or correction store in an adapter.

## Identity, URI grammar and discovery

All new resource URIs use authority `library` and version path `/v1`. They are
scoped to the configured Uoink server instance; moving a URI between installations
does not establish that the libraries are the same. Resources never resolve a
client-supplied filesystem path or fetch a remote URL.

`item_key` is unpadded base64url of the exact UTF-8 `yoinks.video_id`; `shelf_key`
encodes the stable `shelf_id` the same way. Decoded IDs contain 1–512 UTF-8 bytes,
no control characters, and must round-trip to the identical encoding. Do not case
fold or normalize identities. Slugs are discovery aliases only. A hash is exactly
64 lowercase hexadecimal digits. `selection` is the card builder's version string
matching `[A-Za-z0-9_-]{1,64}`. `offset` is a canonical nonnegative decimal byte
offset with no leading zeros except `0`; `length` is a positive decimal.
New structured hashes use SHA-256 over UTF-8 `library_cards.serialize_card(value)`;
existing card/excerpt hashes stay unchanged, and corpus/filename hashes use the
raw bytes explicitly named above. Render version is `reach-markdown-v1`; a future
change to the addressed representation requires a URI version change.

Freeze exactly these five templates, all returning `text/markdown`:

| Template after `uoink://library/v1/` | Meaning |
|---|---|
| `items/{item_key}/cards/{source_revision}/{selection}/{card_hash}` | The default `librarian` card, with all three bindings checked. No arbitrary profile or selection options. |
| `items/{item_key}/excerpts/{source_revision}/{excerpt_id}` | One original excerpt, using the existing card excerpt identity before truncation. Maximum 2,000 Unicode code points of text. |
| `items/{item_key}/corpus/{corpus_revision}/{offset}/{length}` | A bounded original-corpus chunk. `corpus_revision` is SHA-256 of the complete stored file bytes, separate from card `source_revision`. |
| `shelves/{shelf_key}/{taxonomy_revision}/{projection_revision}/{shelf_revision}/{offset}` | Shelf definition and a page of current members. Here `offset` is a member ordinal, and `projection_revision` is the canonical decimal Phase 2 revision. |
| `briefs/{date}/{brief_hash}` | One persisted client-produced brief; date is a valid UTC `YYYY-MM-DD`, hash binds the accepted artifact. |

For example, item ID `video-1` has key `dmlkZW8tMQ`. Its card URI ends with the
actual `source_revision`, `spread-longest-v2` and `card_hash` returned by the
builder; placeholders are not valid hash values. Canonical URIs are returned by
discovery, so clients need not manufacture hashes.

Reject other authorities, ports, userinfo, schemes, fragments, queries, percent
escapes, backslashes, dot segments, malformed UTF-8/base64, extra segments and
overlong URIs. Decode once. A clip sequence number, row ID, title or slug must
never substitute for an excerpt key. The proposed unversioned memo URIs were
never shipped in this base; no redirect aliases are required for them.

`resources/templates/list` returns these five definitions, with fixed descriptions
and argument meaning. `resources/list` returns at most 41 curated entries: the
latest valid brief for the UTC date, up to 20 recent item cards, 10 additional
highest-engagement item cards, and 10 active shelves. Deduplicate item identities;
tie-break by stable ID. Rank shelves by nondeleted member count, then shelf ID.
Do not enumerate clips or the entire corpus. Omit absent categories and stale
briefs. If storage fails, fail the list rather than return an empty library.

The list is one page, without `nextCursor`; supplied cursors are invalid. If the
wire budget is reached, drop whole entries in the order above. This is a curated
picker, not a complete inventory. Search remains the route to other items. Emit
resource `size` only when the exact rendered UTF-8 size is known; otherwise omit
it. Never substitute file size, character count or an estimate.

## Bounded reads and refusal shapes

All numbers in this section are Uoink product limits chosen for Phase 4. They are
not claims about Claude's context window or MCP's maximum message size. Grok must
identify any stricter client limit; a stricter limit requires a recorded contract
amendment and affected tests before implementation is accepted.

| Limit | Frozen value |
|---|---|
| New read/prompt request | 8,192 serialized UTF-8 bytes; URI at most 2,048 bytes; query/topic at most 512 code points and 2,048 bytes |
| New read/list/prompt response | 65,536 serialized UTF-8 bytes including the complete MCP result or error; count duplicate structured/text representations if present |
| Resource text | 24,576 UTF-8 bytes after safe rendering; card text retains its stricter 8,192-byte limit |
| Bounded search | Default 5, maximum 20 hits; one excerpt preview at most 240 code points per hit |
| Card | Existing default `librarian` profile: at most 6 excerpts, 240 code points each; preserve the builder's actual truncation and mixed-evidence rules |
| Excerpt | One excerpt; at most 2,000 code points, with original length and explicit `truncated` flag; no concatenated clips |
| Corpus chunk | `length` 1–8,192 source bytes; suggested 4,096. Source-file admission ceiling 16,777,216 bytes, then `resource_too_large` |
| Shelf page | Up to 20 nondeleted members, sorted by stable item ID; whole entries only; explicit next URI or null |
| Service deadline | 2 seconds from accepted request through result construction, including reads, locks and serialization; no internal retry after deadline |
| Read concurrency/rate | At most 2 active new read/prompt operations per serving process; 60 admissions per rolling 60 seconds, shared across these new entry points; reject excess without queuing |

The rate limit is a per-process guard, not an installation-wide quota or permission
boundary. One prompt fan-out consumes one admission and the same total deadline.
Legacy tool and Phase 2 rate limits remain in force for their own calls.

Freeze three additive read tools in both the shared registry and stdio:

| Name and arguments | Return |
|---|---|
| `search_library(query, limit=5)` | Bounded clip-first search, with item-FTS fallback for items without clips. Each hit carries item identity, source revision, safe title/source link, evidence kind/timing, excerpt preview and revision-bound follow-up URIs. Return `next_step` when more retrieval is needed; do not imply exhaustive search. |
| `get_library_item(video_id?, slug?)` | Exactly one selector required. Return the unchanged default Librarian card under `card`, plus canonical card, selected-excerpt and initial corpus-chunk URIs. If corpus chunk admission fails, report that separately while retaining a usable card. |
| `read_library_resource(uri)` | Same URI validation, contents and refusals as `resources/read`; a tool fallback for a client that cannot attach a template-derived URI. No second renderer. |

Tool arguments are strict objects: reject unknown fields, duplicate JSON keys,
non-finite values, nulls for supplied selectors, wrong types and booleans used as
integers. Out-of-range limits fail; do not silently clamp them. Existing
`search_clips`, `get_evidence_card` and `get_uoink_corpus` retain their names,
arguments and default behavior. Teach the new workflow to use bounded tools;
do not suggest the whole-corpus legacy tool as an automatic overflow fallback.
New tool successes include `ok:true`, `schema_version:1` and this
`contract_version`, followed by the named result fields. Their model-facing text
uses the shared safe envelope renderer; adapters must not append an unfenced
copy of source prose. `read_library_resource` returns the same `contents` array
as the resource method, including identical resource text.

The shared module obtains a coherent item/clip snapshot and uses `library_cards`
for card revisions, selection and rendering. Resolve excerpt IDs with that
module's existing pre-truncation identity rules, including text-only opening
prose; do not hash a shortened quote or replace an ID with its sequence number.
Search previews use the same bindings. If item-FTS text cannot be tied to an
original excerpt, label it `discovery_hint`, provide the card URI, and omit an
excerpt URI. Hints cannot establish a quotation.

A card read returns exactly `card_text(default_librarian_card)` as its resource
text. Other documents use a fixed envelope containing schema/contract version,
identity, requested revision, body, evidence type, truncation, and continuation.
Never advertise a resource whose reader has not been implemented.

Check current deletion state before returning any stored resource or cached
document. Compare all requested revisions with a coherent current snapshot;
never silently serve current text under an old URI. Phase 4 does not retain old
source snapshots. Reindexing unchanged content keeps keys stable; changed source
or selection produces a new URI and an old-URI refusal. Shelf reads additionally
recheck member deletion/source state, even if projection revision did not change.
`shelf_revision` hashes the canonical shelf definition, taxonomy/projection
revisions and ordered nondeleted member identities with their source revisions
and displayed metadata. It binds every page of that membership snapshot. A
source edit or deletion invalidates old shelf addresses.

Corpus chunks hash the full file with bounded streaming I/O, reject files above
the admission ceiling and verify the file did not change during hashing/read.
The offset must be a UTF-8 boundary. End at the last complete code point that
fits `length`; return actual start/end bytes, total bytes, `has_more` and the next
URI. Offset at EOF returns an empty complete document; offset beyond EOF is
invalid. If `length` cannot fit the next complete code point, refuse
`invalid_request` with the minimum required byte length; never return a
continuation that makes no progress. Invalid UTF-8 refuses instead of fabricating replacement
text. Embedded metadata remains data, and local paths are redacted with explicit
redaction spans; offsets/hash still describe the original bytes. Corpus chunks
are reading aids, not an extension of Phase 2's accepted evidence bases.

An explicit prefix/page is a successful bounded selection and carries truncation
or continuation. Never cut an identity, link, fence, JSON document or UTF-8
sequence to meet a budget. Drop complete search/shelf entries; if one mandatory
unit or rendered excerpt cannot fit, return `resource_too_large` with a smaller
chunk request or bounded-card next step. Check both rendered text and final wire
bytes. Do not label truncated content complete.

Domain refusals have this shape, with no raw exception, path, token or quoted
attacker input in `message` or `details`:

```json
{
  "ok": false,
  "schema_version": 1,
  "contract_version": "phase4-v1-2026-09-08",
  "error": {
    "code": "revision_unavailable",
    "message": "This revision is unavailable. Resolve the item again.",
    "retryable": false,
    "details": {"next_step": "get_library_item"}
  }
}
```

Freeze domain codes `invalid_request`, `resource_not_found`, `resource_deleted`,
`revision_unavailable`, `resource_too_large`, `invalid_encoding`,
`library_unavailable`, `deadline_exceeded`, `rate_limited`, `feature_unavailable`,
`stale_brief`, `invalid_source_data` and `internal_error`. Only unavailable,
deadline and rate failures are retryable unchanged. Rate failure includes integer
`retry_after_ms` bounded to
60,000; stale/deleted replies contain no old source content. A known soft deletion
returns `resource_deleted`; after hard purge, missing identity returns
`resource_not_found`. Concurrent change refuses with `revision_unavailable`.

For legacy MCP, invalid parameters use JSON-RPC `-32602`; missing/deleted resource
uses `-32002`; other resource execution failures use `-32603` with the domain
envelope in `error.data`. Tools return a text encoding of the domain envelope and
`isError:true`; success uses `isError:false`. Resource failures never masquerade
as successful `contents`, and prompts have no invented `isError` field. The
plain HTTP tool adapter retains its existing outer envelope/status conventions.
These transport rules follow the pinned-era
[resource](https://modelcontextprotocol.io/specification/2025-11-25/server/resources),
[prompt](https://modelcontextprotocol.io/specification/2025-11-25/server/prompts)
and [tool](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)
specifications; the domain codes and budgets are this contract's choices.

## Trust boundary

Use `library_cards.card_text` unchanged for cards. For other documents apply its
canonical JSON escaping to the data body inside a fixed untrusted-evidence fence
and preface. Titles, source text, shelf names/definitions, client brief prose,
prompt argument values and error details are data. None may close the boundary,
introduce a role/message or create an instruction outside it. Preserve original
quotation text through reversible escaping, and report any redaction; never
silently rewrite a quote and then claim verbatim identity.

Source links must be validated HTTP(S) URLs with a host, no credentials, controls
or whitespace; unsafe/missing links are null. Render link destinations separately
from escaped labels. No raw HTML, remote images, executable links, local file
URIs, terminal escapes or automatic fetches. Expose a valid original source link
for text-only items without inventing timestamps. Coarse clip timing stays coarse.
If an existing hashed card contains an unsafe URL, active terminal control
sequence or leaked runtime path, refuse with `invalid_source_data`; do not mutate
its fields while retaining its hash.

Prompt instructions live in fixed server-authored text outside the data fence.
No prompt reads credentials or calls a model, starts capture, applies assignments,
mints approvals, installs a connector or launches another client. Recall retains
its separate hook envelope and existing limits; test its delimiter neutralization
alongside the tool/resource cases. Structural tests prove fence preservation.
Only AW's authorized client exercise can establish observed model behavior.

## User-invoked prompts

Freeze four names. All arguments on `prompts/get` are strings; validate them
before data access. A missing required argument, unknown name/argument, impossible
date or malformed number returns invalid parameters. No partial prompt on failure.

| Prompt | Arguments | Returned messages |
|---|---|---|
| `consult-library` | Required `topic` | Fixed instruction to answer from cited evidence plus up to 5 relevant excerpt previews, each at most 240 code points, with bound follow-up URIs and public source links. Empty results explicitly say no matching evidence was retrieved. |
| `evidence-brief` | Required `topic`; optional `since` as UTC `YYYY-MM-DD` | Fixed instruction to compose a citable brief plus up to 5 bounded Librarian cards. Include exact selection/counts, source identities, capture dates and shelf metadata. `since` filters capture time, never publication time. It returns evidence, not a server-written synthesis or a queued job. |
| `whats-new` | Optional `days`, canonical decimal 1–30, default `7` | Deterministic counts and up to 20 events for the half-open UTC interval ending at invocation time: captures, recorded shelf revisions and applied membership changes. Identify event kind and available history coverage; never infer old changes from today's state. |
| `reshelve-review` | Required `preview_id`, using Phase 2's ID grammar | Read the existing stored preview: run, revisions, delta hash, expiry, additions/removals, preserved pins, exclusions and churn, plus the local review route. Expired/invalidated preview refuses. No call to `apply_reshelving`, no new preview, no approval token. |

Each result contains one fixed instruction message and one fenced data message,
both in the protocol's supported user-message form. Use the shared reader for
lookups; do not tell the model to fetch evidence that the prompt promised to
include. If the complete review delta exceeds the response budget, return
`resource_too_large` with a local review next step rather than show an incomplete
approval view. Counts may be complete while event/member rows are a labeled
sample. Missing Phase 2 tables/history returns `feature_unavailable` or an
explicit coverage gap, not invented empty history.

Prompt invocation changes no queue, source, projection, settings or mirror state.
Use a report-only reader for queue/preview data: the existing `list_work` performs
lease maintenance and must not be called implicitly by prompt/resource reads.

## Brief generation belongs to the client

A daily brief is a client-run report over the Phase 2 queue and applied journal,
with a frozen evidence sample. The current assignment queue cannot accept a
brief row. Do not insert a synthetic video, claim assignment work merely to write
a report, or change Phase 2's schema/result validator. The client tracks its own
report job; Uoink prepares bounded input and validates/persists the submitted
artifact. No server scheduler, model, sampling request or fallback cognition.

Freeze two additional tools, separate from the three ordinary read tools:

| Name and arguments | Contract |
|---|---|
| `get_library_brief_input(date, run_id)` | Both required. Date is a valid UTC day; run uses Phase 2's ID grammar. Read a consistent report snapshot for that run/date. Return `job_key`, `input_hash`, bound queue/run/projection revisions, capture/event counts, coverage, up to 20 work-status rows and up to 5 default Librarian cards. No lease or persistent mutation. |
| `publish_library_brief(job_key, input_hash, input_packet, submission_key, document, citations, usage)` | Explicit write, invoked only as part of the user's requested brief job. Validate the current bindings and persist one artifact/receipt. It cannot apply labels or alter the assignment queue. |

The input packet is at most 24,576 UTF-8 bytes before the MCP envelope; whole cards
are omitted to meet the 65,536-byte wire limit. Sample recent eligible items by
capture time descending, then item ID; include queue dispositions and exclusions
separately from evidence. State exactly which items were sampled and whether
anything was omitted. UTC date selects `[00:00:00Z, next-day 00:00:00Z)`; every
packet records `as_of=min(server_now, day_end)`. Future dates are invalid. The
date describes capture/activity time, not publication recency.

`input_hash` binds the complete canonical input packet, excluding the returned
`input_hash` and `job_key` themselves, including selected card hashes,
all covered queue state/counts, run revision, taxonomy/projection revision, latest
covered operation sequence and interval. `job_key` is SHA-256 of canonical
`[date, run_id, input_hash]`. Freeze queue-state digests as well as run revision:
a lease/state change need not increment `run_revision`. A client-local job record
tracks `prepared`, `running`, `submitted`, `stale`, `failed` or
`waiting_for_client`, with the input hash and receipt. If no client runs, no brief
appears; the UI may show waiting. A clock alone never produces a document.

Publication accepts at most 65,536 request bytes, an 8,192-byte UTF-8 `document`
and 20 citations. Each citation names item ID, source revision, card hash,
excerpt ID, a nonempty quote of at most 500 code points, evidence kind and original
time bounds. The quote must occur within that one supplied excerpt using Phase
2's NFC/whitespace matching rules. Every source-dependent statement in the brief
must cite supplied evidence; textual validation is necessary, and AW checks
faithfulness separately. Summary hints cannot be submitted as original quotes.

The submit request echoes no caller-controlled path, date or run outside the
bound job packet. `submission_key` follows Phase 2's operation-key grammar. Store
an immutable artifact and exact receipt under `DATA_ROOT/reach/briefs/`, with a
manifest binding the job packet, request hash, document/citations, UTC timestamps,
client identity and usage. Retain the prepared packet alongside the client job
so publication can present it as `input_packet` after restart. The server rebuilds
and checks its canonical content against current authoritative data, using the
original date/`as_of` to filter the interval. Require
`day_start <= as_of <= day_end` and `as_of <= server_now`. Changed queue/source
state refuses; no
historical queue state is invented to make an old packet pass. A client-supplied
hash alone cannot validate invented input. The entire packet, document, citations
and usage count toward the request byte limit.

Publication serializes cross-process writers and rechecks source deletion,
evidence hashes, queue-state digest and projection before its atomic replace.
Check recorded receipt identity before freshness: identical key/request retry
returns the recorded receipt without republishing; changed content under that
key returns `idempotency_conflict`. A receipt contains hashes/status, not old
source text, and does not bypass current read/deletion checks.
The first accepted artifact for a job key wins; a competing different artifact
returns `brief_conflict`. A changed snapshot returns `stale_brief` and requires
fresh input. An interrupted write leaves either the prior valid manifest or a
recoverable complete artifact; it never advertises half a brief. These two
publication-only conflict codes extend the read refusal set.

All write responses obey the 65,536-byte wire cap. Each published artifact has a
`brief_hash` over its canonical manifest and content. Discovery selects the most
recent valid artifact by accepted UTC timestamp, then hash, rather than expose a
mutable date-only URI. Source deletion or changed dependencies make a brief
unavailable immediately, even before its local/mirror file cleanup completes.
Retain no stale brief text in resource errors.
Hard purge also removes service-owned local brief documents and stored input
packets that depend on the deleted item, including interrupted publication files.
Retain content-free receipt hashes for retry/deletion accounting. Independently
saved client copies are outside this store's ownership and deletion guarantee.

Usage separates reported tokens, locally counted bytes, elapsed time, estimates
and paid cost. Missing client usage is null/unavailable, never zero measured
tokens or a dollar-cost result. Brief publication never enables paid features.
Generated brief text remains untrusted data when read back by another client.

## Opt-in corpus mirror

The corpus mirror is a one-way view of bounded evidence cards, shelf pages and
accepted briefs. Existing `obsidian_vault_path` authorizes only the current taste
integration. Add a separate `library_mirror_enabled=false` setting and record the
canonical destination, consent time and scope (`all_current_and_future_items` or
an explicit item-ID allowlist). Enabling or broadening scope requires a concrete
user-selected destination/scope preview. Reads and prompts never grant that
consent. A destination change disables the mirror until its scope is selected.

The preview explains that other software with access to that vault can index its
contents. Uoink does not register the vault with Basic Memory/Hermes, start another
indexer, edit its configuration, turn on sync or infer consent from an installed
application. Existing third-party indexing is outside Uoink's deletion control;
the mirror status must not claim otherwise. No full transcripts, correction
journals, private memory notes, credentials or local corpus paths are exported.
For allowlist scope, shelf/index counts and membership reflect only allowed
items; a brief is exportable only if every source dependency is allowed. Removing
an item from scope schedules cleanup of its generated derivatives using the same
ownership checks as deletion.

Freeze paths below the resolved `<vault>/Uoink/` root:

```text
Library/<item-hash>.md
Shelves/<shelf-hash>.md
Briefs/<date>-<brief-hash>.md
Library.md
.uoink-mirror/manifest.json
```

`item-hash` and `shelf-hash` are full SHA-256 of the exact UTF-8 stable IDs. This
flat layout avoids title/channel renames, Windows reserved names, case folding
and Unicode normalization collisions. Titles and shelf paths are escaped display
text in the file, never directories. Brief dates follow the URI grammar. Resolve
and check containment for every file/temp path; refuse symlinks, junctions,
reparse points and hard-linked targets/ancestors that defeat ownership or root
containment. Check filesystem volume/path limits before writing. No `..`, drive,
UNC or alternate data-stream name can come from an item field.

The manifest records exact identity-to-path ownership. Even a hash collision must
fail `path_collision`, never overwrite another identity. An existing file without
a matching ownership entry is user-owned; report `unmanaged_conflict`. A missing
or corrupt manifest stops writes for reconciliation, never adopts all Markdown
files as generated. Initial setup creates an empty manifest only after checking
that planned destination files do not exist.

Each generated file includes schema/renderer version, stable identity, source
revision/card hash or dependency hashes, generated UTC time, validated source
links and the notice that edits are not imported. Build frontmatter with escaped
scalar values; source text cannot inject YAML keys, raw HTML or wikilinks. Only
renderer-created links target the generated relative paths. `Library.md` contains
counts and a bounded recent/shelf list, with omissions labeled. Item files retain
the Librarian card's evidence/truncation limits; brief files retain the brief
limit. No file exceeds 65,536 UTF-8 bytes including frontmatter and footer.

Keep `TASTE.md` and `USER.md` outside this writer's ownership. The Phase 4 writer
never reads them back as corrections or overwrites them. In particular, extending
`_maybe_mirror` must not route a corpus update through `write_user`. Existing
explicit user-memory writes are a separate operation.

Use a local durable mirror ledger at `DATA_ROOT/reach/mirror/` containing desired
generation, dependency hashes, destination identity, last successful file hash,
status and pending deletions. It contains no copied source text. The ledger is
derived delivery state, not the authoritative Phase 2 correction store. Losing
it cannot lose pins or cause deleted items to be resurrected. Rebuild desired
state from current authoritative sources; require ownership reconciliation before
replacing existing files.

Serialize writers across processes for each destination. Under that lock, compare
the destination's entire byte hash with the last successfully written hash before
any replace or deletion. A mismatch is `user_edit_conflict`: preserve those bytes,
record the pending generation locally and leave the edit outside synchronization.
Do not overwrite, merge, rename, or create an extra exported conflict copy. Resume
only after the user explicitly resolves the file or chooses regeneration.

For an owned, unchanged target: write a unique same-directory temporary file,
flush and close it, recheck current dependencies/deletion generation, then replace
atomically. Advance the mirror manifest only after file replacement; persist a
local intent first so restart can reconcile a replaced file whose manifest update
was interrupted. Atomicity is per file, not the whole vault. Write `Library.md`
last, referencing only completed files. A crash must leave the old complete file
or new complete file, with repairable status. Never publish an older generation
over a newer one. Remove only manifest/intent-owned abandoned temp files.

Mirror work follows committed capture, source refresh, apply, brief publication,
restore and deletion events. Reads do not export. No new polling timer or watcher.
A bounded explicit resync and subsequent existing events drain pending work.
Record desired generation before attempting I/O. Limit an attempt to 2 seconds
and 20 files; run vault I/O in a cancellable isolated worker so a disconnected
drive cannot hold capture or the primary database lock. No acknowledgement of a
successful mirror write after timeout without rechecking the receipt/manifest.

A missing drive/root is `destination_unavailable`: the primary operation succeeds,
the local ledger remains pending, and no fallback directory is created elsewhere.
Do not recreate a missing vault root. A per-destination marker distinguishes a
reconnected vault from a different volume appearing at the same path. On resync,
validate that marker and process pending deletions before any content write.
Return counts for pending, synced, stale, conflicts and deletion-pending files;
do not mark a disconnected destination synchronized. Old offline files cannot be
recalled remotely; they remain visibly pending cleanup in local status.

Soft deletion immediately revokes resource/brief access. For an owned, unedited
item mirror file, replace the body with a content-free tombstone at the same path,
with identity, deletion time and `deleted:true`. Remove its source title, URL and
quotations. Rebuild/invalidate shelf/index/brief derivatives that cite the item,
including older generated brief versions. Preserve no deleted quotation in a
generated tombstone, temporary file or recovery copy. Restore can replace an
unchanged tombstone only after authoritative undelete and fresh dependency checks.

Hard purge removes all owned, unchanged item files, dependent generated brief
files and owned temporary artifacts; recompute shelf/index references. The local
deletion ledger keeps only enough identity/path hashes to finish offline cleanup.
Repeated purge is idempotent. A late capture/render event must recheck deletion
before publication and cannot recreate the file. Turning the mirror off stops
new exports but retains pending deletion status and permits deletion-only cleanup.

User-edited files create a deliberate limit: preserve edits and report
`purge_blocked_user_edit` for deletion conflicts. Do not claim hard deletion or
mirror acceptance has completed while any such file remains. Stop new exports
to that destination until the user resolves the affected files; do not silently
move their text into another indexed folder. This is the explicit resolution of
the edit-preservation/deletion conflict, and it must be covered by tests.

Authoritative pins, exclusive policies and journal recovery remain under Phase
2's correction-store contract. Neither vault failure, mirror disablement, mirror
cleanup nor loss of its manifests changes that store. Basic Memory compatibility
here means readable escaped Markdown and links; no graph/indexing integration is
claimed without a separate consent and verification gate.

## Capabilities, compatibility and client artifacts

For the existing negotiated MCP protocol family, stdio advertises tools,
resources and prompts only after the corresponding methods exist. Resources
have `subscribe:false` and `listChanged:false`; prompts/tools have
`listChanged:false`. No resource subscriptions, unsolicited list-change events,
sampling, completions, tasks or logging capability is added. A changing curated
list does not justify advertising a notification that this process cannot emit
reliably. Refresh is an explicit list/read or client reconnect. The resource
specification makes subscriptions and list-change notifications optional;
the chosen settings are consistent with its
[capability definition](https://modelcontextprotocol.io/specification/2025-11-25/server/resources).

Register resources outside `TOOL_REGISTRY`. The three new read tools and two
brief-job tools belong in that registry and stdio, with public schemas and
consistent errors; `publish_library_brief` is labeled as a local write. The
existing six Phase 2 tools remain on their current transport unless Fable
separately assigns their stdio adapters. A brief report does not require those
mutation tools to be exposed on stdio.

HTTP MCP remains tools-only during AV; its advertised capabilities must reflect
that. New registry tools inherit HTTP authentication and validation. Future HTTP
resource/prompt routes require the same contract tests before advertisement.
Do not copy the stdio capability object into HTTP while its handlers are absent.
Existing protocol negotiation and all 25 legacy stdio tools remain operational.

Do not upgrade an SDK or add a protocol date merely to make a support claim.
Use Grok's verified protocol/client matrix to decide whether the installed pin
can serve the required pair. If migration is necessary, start with the official
Python migration path named in the brief, test it separately, and retain a
working legacy negotiation path until its regression gates pass. Fable records
the dependency/lock/build files and exact protocol versions affected. The AU
memo's older assumption that Python support must still arrive is not a reason
to defer verification or rewrite FastMCP. A `.mcpb` package does not itself prove
Claude Code installation or any current client capability.

AV must produce these reviewable artifacts:

| Artifact | Required contents |
|---|---|
| `docs/claude-code-mcp.md` (new) | Installed Windows stdio setup, exact supported CLI/version and config scope, first bounded query, resource/prompt invocation, fallback tool, restart/failure steps, and removal instructions. Populate client-specific syntax from Grok's evidence and AW observation. |
| `docs/examples/claude-code.mcp.json` (new) | A project-scoped `uoink` stdio entry: absolute installed console `python.exe`, argument array containing installed `uoink_mcp.py`, UTF-8 output. Clearly marked placeholders, no credentials, checkout-specific paths or resident-helper URL. Verify its schema against the selected client. |
| `skills/uoink/SKILL.md` | Library-oriented read workflow, bounded tools first, safe evidence handling, text-only sources, honest timestamps, and client-run brief procedure. A provider API key is not required for library reading. Existing explicit paid tools retain their own documented requirements. |
| `docs/v2-mcp.md`, `.mcpb/manifest.json`, `.mcpb/README.md`, `docs/mcpb-bundle.md` | Reconciled tool inventory, resource/prompt documentation and thin-launcher prerequisites. Bundle syntax/validation uses Grok's current format findings. Keep Desktop compatibility separate from Claude Code acceptance. |
| Existing installer/bundle inventories | Include the shared rendering and brief persistence modules; clean installed-tree imports must work with the source checkout absent. Update the existing inventory/count assertions through their owning dispatch. |

Client configuration uses a console interpreter, never `pythonw.exe`, and keeps
arguments separate so spaces in installation paths work. Installing the candidate
is enough to run stdio; running the resident HTTP service is not a read
prerequisite. Keep stdout strictly JSON-RPC and diagnostic output on stderr.
Missing/unreadable storage returns `library_unavailable`; do not create a new
empty database as a substitute or fall back to another installation's data.

Recall is a separate opt-in configuration entry using the installed hook path.
Its index override is `UOINK_INDEX_PATH`; that variable does not redirect the
stdio backend's `DATA_ROOT` in this base. For Windows acceptance, isolate
`LOCALAPPDATA`, `APPDATA`, `TEMP` and `UOINK_OUTPUT_DIR` in the dedicated test
profile before launching either child. Set the hook's explicit copied index
path too. Verify resolution before launch; environment examples must not point
to the resident data directory. Do not install hooks or alter the user's real
client configuration during AU or AV fixture tests.

Tool fallback is required even if Claude Code exposes resource templates poorly:
`read_library_resource(uri)` retrieves the identical content. AW records native
resource/template UI support separately. It must exercise at least one actual
resource read and prompt invocation where supported, and document any missing
client affordance instead of marking that path passed through a synthetic probe.
If the client cannot perform the required workflow through either native access
or the frozen fallback, Phase 4 acceptance remains blocked for that pair.

Public tunnels, OAuth/cloud connectors, registry publication and automatic
Basic Memory installation are outside this contract. `source_manifest.py` support
claims must not be broadened from a stdio test. Any marketing/support correction
to that shared file is a separately reserved integration edit.

## Acceptance gates to implement in AV

All gates below are required; none ran in AU. Gemini owns independent adversarial
fixtures and the detailed test plan. Suggested new test filenames are reservations
for Fable to finalize, not files to create in this dispatch. Tests use temporary
fixture databases, source files and vaults; every mutated path is inside the
dispatched sandbox. Never import/start the real backend against default settings.

| Gate | Observed result required | Proposed test surface |
|---|---|---|
| P4-01 identity | Rename slug/channel, rebuild clips, reorder/re-extract evidence, edit corpus beyond its first 8 KiB, change selection, and swap item IDs. Unchanged inputs retain addresses; stale addresses refuse; corpus tail edits change only the full-file binding as applicable. | `tests/test_library_resources.py` |
| P4-02 URI validation | Reject path/authority tricks, double encoding, invalid IDs/hashes, negative/boolean/oversized offsets, extra fields and duplicate JSON keys before data access. Known valid URI works through both read entry points. | Same; transport-level malformed frames |
| P4-03 bytes and limits | Boundary and one-over cases with multibyte UTF-8, escaping expansion, long URLs, metadata and a single huge cue. Measure actual serialized result bytes; complete units only; honest truncation, MIME, `size` and continuation. | Same; response serializer fixtures |
| P4-04 provenance and trust | Timed, coarse, mixed, prose, hint-only and empty items retain evidence kinds. Closing fences, role text, Markdown links, YAML and terminal controls cannot escape or become active instructions. Tool/resource/prompt/hook fixtures cover the same hostile source text. | `tests/test_library_resource_trust.py`; existing hook fixtures via their owner |
| P4-05 failure bounds | Missing/locked/corrupt DB, unavailable corpus, interrupted file read, slow query and concurrent reads. Storage failure is distinct from no matches; service result/refusal meets 2 seconds, rate/concurrency overflow does not queue, and stdout stays protocol-clean. | `tests/test_library_resources.py`, isolated subprocesses |
| P4-06 capabilities | Discovery advertises exactly implemented methods. Five templates, four prompts, curated list at most 41. No promised notifications; no HTTP resource/prompt advertisement; legacy negotiated versions and 25 old tools still work. | `tests/test_phase4_stdio.py`; existing transport regressions |
| P4-07 prompts | Exact names/required strings/ranges, no-match and missing-history states, stale/oversized previews. Hash queue/projection/settings before/after invocation; no mutation, lease maintenance, network or model execution. | `tests/test_library_prompts.py` |
| P4-08 briefs | Prepared input survives client restart. Wrong item/quote/revision/input hash fails; concurrent different publication conflicts; identical retry returns one receipt. Changes during drafting produce `stale_brief`. No client produces no new brief. Missing usage stays unavailable. | `tests/test_library_briefs.py` |
| P4-09 mirror paths and consent | Disabled by default even with an existing taste vault; allowlist honored; destination change resets consent; traversal, reserved names, case/Unicode collisions, hash collisions and reparse/hardlink races cannot escape/overwrite. No indexer/config/network side effect. | `tests/test_library_mirror.py` |
| P4-10 edits and atomicity | Edited/unmanaged files stay byte-identical. Crash before/after replacement and before manifest commit, two writers and stale delayed work preserve complete files and recover once. Corrupt/lost manifests do not grant ownership. | Same, independent crash fixtures |
| P4-11 deletion | Soft tombstone strips source content; hard purge cleans every owned derivative/temp; replay and restore do not resurrect deleted text. Edited file reports a blocked purge; disconnected destination records pending cleanup and drains deletes before new exports. | Same, with dependent shelf/brief fixtures |
| P4-12 correction separation | Mirror unavailable, disabled, corrupted, removed and rebuilt leave authoritative corrections/pins unchanged and recoverable. No generated vault file enters correction replay. | Same, using Phase 2 service fixture through its owner |
| P4-13 installed compatibility | Candidate runs from installed files with checkout absent, spaced paths and clean stdout. Config/bundle inventories agree with live discovery; previous client config and negotiation still work. | Existing packaging/C-01 tests plus `tests/test_phase4_stdio.py` |
| P4-14 real client | Claude Code retrieves identical item/quote/revision through bounded tool and resource/fallback, invokes a prompt, follows a real source link and reconnects. Test helper/process-down states separately as below. | AW receipt owned by Astra |
| P4-15 client behavior | With only fixture reads and inert action sentinels permitted, injected source instructions trigger no unauthorized tool, shell, file, connector or network action. Compare actual client actions, not only escaped text. | AW adversarial client receipt; Gemini fixtures |

These tests must include an allowed synthetic failure source as well as a named
real copied item. A passing fake protocol client does not satisfy P4-14 or P4-15.
Conversely, a model saying that a quote is correct does not replace byte/revision
comparison. Keep all measurements, fixtures and acceptance claims separate.

## AW real-client verification procedure

1. Fable names the integrated candidate SHA, installed artifact/hash, Claude Code
   version, protocol/SDK versions, allowed corpus-copy manifest and hashes, source
   dates, dedicated test profile, isolated port if HTTP is exercised, and bounded
   client execution scope. The brief reports CLI 2.1.261; AW records the version
   actually installed. AU authorizes none of these launches or corpus egress.
2. Verify the named source copy before opening it. Make a writable disposable
   duplicate within the acceptance workspace. Supply copied corpus files needed
   for the chosen timed and text-only items, fix fixture paths inside that copy,
   and hash them. Do not follow a copied row's old absolute path to another
   checkout or the live corpus. Capture expected IDs, quotes, hashes and links.
3. Install/stage the candidate in isolation, apply the reviewed project-scoped
   client configuration in the test profile, and inspect resolved paths. Disable
   background features and Recall for the first pass. Launch the client-owned
   stdio child, with no listener on 5179 and no resident helper interaction.
4. In the real client, inspect discovery and choose a copied item through
   `search_library`. Read it with `get_library_item`, attach/read its canonical
   card URI (or use the documented fallback), then read one excerpt URI. Compare
   exact item ID, source revision, card/excerpt IDs, quote and timing against the
   frozen expected packet. Also exercise a text-only item without fake timestamps.
5. Invoke `consult-library` and `reshelve-review` on fixtures; verify bounded data
   and unchanged queue/projection. Exercise the client brief input/publication
   flow only within the declared client budget. Open one returned real public
   source link in the isolated browser profile; record the destination and timed
   seek where available. A broken external source is an explicit blocked link
   gate, not a fabricated successful click.
6. Restart only the recorded test stdio child. Reconnect and rediscover; the same
   unchanged item returns the same quote/revision. If an isolated HTTP helper was
   also launched, stop/restart only its recorded PID: stdio reads should continue
   because they use local storage directly. This is separate evidence from MCP
   child reconnection; neither operation targets the resident helper.
7. With the child still running, make its fixture storage unavailable and record
   a domain `library_unavailable` result within the 2-second service deadline.
   With the child stopped or launch deliberately broken, record the real client's
   connection/transport failure within 15 seconds of the tool request or explicit
   connection attempt. A dead process cannot emit a JSON domain error. Configure
   a documented client timeout if required; if the installed client cannot meet
   the bound, record a failing gate and repair/configure it before acceptance.
   Allow at most one explicit reconnect; do not hide a hung attempt in a retry.
8. Re-enable only the isolated Recall fixture configuration and exercise the
   hook/adversarial cases. Show hook output remains bounded when HTTP is stopped;
   hook failure remains silent JSON-channel behavior. Run the disconnected-vault,
   edit and deletion fixtures, then record final pending/conflict counts.
9. Record transcript excerpts/screenshots where supported, request/response byte
   counts, monotonic timings, stdout/stderr separation, exact commands/config
   hashes and before/after data hashes. No tokens or private paths in public
   receipts. Stop only test PIDs and remove only test configuration. Astra reports
   observed versus expected for each gate on the integrated SHA; subsequent
   affected code/prompt changes invalidate that result.

## Ambiguities resolved and remaining integration decisions

| Ambiguity in the inputs | Frozen ruling |
|---|---|
| Slug/sequence versus durable text identity | Encode stable item ID; bind card/source/selection and existing excerpt hashes. Slug remains discovery only. |
| Card revision versus complete corpus revision | Preserve the shared card algorithm; use a separate full-file hash for corpus chunks, including tail edits. |
| Memo's 256 KB truncation plus unbounded fallback | Use explicit small chunks and total wire budgets. Never route overflow automatically to a full-corpus tool. |
| Card defaults and excerpt options | Reuse default Librarian card unchanged; legacy full/default reads remain compatible. No Phase 2 evidence-basis extension. |
| Resource list changes versus notification support | Small pull-only list; `listChanged:false`, no subscriptions. |
| Resources/prompts over both transports | Prove stdio first. HTTP stays tools-only and advertises that distinction. |
| Search-as-resource and date-only brief URI | Search is a tool; only revision/hash-bound documents have resource addresses. |
| Preview prompt's `apply_id` | Use `preview_id`, since review precedes apply; read an existing preview without mutation. |
| Prompt data versus deferred tool instructions | Prompts include bounded data and fixed instructions, with no server synthesis or implicit job creation. |
| Briefs over an assignment-only queue | Client report consumes a read-only queue snapshot; no synthetic work row, new queue kind or migration. Explicit artifact publication is separate. |
| Once-a-day brief and event-driven mirror | No timer creates prose. An active client produces a brief; committed events/resync deliver it to the mirror. |
| Existing vault setting as corpus consent | Separate default-off corpus consent bound to destination and scope. No automatic third-party indexing. |
| Channel/slug filenames and renames | Flat full-hash paths plus exact identity ownership checks; display names stay inside files. |
| User edits versus deletion | Preserve edits and report blocked purge; all unedited owned derivatives are removed/tombstoned. No false deletion success. |
| Mirror versus correction authority | Mirror is disposable output; Phase 2 authoritative correction records remain separate. |
| Helper restart/down under stdio | Distinguish the client-owned stdio child, independent HTTP service and storage. Test each relevant failure honestly. |
| SDK release and `.mcpb` assumptions | Grok's verified matrix governs migration/config syntax; no capability or supported-client claim follows from version labels alone. |

Fable's remaining integration decisions are concrete: reconcile the two companion
AU documents, reserve the AV shared-file owners, and name AW's candidate, fixture
copy, installed client/configuration, safe test port and execution budget. If a
protocol/client finding contradicts a frozen gate, record an amendment with the
failing evidence before AV; do not silently relax the contract. No runtime gate
has been passed by this document.

## AU verification receipt

Read-only source inspection established the baseline above; no application module
was imported. `git diff --no-index --check -- NUL
docs/library/PHASE4-CONTRACT-2026-09-08.md` reported no whitespace errors. Static
PowerShell checks resolved all five relative document links, parsed the one JSON
example, found 15 distinct acceptance gate IDs and four balanced Markdown fence
markers. `rg -c '^@mcp.tool' uoink_mcp.py` returned 25. `git status --short` showed
only this new contract. Runtime, model, client, database and packaging tests were
not run in AU. No code, migration, commit or merge was produced.
