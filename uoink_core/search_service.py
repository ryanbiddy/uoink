"""Shared search mode selection. Search never starts model work or downloads."""
from __future__ import annotations

MODES = ("auto", "keyword", "semantic", "hybrid")
MODE_SCHEMA = {"type": "string", "enum": list(MODES), "default": "auto",
               "description": "Auto uses hybrid when the local semantic index is ready, otherwise keyword."}
META_FIELDS = ("search_mode", "requested_mode", "fallback_reason")
CITATION_FIELDS = ("passage", "source_id", "passage_id", "span", "timestamp_seconds",
                   "passage_verified", "citation_reason")
_COORDINATE_FIELDS = frozenset(("passage", "passage_id", "span", "timestamp_seconds",
                              "start", "end", "timing", "source_deep_link"))


def unverified(row, reason="No matched passage could be verified in stored source text.", *, copy_row=True):
    row = dict(row) if copy_row else row
    for key in row.keys() & _COORDINATE_FIELDS:
        del row[key]
    row.update(source_id=row["video_id"], passage_verified=False, citation_reason=reason)
    return row


def metadata(result):
    return {key: result[key] for key in META_FIELDS if key in result}


def citation_fields(row, *, copy_row=True):
    if row.get("passage_verified") is not True:
        return unverified(row, row.get("citation_reason") or "No matched passage could be verified in stored source text.", copy_row=copy_row)
    row = dict(row) if copy_row else row
    passage = row.get("passage")
    if not passage and row.get("clip_id") is not None:
        passage = {key: row.get(key) for key in ("video_id", "clip_id", "text", "start", "end", "timing")}
    if passage:
        passage = dict(passage)
        source_id = row["video_id"]
        timed = passage.get("clip_id") is not None
        span = passage.get("span") or ({"kind": "clip", **{key: passage.get(key) for key in ("clip_id", "start", "end")}}
                                       if timed else {"kind": "text", **{key: passage.get(key) for key in ("char_start", "char_end")}})
        passage_id = passage.get("passage_id") or (f"clip:{passage['clip_id']}" if timed else f"text:{passage.get('char_start', 0)}")
        extra = {"source_id": source_id, "passage_id": passage_id, "span": span,
                 "timestamp_seconds": passage.get("timestamp_seconds", passage.get("start"))}
        passage.update(extra)
        row.update(extra, passage=passage)
        row.pop("citation_reason", None)
        return row
    return unverified(row, copy_row=False)


def select_mode(index, mode):
    if mode not in MODES:
        raise ValueError("mode must be auto, keyword, semantic or hybrid")
    if mode == "keyword":
        return "keyword", None
    engine = getattr(index, "_local_search", None)
    try:
        if engine is None or not engine.enabled:
            reason = "Semantic search is off. Enable it in Settings."
        else:
            status = engine.status()
            if not status["acceptance"]:
                reason = "Accept the current Gemma terms in Settings first."
            elif status["paused"]:
                reason = "Semantic search is paused. Resume it in Settings."
            elif status["state"] != "ready" and not engine.retry_ready():
                reason = "Semantic search is not ready (" + status["state"] + ")."
            else:
                return ("hybrid" if mode == "auto" else mode), None
    except Exception:
        reason = "Semantic search is unavailable. Keyword search still works."
    return "keyword", reason


def _hydrate(index, hits, *, clips_only=False):
    """Use live source rows and stored passage coordinates, never generated text."""
    from clips import timing_kind
    hits = list(hits)
    if not hits:
        return []
    result = []
    with index.detached_snapshot() as db:
        from uoink_core.local_search import IndexSources
        sources_reader = getattr(getattr(index, "_local_search", None), "sources", None) or IndexSources(index)
        identities = list(dict.fromkeys(hit.source_id for hit in hits))
        current = {source.source_id: source for source in sources_reader.snapshot(source_ids=identities, _db=db)}
        placeholders = ",".join("?" for _ in identities)
        sources = {row["video_id"]: dict(row) for row in db.execute(
            "SELECT * FROM yoinks WHERE video_id IN (" + placeholders + ") AND deleted_at IS NULL", identities)}
        for hit in hits:
            row = sources.get(hit.source_id)
            if row is None:
                continue
            row = dict(row)
            source = current.get(hit.source_id)
            stored = next((p for p in source.passages if p.passage_id == hit.passage_id), None) if source else None
            row.update(_score=-hit.score, _snippet="")
            if (source is None or not hit.fingerprint or source.fingerprint != hit.fingerprint
                    or stored is None or stored.span != hit.span or stored.timestamp_seconds != hit.timestamp_seconds):
                if clips_only:
                    row["clip_id"] = hit.span.get("clip_id")
                result.append(unverified(row, "The matched semantic chunk changed or could not be verified."))
                continue
            span = dict(hit.span)
            passage = {"video_id": hit.source_id, "source_id": hit.source_id,
                       "passage_id": hit.passage_id, "span": span,
                       "timestamp_seconds": hit.timestamp_seconds, **span}
            if span["kind"] == "clip":
                clip = db.execute("SELECT * FROM clips WHERE video_id=? AND clip_id=?",
                                  (hit.source_id, span["clip_id"])).fetchone()
                if clip is None:
                    continue
                clip = dict(clip)
                if any(clip.get(key) != span.get(key) for key in ("start", "end", "media_revision")):
                    continue
                passage.update({key: clip.get(key) for key in ("text", "start", "end", "clip_id")})
                passage["timing"] = timing_kind(clip)
                if clips_only:
                    row.update(clip)
                    row["timing"] = passage["timing"]
            elif span["kind"] == "citation":
                citation = db.execute("SELECT text FROM citations WHERE video_id=? AND kind=? AND seq=?",
                                      (hit.source_id, span["citation_kind"], span["seq"])).fetchone()
                if citation is None:
                    continue
                passage["text"] = citation["text"]
                passage["timing"] = "coarse" if hit.timestamp_seconds is not None else "not_timed"
            else:
                passage.update(text=stored.text,
                               field="content" if source.content else "title", timing="not_timed")
            row.update(source_id=hit.source_id, passage_id=hit.passage_id, span=span,
                       timestamp_seconds=hit.timestamp_seconds, passage=passage,
                       passage_verified=True, _snippet=passage["text"], _score=-hit.score)
            result.append(row)
    return result


def search(index, query, *, mode="auto", limit=50, offset=0, filters=None,
           source_types=None, source_id=None, clips_only=False, keyword, passages=True, match="forgiving"):
    """Keyword callback accepts (limit, offset, match override) for existing contracts.

    Hybrid fuses 100 forgiving keyword and 100 semantic candidates with k=60.
    Counts describe that candidate pool. Exact titles retain the pass 1 guard.
    """
    actual, reason = select_mode(index, mode)
    if not (query or "").strip():
        actual = "keyword"
        reason = "Enter search text to use semantic search." if mode in ("semantic", "hybrid") else None
    if actual != "keyword":
        try:
            from index import _search_title_key
            from uoink_core.local_search import rrf_merge
            hits = index._local_search.embedding_search(
                query, limit=100, filters=filters, source_types=source_types,
                source_id=source_id, clips_only=clips_only)
            semantic = _hydrate(index, hits, clips_only=clips_only)
            key = "clip_id" if clips_only else "video_id"
            rows = {row[key]: row for row in semantic}
            ranking = [(row[key], -row["_score"]) for row in semantic]
            if actual == "hybrid":
                lexical = keyword(100, 0, "forgiving")["results"]
                for row in lexical:
                    if row[key] not in rows or (not rows[row[key]].get("passage_verified") and
                                               (row.get("passage_verified") or "_content" in row)):
                        rows[row[key]] = row
                ranking = rrf_merge([row[key] for row in lexical], [row[key] for row in semantic], k=60)
            title_key = _search_title_key(query)
            ranking.sort(key=lambda pair: _search_title_key(rows[pair[0]].get("title") or "") != title_key)
            results = [{**rows[identity], "_score": -score, "_search_order": rank}
                       for rank, (identity, score) in enumerate(ranking)]
            page = results[offset:offset + limit]
            if passages and not clips_only:
                page = index._search_passages(page, query, "forgiving")
            return {"total": len(results), "results": page,
                    "search_mode": actual, "requested_mode": mode, "fallback_reason": None}
        except Exception:
            reason = "Semantic search is temporarily unavailable. Keyword search still works."
    result = keyword(limit, offset, None)
    rows = result["results"]
    if query and passages and not clips_only:
        rows = index._search_passages(rows, query, match)
    return {**result, "results": rows,
            "search_mode": "keyword", "requested_mode": mode, "fallback_reason": reason}
