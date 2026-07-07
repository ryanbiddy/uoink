"""V-3 taste-aware auto-uoink -- the taste-scoring helper.

Scores a candidate source (a video the user has NOT yet captured, surfaced
by an already-monitored playlist) against the taste model Uoink already
keeps. Nothing here touches the network or an LLM -- it is pure, local,
deterministic arithmetic over data the corpus already holds:

  * taste anchors (memory_layer.get_taste_anchors): the user's explicit
    "this was a 10/10" (best) / "0/10" (worst) videos + admired channels.
  * engagement signals (idx.top_engaged): the videos the user actually
    opens/cites, time-decayed -- resolved to their channels + title words.
  * the corpus itself (idx.search_yoinks_for_memory): channel + topic
    frequency + title vocabulary of everything already saved.
  * the anchor "avoid" note (memory_layer.get_anchor) -- explicit dislikes.

The score is a transparent sum of small, signed contributions, clamped to
[0, 1]. Every contribution carries a human-readable reason so the digest
can show *why* something was auto-uoinked instead of asking the user to
trust a black box. Sparse corpora score low on purpose: with no anchors
and no engagement the profile is "empty" and nothing clears the threshold,
so auto-uoink stays quiet until it has real signal -- honest by design.

This module owns no transport and no storage. server.py builds a profile
once per scan and passes a filter closure into mobile_playlists.
"""

from __future__ import annotations

import logging
import re

log = logging.getLogger("uoink.taste_scoring")

# Default capture bar. A candidate must score >= this to be auto-uoinked.
# 0.5 means "at least one strong signal (admired/best channel) OR a couple
# of weaker corroborating ones". Exposed read-only via /auto-uoink/status.
DEFAULT_THRESHOLD = 0.5

# How many engagement signals / corpus rows to fold into the profile.
_ENGAGEMENT_LIMIT = 40
_CORPUS_LIMIT = 200

# Contribution weights (signed). Kept small + explainable on purpose.
_W_ADMIRED_CHANNEL = 0.55
_W_BEST_CHANNEL = 0.35
_W_ENGAGED_CHANNEL = 0.30    # scaled by that channel's engagement weight
_W_TOP_CORPUS_CHANNEL = 0.20
_W_BEST_KEYWORD = 0.10       # per matched keyword, capped
_W_CORPUS_KEYWORD = 0.06     # per matched keyword, capped
_W_WORST_CHANNEL = -0.60
_W_AVOID_TERM = -0.45        # per matched avoid term

_BEST_KEYWORD_CAP = 0.30
_CORPUS_KEYWORD_CAP = 0.24

# Words too generic to be taste signal.
_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "for",
    "with", "how", "why", "what", "when", "your", "you", "is", "are", "be",
    "this", "that", "it", "at", "by", "from", "as", "my", "we", "i", "do",
    "does", "vs", "into", "out", "up", "new", "best", "top", "video",
    "watch", "full", "part", "ep", "episode", "official", "ft", "feat",
}


def _norm(text) -> str:
    return (str(text or "")).strip().lower()


def _tokenize(text) -> list[str]:
    """Lowercase word tokens >= 3 chars, minus stopwords + pure numbers."""
    words = re.findall(r"[a-z0-9]+", _norm(text))
    return [w for w in words
            if len(w) >= 3 and w not in _STOPWORDS and not w.isdigit()]


def _channel_key(channel) -> str:
    return _norm(channel)


def build_taste_profile(idx) -> dict:
    """Assemble the local taste profile once. Fail-open on any sub-source:
    a missing signal just means that dimension contributes nothing, never
    an exception that kills a scan.

    Returns a dict the scorer + the status endpoint both read:
        {admired_channels, best_channels, worst_channels,
         engaged_channels: {chan: weight 0..1},
         top_corpus_channels: set, best_keywords: set,
         corpus_keywords: set, avoid_terms: [str],
         signal_count: int, has_signal: bool}
    """
    import memory_layer  # local import avoids an import cycle at module load

    admired: set[str] = set()
    best_channels: set[str] = set()
    worst_channels: set[str] = set()
    best_keywords: set[str] = set()

    try:
        anchors = memory_layer.get_taste_anchors(idx)
    except Exception as e:  # pragma: no cover - defensive
        log.warning("taste profile: anchors unavailable: %s", e)
        anchors = {"best": [], "worst": [], "admired_channels": []}

    for name in anchors.get("admired_channels") or []:
        key = _channel_key(name if isinstance(name, str)
                           else (name or {}).get("name"))
        if key:
            admired.add(key)

    def _resolve_anchor(video_item):
        """A best/worst anchor stores {video_id, title}. Resolve the saved
        corpus row (if still present) for its channel; always mine the
        stored title for keywords."""
        vid = ""
        title = ""
        if isinstance(video_item, dict):
            vid = _norm(video_item.get("video_id"))
            title = video_item.get("title") or ""
        chan = ""
        try:
            row = idx.get_yoink(vid) if vid else None
        except Exception:
            row = None
        if row:
            chan = _channel_key(row.get("channel"))
            title = title or row.get("title") or ""
        return chan, title

    for item in anchors.get("best") or []:
        chan, title = _resolve_anchor(item)
        if chan:
            best_channels.add(chan)
        best_keywords.update(_tokenize(title))
    for item in anchors.get("worst") or []:
        chan, _title = _resolve_anchor(item)
        if chan:
            worst_channels.add(chan)

    # Engagement: channels the user actually interacts with, weighted by a
    # normalized time-decayed value_score (0..1 across the returned set).
    engaged_channels: dict[str, float] = {}
    try:
        signals = idx.top_engaged(limit=_ENGAGEMENT_LIMIT)
    except Exception as e:
        log.warning("taste profile: top_engaged unavailable: %s", e)
        signals = []
    max_score = max((s.get("value_score") or 0.0 for s in signals),
                    default=0.0)
    for s in signals:
        vid = _norm(s.get("video_id"))
        if not vid:
            continue
        try:
            row = idx.get_yoink(vid)
        except Exception:
            row = None
        if not row:
            continue
        chan = _channel_key(row.get("channel"))
        if not chan:
            continue
        w = ((s.get("value_score") or 0.0) / max_score) if max_score else 0.0
        engaged_channels[chan] = max(engaged_channels.get(chan, 0.0), w)

    # Corpus shape: channel frequency + title vocabulary of what's saved.
    top_corpus_channels: set[str] = set()
    corpus_keywords: dict[str, int] = {}
    channel_counts: dict[str, int] = {}
    try:
        res = idx.search_yoinks_for_memory(limit=_CORPUS_LIMIT)
        rows = res.get("results") or []
    except Exception as e:
        log.warning("taste profile: corpus scan unavailable: %s", e)
        rows = []
    for row in rows:
        chan = _channel_key(row.get("channel"))
        if chan:
            channel_counts[chan] = channel_counts.get(chan, 0) + 1
        for tok in _tokenize(row.get("title")):
            corpus_keywords[tok] = corpus_keywords.get(tok, 0) + 1
    # A "top corpus channel" is one you've saved from more than once -- a
    # single save is too weak to be taste.
    top_corpus_channels = {c for c, n in channel_counts.items() if n >= 2}
    # Keep title words that recur across the corpus (>= 2) as taste vocab.
    corpus_kw = {w for w, n in corpus_keywords.items() if n >= 2}

    avoid_terms: list[str] = []
    try:
        avoid_body = memory_layer.get_anchor(idx, "avoid")
    except Exception:
        avoid_body = ""
    for line in (avoid_body or "").splitlines():
        term = _norm(line.lstrip("-* ").strip())
        if len(term) >= 3:
            avoid_terms.append(term)

    signal_count = (len(admired) + len(best_channels) + len(worst_channels)
                    + len(engaged_channels) + len(top_corpus_channels))

    return {
        "admired_channels": admired,
        "best_channels": best_channels,
        "worst_channels": worst_channels,
        "engaged_channels": engaged_channels,
        "top_corpus_channels": top_corpus_channels,
        "best_keywords": best_keywords,
        "corpus_keywords": corpus_kw,
        "avoid_terms": avoid_terms,
        "signal_count": signal_count,
        "has_signal": signal_count > 0,
    }


def score_candidate(profile: dict, candidate: dict) -> dict:
    """Score one candidate {title, channel, video_id?} against the profile.

    Returns {score: float 0..1, reasons: [str], matched: {...},
             blocked: bool} -- ``blocked`` marks an explicit worst-channel /
    avoid-term hit so callers can distinguish "no signal" from "actively
    disliked" if they want to.
    """
    chan = _channel_key(candidate.get("channel"))
    title_tokens = set(_tokenize(candidate.get("title")))
    title_norm = _norm(candidate.get("title"))

    score = 0.0
    reasons: list[str] = []
    blocked = False

    if chan and chan in profile.get("admired_channels", set()):
        score += _W_ADMIRED_CHANNEL
        reasons.append(f"from a channel you marked admired ({chan})")
    elif chan and chan in profile.get("best_channels", set()):
        score += _W_BEST_CHANNEL
        reasons.append(f"same channel as a 10/10 anchor ({chan})")

    eng = profile.get("engaged_channels", {})
    if chan and chan in eng:
        contrib = _W_ENGAGED_CHANNEL * eng[chan]
        if contrib > 0:
            score += contrib
            reasons.append(f"you engage with this channel ({chan})")

    if chan and chan in profile.get("top_corpus_channels", set()):
        score += _W_TOP_CORPUS_CHANNEL
        reasons.append(f"you've saved this channel before ({chan})")

    best_kw_hits = title_tokens & profile.get("best_keywords", set())
    if best_kw_hits:
        contrib = min(_BEST_KEYWORD_CAP,
                      _W_BEST_KEYWORD * len(best_kw_hits))
        score += contrib
        reasons.append(
            "title echoes your 10/10 topics ("
            + ", ".join(sorted(best_kw_hits)[:3]) + ")")

    corpus_kw_hits = title_tokens & profile.get("corpus_keywords", set())
    if corpus_kw_hits:
        contrib = min(_CORPUS_KEYWORD_CAP,
                      _W_CORPUS_KEYWORD * len(corpus_kw_hits))
        score += contrib
        reasons.append(
            "matches topics across your corpus ("
            + ", ".join(sorted(corpus_kw_hits)[:3]) + ")")

    if chan and chan in profile.get("worst_channels", set()):
        score += _W_WORST_CHANNEL
        blocked = True
        reasons.append(f"channel you marked 0/10 ({chan})")

    hit_avoid = [t for t in profile.get("avoid_terms", [])
                 if t and t in title_norm]
    if hit_avoid:
        score += _W_AVOID_TERM * len(hit_avoid)
        blocked = True
        reasons.append("matches your avoid list ("
                       + ", ".join(hit_avoid[:3]) + ")")

    score = max(0.0, min(1.0, round(score, 4)))
    if not reasons:
        reasons.append("no taste signal yet -- add anchors or save more")
    return {"score": score, "reasons": reasons,
            "matched": {"channel": chan,
                        "best_keywords": sorted(best_kw_hits),
                        "corpus_keywords": sorted(corpus_kw_hits)},
            "blocked": blocked}


def make_filter(profile: dict, threshold: float = DEFAULT_THRESHOLD):
    """Return a callable(candidate) -> {capture, score, reason, reasons}
    for mobile_playlists.poll_playlist. ``capture`` is True only when the
    score clears the threshold AND the candidate isn't explicitly blocked."""
    def _filter(candidate: dict) -> dict:
        res = score_candidate(profile, candidate)
        capture = (res["score"] >= threshold) and not res["blocked"]
        return {
            "capture": capture,
            "score": res["score"],
            "reason": "auto_uoink:taste",
            "reasons": res["reasons"],
            "blocked": res["blocked"],
        }
    return _filter
