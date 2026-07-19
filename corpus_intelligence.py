"""Local corpus-intelligence queries over Uoink's private index.

This module owns selection and ranking. It does not own workspaces,
transport, persistence, or model calls.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import corpus_contract

log = logging.getLogger("uoink.corpus_intelligence")


def assemble(idx, request: corpus_contract.AssemblyRequest, *,
             data_root: Path) -> dict:
    """Return a deterministic, locally grounded corpus slice.

    Ranking is performance tier first, then the local engagement value score.
    Optional topic and hook filters are ORed within the selected format.
    Audience questions, self-channel history, and taste anchors enrich the
    result without changing the ranked selection.
    """
    wheres: list[str] = ["y.deleted_at IS NULL"]
    params: list = []
    if request.format:
        wheres.append("y.format = ?")
        params.append(request.format)
    sub_clauses: list[str] = []
    if request.hook_target:
        sub_clauses.append("y.hook_type = ?")
        params.append(request.hook_target)
    if request.topic:
        sub_clauses.append("y.topic LIKE ?")
        params.append(f"%{request.topic}%")
    if sub_clauses:
        wheres.append("(" + " OR ".join(sub_clauses) + ")")

    sql = (
        "SELECT y.video_id, y.slug, y.title, y.channel, y.topic, "
        "y.hook_type, y.format, y.performance_tier, y.length_bucket, "
        "y.yoinked_at "
        "FROM yoinks y "
        "WHERE " + " AND ".join(wheres))
    rows = idx._conn.execute(sql, params).fetchall()

    tier_score = {"over": 3, "average": 2, "under": 1}

    def score(row: dict) -> tuple[int, float]:
        tier = (row.get("performance_tier") or "").strip()
        try:
            signal = idx.engagement_signal(row["video_id"])
            return (
                tier_score.get(tier, 0),
                float(signal.get("value_score") or 0.0),
            )
        except Exception:
            return (tier_score.get(tier, 0), 0.0)

    scored = [(score(dict(row)), dict(row)) for row in rows]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    assembled = [
        row for _score, row in scored[:request.n_examples]
    ]

    audience_questions: list[dict] = []
    for row in assembled:
        try:
            metadata_row = idx._conn.execute(
                "SELECT metadata_json FROM yoinks WHERE video_id=?",
                (row["video_id"],),
            ).fetchone()
            if not metadata_row:
                continue
            metadata = json.loads(metadata_row["metadata_json"] or "{}")
        except (json.JSONDecodeError, TypeError):
            metadata = {}
        for comment in (metadata.get("comments") or [])[:5]:
            text = (comment.get("text") or "").strip()
            if "?" in text and len(text) <= 280:
                audience_questions.append({
                    "video_id": row["video_id"],
                    "question": text,
                    "likes": int(comment.get("likes") or 0),
                })

    self_snapshot = None
    if request.your_channel:
        try:
            import channels
            self_snapshot = channels.self_analysis(
                idx, handle=request.your_channel, top_n=5)
        except Exception as error:
            log.warning(
                "corpus self_analysis skipped: %s", error)
            self_snapshot = {"ok": False, "error": str(error)}

    taste_anchors = None
    try:
        import memory_layer
        taste_payload = memory_layer.read_taste(idx, data_root)
        if taste_payload.get("ok"):
            taste_anchors = taste_payload.get("content")
    except ImportError:
        taste_anchors = None
    except Exception as error:
        log.warning("corpus taste pull skipped: %s", error)

    return {
        "filters": {
            "format": request.format,
            "topic": request.topic,
            "hook_target": request.hook_target,
            "your_channel": request.your_channel,
            "n_examples": request.n_examples,
        },
        "assembled": assembled,
        "audience_questions": audience_questions[:20],
        "self_snapshot": self_snapshot,
        "taste_anchors": taste_anchors,
    }
