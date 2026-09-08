# Phase 5 contract: library activity, 2026-09-08

Contract: `phase5-v1`. Owner: codex (Astra). Implementation: run AZ. Acceptance
review: run BA. This document freezes Part A; it records no implementation,
performance measurement or achieved model accuracy.

Implement descriptive counts of saved items, recorded shelf changes and source
observations. Every number must identify its population, clock, interval and
evidence. A 200-item archive import is capture activity. It does not establish a
publication trend.

The [brief](PHASE5-BRIEF-2026-09-08.md) was read first. Its base is
`2ca9ae2db54f637a95fc9c84e2ed6bf301502e7c`; the inspected checkout is
`397fdcc556382a92bd6150cb04a80c3c2e98d703`. Committed inputs are Gemini's
[evaluation design](PHASE5-EVALUATION-2026-09-08.md), commit
`23498ca5b321d66fa266c9aca0400c2748d7d521`, and Grok's
[cost audit](PHASE5-COST-AUDIT-2026-09-08.md), commit
`397fdcc556382a92bd6150cb04a80c3c2e98d703`. The dispositions below supersede
their proposed response shapes, SQL and expected fixtures where stated. Those
input files remain unchanged.

AY changes this document only. AZ needs pure aggregation in `library_analysis.py`,
read helpers in `index.py`, a shared registry read and a dashboard panel. Fable
reserves adapter/UI edits before AZ. This contract authorizes no model, resident
helper, live index, port 5179, paid computation, commit or merge in AY. It changes
no Phase 2/3/4 service, prompt, card builder or test. No migration or report table
is required; `0029` is not allocated by this contract.

## Evidence at the inspected base

These are source findings, not observations from a running library.

| Input inspected | Consequence for Part A |
|---|---|
| `migrations/0001_initial_schema.sql:22-34,86-88`; `0004_memory_indexes.sql:15-16`; `index.py:99-100,542-608,1486-1512` | `video_id` is the capture-row identity. Upsert replaces its timestamp and metadata; it is not an append-only capture log. `yoinked_at` and `deleted_at` can be local-naive ISO text. Restore clears the tombstone; hard deletion removes the row. |
| `migrations/0015_universal_site.sql:11-13`; `0020_platform_author.sql:26-30`; `0025_source_type_backfill.sql`; `0026_provenance_precedence.sql` | Type, platform and author are indexed observations. `author` can be an uploader, handle, subreddit or host. It is not a verified person ID. Reports use stored types and do not run backfills. |
| `migrations/0010_podcast_feeds.sql:31-58`; `0022_podcast_corpus.sql`; `0023_podcast_watch.sql:14-15`; `podcasts.py:390,425,503` | Episodes link through `yoink_video_id`. Publication strings may be RSS dates, not sortable ISO timestamps. The existing publication index does not make mixed-format lexical comparisons correct. |
| `migrations/0027_library_substrate.sql:11-51,117-183`; `library_work.py:851-864,916-940,1232-1309` | Applied deltas contain `items` maps with full before/after membership arrays. Only projection-changing operations enter `library_applies`. Receipts include no-change operations. `created_at` from `_stamp()` is epoch milliseconds encoded as text. |
| `migrations/0028_source_subscriptions.sql:9-40,64-116`; `source_subscriptions.py:1933-1977` | Source items include uncaptured entries and retained deleted identities. First/last observation timestamps survive; intermediate sightings do not. Cursor coverage describes the latest enumeration. Publication data can change without a subscription revision change. |
| `migrations/0006_v2_schema.sql:45-53`; `0021_suite_engagement.sql:4-7` | Engagement has its own event clock and no item foreign key. It is available but outside this Part A report set. |
| `migrations/0024_clips.sql:17-33`; `0008_a2_claims.sql`; `claims.py:1-19,39-57,86-174` | Clips are derived evidence. Claim extraction/verification persists client-supplied work; alignment signals are assistance, not truth verdicts. Neither table is a prerequisite for Part A. |
| `library_cards.py:97-142,222-223`; `index.py:527-540`; `PHASE4-CONTRACT-2026-09-08.md`, "User-invoked prompts" | Card `source_revision` hashes evidence and opening prose. There is no universal current source-revision column on `yoinks`; existing invalidation hooks do not cover every report dependency. `whats-new` promises capture, revision and membership counts plus at most 20 events. |

## Report set and populations

The following set is closed for `phase5-v1`. Computation is deterministic and
requires no claims, clips, full transcripts, sidecar walk or external requests.

| Report | Required result and population | Clock |
|---|---|---|
| A1: saved-item activity | Distinct current nondeleted `yoinks.video_id` in the interval, grouped by stored source type, creator hint, and the joint type/hint key. Each item contributes once to each partition. Unknown values have explicit buckets. | Capture time by default. |
| A2: publication view | The same saved-item population selected by an available publication instant. Include timestamp availability and exclusion counts for the whole current library, separately from the selected interval total. Uncaptured observations never enter this item total. | Publication time, explicitly selected. |
| A3: recorded membership activity | Applied operation count, membership additions/removals/net per stable shelf ID, distinct affected items, primary changes, and metadata-only changes. Include undo operations at their own time. | Applied-journal time, regardless of the A1/A2 selector. |
| A4: shelf size and churn | Current direct member counts, plus interval journal additions/removals. Historical endpoint sizes and interval churn appear only with a proved baseline. Show initial filing separately. | Current size at `as_of`; historical quantities use journal time. |
| A5: sources with activity | Sources with captured items or newly observed entries in the interval; counts and the actual observation span for each. Include archived/disabled sources when they have qualifying activity. | Captures use capture time; new observations use `first_seen_ms`. |
| A6: recorded revisions | Taxonomy versions created and assignment runs created in the interval, their stable IDs, and current revision bindings. Activation is an A3 event. | Stored creation time, normalized as specified below. |

The contract's A6 is revision history needed by `whats-new`. Grok's proposed A6
engagement report is rejected for this release. Engagement is neither a new report
nor a weighting factor in these counts.

The population is the current retained library, evaluated at `as_of`. A1 is not a
count of all captures that ever happened: recapture can replace a row, deletion
can remove it, and restore can clear deletion history. Labels must say "saved
items captured in this interval". The total changes after deletion or correction,
including when the selected interval is in the past.

Current shelf membership is direct membership only. Do not roll children into
parents or sum overlapping shelves into a unique-item total. Return both the
distinct assigned-item count and membership count with their different units.
Include shelves referenced by current memberships or interval events even if
retired or absent from the active taxonomy. Resolve labels by the membership or
event's version; expose active labels separately. Renaming a stable shelf is not
membership churn. Changing a run's current `run_revision` is not a reconstructable
historical revision event; only its retained creation row has a creation time.

There are no implicit comparison periods, percentage growth, popularity rankings,
publication velocity estimates or trend labels. Daily buckets and net membership
counts provide descriptive changes. A later comparison feature needs its own
matched populations and coverage rule.

## Interval grammar and timestamp admission

The required `interval` argument is an object with exactly `start` and `end`.
Both are valid Gregorian UTC timestamps in either `YYYY-MM-DDTHH:MM:SSZ` or
`YYYY-MM-DDTHH:MM:SS.sssZ` form. Canonical output always has three fractional
digits. Seconds are 00-59; leap seconds, naive inputs, offsets, date-only inputs,
relative expressions and extra fields are invalid. Require `start < end`, at most
30 times 86,400,000 milliseconds, and `end <= as_of`. Freeze `as_of` once at
request admission. Future end bounds fail; do not clamp them silently.

Every interval is half-open `[start,end)`. Capture at `start` counts; capture at
`end` does not. Buckets are UTC calendar days intersected with the interval, with
explicit bounds for short first/last buckets. A rolling 30-day interval can
intersect 31 UTC days, so the cap is **31 buckets**, amending the audit's 30.
Daily counts partition the selected total. No hourly chart is required.

Stored data has a separate admission rule:

| Stored clock | Conversion |
|---|---|
| `yoinks.yoinked_at`, `deleted_at` | Parse timezone-aware ISO text and convert to UTC. A naive value has `timezone_unknown`; do not assume UTC, the current OS timezone or this worker's timezone. Such a row remains in the library denominator but cannot enter a UTC capture bucket. |
| `library_applies`, `shelf_versions`, `library_runs` creation times | Parse decimal epoch-millisecond text emitted by `LibraryWorkService._stamp()`. Also accept timezone-aware ISO text for imported/test records, with the original encoding recorded. Reject malformed or naive values. Sequence orders operations; it never substitutes for a timestamp. |
| `source_items.*_ms`, subscription/cursor `*_ms` | Integer Unix milliseconds. A default zero used as "never observed" is unknown for observation-span purposes. Booleans and invalid/out-of-range dates are rejected as source data. |
| `podcast_episodes.published_at` | Accept timezone-aware ISO or RFC 2822/RSS dates with an explicit offset or GMT/UTC. Convert before filtering. Naive, malformed or date-only text is unavailable for a UTC instant query. |

Normalization must precede the final predicate. A raw ISO SQL range may narrow a
homogeneous, proved UTC subset only; it must not silently exclude offset/RSS
records. AZ cannot reuse the inclusive date-only memory search as this reader.
Corrected timestamps can move an item between intervals; this invalidates both
reports. No read writes normalized dates back into the index.

Publication selection is one instant per live item. First use retained, nondeleted
`source_items` linked by exact `video_id`; if those have no admissible publication
instant, use linked `podcast_episodes`. Within the chosen tier, all admissible
timestamps must agree after normalization. Disagreement makes the item
`publication_conflict`, with no count and no fallback. A lower-tier disagreement
is disclosed, while the selected higher tier remains authoritative. Repeated
links never multiply the item count.

Source-item milliseconds are labelled `adapter_normalized`, not independently
verified source time. At this base `source_subscriptions.parse_published_ms`
(`source_subscriptions.py:424-445`) assigns UTC to timezone-naive input. Part A
does not reverse-engineer that lost precision or claim to have checked the
original timezone. Direct episode-string reads use the stricter rule above;
persisted adapter instants retain their stated provenance. This distinction
must appear in publication evidence and the view's coverage explanation.

Unindexed YouTube sidecar upload dates and `yoinks.metadata_json` publication keys
are outside the Part A query path. They may carry real publication information;
label this case `not_available_in_report_index`, not "never published". This
adopts Grok's cost boundary and amends Gemini's JSON-path fallback. Date-only
upload metadata does not establish a precise UTC instant either. Supporting those
dates later requires a separately reserved projection/clock amendment; capture
time is never the fallback publication date.

## Denominators and coverage

Every displayed metric uses the metric shape below. Counts have a unit and an
explicit population. A share has a numerator and denominator as well as a value.
No chart computes a denominator from the displayed top rows or evidence sample.

| Quantity | Denominator or scope |
|---|---|
| Type/hint/joint count share | Selected A1 or A2 item total before pagination. Unknown is a partition member. |
| Publication availability | All current live saved items. Partition into available and unavailable; unavailable reasons are missing/unindexed, invalid, timezone unknown, date only or conflict, one primary reason per item in that order of specificity: conflict, invalid, timezone unknown, date only, missing/unindexed. |
| Capture timestamp availability | All current live saved items; valid UTC capture timestamp versus unavailable. |
| Deleted items excluded | Retained tombstone rows whose admissible capture timestamp lies in the interval, not deletions that happened in the interval. Undated tombstones have a separate unlocated count. Hard-purged rows cannot be counted. |
| Source captures | Distinct live captured IDs linked to that source and captured in the interval. This stays on capture time even in publication view. |
| New source observations | Distinct `(source_id, entry_id)` with `first_seen_ms` in the interval, including retained tombstones and never-captured entries, with state/deleted breakdowns. Not poll count or captured-item count. |
| Churn | Distinct baseline assigned items whose shelf set or primary changes at least once in the interval, divided by the distinct assigned items in that same proved baseline. |

Zero selected items gives share `null` with numerator 0, denominator 0 and reason
`empty_population`; never NaN or infinity. Current size zero is valid for a known
shelf. An unknown historical size is `null`, never zero. For interval churn, a
proved empty baseline gives `0/0`, `percent:null`, `initial_filing:true`. This
display rule differs deliberately from the Phase 2 preview's `0.0`; the preview,
its 15% approval stop and its user-operation rules are unchanged.

Coverage belongs to each metric family, not one global `complete` boolean.
Freeze statuses `retained_records`, `journal_complete`, `partial`, `no_history`
and `unavailable`. Each coverage record includes `clock`, requested bounds,
earliest/latest retained timestamps or null, and reason codes. These spans do not
prove uninterrupted monitoring or historical completeness. Invalid or unknown
timestamps give `partial` and exclusion counts. A valid SQL zero can be retained
as `recorded_count:0`; if the interval precedes the earliest retained observation,
the historical metric has `value:null`, `coverage:no_history`. The UI says
"No recorded history for this interval", not "nothing happened".

Capture coverage never proves a complete history of imports or deletions.
Publication coverage describes dates of currently retained items, not an observed
publishing population. For example, an item captured in 2026 with a verified 2023
publication instant can be counted in a 2023 publication view. It supplies no
evidence that this library monitored its source in 2023. This is why Gemini's
whole-response `history_coverage_gap` error is amended to per-section coverage.
Useful present size and dated publication records must remain readable.

For each subscription, return enrollment time separately from:

- `first_observed_at = MIN(source_items.first_seen_ms)` over retained identities;
- `last_item_seen_at = MAX(source_items.last_seen_ms)` over retained identities;
- latest successful poll and latest observation time, when recorded;
- cursor enumeration coverage, observed count, truncated flag and current source
  and cursor revisions.

State breakdowns describe each retained row at `as_of`, not its state when it was
first observed. Include tombstones when measuring that span. Enrollment alone is not an
observation. Last-success and last-seen values are endpoints, not a poll history;
do not infer a continuous span or count intermediate sightings. Cursor `complete`
means one enumeration was complete. A 15-entry Atom window or truncated podcast
enumeration is not a complete back catalog. For an interval older than today's
cursor, display it as "latest enumeration at as_of", never as that interval's
coverage. A source with only a latest poll in the interval may appear with zero
new observations, labelled "latest recorded poll"; this does not imply a count
of polls.

Unsubscribed captures appear in A5 as hint groups with `source_id:null`,
`identity_kind:"creator_hint"`, and only a retained capture span. They have no
subscription observation window. A saved item linked to several subscriptions
counts once in the item total, once per linked source in source rows, and once in
the union count. Expose that overlap; never sum source rows into the item total.
`source_id` is a registered source identity, not a creator identity. Do not join a
capture to a subscription merely because display names match. The legacy podcast
link through `podcast_episodes.feed_id` and `source_subscriptions.legacy_feed_id`
is allowed; deduplicate it against exact source-item links.

## Creator hints and repetition

Part A deduplication has two distinct units: items use exact `video_id`; creator
grouping uses exact observed hint keys. Trim leading/trailing whitespace for a
display hint and retain the original value in evidence. Do not case-fold,
strip handles, equate platforms, infer people from names or call an entity/model
resolver. The hint key is `(platform-or-unknown, field, trimmed-value)` where
`field` is `author` when nonempty, otherwise `channel`, otherwise `unknown`.
Thus the same author string on the same platform shares a descriptive bucket;
the same string across platforms remains separate. Preserve channel breakdowns
even when author buckets coincide. Empty hints form an unknown bucket, never a
new independent creator per item.

Repeated captures with the same item ID count once. Three cross-posts with three
item IDs count as three saved items. Identical clip text is not proof of one
origin or three independent creators. Part A neither clusters clip text nor
labels matching author strings as "verified author identities". Both proposals
would require evidence absent from the schema and add a content-analysis pass.

Every packet includes `analysis_scope:"descriptive"`,
`trend_eligible:false`, `independent_creator_count:null` and
`independent_creators_minimum_met:false`. These remain so with any number of
items or hints. `support_level` is `none` for no selected items, `single_source`
only when the union of selected items' registered-source links contains exactly
one source and there are no unlinked items, and `unresolved` otherwise. For one unsubscribed hint group, the
UI says "one creator hint observed". Multiple source rows mean multiple source
observations; they do not establish independence or agreement.

## Applied journal, shelf sizes and churn

Use `library_applies` ordered by `operation_sequence`. Join receipts for bindings
and gap checks, not to invent dated no-change events. The actual delta is
`{items:{video_id:[membership rows]}, policies:{video_id:policy-or-null},
active_version_id?:version-or-null}`. Both forward and inverse have the `items`
and `policies` maps. An absent item key means no change; an empty array means no
memberships after that side of the operation. Array rows have the ten
`item_shelves` columns listed in migration 0027 and `_project_delta`.

For each affected item, compare inverse and forward arrays by stable shelf ID.
For a shelf, `added` counts item/shelf pairs present only after, `removed` counts
pairs present only before, and `net = added - removed`. Repeated changes count as
separate pair mutations. `membership_mutations = additions + removals`;
`affected_items` is distinct IDs with a shelf-set or primary change;
`item_change_events` counts each such item once per operation. A primary-only
change increments both of those item measures but no addition/removal. Changes
only to confidence, evidence, lock, source revision, assigned time, policy or
taxonomy activation have separate counters and zero membership churn.

`metadata_only_item_events` counts an item once per operation when its row data
changes but its shelf set and primary do not. `policy_change_events` counts an
item policy change once per operation. `activation_events` counts operations
whose active-version value changes. These units do not add to distinct items.

`applied_operations` includes every recorded projection-changing apply, activate,
pin and undo, even when membership change is zero. `no_change` receipts count in
neither applied operations nor timed events. Sequence gaps between applies are
legal when accounted for by no-change receipts; gaps in the complete receipt
sequence or projection revision chain make history partial. Validate both JSON
shape and before/after revision continuity. Malformed deltas are unavailable
source data, never guessed `remove`/`add` lists.

Recorded journal counts retain operations involving subsequently deleted items.
Their evidence rows say `item_deleted` or `item_missing`; no deleted source text
is returned. Current sizes exclude those items. Deletion is not an invented
shelf-removal operation. A report can therefore show a recorded addition for an
item that is absent now, with the population distinction visible.

Historical sizes and churn use the **currently live survivor population** across
both endpoints. This is explicitly labelled `current_live_survivors`, not the
population that was live at the time. Exact historical liveness is unavailable
after restore/purge. A deletion removes that item from both historical endpoints
and the denominator when recomputed; recorded journal counts remain unchanged.

A baseline is proved only when all of the following hold:

1. `library_meta.recovery_state` is `ready`, all receipts through
   `last_operation_sequence` exist, and all projection-changing revisions from
   zero through `projection_revision` are represented by valid applied rows.
2. Forward replay begins with the Phase 2 empty projection; every inverse matches
   the preceding projected membership state for current live items, and replay
   ends at their current `item_shelves` state. Current membership alone cannot
   supply a missing starting state. No service recovery is invoked by this read.
3. Applied timestamps needed for the endpoints are valid, no later than `as_of`,
   and nondecreasing in sequence. A clock regression preserves individually
   dated event counts but makes interval baselines unavailable.
4. `start` is at or after the first retained applied timestamp. Empty journal or
   a requested interval before that floor supplies no dated historical baseline.

Replay operations strictly before `start` for the starting state, and strictly
before `end` for the ending state. An operation exactly at `start` changes the
interval; one at `end` does not. Same-time operations retain sequence order.
Historical endpoint counts refer to states immediately before those boundaries.
The churn denominator is the survivor IDs assigned at the starting state. Count
each baseline item once if it changes shelf set or primary at any point inside
the interval, including a change later undone. Count previously unassigned items
first filed in the interval separately. Per-shelf churn uses that shelf's
starting members; an incoming item is an addition, not a starting-member churn
numerator. This is an interval statistic, not the Phase 2 apply-approval metric.

If proof fails, return current size and valid recorded changes, but null
historical endpoints, denominator and percent with `baseline_unavailable`.
Do not read expiring preview summaries as historical baselines. Do not hide
unavailability by dividing by current size or by only changed items.

Example for the amended undo fixture: seed a valid earlier journal operation
filing one live item in Alpha. Inside the queried interval, pin/move Alpha to
Beta, then undo Beta to Alpha. Expect 2 applied operations, 2 item-change events,
4 membership mutations, 1 distinct affected item, Alpha `+1/-1/net 0`, Beta
`+1/-1/net 0`, and interval churn `1/1 = 100%`. Alpha starts/ends with 1; Beta
starts/ends with 0. Without the seed history, churn is null. A narrower interval
ending before the undo retains `Alpha -1, Beta +1` after recomputation; a later
undo never rewrites the earlier event's timestamp or erases its occurrence.

## Read interface, provenance and invalidation

Register exactly one new read tool, `get_library_activity`, in
`uoink_mcp_tools.TOOL_REGISTRY` with the same service behind stdio and the existing
HTTP tool route. Advertise read-only/idempotent annotations where supported.
It requires ordinary library read access, no local-user intent, approval token
or new capability. Missing storage fails; it must not open/create/migrate/recover
the live index to make a read succeed. Avoid `library_service`, `list_work`,
polling services and any read wrapper that performs maintenance.

| Argument | Frozen meaning |
|---|---|
| `interval` | Required object defined above. |
| `date_basis` | `capture_time` (default) or `publication_time`; selects the item report clock only. |
| `detail` | Optional: `creator_hints`, `type_creator_hints`, `shelves`, `sources`, `events` or `evidence`. Absent means the summary packet. |
| `metric_id` | Required only for `detail:evidence`: an exact ID returned by this reader, at most 512 UTF-8 bytes. It selects numerator/support rows; the metric's denominator has its own evidence ID where different. |
| `offset`, `limit` | Detail-only ordinal pagination. Offset is integer 0-1,000,000; limit is integer 1-20, default 20. No implicit clamping. |
| `expected_revision` | Required for every detail request: the summary's `report_revision`, exactly 64 lowercase hexadecimal digits. |

No `start`/`end` top-level aliases, `shelf_id`/`source_id` filters, arbitrary SQL,
path, URL, model or narration argument in v1. Details select already computed
groups without redefining the summary's population. Reject unknown fields,
duplicate JSON keys, null supplied arguments, booleans as integers and malformed
selectors. Invalid arguments fail before storage access. A valid out-of-range
page is empty with `next:null`; an unknown metric is `not_found`.

A success has `ok:true`, `schema_version:1`, `contract_version:"phase5-v1"`,
`as_of`, canonical `interval`, `date_basis`, `report_revision`, `provenance`,
`coverage`, `items`, `shelf_activity`, `sources`, `revisions`, `events`,
`warnings`, the descriptive-support fields above, and `pagination`. A detail
response retains the envelope/provenance/coverage and supplies `detail`, `rows`,
`total_rows` and `next` instead of repeating summary collections. `next` is either
null or the complete next tool arguments, including revision and interval.

Freeze the summary family fields below. Counts and ratio objects are metrics;
the named lists carry rows with stable keys and metrics. Every family also has
its `coverage_ref`. Evidence pages use the same field meanings.

| Family | Fields |
|---|---|
| `items` | `total`, `by_source_type`, `by_creator_hint`, `by_type_creator_hint`, `daily_buckets`, `live_population`, `capture_time_available`, `capture_time_unavailable`, `publication_time_available`, `publication_time_unavailable`, `publication_unavailable_by_reason`, `deleted_items_excluded`, `deleted_items_unlocated`. Each item group/bucket has `count` and `share`; capture/publication availability use the whole live population. |
| `shelf_activity` | `applied_operations`, `membership_additions`, `membership_removals`, `membership_mutations`, `affected_items`, `item_change_events`, `primary_change_events`, `metadata_only_item_events`, `policy_change_events`, `activation_events`, `current_assigned_items`, `current_memberships`, `shelves`, `churn`, `initial_filing_items`. Each shelf row has `current_size`, `start_size`, `end_size`, `added`, `removed`, `net` and `churn`. |
| `sources` | `active_sources_count` (registered sources with the activity defined in A5, not enabled-source count), `unlinked_hint_groups_count`, `linked_capture_union_count`, `multiply_linked_capture_count`, `details`. Each source row has `captures_in_interval`, `new_observations`, `new_observations_by_state`, `observation_window` and current source/cursor bindings. Unlinked rows have capture metrics only. |
| `revisions` | `taxonomy_versions_created`, `runs_created`. Their evidence pages contain the IDs and creation times. |
| `events` | `total`, `rows`, `returned_rows`, `omitted_rows`, `next`. This is the combined event population; a membership operation is one event regardless of its affected-item count. |
| `pagination` | Map from paged collection name to `{total_rows,returned_rows,omitted_rows,next}`; disjoint item partitions additionally have `other_count`. No pagination object changes a metric's denominator. |

All metrics, including row/bucket counts, have this logical shape:

| Metric field | Requirement |
|---|---|
| `metric_id`, `value`, `unit` | Stable metric ID, integer count or null, and explicit unit. Signed net counts are allowed. Ratios additionally have exact integer `numerator`, `denominator`, `percent` and `reason`; percent is rounded to two decimal places, halves upward. |
| `population`, `clock`, `interval` | Defined population, actual clock and canonical half-open bounds. Current-size metrics use `clock:as_of` and `interval:null`, plus envelope `as_of`. |
| `query_id`, `query_version`, `revision_ref`, `coverage_ref` | Named query below, version `phase5-v1`, reference to the packet's report/projection/taxonomy/source bindings, and the applicable coverage record. |
| `evidence` | Exact `get_library_activity` detail arguments bound to the report revision. Explicit evidence row count, sample count and whether more rows exist. Distinct denominator evidence is separately addressable. |

Serialize repeated bindings through `provenance.scopes`: each metric carries a
`scope_ref` resolving its population, clock, interval, query/version, revision and
coverage fields. `evidence` may be a compact `{metric_id,role}` descriptor, with
role `numerator` or `denominator`, resolved through the packet's fixed
`evidence_request` template: same interval/basis/revision, `detail:evidence`,
the corresponding returned metric ID, offset 0 and limit 20. These references
must be self-contained in every packet. Do not repeat a full request and interval
inside every daily bucket; that needlessly consumes the wire budget. Missing or
unresolvable references fail the provenance gate.

Metadata numbers such as schema version, offset and byte limits are not measured
activity and do not need metric wrappers. Counts displayed from evidence, such
as an event's affected-item count, do. Stable metric IDs are dot-separated field
paths; group keys append the SHA-256 of canonical JSON for the exact key tuple.
This bounds IDs even when an original hint is long; it does not merge hints.
Validate by matching a recomputed metric ID, never by accepting a free
query expression.

Evidence is the observation supporting the count, not necessarily source prose.
Return stable item/source/apply/version/run IDs; the source table and key;
normalized event time, original clock encoding, and a hash of the selected
observation fields. Applied evidence includes `operation_sequence`,
`authoritative_record_hash`, before/after revisions, `undo_of`, and thin
before/after shelf identities. Source evidence includes source/cursor revisions
and original observation timestamps. Item evidence offers the existing
`get_library_item(video_id)` follow-up; that read obtains the current canonical
card/excerpt bindings. Do not manufacture card URIs or call an observation hash
a card `source_revision`. Deleted evidence exposes identity/time only.

Provenance includes the input schema version, all query IDs used,
`projection_revision`, `last_operation_sequence`, active taxonomy ID/hash or
null, and digests of relevant taxonomy/run and source-observation records.
Every metric's `revision_ref` resolves to those bindings in the same packet.
Names and counts alone are not provenance. Evidence pages preserve the same
population and prove totals before sampling.

Use one consistent SQLite read snapshot and the existing Index locking boundary.
The pure aggregator receives immutable query results and a fixed clock.
`report_revision` is SHA-256 over canonical JSON containing the contract/query
versions, database generation, normalized interval/basis and sorted report input observations before
pagination. Include all retained item IDs and selected capture/type/creator/
deletion fields, publication candidates including conflicts, source links,
source/cursor observation state, current memberships, journal headers and hashes
of both deltas, taxonomy/run bindings and coverage exclusions. Include all these
inputs even when outside the chosen interval: a correction can move into it.
Exclude `as_of`, display truncation and pagination from this content binding;
current states are otherwise bound. Evidence row hashes use the same canonical
serialization as Phase 4 (`library_cards.serialize_card`); no second card
revision algorithm is introduced.

The database generation is a reader-instance nonce, connection `total_changes`
and SQLite `PRAGMA data_version`, captured at the read boundary. The nonce
changes on process/connection replacement; the other two values detect writes
on the shared connection and other connections respectively. This is a
conservative invalidation token, not a durable source identity. It catches
committed clip/citation corrections even when all counted fields stay equal.
Do not inherit a caller's open write transaction or allow commits during packet
construction to combine snapshots. If generation changes across construction,
return `stale_report` for a new read, without an internal retry. Disk-only source
text is not an activity input; its fresh card follow-up remains responsible for
validating that content revision.

**No report cache in v1.** Recompute on every summary, detail request and refresh.
There is no persisted report, TTL-based reuse or stale-while-revalidate result.
If a detail's recomputed binding differs, return `stale_report` and require a new
summary; never combine pages from different bindings. Source content itself is
not cached in activity packets; card follow-ups always use the existing revision
validation. A card source-revision change cannot leave a cached card or report
in this path because neither is retained for reuse.

Deletion, restore, hard purge, capture recorrection, author/type correction,
publication correction, observation update, apply/undo, taxonomy or run change
invalidates dependent displayed results. Do not rely solely on subscription
`revision`, `run_revision`, item count, newest timestamp or projection revision;
each can stay unchanged while report inputs change. On a known mutation, the UI
marks its packet stale, disables old evidence pagination and recomputes. On tab
focus, manual Refresh and once per 60 seconds while the panel is visible, it
refreshes from the reader; there is no background task while hidden. Until the
next read detects an external mutation, label the packet "As of ..."; do not
promise push invalidation the current app does not have. A failed refresh shows
stale/error state rather than continuing to present the previous packet as fresh.

## Budgets, errors and dashboard

Adopt Phase 4's 8,192-byte request and 65,536-byte complete serialized UTF-8
response caps, including protocol envelopes and any duplicate text/structured
representation. Target at most 24,576 bytes for the dashboard packet; it is a
target, not permission to exceed the wire cap. Adopt its 2-second service deadline
including lock/read/aggregation/serialization, two active reads and 60 admissions
per rolling 60 seconds per serving process, shared with the new Phase 4 reads.
No model token budget or paid service is involved.

The summary has at most 20 combined events, 20 creator rows, 20 joint type/creator
rows, 20 shelf rows, 20 source rows and 31 daily buckets. Known source-type buckets
are the nine canonical types in migration 0026 plus `unknown`; unrecognized
stored types enter unknown with their original value retained in evidence.
Group tables order by count descending then canonical key; shelves and sources
page by stable key. Events order by normalized time descending, then kind and
stable ID; applied events tied in time use descending operation sequence.
`events` merges captures/publications on the selected basis, applied operations,
taxonomy creations and run creations. One row per event, never per clip.

Rows outside a top page have exact omitted-row and omitted-count metadata. An
`other` count is the sum of omitted disjoint item buckets, not a guessed creator.
Source and shelf overlaps prohibit an additive `other` item total. Detail pages
provide every row on demand. Evidence pages never contain raw `forward_json`,
`inverse_json`, `evidence_json`, `metadata_json`, cards or transcripts. Labels
are capped at 120 Unicode code points with explicit truncation; IDs are preserved.

To fit the wire cap, drop whole optional display rows in this fixed order: event
rows, joint creator rows, creator rows, source rows, shelf rows. Keep totals,
coverage, evidence selectors and continuation metadata. Re-measure the actual
serialization after each reduction. Do not drop metric families, exclusions or
mandatory provenance. If the mandatory response or a single evidence identity
cannot fit, fail `resource_too_large`. A sampled list cannot become the total.

Bound journal JSON admission to 64 MiB of combined forward/inverse bytes per
request, including any baseline replay; do not hold all history decoded at once.
Requests exceeding that limit fail `resource_too_large` with a narrower-window
next step only when it can help; baseline replay may still require older rows.
Deadline exhaustion returns `deadline_exceeded`, never a successful zero or
an unlabeled estimate. The bound is a product limit, not a measured speed claim.

Errors follow Phase 4's tool mapping and carry
`{ok:false,schema_version:1,contract_version:"phase5-v1",error:{code,message,
retryable,details}}`. Freeze `validation_error`, `not_found`, `stale_report`,
`feature_unavailable`, `storage_unavailable`, `invalid_source_data`,
`recovery_pending`, `resource_too_large`, `deadline_exceeded` and `rate_limited`.
Storage/rate/deadline/recovery errors are retryable; stale reports require a new
summary. Missing required tables are `feature_unavailable`; present but empty
tables return coverage-aware success. Invalid individual dates are exclusions;
invalid journal shape is `invalid_source_data`. No report read repairs storage.

In `assets/dashboard/index.html`, add one read-only "Library activity" panel in
the Library surface. Default to the rolling seven-day capture interval ending
at invocation; presets 1, 7 and 30 days and a validated custom interval share the
same reader. Put the UTC interval, capture/publication selector, `as_of`, coverage
and exclusions above counts. Show daily captures/publications, hint breakdowns,
current shelf size, recorded shelf changes/churn, source windows and the combined
event list. Unknown historical values display "Unavailable" with their reason.
An empty retained library is distinct from an unavailable database.

Each displayed number opens its bound evidence page; each live item can open the
existing item view. Do not route an exact UTC/publication query through an
incompatible inclusive date-only Library filter. Use ordinary pagination, not
infinite scrolling through all items. The panel must be keyboard accessible and
readable without charts. Escape titles/hints as data, validate any displayed
HTTP(S) source link, and reuse Phase 4's untrusted-data envelope for model-facing
text. No HTML from stored labels, source fetch, auto-narration, enrollment,
capture, assignment, approval, scheduler or new authority is introduced.

`whats-new` agrees with Phase 4: `days` remains canonical decimal 1-30, default
7; resolve once to the same rolling half-open UTC interval, force capture basis,
and return complete retained counts plus at most 20 combined events with
coverage. Its recorded shelf revisions mean the retained taxonomy/run creation
rows and journal activation events, not invented updates to mutable revisions.
Phase 5 supplies the semantics and shared aggregation seam. The Phase 4 prompt
owner integrates that seam in a reserved follow-up; AY edits no prompt or
`library_resources.py`. There is no silent supersession of the prompt interface.

## Disposition of the committed inputs

Gemini's counterexamples are adopted as scenarios and test names, with these
explicit amendments. Its interface and example dictionaries are proposals, not
an additional contract to implement.

| Evaluation input | Decision and required amendment |
|---|---|
| Section 2 interface, standard packet, 65,536-byte limit | Amend interface/packet to this contract; adopt half-open UTC and wire cap. Replace global complete coverage and positive creator-independence flags with per-family coverage and descriptive support. |
| Fixture 1: 200 backlog items versus steady capture | Adopt counts 201 captures versus 1 current publication for the first day. Seed all 205 rows and explicit publication links for all five steady items; do not rely on metadata fallback. Use historical publication dates outside the current interval and valid UTC captures. The exact deterministic warning is `capture_is_not_publication`; no statistical backlog detector or arbitrary prior-to-2025 threshold is implied. |
| Fixture 2: three identical cross-posted clips | Adopt the adversarial input and three-item total. Reject claimed one-origin text clustering and its invented hash. Preserve three hint rows; creator count remains null, minimum unmet, support unresolved. Count equality proves neither authorship nor independent support. No clip scan is required. |
| Fixture 3: one name under two channels/platforms | Adopt scenario; reject verified-author inference. Two platform-qualified hint rows and both channels remain. No identity is merged across platforms and no creator minimum is met. |
| Fixture 4: deletion after computation | Adopt 5-to-4 live total, one retained excluded tombstone and changed report binding. Amend cached-report assertions to recompute-on-read and stale detail rejection. The source observation hash is not a made-up card source-revision string. |
| Fixture 5: pin then undo | Adopt event accounting and invalidation; replace flat `video_id/remove/add` JSON with actual full `items` maps and required policy maps. Add a real earlier filing journal chain for the denominator. Distinguish 2 item-change events from 4 pair mutations; test the unchanged narrower interval after undo. |
| Fixture 6: single source | Adopt 3 saved items and single-source wording, but add exact source-item or legacy episode links. A matching channel name alone does not join the three fixture items to the subscription. |
| Fixture 7: pre-observation interval | Adopt refusal to invent past history; amend whole-request error to null historical metrics, `no_history` and zero retained matching rows. Current sizes and valid older publication dates remain available under their own coverage. |
| Section 4 faithfulness metric and Cases A-D | Adopt zero unsupported assertions in each released narration and the four adversarial cases. Amend bare-number/token/date matching to assertion-level support with metric IDs, populations and clocks. Dates explicitly present in evidence may precede the requested interval (archive dates); unrelated matching numbers are not support. No model evaluator runs in Part A. |
| Section 5 harness | Adopt isolated SQLite, migrations through 0028 and exact assertions. Repair invalid seed constraints and incomplete rows before AZ; generate epoch values from the written UTC instants rather than copying inconsistent illustrative millisecond constants. Use fixed hashes calculated from fixture data, not placeholder hashes. |

Grok's audit names six primary query families Q1-Q6 and supporting Q7/Q8. Keep
those names in provenance with the following definitions; this resolves the
brief's "six named queries" wording without discarding its supporting reads.

| Query | Decision, final meaning and cost consequence |
|---|---|
| Q1 | Adopt capture aggregation; amend timestamp normalization, exact item deduplication and platform/field-qualified hint keys. Raw lexical ranges in the proposed SQL are unsafe on local-naive/offset timestamps. Thin-column scans are acceptable at 10k. |
| Q2a/Q2b | Amend to one deduplicated saved-item publication relation. Q2a supplies episode candidates; Q2b supplies linked source-item candidates at higher precedence. Uncaptured rows belong to Q5 observations, not A2. Normalize RSS before filtering; do not sum both query counts. |
| Q2c | Adopt exclusion of sidecar/metadata publication walks in this release; disclose unavailable indexed publication data. Its quoted 10k cost is a forecast, not a benchmark. |
| Q3 | Adopt applied headers and full before/after comparison for membership measures. `json_each` of forward item keys alone counts metadata replacements and cannot prove churn. Parsing is required for exact metrics; reject "items_changed if cheap" and silent skipped JSON. |
| Q4 | Adopt current live shelf-size aggregation; amend interval churn to the survivor baseline and proof rule above. Do not use current size or preview summary as historical denominator. |
| Q5 | Adopt observation/cursor reporting; include archived sources with activity and retained tombstones in observation spans. Aggregate thin source-item columns in a batched pass, not one query per displayed source. Source rows are 20 per page to preserve provenance bytes, amending 50/100. |
| Q6 | Reject engagement for Part A. The audited query remains a future cost reference. No engagement scan, scores or popularity surface in AZ. |
| Q7 | Amend invalidation to all input changes, including same-count corrections outside the interval. In-window deletion/undo queries alone miss them. Adopt no report cache. |
| Q8 | Adopt current revision bindings; add creation-event counts for A6 and hashes of retained relevant bindings. Current revision/status is not a complete history of transitions. |

Adopt the audit's warning that item counts do not bound journal bytes or source
observations. Its 548-item and 10,000-item timings remain schema-based forecasts.
UTC normalization, complete provenance input scans, inverse-delta parsing and
baseline replay add work that its header-only estimates do not cover. AZ must
measure the final reader, including its error path, on synthetic fixtures.

Reject an index migration based solely on the audit. Existing date indexes do
not solve mixed clock encodings; an index on time cannot reduce the JSON needed
for a baseline. Also, `yoinks(yoinked_at) WHERE deleted_at IS NULL` is not covering
for type/creator aggregation, and `len(forward.items)` is not semantic changed
item count. No new `changed_item_count` column is approved. If AZ demonstrates
an unmet budget that needs schema work, Fable must reserve **0029** and amend
this contract with the measured query/plan and exact DDL before it is implemented.
No alternative migration number or materialized report is implicitly authorized.

## Acceptance gates for AZ and BA

All test names below are requirements, not claims of passing tests. AZ adds
`tests/test_library_analysis_fixtures.py` and its own registry/UI tests; it does
not edit Phase 2/3/4 tests or the proof harness. Fixtures use disposable databases
inside the test workspace, apply migrations through 0028, satisfy foreign keys
and CHECK constraints, and set a fixed UTC clock. They exercise pure aggregation
and the real read adapter without a resident helper, live index or port 5179.

| Test name | Exact gate |
|---|---|
| `test_gate1_backlog_import_vs_steady_capture` | Amended Gemini fixture gives day-one A1 201 and A2 1; 200 historical publications cannot be called current publishing activity. All independence/trend flags remain false. |
| `test_gate2_cross_posted_clips_not_independent_creators` | Three item IDs and identical clip text yield three captures, no content-origin claim and no independent-creator count. Aggregator succeeds with the clips table unread. |
| `test_gate3_creator_dual_channel_unmerged_hints` | Same name across YouTube/podcast stays two qualified hints. Same-platform exact hints group; case variants and unknown hints never become verified people. |
| `test_gate4_deletion_invalidates_derived_report` | Five becomes four, tombstone exclusion is one, binding changes, old evidence request refuses `stale_report`. |
| `test_gate5_undo_correction_reverts_journal_and_invalidates` | Seeded Alpha/Beta example reproduces 2 operations, 2 item-change events, 4 mutations, net zero and 1/1 churn; old shorter interval keeps its original net. Missing seed yields null denominator. |
| `test_gate6_single_source_interval_thin_support` | Three explicitly linked items yield one registered source and `single_source`; remove the links and support becomes unresolved with unlinked hint coverage. |
| `test_gate7_pre_observation_interval_coverage_gap` | Prehistory returns null historical activity with `no_history`, never a zero-percent assertion. An explicitly dated older publication remains countable in publication view. |
| `test_activity_interval_half_open_utc` | Start included, end excluded, leap-day validity, 30-day rolling 31-bucket case, future/reversed/overlong/naive bounds rejected. |
| `test_activity_mixed_stored_clocks` | Equivalent offset ISO, GMT RSS and epoch-ms instants enter the same bucket; local-naive capture/date-only publication are excluded with reasons, independent of machine timezone and DST. |
| `test_activity_publication_dedup_and_conflict` | Episode plus two source links count one item; conflicting chosen-tier dates exclude it; uncaptured observations never enter saved-item total. |
| `test_activity_denominator_and_pagination` | Top-20 plus other equals a disjoint full item partition; 0/0 is null, unknowns included, overlap not summed, every detail page retains full denominators. |
| `test_activity_journal_shapes_and_no_change_receipts` | Actual maps, empty arrays, policy-only/activation-only/metadata-only deltas, same-time sequences and no-change receipt gaps are handled distinctly; malformed JSON shape refuses. |
| `test_activity_primary_only_and_initial_filing` | Primary-only change adds no membership pairs but changes churn; first filing outside the starting population is separately counted; empty baseline percent is null. |
| `test_activity_history_chain_and_clock_regression` | Missing receipt/revision, mismatched inverse, current-state-only seed, empty journal, future apply or regressed clock prevents baseline proof. Valid retained event counts remain labelled. |
| `test_activity_deleted_journal_survivors_and_restore` | Recorded journal events survive soft/hard deletion, current sizes exclude missing items, survivor denominator recomputes, restore cannot fabricate historical liveness. |
| `test_activity_source_observation_windows` | Enrollment-only source has no observation span; archived active-history source remains; tombstones preserve span; cursor complete/window/partial never asserts continuous history. |
| `test_activity_source_overlap_and_legacy_link` | Shared captured ID in two sources contributes one union item and one per source; legacy podcast link deduplicates; same display name does not link. |
| `test_activity_corrections_outside_interval` | Same-count author/type/capture/publication correction, a row moving into the interval, restore, cursor/source-item changes with unchanged subscription revision, and clip/citation revision writes all invalidate old bindings. Exercise shared-connection and external-connection writes and connection replacement. |
| `test_activity_provenance_for_every_metric` | Every displayed total, ratio, group, bucket and mutation resolves to query/version, population, clock, interval, revisions and exact paged evidence; numerator/denominator evidence reconciles. |
| `test_activity_registry_stdio_http_parity` | Same validated arguments produce the same semantic packet through both adapters; unknown fields/duplicate keys fail before reads; missing table/storage never becomes empty success. |
| `test_activity_read_has_no_side_effects` | Compare fixture DB and filesystem before/after; spy on model/network/card/claim/clip/service/recovery/poller calls and require zero calls. No cache or report row is written. |
| `test_activity_wire_budget_and_untrusted_labels` | Worst-case Unicode/escaped labels, many groups and duplicate protocol representations stay within 65,536 bytes; truncation is explicit and whole-row; invalid links/control text cannot escape the evidence fence. |
| `test_activity_deadline_and_work_bounds` | Delayed lock/query and over-64-MiB journal yield bounded named errors; no partial success, automatic retry or abandoned background aggregation. |
| `test_activity_cost_548_and_10000` | Measure synthetic 548/10k libraries with 1-3 memberships each, up to 100k observations, and a complete journal including a full-library apply. Record actual combined journal bytes, query plans, elapsed construction/serialization time and peak memory. Normal admitted fixtures must finish within 2 seconds and the wire cap. Include a separate over-budget refusal case; no live performance claim. |
| `test_activity_dashboard_evidence_and_staleness` | UI fixture verifies UTC labels, unavailable states, keyboard evidence navigation, new-summary-on-stale, focus/60-second refresh and no hidden polling or write action. No listener on port 5179. |
| `test_activity_whats_new_semantic_parity` | Same clock and days give matching capture/revision/applied counts, history labels and combined 20-event sample. Validate adapter seam in Phase 5-owned tests; prompt integration waits for its reserved owner. |
| `test_activity_part_b_remains_deferred` | Empty or populated claims, many sources and repeated clips cannot enable trends, contradiction output, narration or model work. |
| `test_narration_faithfulness_metric` | Static labelled examples: compliant Alpha/Beta narration passes; wrong count, wrong clock, invented topic, unsupported consensus, missing denominator, reversed direction and a numerically matching but unrelated fact fail. Explicit archive date from evidence is allowed. No model invocation. |

BA accepts only the integrated candidate's recorded gate results, measurements
and provenance review. Passing count fixtures does not establish real-world
creator resolution, narration accuracy or production latency.

## Exact Part B deferral and future evaluation threshold

Part B includes term/phrase extraction and normalization, burst detection,
week-over-week term lift, statistical significance or trend ranking, content
syndication clustering, verified creator/entity resolution, claim extraction,
disagreeing sentence-pair retrieval, contradiction/consensus suggestions and
free-form narration. None is implemented, scheduled or enabled in Part A.
Existing `claims.py` persists client work under its present assistance framing;
Part A does not invoke it, populate its table or interpret empty claims as a
failure of activity reporting. There is no resident or fallback model path.

For a future separately authorized Part B, resolve the direction's ambiguous
"at least 3 items from 2-3 creators" conservatively: **at least 3 distinct items
from at least 3 verified independent creators after duplicate/syndication
resolution**. Repeated clips/cross-posts cannot satisfy those minima. Item/hint
counts from this contract cannot satisfy creator verification. This is a
necessary threshold, not sufficient evidence of a trend. Observation depth,
matched exposure denominators, baseline/comparison intervals, term algorithm and
false-positive thresholds require a new contract and labelled history fixtures
before any trend can ship; Part A chooses none of them.

Adopt the direction's faithfulness target **at least 0.90** on a declared,
independently labelled evaluation sample as a future release gate, not an
achieved score. Define score as supported factual assertions divided by all
factual assertions, with each assertion mapped to evidence, population, clock,
interval and revisions. Report the sample size, failures and denominator; empty
output has no score. Separately, each narration actually shown must contain
**zero unsupported factual assertions**, as Gemini proposes. Passing a 0.90
evaluation sample does not license unsupported assertions in the remaining 10%.
An assertion is not supported merely because its number occurs somewhere in a
packet. Count/clock/direction checks and static adversarial fixtures are necessary;
they do not prove a token-list evaluator understands arbitrary prose. Future
client narration and sentence pairs require independent contextual review and
revision revalidation, with no automated verdict about who is right.

All implementation ambiguities raised by the brief and committed inputs are
resolved above. Remaining work is AZ implementation and measurement, the reserved
Phase 4 prompt seam integration, and BA acceptance. Any broader history store,
publication projection, migration 0029 or Part B feature requires an explicit
contract amendment.
