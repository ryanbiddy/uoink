# The Phase 2 substrate, as a contract

**Date:** 2026-09-04 · **Author:** Claude (run A) · **Status:** spec + draft SQL. Nothing implemented.
**Migration number:** `0026_library_substrate.sql`. 0024 is clips (shipped in the Phase 1 draft), **0025 is reserved for Phase 0's `source_type` backfill** (`PHASE0-BRIEF-2026-09-04.md`), 0026 is this.
**Prototype:** `scripts/librarian/dryrun.py` is this loop with a JSON file where the database goes. §8 reconciles the two line by line.

---

## 1. What this is, and what it must never become

uoink prepares work and persists results. **uoink does not think.** Every model call in this
loop happens in a client the user already pays for — a Claude Code routine, a Hermes cron
job, a Gemini scheduled action, `codex exec`, or a local LM Studio model — and reaches uoink
only over the tool registry. That is decision 2 (pure client-run, option iii) and decision 3
(D-17) expressed as a schema. See `D-17-2026-09-04.md`.

The failure mode this contract exists to prevent is the obvious one: a background thread in
`server.py` that "just runs the assignments itself when no client has claimed them in 24
hours." There is no such thread. `claim_library_work` hands out an evidence packet and
nothing else; if nobody claims it, the row sits there. A library that does not organize
itself while the user is away is the *correct* behaviour under decision 2, and the honest
counter-argument (Gemini's local daemon, Grok's "hidden product dependency") is explicitly
deferred until Phase 1 is measured.

---

## 2. Invariants

1. **The server never calls a model.** No module added by 0026 imports `urllib`, `requests`,
   `httpx`, `anthropic` or `openai`. Gate G3 already tests this shape for `clips.py`; extend
   the same test.
2. **Evidence or it did not happen.** Every assignment carries a `confidence` and an
   `evidence_quote` that must appear in one of the item's clips. An assignment with neither
   is rejected by `submit_library_result`, not stored with a warning.
3. **User corrections are immutable.** `item_shelves.locked = 1` means no agent, no version
   bump and no re-shelving pass may move, delete or re-confidence that row. The Librarian
   reads locked rows as few-shot anchors and writes nothing.
4. **Every apply is reversible.** A single `library_applies` row carries the inverse patch.
   Undo is replaying it, not reconstructing intent from a diff.
5. **Taxonomy is versioned; assignments point at a version.** Nothing is edited in place. A
   structural change creates a new `shelf_versions` row and re-classifies against it.
6. **Markdown on disk stays canonical.** Everything in 0026 is a rebuildable derivative,
   like clips. Losing `index.db` costs a re-run, never a corpus.
7. **Idempotent submission.** The same `idempotency_key` submitted twice produces one result.
   A client that times out and retries cannot double-apply.

---

## 3. Tables

Five, not the four named in the dispatch. `shelves`, `shelf_versions`, `item_shelves` and
`library_work` are as briefed; **`library_applies` is the fifth and it is load-bearing.** The
dispatch asks for "every apply is a version, every version has an undo," and assignment
applies do not map one-to-one onto taxonomy versions — a nightly assign pass touches 40 items
under the *same* active version. Without an apply journal, undoing last night's pass means
reconstructing it from timestamps. One extra table buys a real undo; flagging it here rather
than smuggling it in.

### One design note worth reading before the SQL

**`item_shelves` stores no foreign key into `clips`.** The obvious design points
`evidence_clip_id` at `clips.clip_id`, and it is wrong: clips are *derived*, and
`clips.rebuild_all_clips()` deletes and re-inserts every row, so `clip_id` values are not
stable across a rebuild. A FK with `ON DELETE SET NULL` would silently null every piece of
evidence in the library the first time anyone runs `--rebuild-index`; `ON DELETE CASCADE`
would delete the assignments outright. Evidence is therefore stored as
`evidence_quote` + `evidence_start` (seconds) + `evidence_deep_link`, all of which survive a
rebuild because clips.py derives them deterministically from `citations`. Verification is by
substring match against the item's current clips, not by id.

### `0026_library_substrate.sql` (draft)

```sql
-- Living library, phase 2: the Librarian substrate.
--
-- uoink prepares work and persists results; the calling client does every
-- piece of model reasoning (decision 2, pure client-run; D-17). Nothing in
-- this migration is consumed by a server-side worker: `library_work` is a
-- queue an outside client leases from, and if no client ever claims a row,
-- the row simply waits.
--
-- Everything here is a rebuildable derivative of the markdown corpus plus
-- the clip layer (0024). Losing index.db costs one re-run of the Librarian,
-- never a note, a transcript or a user correction that was mirrored to disk.
--
-- 0025 is reserved for the phase 0 source_type backfill.

-- ---- 1. Taxonomy versions ---------------------------------------------------
-- One row per taxonomy generation. A structural change (rename / merge /
-- split / add) NEVER edits shelves in place: it writes a new version, and
-- every item is re-classified against it before the version goes active.
CREATE TABLE IF NOT EXISTS shelf_versions (
    version_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_version_id INTEGER,             -- the version this was derived from
    status            TEXT NOT NULL DEFAULT 'draft',
                                           -- draft|active|superseded|rolled_back
    reason            TEXT NOT NULL,       -- induce | unmapped>=10 | leaf>40 |
                                           -- term-burst:<term> | correction:<video_id>
    created_by        TEXT NOT NULL,       -- claude-code|codex|hermes|gemini|local|user
    created_at        TEXT NOT NULL,
    activated_at      TEXT,
    node_count        INTEGER NOT NULL DEFAULT 0,
    stats_json        TEXT,                -- {churn, items_moved, unmapped_before/after}
    FOREIGN KEY (parent_version_id) REFERENCES shelf_versions(version_id)
);

-- Exactly one active taxonomy at a time, enforced in SQL rather than by
-- convention. SQLite honours partial unique indexes (>= 3.8.0).
CREATE UNIQUE INDEX IF NOT EXISTS idx_shelf_versions_one_active
    ON shelf_versions(status) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_shelf_versions_created
    ON shelf_versions(created_at DESC);

-- ---- 2. Shelves (nodes of one version) --------------------------------------
-- 1-3 levels, path stored canonically as 'A > B > C'. include/exclude are the
-- concept memory bank: the cues that decide membership, which is what makes a
-- later re-check against an older item possible at all.
CREATE TABLE IF NOT EXISTS shelves (
    shelf_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    version_id   INTEGER NOT NULL,
    path         TEXT NOT NULL,            -- 'AI and ML > Agent harnesses > Loop engineering'
    level        INTEGER NOT NULL,         -- 1|2|3, == number of path segments
    parent_path  TEXT,                     -- NULL at level 1
    definition   TEXT NOT NULL,
    include_json TEXT NOT NULL DEFAULT '[]',
    exclude_json TEXT NOT NULL DEFAULT '[]',
    -- New shelves stay hidden from the UI until they hold >= 5 items across
    -- two passes (stability rule, THE-LIVING-LIBRARY section 6).
    hidden       INTEGER NOT NULL DEFAULT 1,
    -- Denormalised count, recomputed on every apply. Cheap to rebuild; the
    -- leaf-over-40 structural trigger reads it on every pass.
    item_count   INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL,
    FOREIGN KEY (version_id) REFERENCES shelf_versions(version_id) ON DELETE CASCADE,
    UNIQUE (version_id, path)
);
CREATE INDEX IF NOT EXISTS idx_shelves_version_level ON shelves(version_id, level);
CREATE INDEX IF NOT EXISTS idx_shelves_parent        ON shelves(version_id, parent_path);

-- ---- 3. Item assignments ----------------------------------------------------
-- An item can sit on several shelves ("this is about jobs, this is about
-- money"). shelf_path is denormalised on purpose: an assignment must survive
-- the version that produced it, and a path is the stable identity of a shelf
-- across versions where shelf_id is not.
--
-- No FK into clips: clips are derived and rebuild_all_clips() re-issues every
-- clip_id, so a FK would null (or cascade away) the library's entire evidence
-- layer on the first --rebuild-index. Evidence is stored as quote + start +
-- deep link, all of which clips.py reproduces deterministically.
CREATE TABLE IF NOT EXISTS item_shelves (
    video_id          TEXT NOT NULL,
    shelf_path        TEXT NOT NULL,
    version_id        INTEGER NOT NULL,    -- taxonomy version this was decided against
    confidence        REAL,                -- 0.0-1.0, agent-supplied; NULL when source='user'
    evidence_quote    TEXT,                -- must appear in one of this item's clips
    evidence_start    REAL,                -- seconds into the source
    evidence_deep_link TEXT,               -- source-neutral link, same field clips carry
    source            TEXT NOT NULL DEFAULT 'agent',  -- agent|user|auto (matches yoink_tags)
    -- The lock. A user correction is immutable: no agent, no re-shelving pass
    -- and no version bump may move, delete or re-score a locked row.
    locked            INTEGER NOT NULL DEFAULT 0,
    is_primary        INTEGER NOT NULL DEFAULT 0,
    assigned_at       TEXT NOT NULL,
    PRIMARY KEY (video_id, shelf_path),
    FOREIGN KEY (video_id) REFERENCES yoinks(video_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_item_shelves_path    ON item_shelves(shelf_path);
CREATE INDEX IF NOT EXISTS idx_item_shelves_locked  ON item_shelves(locked);
CREATE INDEX IF NOT EXISTS idx_item_shelves_version ON item_shelves(version_id);

-- ---- 4. The work queue ------------------------------------------------------
-- Leases, retries, idempotent results. Conventions deliberately mirror
-- pending_yoinks (0005): a status/state string, an attempt counter capped at
-- 3, a terminal set, and an opportunistic cap on dead rows.
CREATE TABLE IF NOT EXISTS library_work (
    work_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind             TEXT NOT NULL,        -- induce|assign|reshelve|summarize
    state            TEXT NOT NULL DEFAULT 'ready',
                                           -- ready|leased|done|failed|cancelled
    priority         INTEGER NOT NULL DEFAULT 100,   -- lower runs first
    -- Deduplicates work AND results. Deterministic:
    --   assign:<version_id>:<video_id>
    --   reshelve:<version_id>:<shelf_path_hash>:<video_id>
    --   induce:<version_id>:<sample_hash>
    idempotency_key  TEXT NOT NULL UNIQUE,
    version_id       INTEGER,              -- taxonomy version the work is against
    payload_json     TEXT NOT NULL,        -- the bounded evidence packet
    lease_owner      TEXT,                 -- client id holding the lease
    lease_expires_at TEXT,                 -- ISO; a lapsed lease returns to 'ready'
    attempts         INTEGER NOT NULL DEFAULT 0,
    max_attempts     INTEGER NOT NULL DEFAULT 3,
    result_json      TEXT,                 -- the structured result, as submitted
    last_error       TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    completed_at     TEXT,
    FOREIGN KEY (version_id) REFERENCES shelf_versions(version_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_library_work_claimable
    ON library_work(state, priority, created_at);
CREATE INDEX IF NOT EXISTS idx_library_work_lease
    ON library_work(state, lease_expires_at);
CREATE INDEX IF NOT EXISTS idx_library_work_kind ON library_work(kind, state);

-- ---- 5. The apply journal ---------------------------------------------------
-- Reversibility. One row per applied batch, carrying the exact inverse patch,
-- so undo is a replay rather than an inference. Assignment applies do not map
-- 1:1 onto taxonomy versions (a nightly pass touches N items under the same
-- active version), which is why this is a table and not a column.
CREATE TABLE IF NOT EXISTS library_applies (
    apply_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    work_id      INTEGER,
    kind         TEXT NOT NULL,            -- assign|reshelve|activate_version|pin|unpin
    version_id   INTEGER,
    actor        TEXT NOT NULL,            -- client id, or 'user'
    applied_at   TEXT NOT NULL,
    summary_json TEXT NOT NULL,            -- {items, added, moved, removed, churn}
    -- Every item_shelves row this apply overwrote or deleted, verbatim.
    -- Replaying it restores the exact prior state.
    inverse_json TEXT NOT NULL,
    undone_at    TEXT,
    FOREIGN KEY (work_id) REFERENCES library_work(work_id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_library_applies_applied
    ON library_applies(applied_at DESC);
```

**Housekeeping to implement alongside the SQL** (in `index.py`, mirroring `pending_yoinks`):

- `_LIBRARY_WORK_MAX_ATTEMPTS = 3` and `_LIBRARY_WORK_TERMINAL = ("done", "failed", "cancelled")`, matching `_PENDING_MAX_ATTEMPTS` / `_PENDING_TERMINAL_STATES` (`index.py:49-50`).
- `_LIBRARY_WORK_CAP = 5000`: on enqueue, opportunistically delete the oldest terminal rows past the cap. Never evict `ready` or `leased`. Same rule as `_PENDING_TABLE_CAP` (`index.py:56`).
- Lease reaping is lazy, not a thread: `list_library_work` and `claim_library_work` sweep
  `state='leased' AND lease_expires_at < now` back to `ready` and increment `attempts`. No
  background timer, no new thread, nothing to die silently.

---

## 4. The five registry tools

**HTTP/OpenAPI registry only.** These do not go in the 23-tool stdio set — same reasoning
that put `search_clips` and `get_evidence_card` in the registry: the stdio surface is pinned
by CI in lock-step with `docs/v2-mcp.md`, and a Librarian loop is an HTTP-client story
(routines, cron, scheduled actions) before it is a desktop-MCP story. Adding these five takes
the registry from 67 to 72; `openapi_bridge.build_spec` picks them up with no change.

Schemas below are written for `_schema(properties, required)` (`uoink_mcp_tools.py:2269`) —
closed objects, the same small JSON Schema subset `openapi_bridge.validate_arguments`
executes. All five return the standard `{"ok": bool, ...}` envelope.

### 4.1 `list_library_work` — read-only

```python
input_schema=_schema({
    "kind":  {"type": "string", "enum": ["induce", "assign", "reshelve", "summarize"]},
    "state": {"type": "string", "enum": ["ready", "leased", "done", "failed", "cancelled"]},
    "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
}),
```

Returns `{ok, counts: {ready, leased, done, failed}, work: [{work_id, kind, state, priority,
version_id, created_at, attempts, payload_summary}]}`. **`payload_summary` only** — item
counts and ids, never the evidence text. A client polls this cheaply; it pays for the packet
only when it claims. Rate limiter: `_RateLimiter(30)`, matching the other read tools.

### 4.2 `claim_library_work` — leases and returns the packet

```python
input_schema=_schema({
    "client_id":     {"type": "string", "maxLength": 64},
    "kind":          {"type": "string", "enum": ["induce", "assign", "reshelve", "summarize"]},
    "max_items":     {"type": "integer", "minimum": 1, "maximum": 25, "default": 12},
    "lease_seconds": {"type": "integer", "minimum": 60, "maximum": 3600, "default": 900},
}, ["client_id"]),
```

Atomically (one `BEGIN IMMEDIATE` under `Index._lock`): reap lapsed leases, select up to
`max_items` `ready` rows of the requested kind ordered by `(priority, created_at)`, set
`state='leased'`, `lease_owner`, `lease_expires_at`, `attempts = attempts + 1`, and return
the full packets.

Returns `{ok, lease_id, expires_at, work: [{work_id, kind, idempotency_key, version_id,
payload}]}` where `payload` for an `assign` batch is:

```json
{"taxonomy": [{"path": ["AI and ML", "Agent harnesses"], "definition": "...",
               "include": ["..."], "exclude": ["..."]}],
 "cards": [{"video_id": "...", "slug": "...", "title": "...", "channel": "...",
            "platform": "youtube", "yoinked_at": "2026-03-11",
            "current_topic": "Uncategorized", "clip_count": 34,
            "clips": [{"t": 512, "text": "...", "link": "https://...&t=512s"}]}],
 "rules": {"max_shelves_per_item": 3, "min_confidence_to_assign": 0.6,
           "evidence_quote_required": true}}
```

That is `dryrun.card_text()` as JSON. **The packet is bounded**: 12 cards × 10 clips × 240
chars ≈ 29 KB of clip text plus metadata, which is the whole point of Phase 1 — the Librarian
never sees a transcript. `max_items` caps it at 25.

Default lease 15 minutes: long enough for a Sonnet-class batch of 12 (dryrun measures these
in seconds to low minutes), short enough that a client killed mid-batch frees the work before
the next nightly run.

### 4.3 `submit_library_result` — idempotent, validating, applies nothing

```python
input_schema=_schema({
    "work_id":         {"type": "integer"},
    "client_id":       {"type": "string", "maxLength": 64},
    "idempotency_key": {"type": "string", "maxLength": 200},
    "status":          {"type": "string", "enum": ["ok", "error"], "default": "ok"},
    "error":           {"type": "string", "maxLength": 500},
    "result":          {"type": "object"},
}, ["work_id", "client_id", "idempotency_key"]),
```

`result` is one of the three shapes `dryrun.py` already defines — `INDUCE_SCHEMA`,
`ASSIGN_SCHEMA`, `RESHELVE_SCHEMA` (`scripts/librarian/dryrun.py:55-101`) — selected by the
row's `kind`. Lift those constants into the shipping module verbatim; they are the contract
and they have already been run against three different clients' structured-output modes.

Server-side validation, all of it mechanical:

1. `idempotency_key` must match the row's. A replay returns the stored result with
   `{"ok": true, "duplicate": true}` and changes nothing.
2. `client_id` must hold the lease, and the lease must not have expired.
3. Every `video_id` in the result must have been in the packet. Extras are dropped and
   reported in `unexpected[]` (dryrun already does this, line 358).
4. Every non-unmapped assignment needs `confidence` in [0,1] and a non-empty
   `evidence_quote` whose normalized form is a substring of one of that item's clips. Failing
   items land in `rejected[]` with a reason. **This is the anti-slop gate and it is pure
   string comparison — no model, no judgement.**
5. Any shelf path not in the packet's taxonomy is only legal when `unmapped: true` and
   `proposed_new_leaf` is set.

Then `state='done'`, `result_json` stored, `completed_at` set. **Nothing is written to
`item_shelves`.** Submission and application are separate calls on purpose: it is what makes
"a dry run over all 537 applying nothing" (Phase 2's proof) the same code path as a real run
with one fewer step.

Returns `{ok, work_id, accepted, rejected: [{video_id, reason}], unexpected: [...],
duplicate: false}`.

### 4.4 `apply_reshelving` — the only writer, always reversible

```python
input_schema=_schema({
    "work_ids":    {"type": "array", "items": {"type": "integer"}, "maxItems": 200},
    "version_id":  {"type": "integer"},
    "activate_version": {"type": "boolean", "default": False},
    "dry_run":     {"type": "boolean", "default": True},
    "max_churn":   {"type": "number", "minimum": 0, "maximum": 1, "default": 0.15},
    "actor":       {"type": "string", "maxLength": 64},
}, ["actor"]),
```

`dry_run` defaults to **true**. Getting the real thing requires typing `false`.

Behaviour:

1. Gather the stored results for `work_ids` (all `done` rows of the version when omitted).
2. Compute the delta against current `item_shelves`: added, moved, removed, unchanged.
3. **Skip every `locked = 1` row**, and report them as `skipped_locked[]`. Invariant 3.
4. Compute churn = (moved + removed) / total assigned items. If churn > `max_churn`, refuse
   with `{"ok": false, "error": "churn 0.31 exceeds max_churn 0.15", "summary": {...}}`. The
   15% alert threshold from THE-LIVING-LIBRARY §6 becomes a hard stop with an explicit
   override rather than a log line nobody reads.
5. If `dry_run`, return the summary and stop.
6. Otherwise, in one transaction: write the inverse patch (every row about to be overwritten
   or deleted, verbatim) into `library_applies.inverse_json`, apply the changes, recompute
   `shelves.item_count`, unhide any shelf that has now held ≥5 items across two passes, and
   — when `activate_version` — flip the version to `active` and the previous one to
   `superseded`.

Returns `{ok, apply_id, dry_run, summary: {items, added, moved, removed, churn,
skipped_locked}, undo: "undo_library_apply(apply_id)"}`.

**Undo** is a sixth tool the dispatch does not name but reversibility requires:
`undo_library_apply(apply_id)` replays `inverse_json` inside one transaction, sets
`undone_at`, and writes its own `library_applies` row of kind `undo`. Undo is itself undoable.
Flagging it as an addition rather than assuming it.

### 4.5 `pin_shelf` — the user's veto

```python
input_schema=_schema({
    "video_id":   {"type": "string"},
    "slug":       {"type": "string"},
    "shelf_path": {"type": "string", "maxLength": 300},
    "action":     {"type": "string", "enum": ["pin", "unpin", "move"], "default": "pin"},
    "reason":     {"type": "string", "maxLength": 500},
}, ["shelf_path"]),
```

Resolves by `slug` or `video_id`, exactly like `get_evidence_card`. `pin` sets
`locked = 1, source = 'user', confidence = NULL`; `move` pins the item to a new path and
unpins the old one in one transaction; `unpin` clears the lock and leaves the assignment for
the Librarian to reconsider on the next pass.

Pins are the labeled dataset. `taxonomy_corrections` (migration 0003) already treats hook-type
corrections that way — "corrections become a labeled dataset asset" — and the Librarian
should inject pinned items on a shelf as few-shot examples into that shelf's cues, which is
the human-loop rule from THE-LIVING-LIBRARY §6.

---

## 5. The client loop, step by step

One nightly pass. Written as a Claude Code routine; the Hermes cron job and the Gemini
scheduled action are the same eight steps against the same HTTP endpoints.

```
0. Preconditions. Helper reachable at /health (Phase 0 makes this honest), X-Uoink-Token
   in hand, schema_version >= 26.

1. GET  /tools/list_library_work   {"state": "ready", "limit": 1}
   -> counts. Nothing ready? Exit 0. This is the whole "is there work" check and it
      costs one sub-millisecond query.

2. POST /tools/claim_library_work  {"client_id": "claude-code-nightly",
                                    "kind": "assign", "max_items": 12,
                                    "lease_seconds": 900}
   -> up to 12 evidence packets. Nothing else in the loop reads the corpus.

3. Think. The client runs its own model over the packet with the assign prompt and
   ASSIGN_SCHEMA as structured output. uoink is not involved and never sees a token.

4. POST /tools/submit_library_result  per work_id, with the idempotency_key from step 2.
   -> {accepted, rejected, unexpected}. Rejections are evidence failures, not
      transport failures: re-prompt those items once, then leave them.

5. Repeat 2-4 until list_library_work reports ready == 0 or the routine's budget
   (wall clock or token) is spent. Unclaimed work is still there tomorrow.

6. POST /tools/apply_reshelving  {"actor": "claude-code-nightly", "dry_run": true}
   -> summary. If churn > 0.15 the call refuses; the routine reports and stops.
      A human looks. That is the intended outcome, not an error path.

7. POST /tools/apply_reshelving  {"actor": "...", "dry_run": false}
   -> apply_id. Write it into the daily brief so the undo is one call away.

8. Structural triggers, evaluated by uoink (statistics, not judgement) and enqueued as
   new `induce`/`reshelve` work for tomorrow:
      - unmapped count >= 10
      - any leaf over 40 items
      - a term burst in clips_fts absent from every node's include cues
      - any new pin (a user correction is a signal the taxonomy is wrong)
```

Step 8 is the loop closing. The triggers are all SQL over `item_shelves`, `shelves` and
`clips_fts` — counts, thresholds and a term-frequency delta. No model decides whether to
re-shelve; a model only decides *how* once the statistics have asked.

**Where each client differs:** Claude Code gets a `.claude/routines/` entry and can use the
same `--json-schema` structured output `dryrun.py` already drives (`dryrun.py:215`). Hermes
uses its built-in cron and its HTTP tool. Gemini uses a scheduled action against the OpenAPI
spec at `/openapi/v1/spec.json`. A local LM Studio model uses the same loop through
`bench_local.py`'s OpenAI-compatible client (gemini's deliverable). The queue does not care
which; that is the point of putting the contract in HTTP rather than in a client.

---

## 6. Reversibility, concretely

| Action | Recorded as | Undo |
|---|---|---|
| One nightly assign pass | `library_applies` row, kind `assign`, with the full inverse patch | `undo_library_apply(apply_id)` |
| A taxonomy revision | new `shelf_versions` row + an `activate_version` apply | undo the apply → previous version returns to `active`, new one to `rolled_back` |
| A re-shelving pass onto a new concept | `library_applies` row, kind `reshelve` | same |
| A user pin | `library_applies` row, kind `pin` | `pin_shelf(action="unpin")` |
| Total loss of `index.db` | — | re-run migrations, `rebuild_clips()`, re-run the Librarian. Costs one pass; the corpus and the pins mirrored to the vault are on disk |

The one thing that is **not** reversible by design: a shelf version whose items were later
re-assigned under a newer version. Undo restores assignments, not history. `shelf_versions`
keeps prior generations so the path is auditable, and the churn stop is what keeps a bad
version from touching enough rows to matter before a human sees it.

---

## 7. What uoink computes (no model, ever)

To be explicit about where the line is, because this is the part that will drift:

| Server-side, pure SQL | Client-side, model |
|---|---|
| build the evidence packet (clip spread, metadata, current taxonomy) | decide which shelf an item belongs on |
| verify an evidence quote appears in a clip | write the evidence quote |
| count unmapped items, leaf sizes, term-frequency deltas over `clips_fts` | name a new shelf, write its definition and cues |
| compute churn and refuse over threshold | propose a merge or a split |
| lease, retry, dedup, apply, undo | everything else |

Every row on the left is a `SELECT` or a `COUNT`. If a proposed feature does not fit in that
column, it belongs in a client.

---

## 8. Reconciliation with `scripts/librarian/dryrun.py`

The dry-run harness is this contract with a JSON file where the database goes. Mapping:

| `dryrun.py` | Contract |
|---|---|
| `build_cards()` (129) reading `clips` with a `citations` fallback | the packet builder behind `claim_library_work`. Keep the fallback: pre-0024 copies still work |
| `_pick_spread()` (114) | same spread as `uoink_mcp_tools._spread_clips`; one implementation should win — recommend the tools-module one, since `get_evidence_card` is now the public definition of "evidence card" |
| `card_text()` (183) → a markdown blob | the packet ships **JSON**, not markdown. Clients with structured output want fields; the prompt template does the rendering |
| `INDUCE_SCHEMA` / `ASSIGN_SCHEMA` / `RESHELVE_SCHEMA` (55-101) | lifted verbatim as the `submit_library_result` result schemas |
| `stratified_sample()` (305), oversampling Uncategorized 2× | the `induce` work-item builder. Keep the oversample: 278 of 537 items were Uncategorized at council time (THE-LIVING-LIBRARY §4; not re-measured here) and that is the pile the Librarian exists to fix |
| `phase_assign()` batching at 12 with `--parallel 3` (346) | `claim_library_work(max_items=12)`; parallelism moves to the client, which is where it belongs |
| `with_retry()` (276), 3 tries, linear backoff | `library_work.attempts` / `max_attempts = 3`, matching `_PENDING_MAX_ATTEMPTS` |
| dropping assignments whose `video_id` was not in the batch (358) | `submit_library_result` validation rule 3, `unexpected[]` |
| the reshelve trigger counting cue-term hits in `clips` (588-595) | structural trigger 3 in step 8 — promote from `LIKE '%term%'` to a `clips_fts` MATCH, which is the whole reason Phase 1 exists |
| `write_report()` (422) — before/after distribution, churn, evidence table | `apply_reshelving(dry_run=true)`'s summary, plus the daily brief |
| `usage.json` / `summarize_usage()` (412) | the same numbers D-17's `usage` read produces server-side (`D-17-2026-09-04.md` §4) |

**Two things dryrun.py does that the contract deliberately drops:** it shells out to
`claude`, `codex.exe` and `agy.exe` by absolute path, and it holds a hardcoded path to the
user's control-room install (`dryrun.py:37`). Shipping code never launches a client — the
client calls uoink, not the reverse. That inversion is the difference between a harness and a
product, and it is exactly what D-17 requires.

**One thing dryrun.py does that the contract should adopt and does not yet have a home for:**
per-batch wall-clock and token accounting written next to the result (`meta` at 226-231). Put
it in `library_work.result_json` under a `usage` key at submission time; it is the only place
a client's real cost is visible to uoink, and grok's G4 model needs it.

---

## 9. Open questions for Ryan

1. **Do assignments replace or accumulate?** The contract as written replaces: a new pass
   overwrites `item_shelves` for the items it touched (with the inverse patch preserved). The
   alternative — keeping every historical assignment and reading "current" as max version —
   makes the table grow ~537 rows per pass and makes every read a subquery. Recommend
   replace; the apply journal is the history.
2. **Does `apply_reshelving` need a UI before it needs `dry_run=false`?** Phase 2's proof is a
   dry run over all 537 applying nothing. Ryan may want to see the report in the dashboard
   before any client is allowed to pass `dry_run: false`. Cheap to gate behind a settings flag
   (`librarian_apply_enabled`, default off) in the same shape as D-17's flags.
3. **`max_churn` default.** 0.15 comes from the council's alert threshold. It is a guess until
   a real pass measures actual churn.

**Related:** `D-17-2026-09-04.md` (why the server has no worker), `MCP-REACH-2026-09-04.md`
(how clients discover and read this), gemini's `PROMPT-SPECS-2026-09-04.md` (the prompts that
consume these packets) and `gold-set-2026-09-04.json` (what measures whether they are right).
