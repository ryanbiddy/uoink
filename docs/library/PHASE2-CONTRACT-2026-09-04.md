# Phase 2 dispatch contract, 2026-09-04

Contract version: `phase2-v1-2026-09-04`. Owner: Astra; integrator: Fable. This is a dispatch specification, not a shipped service or permission to apply labels. It supersedes the Phase 2 details and migration allocation in `WORK-QUEUE-CONTRACT-2026-09-04.md`. The frozen semantics below implement the requirements in `ASTRA-PHASE-PLAN-2026-09-04.md`.

The reviewed base is `5d61bc8968bc61ee25fa8e9318cb4ed6b8229a6c`. Its repair acceptance is **REJECT**, for the reproductions in [the acceptance report](ACCEPTANCE-REPORT-2026-09-04.md). Fable must name a repaired integration SHA and obtain acceptance of affected gates before Phase 2 product proof. Specification and isolated substrate development can proceed after the reservations below. No merge or model execution is authorized by this document.

**Dispatch boundaries**

Ship assignment staging against one explicitly approved, fixed taxonomy: immutable shelf definitions, one work row per item, leases, strict result validation, complete previews, reversible apply/undo, user pins, and recovery from authoritative local records. No subscribed client running means visible `waiting_for_client` status. The server never starts a Librarian model or client process.

Taxonomy induction, concept revision, automated structural triggers, standing capture, cloud transport, sync, and Writing Studio growth are separate dispatches. A later induction task must represent one bounded, frozen sample; it must not overload the assignment row or batch semantics below. There is no `induce` work kind in this migration. Default-off metered server features outside the Librarian retain D-17's existing scope.

The normative implementation drafts are [0027_library_substrate.sql](phase2-contract/0027_library_substrate.sql) and [tool-schemas.json](phase2-contract/tool-schemas.json). The SQL stays under `docs/` until Fable reserves and dispatches it; it is not registered as an active migration. All six tool entries contain self-contained JSON Schema 2020-12 input schemas. These schemas replace the earlier draft signatures; none of those five work tools is deployed on the reviewed base.

**Identity and frozen input**

1. `shelf_id` identifies a concept across versions. `shelf_nodes(version_id,shelf_id)` records its name, path, definition, include/exclude cues and retirement. Paths contain 1–3 nonempty segments; sibling names and canonical paths must be unique, with no parent cycles. A rename retains identity. A merge or split creates an explicit proposal and cannot silently redirect a pin.
2. An approved taxonomy revision is immutable and hashed from canonical definitions. Its authoritative JSON must exist before a run or pin references it. At most one version is active. Approval and activation are distinct; approval does not change current assignments.
3. A run freezes its taxonomy revision, policy, prompt hash, card selection version, target manifest and corpus-head hashes. `manifest_hash` covers ordered `(video_id,source_revision)` entries plus explicitly recorded exclusions. Every item in the frozen copy is accounted for, including pinned, deleted, changed, unsupported and unmapped items.
4. Exactly one assignment work row exists per `(run_id,video_id)`. A lease may return several rows, each containing exactly one card. Different runs have different rows; a run never hides multiple items behind one work ID. Stage one approved run for the first proof.
5. Use `library_cards` schema 1, profile `librarian`, selection `spread-longest-v1`, at most six excerpts of 240 characters, and at most 8,192 UTF-8 bytes including the canonical wrapper. Preserve `source_revision`, `card_hash`, excerpt IDs, original start/end, `timing`, evidence kind and truncation. Use the existing `truncation` field and per-excerpt `truncated` flag; the run F test-field mismatch does not define a second spelling.
6. No new source-revision algorithm may be introduced in an adapter. The source revision covers supplied source evidence; the packet hash also binds taxonomy and policy. Applying `item_shelves` does not rewrite legacy `yoinks.topic` or source text. Consequently an assignment does not invalidate its own source revision.
7. A claim response is at most 122,880 serialized UTF-8 bytes, including taxonomy and envelope; taxonomy alone is at most 16,384 bytes. Reduce the number of complete work packets to meet the response budget. Never truncate identities or issue leases for omitted packets. If one complete packet cannot fit, return a visible `packet_too_large` result and block that row for repair.

**Lease and submission semantics**

`library_work.py` owns domain validation and every state transition. Adapters pass a trusted request context and JSON arguments; they must not implement alternate validation or construct a fake HTTP handler. Reject non-object inputs, unknown fields, booleans masquerading as integers, non-finite numbers, malformed IDs and invalid cardinalities before using them as SQL values or hash keys. Decode JSON with duplicate-key and NaN/Infinity rejection. JSON Schema is an input contract; recursive service validation remains mandatory on every transport.

Claim uses `Index.write_transaction()` / `BEGIN IMMEDIATE`, reaps expired attempts, and selects `ready` rows by `(priority,created_at,work_id)`. Recheck source and taxonomy revisions before granting a lease. Create a cryptographically random, at least 256-bit attempt token distinct from work ID, client ID and submission key. Store one current attempt per row; increment `attempts` only when a new claim succeeds. Leases default to 900 seconds, range 60–900; renewal extends from server time but never past 3,600 seconds after the initial claim. The server clock determines expiry; `now >= lease_expires_ms` is expired. Use an injectable clock for boundary tests.

| Event | Work state and durable result |
|---|---|
| Successful claim | `ready -> leased`; new token, attempt number and deadline |
| Valid renewal | Same token and attempt count; current owner only, before expiry |
| Release or expiry | Retire token; `ready` if fewer than 3 claims, otherwise `blocked` |
| Cancel | Retire token, `cancelled`; manifest stays visible with reason; client may cancel only its current attempt |
| Valid assigned result | `accepted`; store immutable submission and proposed memberships; no current labels written |
| Explicit unmapped / unsupported | Corresponding terminal work state and manifest disposition; zero proposed memberships |
| Invalid result or explicit error with valid envelope/token | Store rejection and reasons; retire attempt; `ready` if attempts remain, otherwise `blocked` |
| Source/taxonomy changed or item deleted | Invalidate current attempt and proposals; manifest `changed`/`deleted`; block stale work |

Each submit names one work row and exactly its item, token, schema, source revision, taxonomy revision and packet hash. One accepted assignment contains 1–3 unique memberships; array order defines primary membership. Each membership needs finite confidence in `[0,1]`, a matching approved shelf ID/path, and evidence for that item. The server policy requires confidence at least `0.60` for assignment. A lower score must be an explicit unmapped outcome or a rejected result; it cannot enter the active projection by rounding.

Store `submission_key`, a canonical hash of the entire request, the result and the exact response. An identical retry of a completed submission returns that recorded response, even after the lease has expired or another attempt has begun. A changed request under that key, or a second result under a consumed attempt token, returns `idempotency_conflict`. Check recorded receipts before current-lease checks, after authentication. A stale token with no recorded matching submission returns `stale_attempt` and writes no proposal. A malformed envelope that cannot safely identify an attempt returns a validation error without consuming it. Omitted items retain their leases and later expire; no batch success count consumes them.

Do not reset the three-claim ceiling through `release`, invalid output, cancellation or arbitrary client fields. An exhausted row remains visible. An explicit operator retry creates a new run referencing the previous run and reason. Refreshing changed input increments packet generation and run revision, invalidates previews and accepted proposals, and preserves old attempt/submission records. Once three claims have been consumed, refreshed work also needs a new run. No adapter deletes rejection history to make a run look complete.

**Evidence validation and trust boundary**

`evidence.basis=packet` means the quote was checked against the supplied Librarian packet. `fetched_full` means the client followed up with the existing `get_evidence_card(video_id,profile="full")`, using its default ten-clip selection. The service reconstructs that full card for the same source revision and checks its card hash and excerpt ID. Different selection options require a later contract extension. Do not claim a concept is absent merely because it was absent from a six-excerpt sample.

Normalize Unicode to NFC and collapse whitespace for matching; preserve case and punctuation. A quote must be a substring of **one** specified excerpt for the same item and revision. It cannot span concatenated clips. Timed evidence retains its actual source interval and `timing`; text evidence has null time bounds. A publisher description or client summary is a typed hint, not original-prose evidence. Where origin cannot support an evidence claim, return unsupported. Never relabel a summary as a transcript to pass validation.

The calling client renders all cards with the canonical safe renderer, including benchmark and error/retry paths. Escape delimiter-breaking text before inserting it into prompts. Treat titles, creator names, quotations and URLs as untrusted data. A fence test checks boundary preservation; an independent client test must also check that an injected instruction produces no unauthorized tool action. Server-side quote validation proves textual occurrence, not semantic relevance; human evaluation supplies the latter.

**Preview, apply and churn**

Preview covers the entire target manifest. Return exact additions, replacements, deletions, primary changes, activation effects, unchanged items, preserved pins and exclusions. It stores canonical forward and inverse operations plus a binding hash over the delta, run revision, accepted submission hashes, source revisions, taxonomy revision, policy and expected projection revision. The inverse records absence as well as complete prior rows. Preview creation changes no current assignment, pin, activation or projection revision.

For each previously assigned, nondeleted item in the preview baseline, compare the set of stable shelf IDs and primary ID before/after. Churn numerator is the number of distinct such items whose membership or primary changes, including added secondary memberships. Denominator is the number of distinct previously assigned, nondeleted items in that baseline. Count each item once. Unchanged and pinned items remain in the denominator. Report initial filing of previously unassigned items separately. If the denominator is zero, churn is `0/0`, presented as `0.0` with `initial_filing=true`; it is not evidence of classification quality. Renaming a stable shelf alone does not count as assignment churn.

The service stops agent apply when `100 * changed_items > 15 * baseline_items`. There is no model-supplied `max_churn` override. Exceeding 15% requires a new, trusted human approval bound to that exact delta hash and ceiling. Initial filing also requires explicit preview approval. User pin/move/undo operations are separate user decisions, shown in the journal rather than laundered through the agent churn metric.

`librarian_apply_enabled=false` is the shipping default. Enabling it requires completed preview, independent quality and recovery gates, with the evidence recorded. Even when enabled, apply requires a locally approved, unexpired preview (15-minute lifetime), matching operation key, delta hash and projection revision. Recompute all bindings before persistence. A stale revision, changed source, new pin, changed taxonomy or altered delta returns a conflict with **zero partial changes**. A complete manifest has one explicit disposition for every target item; `waiting`, `rejected`, `changed`, cancelled or exhausted work blocks activation until refreshed or explicitly excluded in a newly approved manifest. Unsupported, unmapped, pinned and deleted entries are accounted exclusions, never implied successes.

Successful apply writes the forward delta, inverse delta, activation and membership changes, one journal receipt, and `projection_revision + 1` as one database transaction after the authoritative record is durable. Replaying the same operation key/request returns its original receipt without changing the revision; changed content under that key is a conflict. A zero-delta apply returns a no-change receipt and does not create a fictitious revision. Persist all receipts in `library_operation_receipts` and the authoritative operation stream; a no-change receipt advances only the operation sequence. `library_applies` contains the subset that changes projection revision.

Undo requires the original apply ID, a new operation key, explicit user intent and the expected current revision. Initially allow only a target whose `after_revision` is the current revision. This conservative rule rejects unrelated newer changes too; it guarantees that undo cannot overwrite a newer pin. Invert the complete operation, including additions, removals, activation and item policy. Record undo as its own reversible journal operation. Repeating the undo key returns its stored receipt; attempting a second undo of the same target with a different key conflicts. The newer undo operation may itself be undone with a new key.

**Pins and authoritative recovery**

`pin_shelf` uses stable item and shelf IDs. `pin` adds/locks that membership, preserving other memberships; if there is no primary it becomes primary. `move` replaces all memberships with one primary locked membership and sets an item-level exclusive-move policy. While exclusive, an agent cannot add any other membership. `pin` to another shelf while exclusive returns a conflict; the user must unpin or move explicitly. `unpin` leaves the membership in place, clears its lock and any exclusive policy that it owns, and permits a later reviewed assignment to reconsider it. Model confidence is null for locked user rows. Every operation preserves its exact inverse.

Pin/move/undo require `user_intent_token`, a short-lived capability minted by an authenticated local dashboard confirmation route. It binds the canonical operation (excluding the token), expected revision, user session and a 5-minute expiry. It is consumed atomically with the operation, with identical retries allowed. A client-supplied actor string cannot grant user authority; no registry tool mints this token. Fable must reserve the dashboard confirmation route and its CSRF/origin protection with the adapter owner. This is a concrete product confirmation of a displayed delta, not a generic confirmation on every read or lease.

Local records under `<output_root>/.uoink/library/` are authoritative. Reserve immutable `taxonomies/<revision_hash>.json` and sequential `operations/<sequence>-<operation_key_hash>.json` records. A record contains schema, operation ID/key/request hash, sequence, previous-record hash, before/after revision, forward/inverse operations, referenced taxonomy hashes and receipt. It includes user pins and exclusive policy; an optional vault mirror has no authority. Never write API keys, client tokens or local source paths into public evidence packets or exported operation receipts.

All projection-changing service calls serialize through a process lock and a cross-process lock for that store. Recheck revisions under the lock. Persist referenced taxonomy records first, then write and flush a temporary operation record and atomically publish it; only then project it in the DB transaction. Do not acknowledge success before file publication and DB commit. Once the file is durable, that operation is committed to the authoritative sequence: if DB projection fails, report `recovery_pending` and block later mutations until replay. Replaying never starts a second model call or invents a new operation ID.

On startup, verify record hashes and sequence, replay durable operations after the DB checkpoint in order, and return the original receipt to retries. Ignore incomplete temporary files; stop visibly on a corrupt or missing committed record. Recovery must not skip a damaged record and continue. Test forced process termination before file publication, after publication/before DB commit, and after commit/before response. The platform-specific flush/rename implementation must pass the crash tests; these tests do not by themselves certify power-loss durability.

For complete DB loss, rebuild corpus identities and clips, reload immutable taxonomies, then replay library operations. Retain corrections for missing/deleted items as orphaned authoritative records and expose their count; do not resurrect deleted content or silently discard the pins. A taxonomy change that retires a pinned identity blocks activation until the user explicitly resolves that pin. Export/rebuild uses this same local record stream, not an optional Obsidian directory. Capture/reindex/deletion integrations must invalidate affected work and previews after source commit; apply revalidates the current source snapshot under its transaction boundary.

**Service surface and adapter returns**

| `library_work.py` function | Responsibility |
|---|---|
| `approve_taxonomy`, `prepare_run`, `refresh_run_item` | Trusted operator entry points; validate/freeze taxonomy, source manifests and packets; prepare/revise work |
| `list_work` | Counts by work state and manifest disposition, run revision, cursor page, waiting/recovery status |
| `claim_work`, `renew_attempt`, `release_attempt`, `cancel_attempt`, `expire_attempts` | All lease transactions; never call a model |
| `validate_result`, `submit_result` | Identity/cardinality/evidence checks, recorded receipts, retry accounting and staging |
| `preview_apply`, `approve_preview`, `apply_preview` | Exact delta/binding hash, trusted review approval, service ceilings and transaction |
| `pin_shelf`, `undo_apply` | User-capability checks, pins/exclusive policy and full inverse journal |
| `recover_operations`, `export_library_state`, `rebuild_library_state` | One authoritative persistence/replay implementation |

The six registry tool names are `list_library_work`, `claim_library_work`, `submit_library_result`, `apply_reshelving`, `pin_shelf`, and `undo_library_apply`. Their exact input contracts are in [tool-schemas.json](phase2-contract/tool-schemas.json). The adapter maps each claim action to the corresponding service method. All work/result packets use `schema_version=1`. Return no raw database exceptions or paths.

Every success includes `ok:true` and `schema_version:1`. List returns `run_revision`, counts, `items`, `next_cursor`, and `waiting_for_client`. Claim returns `work:[{work_id,video_id,attempt_token,attempt_number,lease_expires_ms,source_revision,taxonomy_revision,packet_hash,card}]` and the approved taxonomy/rules once per response. Renew/release/cancel return the affected work state and remaining attempts. Submit returns `work_id`, `video_id`, `outcome`, `accepted_memberships`, `rejected:[{code,field,reason}]`, and `retryable`. Counts describe actual accepted items/memberships separately.

Preview returns `preview_id`, expected revision, `delta_hash`, expiry, full delta, manifest exclusions, baseline/churn counts and `can_apply` with reasons. Apply/pin/undo return `operation_key`, `apply_id`, before/after revision, delta hash and an undo target, or an explicit no-change receipt. Errors use `{ok:false,schema_version:1,error:{code,message,retryable,details}}`; conflict details contain expected/current revisions and affected IDs, not source paths. An expired lease is retryable through a new claim; an idempotency conflict is not retryable with the same key.

**Ownership and integration order**

These are proposed named assignments for the next dispatch; this run does not start other workers. Fable records exact bases and allowed files in each brief. One owner edits each shared surface at a time.

| Worker | Allowed files and responsibility | Independent verification |
|---|---|---|
| Astra | `library_work.py`, reserved `migrations/0027_library_substrate.sql`, new persistence helpers, narrow `index.py` transaction/rebuild hooks; shared card changes only when explicitly allocated | Claude or another assigned reviewer audits transactions and forced-crash cases; Astra cannot certify its own implementation solely with its own tests |
| Claude | After service interface freezes: `uoink_mcp_tools.py`, `uoink_mcp.py`, `server.py`, `assets/dashboard/index.html`, `build.ps1`, `installer/uoink.iss`, client/transport docs | Astra reviews adapter parity, privileges, default-off apply and installed behavior |
| Gemini | Independent `tests/test_library_work_*.py`, crash runner/fixtures, `scripts/librarian/` evaluation harness and prompts, frozen gold/evaluation manifests and report | Astra/Fable adjudicate labels and audit denominator, leakage, rejection and evidence results |
| Grok | Measurement audit and rate assumptions in `docs/library/`; no runtime or prompt edits | Verify measured/reported/estimated/paid fields and arithmetic against raw receipts |
| Fable | Reserve names, repair-base SHA and file ownership; integrate substrate, tests, adapters, packaging in order | Rerun on integrated SHA, preserve failed evidence, dispatch independent acceptance |

Do not let concurrent workers change `library_cards.py`, `index.py`, `server.py`, tool registries, dashboard, prompts or migration numbering. Each transfer of ownership names the new base. If the repair changes prompt/card bytes, regenerate hashes and invalidate affected measurements.

**Exit gates**

| Gate | Required exit evidence on the integrated candidate |
|---|---|
| P2-0: migration and packaging | Fresh and populated schema-26 disposable upgrades to 27; repeat open unchanged; FK/FTS/integrity checks; installed imports without checkout; zero initial assignments/work; rollback of an injected migration failure |
| P2-1: leases | Two concurrent connections/processes contend for one row and receive exactly one current token; batches contain distinct single-item rows; expiry boundary, capped renewal, release, cancel and third-attempt exhaustion; no model/network calls |
| P2-2: validation and retries | Wrong/missing/extra/duplicate IDs, malformed nested output, NaN/Infinity, foreign shelf, joined-clip quote and stale revisions write zero current labels; rejects remain visible; identical submit retry returns exact stored response; changed-key payload conflicts |
| P2-3: preview/apply | All target IDs have dispositions; incomplete activation refused; altered preview/revision/pin conflicts; apply key retry changes zero rows; forward delta matches preview exactly; distinct-item churn and empty/initial filing cases; clients cannot override 15% |
| P2-4: pins/undo | Preserve pins through every claim, submit, taxonomy/activation and apply transition; exclusive move blocks additions; rename retains identity; full inverse restores membership/primary/activation/policy; stale undo refuses newer pins; invalid/expired/reused user intent rejects |
| P2-5: crash and reconstruction | Kill subprocesses at all three durable boundaries; reopen and replay once; exact receipt/revision; corrupt record stops visibly; delete only a verified disposable DB and reconstruct pins/taxonomy/exclusive policy from local authoritative records; orphan pins retained |
| P2-6: access and waiting | Registry, supported stdio and HTTP adapters return identical revisions/results; malformed inputs reach common validation; no client leaves ready rows and visible waiting state; installed client claims/submits/reconnects after helper restart |
| P2-7: product proof | Frozen-copy dry run below, independent quality/evidence audit, input-byte and usage receipts, zero applied labels; apply remains off until P2-0 through P2-7 are accepted |

Use `PYTHONPATH=. python -m pytest -q tests/ -p no:cacheprovider`, with all data/output/temp roots isolated. Mutation and kill tests must use disposable fixture roots and an explicit test port, never the resident helper at `127.0.0.1:5179`. A green suite does not substitute for installed-client or process-recovery receipts.

**Frozen-copy product proof, applying no labels**

Start with the named `uoink-index-copy-2026-09-04-upgraded.db`, source date 2026-09-04, SHA-256 `2765cc359805fb12f7a90aecd3dd0b34d884aa8cb3015785011bf400da3b4dfc`. Verify bytes before SQLite access, then create a writable duplicate inside the dispatched worktree. Upgrade that duplicate; record pre/post hashes and selected corpus-head hashes. Never open the live index. The run F reproduction contains 548 items: 212 timed-evidence items and 336 text-only cards; remeasure rather than hardcoding those as future acceptance results.

Freeze the approved taxonomy, prompt files, card bytes/hashes, model/client configuration, human-adjudicated split and thresholds before model execution. Keep held-out labels out of prompts, examples and taxonomy generation; publish split IDs and hashes. Fable must choose the actual supported client/transport, execution budget, permitted corpus egress and any paid-call authorization. No spend, token allowance or quality result is implied by this contract.

Drive the real claim/submit loop across the entire manifest, with at most one retry for a rejected model result during the proof (the service ceiling remains three claims for crash recovery). Run preview only. For all 548 targets, emit accepted/rejected/unmapped/unsupported/pinned/deleted/changed outcomes, attempt IDs, quoted evidence and basis, and explicit reasons. Preserve every failed attempt, including transport failures; do not report only successful batches.

Measure exact serialized input bytes, end-to-end wall time including failed attempts and retries, and response bytes. Store client-reported input/output/cache tokens with model identity when available; otherwise `usage.status=unavailable`. Keep estimated token/cost calculations and invoice-confirmed paid cost in separate fields. Missing usage cannot prove a dollar-cost gate. A mocked completion is fixture evidence and must never enter the measured quality denominator.

Primary-shelf precision target is at least `0.90` on the frozen held-out set, reported separately for timed-evidence and text-only/metadata-only strata, with numerator, denominator and abstention/coverage counts. Precision means correct primary assignments divided by evaluated assigned items; abstentions are excluded from that ratio but counted against the separately frozen coverage floor. Every accepted assignment must also pass evidence identity/quote checks. Fable must ratify the per-stratum sample size and coverage floor before dispatch; zero assignments or an empty stratum cannot pass precision. Invalid evidence accepted, missing target IDs, applied labels, lost pins or a failed recovery gate blocks apply regardless of precision.

Record projection revision, active memberships, pins and taxonomy activation before and after proof; all must match, and the apply journal must contain zero proof-created applies. A reviewer independently replays the submitted evidence checks and reviews the held-out labels. Publish a complete report and fixture/execution distinction, not a synthetic PASS banner.

**Fable's pre-dispatch reservations and decisions**

- Reserve `0027_library_substrate.sql` and confirm 0026 remains provenance repair; freeze the attached 16-table draft with its sole substrate owner before copying it into migrations.
- Name the repaired integrated base, the one owner of each shared surface, service-review worker and acceptance worker. Preserve the run F failing fixtures and require affected reruns.
- Approve the initial fixed taxonomy and freeze revision/hash, target/source/corpus-head manifests, prompt/card revisions, hold-out split, coverage floor and stratum sizes.
- Reserve the local authoritative directory and Windows locking/flush implementation, export/rebuild hooks, preview approval storage and user-intent confirmation route. Do not treat the optional vault as recovery storage.
- Choose the installed client/transport and isolated test port/profile; set dry-run model scope, wall-time/retry/usage budget and any paid-spend approval. Keep `librarian_apply_enabled=false` throughout the first proof.

Draft verification in run F: `python tests/validate_phase2_contract.py --copy tests/.acceptance-run-f/measurement/rebuild.db` passed six schema checks, 22 request cases and six SQL rejection cases. Sixteen draft tables were added in memory; 548 copied items were unchanged and work/assignments stayed at zero. These checks validate the draft's syntax and selected constraints. P2-0 through P2-7 remain future implementation gates.

## v1.2 rulings

Contract version: `phase2-v1.2-2026-09-04`, as ruled in
[the run L brief](PHASE2-RULINGS-BRIEF-2026-09-04.md). These rulings supersede the
corresponding semantics above. The frozen `(context, args)` service surface,
input tool schemas and `schema_version=1` remain in force.

R1 extends the lease table's invalidation row:

| Event | Work state and durable result |
|---|---|
| Source/taxonomy changed or item deleted; user unpin or undo | Invalidate current attempts, block affected work, delete proposals and previews, and bump `run_revision` in every run containing the item. Source changes use manifest `changed`/`deleted`; unpin and undo use `pinned` when a lock remains, otherwise `changed`. Refresh and re-claim before reconsideration, subject to the existing attempt ceiling. |

R2: `_ready` reports the stored recovery state through the common error envelope:
`recovery_state='conflict'` returns `recovery_conflict`; `'pending'` returns
`recovery_pending`. Both use the message "Recover authoritative records before
mutation" and the same `{code,message,retryable,details}` fields. Pending is
retryable after replay; conflict requires repair. The code depends on the state,
not the endpoint. Existing receipt retries and recovery entry points retain their
replay semantics.

R3: `expire_attempts` and `list_work` call `_expire` only after `_ready` passes.
During pending or conflicting recovery, listing succeeds with the stored work
states, counts and `recovery_state`, without reaping leases. An expiry call returns
the corresponding recovery error and changes nothing. Normal expiry resumes once
recovery is ready.

R4: A missing or invalidated preview returns `preview_conflict` with
`error.details.expected_revision`, `current_revision` and `conflicts`. Preview
requests with stale projection revisions use the same details. `conflicts` lists
currently locked memberships in `(video_id,shelf_id)` order, each as
`{video_id,shelf_id,pin_kind}`; `pin_kind` is `move` for an exclusive move and `pin`
otherwise. These details come from the current projection, so pin invalidation
can still delete previews and the response remains available after restart.
Refusal applies no partial delta.

R5: `library_work.CONTRACT_VERSION` is `phase2-v1.2-2026-09-04`. Every successful
`list_work` response includes that value as `contract_version`, including empty,
filtered and recovery-frozen lists.
