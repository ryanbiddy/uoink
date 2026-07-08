# Surface map: source-agnostic taxonomy + source-first Library (cat P2)

Phase 2 of the categorization plan. The data model was YouTube-shaped:
`yoinks.channel` was the only "who" field, and for every non-YouTube source it
got hard-coded to the URL hostname. So an X Article by @boardyai showed up as
`x.com`, and you could not filter "show my X posts" or "everything from
YouTube." This map is the coherent model every source drops into cleanly.

## The taxonomy

```
Platform     youtube | x | reddit | podcast | web      (stored + indexed)
Source type  video | x_thread | x_article |            (stored + indexed)
             reddit_thread | page | episode
Author       the real "who": YouTube uploader, X        (stored + indexed)
             "Name (@handle)", reddit "r/<sub>",
             or the site host for a bare web page
Topic        classified for every source, not just video
Hook         optional, YouTube-only
```

## Schema (migration 0020)

`migrations/0020_platform_author.sql` adds two nullable, additive columns to
`yoinks` plus their indexes: `platform TEXT`, `author TEXT`. Additive + nullable
means it's backward compatible and reversible-safe (an old reader ignores the
columns; nothing is dropped). The runner routes the ALTERs through
`_safe_alter_add_column`, so a re-run is a no-op.

The SQL-derivable backfill runs in the same migration:
- `platform` from `source_type` (NULL source_type is a legacy YouTube video).
- legacy YouTube rows get `source_type = 'video'` so the Source-type facet is
  complete.
- `author = channel` for YouTube rows (the channel already holds the uploader).

The part that needs the on-disk sidecar (the real X / Reddit author, and
correcting the `x.com` / `reddit.com` channel values) runs in Python:
`page_extractor.backfill_platform_author`. The helper triggers it once per
install from the boot backfill thread (guarded by a `memory_layer` flag), and it
ships as `python server.py --backfill-authors [--dry-run]`. It's idempotent: a
row that already has a real author and a non-hostname channel is skipped.

## Where platform + author get set on write

- `page_extractor.persist_page_yoink` (X posts, X articles, Reddit threads,
  web pages): derives `platform` + `author` from the extractor metadata via
  `platform_for` / `author_for`, sets `channel = author` (so every path that
  still reads `channel` shows the real "who"), classifies a topic through the
  injected `topic_classifier`, writes `metadata_json`, and drops the corpus in a
  readable slug folder (`X/boardyai-<hash8>`, `Reddit/r-python-<hash8>`) instead
  of an opaque hash.
- `_index_yoink` (the video / sidecar-driven path): `platform` from the
  sidecar's source_type, `author = channel`.
- `/extract/any` (generic yt-dlp): `platform` + `author` from the uploader.

Readable folders are new-captures-only. Existing folders keep their paths so the
index never points at a renamed folder.

## Library API

- `GET /library/facets` now returns `platform`, `source_type`, and `author`
  facets (each `{value, label, count}`), alongside the existing ones. The
  video-only facets (format / performance_tier / length_bucket / hook_type) stay
  in the payload; the UI decides when to show them.
- `GET /memory/search` gained `platform`, `source_type`, and `author` filters,
  all AND-combined with the existing ones.

## Library UI (source-first)

`assets/dashboard/index.html`. The filter row leads with the source-first
controls: **Platform**, **Source type**, **Author** (the old "channel" picker,
which used to list `x.com` next to real creators), then **Topic**. The
video-only controls (hook / format / performance / length) carry the
`.video-facet` class and hide whenever a non-YouTube platform is selected, so
the row stays clean instead of offering dead filters.

Each card shows the source clearly: the platform chip stays top-right on the
thumbnail, a source-type badge sits under it, and the card body carries a
`Platform · type` line above the author. The author is the real "who", never the
host.

Before / after, the three canonical sources:

| | Before (v3.4.1) | After |
|---|---|---|
| X Article by @boardyai | channel `x.com`; folder `X\805baf72\`; Uncategorized; findable only by title search | Platform **X** · type **article** · author **Boardy (@boardyai)**; filter Platform=X or Author=@boardyai; folder `X\boardyai-<hash>\` |
| YouTube video | channel = creator; rich video facets | unchanged, plus an explicit Platform=YouTube filter |
| Reddit thread | channel `reddit.com` | Platform **Reddit** · type **thread** · author **r/<sub>** |

## Judgment calls (flagged, not guessed)

- **Topic for non-YouTube sources** reuses the existing keyword classifier
  (`_classify_topic`) over the title + the first 2000 chars of the captured
  markdown. It's the same heuristic YouTube uses (no new model call). Short X
  posts with no topic keyword still land in Uncategorized, which is honest. The
  MCP capture path does not classify a topic yet (only the HTTP routes do).
- **Reddit author** is the subreddit (`r/<sub>`), not the OP username, because
  the OP is frequently `[deleted]` and the community is the durable "who".
- **`channel` is kept and set equal to `author`** for backward compatibility
  (search FTS, the performance-tier heuristic, and the channel picker all still
  read `channel`). The two columns hold the same value going forward.
- **Podcast** is in the platform vocabulary but podcast episodes live in their
  own table, so no yoinks row carries `platform='podcast'` today.

## Tests / proof

- `tests/test_cat_p2_taxonomy.py` -- migration idempotency, persist sets
  platform/author/topic + readable slug, backfill corrects the hostname channel
  and is idempotent, and the HTTP facets + platform/source_type/author filters.
- `tests/test_reddit_extractor.py` -- updated to the new contract (channel =
  `r/<sub>`, readable folder).
- Backfill validated on a copy of the real index: 8 X rows corrected from
  `x.com` to the real author (jack, SpaceX, Boardy, NASA, Reid Wiseman), 0
  stayed hostname, idempotent on re-run.
