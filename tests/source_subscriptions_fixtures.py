"""Shared fixtures for tests/test_source_subscriptions_*.py (Phase 3, run AM).

Fake adapters, a fake capture backend, a settable clock and small helpers that
drive the contract's public interface (module ``source_subscriptions``). No
network, no subprocess, no model, no live index: every test opens a temporary
``index.db`` through ``index.Index.open`` (which runs migration 0028 through the
real runner) or a standalone connection through ``source_subscriptions.open_service``.

Adapter budgets recorded here match docs/library/PHASE3-ADAPTER-LIMITS-2026-09-07.md
section 3.3 and the module constants: HTTP timeout 8 s, response bound 8 MiB,
podcast parser window 50 entries, YouTube Atom window ~15 entries.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import clips as clips_mod  # noqa: E402
import index as index_mod  # noqa: E402
import source_subscriptions as ss  # noqa: E402

# 2026-09-07T12:00:00Z
T0 = 1_788_782_400_000
DAY_MS = 86_400_000
MINUTE_MS = 60_000

SESSION = "dashboard-session-1"
USER = ss.RequestContext(authenticated=True, session_id=SESSION, local_user_confirmed=True,
                         transport="dashboard")
REGISTRY = ss.RequestContext(authenticated=True, session_id=SESSION, transport="registry")
OPERATOR = ss.RequestContext(authenticated=True, session_id=SESSION, operator=True,
                             transport="server")
CHANNEL_ID = "UC" + "a" * 22
CHANNEL_URL = f"https://www.youtube.com/channel/{CHANNEL_ID}"
PLAYLIST_ID = "PL" + "b" * 32
PLAYLIST_URL = f"https://www.youtube.com/playlist?list={PLAYLIST_ID}"
FEED_URL = "https://show.example/feed.xml"


class Clock:
    def __init__(self, now: int = T0):
        self.now = now

    def __call__(self) -> int:
        return self.now

    def advance(self, ms: int) -> int:
        self.now += ms
        return self.now


def vid(n: int) -> str:
    """Deterministic valid 11-character YouTube ids."""
    base = f"{n:011d}"
    return "v" + base[-10:]


class FakeAdapter:
    """Scripted adapter: each poll pops the next AdapterResult (the last one
    repeats), optionally blocking on an event to model a slow network."""

    def __init__(self, results=None, *, gate=None):
        self.results = list(results or [])
        self.calls: list[dict] = []
        self.gate = gate

    def poll(self, source, cursor, *, conditional):
        self.calls.append({"source_id": source["source_id"], "conditional": conditional,
                           "cursor_revision": cursor["revision"]})
        if self.gate is not None:
            self.gate.wait()
        if not self.results:
            return ss.AdapterResult("snapshot", coverage="complete")
        result = self.results.pop(0) if len(self.results) > 1 else self.results[0]
        if callable(result):
            return result(source, cursor, conditional)
        return result


def snapshot(entry_ids, *, coverage="window", truncated=False, published=None,
             titles=None, etag=None, last_modified=None, urls=None):
    observations = []
    for i, entry_id in enumerate(entry_ids):
        observations.append(ss.Observation(
            entry_id=entry_id,
            title=(titles or {}).get(entry_id, f"Title {entry_id}"),
            canonical_url=(urls or {}).get(entry_id, f"https://www.youtube.com/watch?v={entry_id}"),
            published_at_ms=(published or {}).get(entry_id, T0 - (i + 1) * DAY_MS),
            metadata={"identity_method": "test"}))
    return ss.AdapterResult("snapshot", observations=observations, coverage=coverage,
                            truncated=truncated, etag=etag, last_modified=last_modified)


def not_modified(etag="W/1"):
    return ss.AdapterResult("not_modified", etag=etag)


def error(code="feed_unreachable", message="boom", retry_after_ms=None):
    return ss.AdapterResult("error", error_code=code, error_message=message,
                            retry_after_ms=retry_after_ms)


def corpus_identity(item, source):
    """The corpus id and provenance a publisher records for one observation:
    the YouTube id itself, or the deterministic podcast episode id with its
    full feed URL + GUID identity (AS-06)."""
    if source["kind"] == "podcast_rss":
        video_id = ss.podcast_corpus_id(source["source_key"], item["entry_id"])
        metadata = {"feed_url": source["source_key"], "guid": item["entry_id"],
                    "capture_key": item["capture_key"]}
        return video_id, metadata, "podcast", "episode"
    return item["entry_id"], None, "youtube", "video"


def publish(idx, video_id, *, backend=None, url=None, root=None, metadata=None,
            platform="youtube", source_type="video"):
    """Stage the durable publication evidence the service verifies since run AT
    (AS-01): corpus and sidecar files, a yoinks row with provenance, one timed
    transcript citation and its derived clip, plus the fake publisher's own
    completion record (``backend.published``). A bare yoinks row is a partial
    publication and neither completes a start nor links an observation."""
    root = Path(root) if root is not None else Path(idx._path).parent
    url = url or f"https://www.youtube.com/watch?v={video_id}"
    corpus = root / f"{video_id}.md"
    sidecar = root / f"{video_id}.json"
    corpus.write_text(f"Fixture evidence for {video_id}.\n", encoding="utf-8")
    sidecar.write_text(json.dumps({"video_id": video_id, "url": url, "platform": platform,
                                   "source_type": source_type}), encoding="utf-8")
    provenance = {"url": url, **(metadata or {})}
    idx.upsert_yoink(dict(video_id=video_id, slug=f"slug-{video_id}", title=f"Title {video_id}",
                          topic="Old", yoinked_at="2026-09-07", corpus_path=str(corpus),
                          sidecar_path=str(sidecar), platform=platform, source_type=source_type,
                          metadata_json=json.dumps(provenance)))
    with idx.write_transaction() as conn:
        conn.execute("INSERT OR REPLACE INTO citations (video_id, kind, seq, timestamp_start, "
                     "timestamp_end, text, source_url, source_deep_link) "
                     "VALUES (?, 'transcript_chunk', 0, 12.5, 21.75, ?, ?, ?)",
                     (video_id, f"Evidence for {video_id}", url, url + "&t=12s"))
        # Run AT-4 (AS-01): the service validates clips against the real
        # builder's deterministic derivation, so the fixture derives its clip
        # the way index.insert_citations does instead of hand-writing one
        # (a hand-written podcast link differed from the derivation).
        clips_mod.build_clips_for_video(conn, video_id, commit=False)
    if backend is not None:
        backend.published[video_id] = video_id
    return video_id


class FakeBackend(ss.CaptureBackend):
    """Records every run; ``outcome`` may be a CaptureOutcome or a callable.

    Run AT: the service verifies publication before a start succeeds, so the
    default inline success first publishes through ``publisher`` (bound by
    ``make_service`` to the fixture ``publish`` helper), exactly as a real
    executor leaves durable output before its callback."""
    kind = "fake"

    def __init__(self, outcome=None, *, preflight=None, bind_fail=False, probe="stopped"):
        self.outcome = outcome
        self.preflight_outcome = preflight
        self.bind_fail = bind_fail
        self.probe_result = probe
        self.runs: list[dict] = []
        self.binds: list[str] = []
        self.published: dict[str, str] = {}
        self.publisher = None

    def preflight(self, item, source):
        if callable(self.preflight_outcome):
            return self.preflight_outcome(item, source)
        return self.preflight_outcome

    def bind(self, conn, start, item, source):
        if self.bind_fail:
            raise RuntimeError("queue insert failed")
        self.binds.append(start["start_id"])
        return "job-" + start["start_id"]

    def run(self, start, item, source):
        self.runs.append({"start_id": start["start_id"], "item_id": item["item_id"],
                          "source_id": source["source_id"], "owner_token": start["owner_token"]})
        if callable(self.outcome):
            return self.outcome(start, item, source)
        if self.outcome is not None:
            return self.outcome
        video_id, metadata, platform, source_type = corpus_identity(item, source)
        if self.publisher is not None:
            self.publisher(video_id, metadata=metadata, platform=platform, source_type=source_type)
        return ss.CaptureOutcome("succeeded", video_id=video_id)

    def probe(self, start):
        return self.probe_result

    def published_video_id(self, conn, item, source):
        """The fake publisher's completion record, keyed by corpus id."""
        video_id = corpus_identity(item, source)[0]
        return self.published.get(video_id) or self.published.get(item["entry_id"])


def open_index(tmp_path: Path, name: str = "index.db"):
    return index_mod.Index.open(tmp_path / name)


def make_service(idx=None, *, path=None, clock=None, adapter=None, backend=None,
                 instance_id="test-instance"):
    adapters = None
    if adapter is not None:
        adapters = {name: adapter for name in ss.ADAPTERS.values()}
    backend = backend or FakeBackend()
    kwargs = dict(clock=clock or Clock(), adapters=adapters or {},
                  backend=backend, instance_id=instance_id)
    if idx is not None:
        if isinstance(backend, FakeBackend):
            # Bind (or rebind after a restart) the fake executor's publisher to
            # the live index so an inline success leaves complete evidence.
            backend.publisher = lambda video_id, _idx=idx, **kw: publish(
                _idx, video_id, backend=backend, **kw)
        return ss.SourceSubscriptionService(index=idx, **kwargs)
    return ss.open_service(path, **kwargs)


def register(service, kind="youtube_channel", url=CHANNEL_URL, **extra):
    result = service.register_source(REGISTRY, {"kind": kind, "url": url, **extra})
    assert result["ok"] is True, result
    return result["source"]


def status(service, source_id, **extra):
    result = service.source_status(REGISTRY, {"source_id": source_id, **extra})
    assert result["ok"] is True, result
    return result


def mint(service, operation, context=USER):
    result = service.mint_consent_intent(context, {"operation": operation})
    assert result["ok"] is True, result
    return result


def set_consent(service, source_id, state, *, operation_key, context=USER, token=None,
                summary=None):
    summary = summary or status(service, source_id)["source"]
    operation = {"source_id": source_id, "consent_state": state,
                 "expected_revision": summary["revision"], "operation_key": operation_key}
    if state == "on":
        operation["expected_cursor_revision"] = summary["detection"]["cursor_revision"]
    if token is None:
        token = mint(service, operation, context)["user_intent_token"]
    return service.set_source_consent(context, dict(operation, user_intent_token=token))


def turn_on(service, source_id, operation_key=None, context=USER):
    # operation_key is globally unique per the contract DDL (PRIMARY KEY); default to one per source.
    operation_key = operation_key or f"on-{source_id}-1"
    result = set_consent(service, source_id, "on", operation_key=operation_key, context=context)
    assert result["ok"] is True, result
    return result


def turn_off(service, source_id, operation_key=None, context=USER):
    operation_key = operation_key or f"off-{source_id}-1"
    result = set_consent(service, source_id, "off", operation_key=operation_key, context=context)
    assert result["ok"] is True, result
    return result


def rows(conn_or_service, sql, params=()):
    conn = getattr(conn_or_service, "store", None)
    conn = conn.conn if conn is not None else conn_or_service
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def starts(service, source_id=None):
    if source_id is None:
        return rows(service, "SELECT * FROM source_capture_starts ORDER BY reserved_at_ms, start_id")
    return rows(service, "SELECT * FROM source_capture_starts WHERE source_id=? "
                         "ORDER BY reserved_at_ms, start_id", (source_id,))


def items(service, source_id):
    return rows(service, "SELECT * FROM source_items WHERE source_id=? ORDER BY first_seen_ms, item_id",
                (source_id,))


def atom_feed(video_ids, *, channel_id=CHANNEL_ID, titles=None, published=None, extra_entries=""):
    entries = []
    for video_id in video_ids:
        title = (titles or {}).get(video_id, f"Video {video_id}")
        when = (published or {}).get(video_id, "2026-09-01T00:00:00+00:00")
        entries.append(
            f'<entry><id>yt:video:{video_id}</id><yt:videoId>{video_id}</yt:videoId>'
            f'<yt:channelId>{channel_id}</yt:channelId><title>{title}</title>'
            f'<link rel="alternate" href="https://www.youtube.com/watch?v={video_id}"/>'
            f'<published>{when}</published></entry>')
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" '
            'xmlns="http://www.w3.org/2005/Atom"><title>Channel</title>'
            + "".join(entries) + extra_entries + "</feed>").encode("utf-8")


def rss_feed(entries):
    """entries: list of dicts with guid/link/title/enclosure/pubDate (any may be None)."""
    body = []
    for entry in entries:
        parts = ["<item>"]
        if entry.get("title") is not None:
            parts.append(f"<title>{entry['title']}</title>")
        if entry.get("guid") is not None:
            parts.append(f"<guid>{entry['guid']}</guid>")
        if entry.get("link") is not None:
            parts.append(f"<link>{entry['link']}</link>")
        if entry.get("enclosure") is not None:
            parts.append(f'<enclosure url="{entry["enclosure"]}" type="audio/mpeg"/>')
        if entry.get("pubDate") is not None:
            parts.append(f"<pubDate>{entry['pubDate']}</pubDate>")
        parts.append("</item>")
        body.append("".join(parts))
    return ('<?xml version="1.0"?><rss version="2.0"><channel><title>Show</title>'
            + "".join(body) + "</channel></rss>").encode("utf-8")


class FakeFetch:
    """Scripted HTTP fetcher for the real adapters: returns FetchResponse objects
    in order (the last repeats) and records request headers."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests: list[dict] = []

    def __call__(self, url, headers):
        self.requests.append({"url": url, "headers": dict(headers)})
        item = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(item, Exception):
            raise item
        return item


def http(status=200, body=b"", headers=None):
    return ss.FetchResponse(status, dict(headers or {}), body)
