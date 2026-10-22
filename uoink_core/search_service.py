"""Shared search mode selection. Search never starts workers or downloads."""
from __future__ import annotations

MODES = ("auto", "keyword", "semantic", "hybrid")
MODE_SCHEMA = {"type": "string", "enum": list(MODES), "default": "auto",
               "description": "Auto uses hybrid when the local semantic index is ready, otherwise keyword."}
META_FIELDS = ("search_mode", "requested_mode", "fallback_reason")


def metadata(result):
    return {key: result[key] for key in META_FIELDS if key in result}


def citation_fields(row):
    row = dict(row)
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
    return row


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
            elif status["state"] != "ready":
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
    with index.read_snapshot() as db:
        identities = list(dict.fromkeys(hit.source_id for hit in hits))
        placeholders = ",".join("?" for _ in identities)
        sources = {row["video_id"]: dict(row) for row in db.execute(
            "SELECT * FROM yoinks WHERE video_id IN (" + placeholders + ") AND deleted_at IS NULL", identities)}
        # video_id is unindexed in FTS. Read the candidate texts in one scan,
        # rather than scanning the entire FTS table separately for each hit.
        contents = dict(db.execute("SELECT video_id, content FROM yoinks_fts WHERE video_id IN ("
                                   + placeholders + ")", identities))
        for hit in hits:
            row = sources.get(hit.source_id)
            if row is None:
                continue
            row = dict(row)
            content = contents.get(hit.source_id) or row.get("title") or ""
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
                passage.update(text=content[span["char_start"]:span["char_end"]],
                               field="content", timing="not_timed")
            row.update(source_id=hit.source_id, passage_id=hit.passage_id, span=span,
                       timestamp_seconds=hit.timestamp_seconds, passage=passage,
                       _snippet=passage["text"], _score=-hit.score)
            result.append(row)
    return result


def search(index, query, *, mode="auto", limit=50, offset=0, filters=None,
           source_types=None, source_id=None, clips_only=False, keyword):
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
                lexical = [citation_fields(row) for row in keyword(100, 0, "forgiving")["results"]]
                for row in lexical:
                    rows.setdefault(row[key], row)
                ranking = rrf_merge([row[key] for row in lexical], [row[key] for row in semantic], k=60)
            title_key = _search_title_key(query)
            ranking.sort(key=lambda pair: _search_title_key(rows[pair[0]].get("title") or "") != title_key)
            results = [{**rows[identity], "_score": -score, "_search_order": rank}
                       for rank, (identity, score) in enumerate(ranking)]
            return {"total": len(results), "results": results[offset:offset + limit],
                    "search_mode": actual, "requested_mode": mode, "fallback_reason": None}
        except Exception:
            reason = "Semantic search is unavailable. Keyword search still works. Retry setup in Settings."
    result = keyword(limit, offset, None)
    return {**result, "results": [citation_fields(row) for row in result["results"]],
            "search_mode": "keyword", "requested_mode": mode, "fallback_reason": reason}
