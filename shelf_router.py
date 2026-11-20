"""Shelf routing: pick a shelf for a save from what is already on this computer.

Everything here is local. A save's own words (title, post text, a quoted post,
tags, the transcript once it exists), its author, the user's folder from an
import, and the shelves the user already has all count as evidence. The
optional local embedding model adds a nearest-shelf vote when it is installed;
the lexical nearest-shelf vote works without it. Nothing calls a remote model.

A wrong shelf is worse than Uncategorized, so a decision needs either one
strong signal or two that agree. Short videos with little text get a default
"Clips" shelf instead of Uncategorized when nothing better is known.

The module is standalone (stdlib, plus numpy only when vectors are passed in)
so tests and the CLI can use it without the helper running.
"""
from __future__ import annotations

import json
import math
import os
import re
import threading
import time
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import parse_qs, urlparse

FALLBACK = "Uncategorized"
CLIPS_SHELF = "Clips"
SHORT_CLIP_SECONDS = 90
THIN_TEXT_WORDS = 25
SHELF_NAME_MAX = 64
MOVE_LOG_BATCHES = 50
HINT_CAP = 5000
HINT_TTL_SECONDS = 45 * 24 * 3600
MAX_MOVES = 5000

# Keyword evidence: a confident topic needs this much weighted evidence and
# this lead over the runner-up. A specific keyword in the title is 2, in the
# body 1; a word with everyday meanings counts half.
KEYWORD_CONFIDENT = 2.0
KEYWORD_MARGIN = 1.0
KEYWORD_WEAK = 1.0
TRANSCRIPT_WEIGHT = 0.5

# Lexical nearest shelf (k nearest saves already on a shelf).
KNN_K = 7
KNN_FLOOR = 0.12
KNN_STRONG_SIM = 0.30
KNN_STRONG_SHARE = 0.70
KNN_TWIN_SIM = 0.50
KNN_TWIN_SHARE = 0.85
KNN_WEAK_SIM = 0.18
KNN_WEAK_SHARE = 0.55
MIN_SHELF_ITEMS = 3

# Author habit: enough of this author's saves sit on one shelf.
AUTHOR_MIN_ITEMS = 2
AUTHOR_STRONG_SHARE = 0.80
AUTHOR_STRONG_ITEMS = 3

# Embedding nearest shelf (cosine against shelf profiles). Each model has
# its own scale. "gemma" is the optional EmbeddingGemma search model; its
# numbers are conservative and were not calibrated on the real model.
# "static" is the bundled potion-base-8M table (local_embed.py), calibrated
# on tests/fixtures/shelves. Below "weak" the save stays where it is.
EMBED_STRONG = 0.55
EMBED_MARGIN = 0.06
EMBED_WEAK = 0.45
EMBED_TIERS = {
    "gemma": {"strong": EMBED_STRONG, "margin": EMBED_MARGIN, "weak": EMBED_WEAK},
    "static": {"strong": 0.55, "margin": 0.04, "weak": 0.45},
}
# A shelf's profile is the mean of its saves plus this much of its name
# (and topic words). A shelf with too few saves is matched on its name
# alone, which must clear a higher bar.
NAME_WEIGHT = 0.5
NAME_ONLY_BONUS = 0.08

# New shelf proposals during Tidy.
CLUSTER_MIN = 4
CLUSTER_MAX_SHELVES = 6

# Words that also have everyday meanings: they count half as keyword
# evidence, so "interview" in a music interview is not a job-hunt signal.
GENERIC_KEYWORDS = frozenset("""
interview promotion focus schedule calendar habit threads shorts reels
transformer notion claude gemini rag dx founder investor creator
engagement viral follower workflow automation resume copilot subscribers
productivity obsidian
""".split())

# Hashtags that say where a post was meant to travel, not what it is about.
_FORMAT_HASHTAGS = re.compile(
    r"(?<!\w)#(?:shorts?|fyp|foryou|foryoupage|reels?|viral|trending|explore|tiktok|"
    r"youtubeshorts|instagood|reelsinstagram|xyzbca)\b", re.IGNORECASE)

_STOPWORDS = frozenset("""
a about above after again against all almost also always am an and any are
around as at away back be because been before being below between both but by
came can cannot could did do does doing done down during each either else
even ever every few for from further get gets getting got had has have having
he her here hers herself him himself his how however i if in into is it its
itself just let lets like likes made make makes many may me might more most
much must my myself never new next no nor not now of off often on once one
only or other our ours ourselves out over own per put quite rather really
same see seen she should since so some something still such than that the
their theirs them themselves then there these they thing things this those
though through to too two under until up upon us use used using very via
want was way we well were what when where which while who whom why will
with within without would yet you your yours yourself yourselves
im ive dont doesnt didnt cant wont isnt arent youre thats theres
today day days week weeks year years time times first last best better good
great big little lot lots kind sort part look looks looking going go goes
know think thought say says said tell told show shows showing watch watched
watching video videos clip clips post posts thread reply replies tweet tweets
channel subscribe subscribed follow followed following link links bio comment
comments share shared click full check checked here's heres www http https
com org net html amp via ft feat official episode ep vs part
minute minutes hour hours second seconds month months
talk talks talked talking thank thanks listen listening listened guys folks
okay yeah yes um uh gonna wanna
learn learned learning lesson lessons mistake mistakes problem problems honest
honestly nobody small win wins note notes version thought thoughts wild
curious spent weekend bookmark bookmarking saving save saved underrated
surprise surprised changed change start starts started end ends ending
somewhere explained explain simply ignoring ignore matter matters tried try
trying stop rethinking worth while long short quick read reading start
zero three four five six seven eight nine ten hundred thousand went gone
come came put
""".split())

# Words that say what form a save takes, not what it is about. They never
# name a new shelf on their own.
_FORMAT_WORDS = frozenset("""
tip tutorial guide review new update top explained intro introduction beginner
step easy quick simple ultimate complete live stream vlog reaction compilation
highlight trailer short reel lesson thread story edit podcast interview
people world life idea stuff free how why what minute hour second
""".split())

_SHORT_TOKENS = frozenset({"ai", "ml", "ux", "ui", "js", "vr", "ar", "3d", "tv", "dj", "uk", "us", "eu"})

_URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_HANDLE_RE = re.compile(r"(?<![\w@])@[A-Za-z0-9_]{1,30}")
_TOKEN_RE = re.compile(r"[a-z0-9]+(?:['+][a-z0-9]+)*")
_BOILERPLATE_RE = re.compile(
    r"\b(?:follow (?:me|us)|subscribe|turn on (?:post )?notifications|hit the bell|"
    r"link in (?:my )?bio|links? below|join (?:my|our|the) (?:newsletter|discord|community|patreon)|"
    r"support (?:me|the channel|this channel)|patreon|ko-fi|buy me a coffee|"
    r"business (?:inquiries|enquiries|email|contact)|for business|sponsored by|"
    r"this video is sponsored|use (?:my )?code|affiliate|merch|my gear|gear i use|"
    r"music by|music:|timestamps|chapters:|#ad\b|paid partnership|[0-9][0-9,.]*\s*[km]?\+? subscribers|"
    r"(?:instagram|twitter|tiktok|threads|facebook|linkedin|discord|website|email|"
    r"contact|youtube|x|snapchat|twitch)\s*[:\-|])",
    re.IGNORECASE)
_TOPIC_LINE_RE = re.compile(r"^\*\*Topic:\*\* .*$", re.MULTILINE)
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_FORBIDDEN_PATH_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def is_fallback(topic: Any, fallback: str = FALLBACK) -> bool:
    """None, empty and any spelling of the fallback all mean 'no shelf yet'."""
    value = str(topic or "").strip().lower()
    return not value or value == str(fallback or FALLBACK).strip().lower()


def clean_shelf_name(value: Any) -> str | None:
    """A shelf name a user can type: 1 to 64 visible characters that also
    make a usable folder name. Returns the cleaned name or None."""
    if not isinstance(value, str):
        return None
    name = " ".join(_CONTROL_RE.sub(" ", value).split())
    if not name or len(name) > SHELF_NAME_MAX:
        return None
    if not _FORBIDDEN_PATH_CHARS.sub("", name).strip().rstrip("."):
        return None
    return name


def _stem(token: str) -> str:
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    return token


def tokens(text: str) -> list[str]:
    """Lower-case content words, URLs and handles removed, plurals folded."""
    if not text:
        return []
    text = _FORMAT_HASHTAGS.sub(" ", _HANDLE_RE.sub(" ", _URL_RE.sub(" ", str(text)))).lower()
    out = []
    for raw in _TOKEN_RE.findall(text):
        raw = raw.replace("'", "")
        if raw.isdigit() and raw not in _SHORT_TOKENS:
            continue
        if len(raw) < 3 and raw not in _SHORT_TOKENS:
            continue
        if raw in _STOPWORDS:
            continue
        out.append(_stem(raw))
    return out


def strip_boilerplate(text: str) -> str:
    """Drop the lines of a description that say where a creator posts or how
    to support them. They describe the creator, not the save."""
    kept = []
    for line in str(text or "").splitlines():
        bare = _URL_RE.sub(" ", line)
        words = bare.split()
        if _URL_RE.search(line) and len(words) <= 3:
            continue
        if _BOILERPLATE_RE.search(line):
            continue
        if words and all(w.startswith(("@", "#")) for w in words):
            continue
        kept.append(line)
    return "\n".join(kept)


def content_word_count(text: str) -> int:
    """Words a reader would call content: no links, handles or hashtags."""
    text = _HANDLE_RE.sub(" ", _URL_RE.sub(" ", str(text or "")))
    return sum(1 for w in text.split() if not w.startswith("#") and re.search(r"[A-Za-z]", w))


def _as_seconds(value: Any) -> float | None:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    return seconds if math.isfinite(seconds) and seconds > 0 else None


def _x_posts(metadata: dict) -> list[dict]:
    capture = metadata.get("x_capture")
    posts = capture.get("posts") if isinstance(capture, dict) else None
    return [p for p in posts or [] if isinstance(p, dict)]


def _x_duration(posts: list[dict]) -> float | None:
    for post in posts:
        for media in post.get("media") or []:
            if not isinstance(media, dict) or media.get("type") not in ("video", "gif"):
                continue
            info = media.get("video_info") if isinstance(media.get("video_info"), dict) else {}
            for value in (media.get("duration"), media.get("duration_seconds"),
                          (_as_seconds(media.get("duration_millis")) or 0) / 1000 or None,
                          (_as_seconds(info.get("duration_millis")) or 0) / 1000 or None):
                seconds = _as_seconds(value)
                if seconds:
                    return seconds
    return None


# ---------------------------------------------------------------------------
# Signals: everything a save says about itself
# ---------------------------------------------------------------------------

@dataclass
class Signals:
    title: str = ""
    body: str = ""
    quoted: str = ""
    tags: list[str] = field(default_factory=list)
    author: str = ""
    transcript: str = ""
    duration: float | None = None
    is_video: bool = False
    source_type: str = ""
    url: str = ""

    def text_words(self) -> int:
        return content_word_count(" ".join([self.title, self.body, self.quoted]))

    def lexical_text(self) -> str:
        # The title counts twice; the transcript is capped so a long talk
        # does not drown its own title.
        transcript = " ".join(self.transcript.split()[:1500])
        return " ".join([self.title, self.title, self.body, self.quoted,
                         " ".join(self.tags), transcript])


def signals_from_metadata(metadata: dict, *, transcript: str | None = None,
                          source_type: str | None = None, url: str | None = None) -> Signals:
    """Read a yt-dlp info dict, a page/X/Reddit classifier dict or a library
    row (with ``text``) into one shape."""
    metadata = metadata if isinstance(metadata, dict) else {}
    inner = metadata.get("metadata") if isinstance(metadata.get("metadata"), dict) else {}
    posts = _x_posts(inner) or _x_posts(metadata)
    body_parts, quoted_parts = [], []
    for post in posts:
        if post.get("text"):
            body_parts.append(str(post["text"]))
        quote = post.get("quote")
        if isinstance(quote, dict) and quote.get("text"):
            quoted_parts.append(str(quote["text"]))
    description = metadata.get("description") or metadata.get("text") or ""
    body = "\n".join(body_parts) if body_parts else str(description)
    if body_parts and description and not str(description).startswith("# "):
        body = body + "\n" + str(description)
    duration = (_as_seconds(metadata.get("duration")) or _as_seconds(metadata.get("duration_seconds"))
                or _x_duration(posts))
    stype = str(source_type or metadata.get("source_type") or "")
    has_video = bool(inner.get("has_video") or metadata.get("has_video"))
    if not has_video and duration:
        # yt-dlp info and video library rows carry a length; podcasts and
        # notes say what they are in source_type.
        has_video = stype in ("", "video", "short", "youtube") or metadata.get("vcodec") not in (None, "none")
    tags = metadata.get("tags") if isinstance(metadata.get("tags"), list) else []
    author = (metadata.get("author") or metadata.get("channel") or metadata.get("uploader")
              or inner.get("author_handle") or inner.get("author_name") or "")
    return Signals(
        title=str(metadata.get("title") or ""),
        body=strip_boilerplate(_strip_capture_scaffold(body)),
        quoted="\n".join(quoted_parts),
        tags=[str(t) for t in tags if isinstance(t, (str, int))][:40],
        author=str(author or ""),
        transcript=str(transcript or metadata.get("transcript") or ""),
        duration=duration,
        is_video=has_video,
        source_type=stype,
        url=str(url or metadata.get("url") or metadata.get("webpage_url") or ""),
    )


def _strip_capture_scaffold(text: str) -> str:
    """Remove the lines Uoink itself writes around an X/Reddit capture: the
    title heading, post numbers, the Source line and italic notes."""
    lines = []
    for line in str(text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith(("# ", "## ", "**Source:**")):
            continue
        if len(stripped) > 1 and stripped[0] == "*" and stripped[-1] == "*" and not stripped.startswith("**"):
            continue
        lines.append(line)
    return "\n".join(lines)


def is_short_clip(sig: Signals) -> bool:
    """A short video that is mostly picture and little text. An X video
    whose length X did not report counts only when its text is very thin."""
    if not sig.is_video:
        return False
    words = sig.text_words()
    if sig.duration is None:
        return sig.source_type == "x_thread" and words < THIN_TEXT_WORDS * 0.6
    return sig.duration <= SHORT_CLIP_SECONDS and words < THIN_TEXT_WORDS


# ---------------------------------------------------------------------------
# Keyword evidence
# ---------------------------------------------------------------------------

def _keyword_pattern(keyword: str):
    words = str(keyword).lower().split()
    if not words:
        return None
    return re.compile(r"(?<![^\W_])" + r"\s+".join(map(re.escape, words)) + r"s?(?![^\W_])")


class Topics:
    """topics.json, compiled once per load."""

    def __init__(self, cfg: dict | None):
        cfg = cfg if isinstance(cfg, dict) else {}
        self.fallback = (str(cfg.get("fallback") or FALLBACK).strip() or FALLBACK)
        self.entries: list[tuple[str, list[tuple[str, Any, bool]]]] = []
        for topic in cfg.get("topics") or []:
            if not isinstance(topic, dict):
                continue
            name = str(topic.get("name") or "").strip()
            keywords = []
            for kw in topic.get("keywords") or []:
                pattern = _keyword_pattern(kw) if kw else None
                first = re.findall(r"[a-z0-9]+", str(kw).lower())
                if pattern is not None and first:
                    keywords.append((str(kw), pattern, str(kw).lower() in GENERIC_KEYWORDS, first[0]))
            if name and keywords:
                self.entries.append((name, keywords))
        self.names = [name for name, _ in self.entries]

    @staticmethod
    def _field(text: str) -> tuple[str, set]:
        text = _FORMAT_HASHTAGS.sub(" ", _HANDLE_RE.sub(" ", _URL_RE.sub(" ", text))).lower()
        chunks = set(re.findall(r"[a-z0-9]+", text))
        chunks |= {c[:-1] for c in chunks if c.endswith("s")}
        return text, chunks

    def scores(self, sig: Signals) -> list[tuple[str, float, list[str]]]:
        fields = [
            (2.0, sig.title),
            (1.0, sig.body),
            (1.0, sig.quoted),
            (1.0, " ".join(sig.tags)),
            (1.0, sig.author),
            (TRANSCRIPT_WEIGHT, " ".join(sig.transcript.split()[:3000])),
        ]
        fields = [(w, *self._field(text)) for w, text in fields if text and text.strip()]
        out = []
        for name, keywords in self.entries:
            score, hits = 0.0, []
            for keyword, pattern, generic, first in keywords:
                # The word set is a cheap precheck before the real pattern.
                weight = max((w for w, text, chunks in fields
                              if first in chunks and pattern.search(text)), default=0.0)
                if weight:
                    score += weight * (0.5 if generic else 1.0)
                    hits.append(keyword)
            if score:
                out.append((name, score, hits))
        out.sort(key=lambda row: (-row[1], self.names.index(row[0])))
        return out


# ---------------------------------------------------------------------------
# The user's library: lexical neighbours, author habits, optional vectors
# ---------------------------------------------------------------------------

def _doc_text(row: dict) -> Signals:
    return signals_from_metadata({
        "title": row.get("title") or "",
        "text": row.get("text") or "",
        "author": row.get("author") or row.get("channel") or "",
        "tags": row.get("tags") or [],
        "duration_seconds": row.get("duration_seconds"),
        "source_type": row.get("source_type") or "",
        "transcript": row.get("transcript") or "",
    })


def _author_key(author: str) -> str:
    return re.sub(r"\s+", " ", str(author or "").strip().lstrip("@").lower())


class Library:
    """What is already shelved, as evidence for new saves.

    ``rows`` are dicts with video_id, topic, title, text (a short excerpt),
    author, tags, source_type, duration_seconds. ``vectors`` optionally maps
    video_id to a unit vector from a local embedding model, ``names`` maps a
    shelf to the vector of its name, and ``tier`` says which model made them
    (a key of EMBED_TIERS)."""

    def __init__(self, rows: Iterable[dict], *, fallback: str = FALLBACK,
                 vectors: dict | None = None, names: dict | None = None,
                 tier: str = "gemma"):
        self.fallback = fallback
        self.docs: dict[str, dict[str, float]] = {}
        self.topic_of: dict[str, str] = {}
        self.shelf_sizes: Counter = Counter()
        self.author_shelves: dict[str, Counter] = defaultdict(Counter)
        self.postings: dict[str, list[str]] = defaultdict(list)
        df: Counter = Counter()
        raw: dict[str, Counter] = {}
        for row in rows:
            vid = row.get("video_id")
            topic = (row.get("topic") or "").strip()
            if not vid or is_fallback(topic, fallback) or topic == CLIPS_SHELF:
                continue
            sig = _doc_text(row)
            self.topic_of[vid] = topic
            self.shelf_sizes[topic] += 1
            if sig.author:
                self.author_shelves[_author_key(sig.author)][topic] += 1
            counts = Counter(tokens(sig.lexical_text()))
            if counts:
                raw[vid] = counts
                df.update(counts.keys())
        self.n = len(raw)
        self.idf = {term: math.log((1 + self.n) / (1 + count)) + 1.0 for term, count in df.items()}
        for vid, counts in raw.items():
            vec = self._weigh(counts)
            if vec:
                self.docs[vid] = vec
                for term in vec:
                    self.postings[term].append(vid)
        self.shelves = sorted(self.shelf_sizes)
        self.tier = tier if tier in EMBED_TIERS else "gemma"
        self._vectors = vectors or {}
        self._names = {k: _unit(list(v)) for k, v in (names or {}).items()
                       if v is not None and not is_fallback(k, fallback) and k != CLIPS_SHELF}
        self._centroids = self._build_centroids() if (self._vectors or self._names) else {}

    def _weigh(self, counts: Counter) -> dict[str, float]:
        vec = {term: (1.0 + math.log(c)) * self.idf.get(term, math.log(1 + self.n) + 1.0)
               for term, c in counts.items()}
        norm = math.sqrt(sum(v * v for v in vec.values()))
        return {t: v / norm for t, v in vec.items()} if norm else {}

    def vector_for(self, sig: Signals) -> dict[str, float]:
        return self._weigh(Counter(tokens(sig.lexical_text())))

    # -- lexical k nearest neighbours ------------------------------------
    def nearest(self, sig: Signals, *, exclude: str | None = None):
        """(shelf, top_sim, share, n_support, neighbours) or None."""
        query = self.vector_for(sig)
        if not query or not self.docs:
            return None
        scores: dict[str, float] = defaultdict(float)
        for term, weight in query.items():
            for vid in self.postings.get(term, ()):
                if vid != exclude:
                    scores[vid] += weight * self.docs[vid][term]
        ranked = sorted(((s, vid) for vid, s in scores.items() if s >= KNN_FLOOR), reverse=True)[:KNN_K]
        if not ranked:
            return None
        votes: dict[str, float] = defaultdict(float)
        support: Counter = Counter()
        best: dict[str, float] = {}
        for sim, vid in ranked:
            shelf = self.topic_of[vid]
            if self.shelf_sizes[shelf] - (1 if vid == exclude else 0) < MIN_SHELF_ITEMS:
                continue
            votes[shelf] += sim
            support[shelf] += 1
            best[shelf] = max(best.get(shelf, 0.0), sim)
        if not votes:
            return None
        shelf = max(votes, key=lambda s: (votes[s], best[s], s))
        share = votes[shelf] / sum(votes.values())
        return shelf, best[shelf], share, support[shelf], [vid for _, vid in ranked]

    def author_habit(self, author: str):
        """(shelf, count, share) when this author's saves mostly sit on one shelf."""
        counts = self.author_shelves.get(_author_key(author))
        if not counts:
            return None
        total = sum(counts.values())
        shelf, count = max(counts.items(), key=lambda kv: (kv[1], kv[0]))
        if total < AUTHOR_MIN_ITEMS or count < AUTHOR_MIN_ITEMS:
            return None
        return shelf, count, count / total

    # -- optional embedding centroids -------------------------------------
    def _build_centroids(self):
        groups: dict[str, list] = defaultdict(list)
        for vid, topic in self.topic_of.items():
            vec = self._vectors.get(vid)
            if vec is not None:
                groups[topic].append(vec)
        out = {}
        for topic in set(groups) | set(self._names):
            vecs = groups.get(topic) or []
            name = self._names.get(topic)
            if len(vecs) >= MIN_SHELF_ITEMS:
                mean = _unit(_mean(vecs))
                if name is not None:
                    mean = _unit([a + NAME_WEIGHT * b for a, b in zip(mean, name)])
                out[topic] = (mean, False)
            elif name is not None:
                out[topic] = (name, True)
        return out

    def embedding_nearest(self, vector):
        """(shelf, score, margin, name_only) against shelf profiles, or None.
        Items on the fallback shelf are never in a profile, so Tidy needs no
        leave-one-out."""
        if vector is None or not self._centroids:
            return None
        query = _unit(list(vector))
        if not any(query):
            return None
        scored = []
        for topic, (centroid, name_only) in self._centroids.items():
            scored.append((sum(a * b for a, b in zip(query, centroid)), topic, name_only))
        scored.sort(reverse=True)
        top, shelf, name_only = scored[0]
        second = scored[1][0] if len(scored) > 1 else -1.0
        return shelf, top, top - second, name_only

    def has_vectors(self) -> bool:
        return bool(self._centroids)

    def thresholds(self) -> dict:
        return EMBED_TIERS[self.tier]


def meaning_text(sig: Signals) -> str:
    """What an embedding model reads for a save: its words, not its author,
    links or handles. The transcript is capped so the title still counts."""
    transcript = " ".join(sig.transcript.split()[:300])
    text = " ".join(part for part in (sig.title, sig.body, sig.quoted, " ".join(sig.tags), transcript)
                    if part)
    return " ".join(_HANDLE_RE.sub(" ", _URL_RE.sub(" ", text)).split())


def row_meaning_text(row: dict) -> str:
    return meaning_text(_doc_text(row))


def shelf_name_texts(shelves: Iterable[str], topics: "Topics | dict | None" = None) -> dict[str, str]:
    """Text for each shelf's name vector: the name, plus its topic words
    when topics.json defines it."""
    topics = topics if isinstance(topics, Topics) else Topics(topics)
    words = {name: [kw for kw, *_ in keywords] for name, keywords in topics.entries}
    out = {}
    for shelf in list(shelves) + topics.names:
        if not shelf or is_fallback(shelf, topics.fallback) or shelf == CLIPS_SHELF or shelf in out:
            continue
        extra = words.get(shelf) or []
        out[shelf] = shelf + (": " + ", ".join(extra[:16]) if extra else "")
    return out


def _mean(vecs):
    try:
        import numpy as np
        return np.asarray(vecs, dtype=float).mean(axis=0).tolist()
    except ImportError:  # pragma: no cover - numpy ships with the app
        return [sum(values) / len(vecs) for values in zip(*vecs)]


def _unit(values):
    values = [float(v) for v in values]
    norm = math.sqrt(sum(v * v for v in values))
    return [v / norm for v in values] if norm > 1e-12 else values


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

@dataclass
class Decision:
    shelf: str
    source: str           # hint | custom | keywords | library | author | embedding | clip | fallback
    reason: str
    confidence: float = 0.0

    def to_dict(self) -> dict:
        return {"shelf": self.shelf, "source": self.source, "reason": self.reason,
                "confidence": round(float(self.confidence), 3)}


def _quote_list(words: list[str], limit: int = 3) -> str:
    shown = [f'"{w}"' for w in words[:limit]]
    return ", ".join(shown)


def route(metadata: dict, *, topics: Topics | dict | None, library: Library | None = None,
          keyword_topic: str | None = None, hint: str | None = None,
          transcript: str | None = None, vector=None, exclude: str | None = None,
          source_type: str | None = None, url: str | None = None,
          allow_clips: bool = True) -> Decision:
    """Pick a shelf, or the fallback when the evidence is thin.

    ``keyword_topic`` is the helper's classic keyword pick. A pick that is
    not one of the configured topics comes from a custom classifier and is
    trusted as is. ``vector`` is this save's embedding when the local model
    has one."""
    topics = topics if isinstance(topics, Topics) else Topics(topics)
    fallback = topics.fallback
    hint_name = clean_shelf_name(hint) if hint else None
    if hint_name:
        return Decision(hint_name, "hint", f'From your folder "{hint_name}"', 1.0)
    if (keyword_topic and not is_fallback(keyword_topic, fallback)
            and keyword_topic not in topics.names):
        return Decision(keyword_topic, "custom", "Matched your topic rules", 1.0)
    sig = metadata if isinstance(metadata, Signals) else signals_from_metadata(
        metadata, transcript=transcript, source_type=source_type, url=url)

    scored = topics.scores(sig)
    top = scored[0] if scored else None
    second = scored[1][1] if len(scored) > 1 else 0.0
    if top and top[1] >= KEYWORD_CONFIDENT and top[1] - second >= KEYWORD_MARGIN:
        return Decision(top[0], "keywords", "Mentions " + _quote_list(top[2]),
                        min(1.0, top[1] / 4))

    votes: list[tuple[str, str, str, bool]] = []   # (shelf, source, reason, strong)
    # Weak keyword evidence counts as a vote only when at least one hit is a
    # specific word: "interview" alone is too easy to misread.
    if (top and top[1] >= KEYWORD_WEAK and top[1] - second >= 0.5
            and any(hit.lower() not in GENERIC_KEYWORDS for hit in top[2])):
        votes.append((top[0], "keywords", "Mentions " + _quote_list(top[2]), False))
    if library is not None:
        near = library.nearest(sig, exclude=exclude)
        if near:
            shelf, sim, share, support, _ = near
            # Several close neighbours on one shelf, or one near twin.
            strong = ((sim >= KNN_STRONG_SIM and share >= KNN_STRONG_SHARE and support >= 2)
                      or (sim >= KNN_TWIN_SIM and share >= KNN_TWIN_SHARE))
            if strong or (sim >= KNN_WEAK_SIM and share >= KNN_WEAK_SHARE):
                noun = "save" if support == 1 else "saves"
                votes.append((shelf, "library", f"Like {support} {noun} already on this shelf", strong))
        if sig.author:
            habit = library.author_habit(sig.author)
            if habit and habit[2] >= AUTHOR_STRONG_SHARE:
                shelf, count, share = habit
                strong = count >= AUTHOR_STRONG_ITEMS
                votes.append((shelf, "author", f"You keep {count} saves from {sig.author} here", strong))
        if vector is not None:
            near = library.embedding_nearest(vector)
            if near:
                shelf, score, margin, name_only = near
                bar = library.thresholds()
                lift = NAME_ONLY_BONUS if name_only else 0.0
                if score >= bar["weak"] + lift and margin >= bar["margin"] / 2:
                    strong = score >= bar["strong"] + lift and margin >= bar["margin"]
                    votes.append((shelf, "embedding", "Close in meaning to this shelf", strong))

    decided = _settle(votes)
    if decided is not None:
        return decided
    if allow_clips and is_short_clip(sig):
        return Decision(CLIPS_SHELF, "clip", "Short video with little text", 0.5)
    return Decision(fallback, "fallback", "Not enough to go on yet", 0.0)


def _settle(votes: list[tuple[str, str, str, bool]]) -> Decision | None:
    """Turn the softer votes into a decision, or None to stay put.

    Two different kinds of evidence that agree win. One strong vote wins
    when nothing points elsewhere. A strong vote also beats one weak vote
    for another shelf. Anything murkier stays where it is."""
    if not votes:
        return None
    tally: dict[str, list] = defaultdict(list)
    for vote in votes:
        tally[vote[0]].append(vote)
    agreed = [shelf for shelf, vs in tally.items() if len({v[1] for v in vs}) >= 2]
    if len(agreed) == 1:
        shelf = agreed[0]
        others = [v for v in votes if v[0] != shelf]
        if not any(v[3] for v in others):
            reasons = [v[2] for v in tally[shelf]]
            return Decision(shelf, tally[shelf][0][1], ". ".join(reasons[:2]), 0.8)
    if len(tally) != 1:
        return None
    strong = [v for v in votes if v[3]]
    if not strong:
        return None
    vote = strong[0]
    return Decision(vote[0], vote[1], vote[2], 0.7)


# ---------------------------------------------------------------------------
# Tidy: proposals for what already sits on the fallback shelf
# ---------------------------------------------------------------------------

def _phrases(sig: Signals) -> tuple[Counter, dict[str, Counter]]:
    """Single words and two-word phrases, with how each was written."""
    surface: dict[str, Counter] = defaultdict(Counter)
    found: Counter = Counter()
    text = _HANDLE_RE.sub(" ", _URL_RE.sub(" ", " ".join([sig.title, sig.title, sig.body, " ".join(sig.tags)])))
    for line in re.split(r"[\n.!?;:|]+", text):
        words = []
        for raw in re.findall(r"[A-Za-z0-9]+(?:'[A-Za-z]+)?", line):
            low = raw.lower().replace("'", "")
            if low in _STOPWORDS or (len(low) < 3 and low not in _SHORT_TOKENS) or low.isdigit():
                words.append(None)
                continue
            key = _stem(low)
            words.append((key, raw))
        for i, item in enumerate(words):
            if item is None:
                continue
            found[item[0]] += 1
            surface[item[0]][item[1].lower()] += 1
            nxt = words[i + 1] if i + 1 < len(words) else None
            if nxt is not None:
                key = item[0] + " " + nxt[0]
                found[key] += 1
                surface[key][(item[1] + " " + nxt[1]).lower()] += 1
    return found, surface


def _sentence_case(text: str) -> str:
    text = text.strip()
    if not text:
        return text
    words = text.split()
    out = []
    for i, word in enumerate(words):
        if word.lower() in _SHORT_TOKENS and len(word) <= 2:
            out.append(word.upper())
        elif i == 0:
            out.append(word[:1].upper() + word[1:])
        else:
            out.append(word)
    return " ".join(out)


def new_shelf_clusters(items: list[tuple[str, Signals]], existing: Iterable[str]) -> list[dict]:
    """Group leftover saves that clearly share a subject, named from their
    own words. Returns [{shelf, items: [video_id], term}] biggest first."""
    taken_names = {str(name).strip().lower() for name in existing}
    taken_terms = {t for name in taken_names for t in tokens(name)}
    per_item: dict[str, set[str]] = {}
    df: Counter = Counter()
    surfaces: dict[str, Counter] = defaultdict(Counter)
    for vid, sig in items:
        found, surface = _phrases(sig)
        title_terms, _ = _phrases(Signals(title=sig.title, tags=sig.tags))
        strong = {term for term, count in found.items()
                  if term in title_terms or count >= 3}
        strong = {t for t in strong if not (set(t.split()) & taken_terms)
                  and not (" " not in t and (t in _FORMAT_WORDS or t.rstrip("s") in _FORMAT_WORDS))}
        per_item[vid] = strong
        df.update(strong)
        for term in strong:
            surfaces[term].update(surface[term])
    n = len(items)
    if n < CLUSTER_MIN:
        return []
    ceiling = max(CLUSTER_MIN, int(n * 0.5)) if n >= 3 * CLUSTER_MIN else n
    candidates = sorted(
        ((count * (1.5 if " " in term else 1.0), term) for term, count in df.items()
         if CLUSTER_MIN <= count <= ceiling),
        reverse=True)
    assigned: set[str] = set()
    out = []
    for _, term in candidates:
        members = [vid for vid, terms in per_item.items() if term in terms and vid not in assigned]
        if len(members) < CLUSTER_MIN:
            continue
        name = _sentence_case(surfaces[term].most_common(1)[0][0]) if surfaces[term] else _sentence_case(term)
        name = clean_shelf_name(name)
        if not name or name.lower() in taken_names or name.lower() == CLIPS_SHELF.lower():
            continue
        taken_names.add(name.lower())
        assigned.update(members)
        out.append({"shelf": name, "items": members, "term": term})
        if len(out) >= CLUSTER_MAX_SHELVES:
            break
    return out


def propose(candidates: list[dict], *, topics: Topics | dict | None, library: Library,
            vectors: dict | None = None, existing_shelves: Iterable[str] = ()) -> dict:
    """Proposals for saves on the fallback shelf.

    ``candidates`` are library rows (same shape as Library rows). Returns
    {groups: [{shelf, new, count, items: [{video_id, title, reason, source}]}],
     stays, total}. Nothing is moved here."""
    topics = topics if isinstance(topics, Topics) else Topics(topics)
    known = {s.lower(): s for s in list(library.shelves) + list(existing_shelves) + topics.names}
    groups: dict[str, dict] = {}
    leftovers: list[tuple[str, Signals]] = []
    titles: dict[str, dict] = {}
    for row in candidates:
        vid = row.get("video_id")
        if not vid:
            continue
        sig = _doc_text(row)
        titles[vid] = row
        decision = route(sig, topics=topics, library=library,
                         vector=(vectors or {}).get(vid), exclude=vid, allow_clips=True)
        if decision.source == "fallback":
            leftovers.append((vid, sig))
            continue
        shelf = known.get(decision.shelf.lower(), decision.shelf)
        group = groups.setdefault(shelf, {"shelf": shelf, "new": shelf.lower() not in known,
                                          "items": []})
        group["items"].append(_proposal_item(row, decision.reason, decision.source))
    for cluster in new_shelf_clusters(leftovers, known.keys()):
        members = set(cluster["items"])
        group = groups.setdefault(cluster["shelf"], {"shelf": cluster["shelf"], "new": True, "items": []})
        noun = "saves" if len(members) != 1 else "save"
        for vid in cluster["items"]:
            group["items"].append(_proposal_item(
                titles[vid], f'{len(members)} {noun} share "{cluster["shelf"].lower()}"', "cluster"))
        leftovers = [(vid, sig) for vid, sig in leftovers if vid not in members]
    out = sorted(groups.values(), key=lambda g: (g["new"], -len(g["items"]), g["shelf"].lower()))
    for group in out:
        group["count"] = len(group["items"])
    return {"groups": out, "stays": len(leftovers), "total": len(candidates)}


def _proposal_item(row: dict, reason: str, source: str) -> dict:
    return {"video_id": row.get("video_id"), "title": row.get("title") or "Untitled",
            "author": row.get("author") or "", "platform": row.get("platform") or "",
            "source_type": row.get("source_type") or "", "reason": reason, "source": source}


# ---------------------------------------------------------------------------
# Files: keep the save's own files in step with its shelf
# ---------------------------------------------------------------------------

def sync_files(sidecar_path: Any, corpus_path: Any, shelf: str) -> list[str]:
    """Write the new shelf into the save's sidecar (when it records one) and
    the corpus note's Topic line (when it has one). Folders stay where they
    are. Returns the files changed."""
    changed = []
    from uoink_core.storage import _atomic_write_text
    if sidecar_path:
        path = Path(sidecar_path)
        try:
            data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
        except (OSError, ValueError):
            data = None
        if isinstance(data, dict) and "topic" in data and data.get("topic") != shelf:
            data["topic"] = shelf
            _atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False))
            changed.append(str(path))
    if corpus_path:
        path = Path(corpus_path)
        try:
            text = path.read_text(encoding="utf-8") if path.is_file() else None
        except OSError:
            text = None
        if text is not None:
            line = f"**Topic:** {shelf}"
            match = _TOPIC_LINE_RE.search(text)
            if match and match.group(0) != line:
                _atomic_write_text(path, text[:match.start()] + line + text[match.end():])
                changed.append(str(path))
    return changed


def files_topic(sidecar_path: Any, corpus_path: Any) -> dict:
    """What the save's own files say its shelf is (for checks and tests)."""
    out = {"sidecar": None, "corpus": None}
    try:
        data = json.loads(Path(sidecar_path).read_text(encoding="utf-8"))
        out["sidecar"] = data.get("topic") if isinstance(data, dict) else None
    except (OSError, ValueError, TypeError):
        pass
    try:
        match = _TOPIC_LINE_RE.search(Path(corpus_path).read_text(encoding="utf-8"))
        out["corpus"] = match.group(0)[len("**Topic:** "):] if match else None
    except (OSError, TypeError):
        pass
    return out


# ---------------------------------------------------------------------------
# Move log (undo) and folder hints, both small JSON files in the data folder
# ---------------------------------------------------------------------------

_lock = threading.RLock()


def _read_json(path: Path, default):
    try:
        if path.is_symlink():
            return default
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, type(default)) else default
    except (OSError, ValueError):
        return default


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def move_log_path(data_root: Path) -> Path:
    return Path(data_root) / "shelf-moves.json"


def record_batch(data_root: Path, moves: list[dict], *, label: str = "",
                 append_to: str | None = None) -> dict | None:
    """Remember one batch of moves so it can be undone. ``moves`` are
    {video_id, from, to}. ``append_to`` adds them to the newest batch when
    it has that id and is not undone (a big move sent in several requests
    stays one undo); otherwise None comes back and nothing is written."""
    with _lock:
        path = move_log_path(data_root)
        data = _read_json(path, {})
        batches = [b for b in data.get("batches") or [] if isinstance(b, dict)]
        if append_to:
            batch = batches[-1] if batches else None
            if (not batch or batch.get("id") != append_to or batch.get("undone")
                    or len(batch.get("moves") or []) + len(moves) > MAX_MOVES):
                return None
            batch["moves"] = list(batch.get("moves") or []) + list(moves)
        else:
            batch = {"id": "mv_" + uuid.uuid4().hex[:12], "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                     "label": str(label or "")[:80], "moves": moves, "undone": False}
            batches.append(batch)
        _write_json(path, {"version": 1, "batches": batches[-MOVE_LOG_BATCHES:]})
    return batch


def batches(data_root: Path) -> list[dict]:
    data = _read_json(move_log_path(data_root), {})
    return [b for b in data.get("batches") or [] if isinstance(b, dict)]


def find_batch(data_root: Path, batch_id: str | None) -> dict | None:
    """A batch by id, or the newest one not undone yet."""
    items = batches(data_root)
    if batch_id:
        return next((b for b in items if b.get("id") == batch_id), None)
    return next((b for b in reversed(items) if not b.get("undone")), None)


def mark_undone(data_root: Path, batch_id: str) -> None:
    with _lock:
        path = move_log_path(data_root)
        data = _read_json(path, {})
        for batch in data.get("batches") or []:
            if isinstance(batch, dict) and batch.get("id") == batch_id:
                batch["undone"] = True
        _write_json(path, data)


def batch_summary(batch: dict | None) -> dict | None:
    if not batch:
        return None
    moves = batch.get("moves") or []
    shelves = sorted({m.get("to") for m in moves if m.get("to")})
    return {"id": batch.get("id"), "at": batch.get("at"), "label": batch.get("label") or "",
            "count": len(moves), "shelves": shelves, "undone": bool(batch.get("undone"))}


def url_key(url: Any) -> str | None:
    """A stable identity for a saved URL, so a hint matches the capture even
    when the URL is written differently (handle, www, tracking query)."""
    if not isinstance(url, str) or not url.strip():
        return None
    raw = url.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", raw):
        return "yt:" + raw
    try:
        parsed = urlparse(raw if "://" in raw else "https://" + raw)
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host.startswith("m."):
        host = host[2:]
    path = parsed.path or "/"
    if host in ("youtube.com", "music.youtube.com", "youtube-nocookie.com"):
        vid = (parse_qs(parsed.query).get("v") or [None])[0]
        match = re.match(r"/(?:shorts|embed|live|v)/([A-Za-z0-9_-]{11})", path)
        vid = vid or (match.group(1) if match else None)
        if vid and re.fullmatch(r"[A-Za-z0-9_-]{11}", vid):
            return "yt:" + vid
    if host == "youtu.be":
        vid = path.strip("/").split("/")[0]
        if re.fullmatch(r"[A-Za-z0-9_-]{11}", vid):
            return "yt:" + vid
    if host in ("x.com", "twitter.com", "mobile.twitter.com", "fixupx.com", "vxtwitter.com"):
        match = re.search(r"/status(?:es)?/([0-9]+)", path)
        if match:
            return "x:" + match.group(1)
    if host.endswith("reddit.com"):
        match = re.search(r"/comments/([A-Za-z0-9]+)", path)
        if match:
            return "reddit:" + match.group(1).lower()
    if not host:
        return None
    return "url:" + host + path.rstrip("/").lower()


def hints_path(data_root: Path) -> Path:
    return Path(data_root) / "shelf-hints.json"


def remember_hints(data_root: Path, pairs: Iterable[tuple[str, str]]) -> int:
    """Remember the shelf a not-yet-captured URL should land on."""
    now = time.time()
    clean = []
    for url, shelf in pairs:
        key, name = url_key(url), clean_shelf_name(shelf)
        if key and name:
            clean.append((key, name))
    if not clean:
        return 0
    with _lock:
        path = hints_path(data_root)
        data = _read_json(path, {})
        hints = {k: v for k, v in (data.get("hints") or {}).items()
                 if isinstance(v, dict) and now - float(v.get("at") or 0) < HINT_TTL_SECONDS}
        for key, name in clean:
            hints[key] = {"shelf": name, "at": now}
        if len(hints) > HINT_CAP:
            hints = dict(sorted(hints.items(), key=lambda kv: kv[1].get("at") or 0)[-HINT_CAP:])
        _write_json(path, {"version": 1, "hints": hints})
    return len(clean)


def hint_for(data_root: Path, *urls: Any) -> str | None:
    """The remembered shelf for any of these URLs, if one is still fresh."""
    keys = [k for k in (url_key(u) for u in urls) if k]
    if not keys:
        return None
    path = hints_path(data_root)
    if not path.exists():
        return None
    hints = _read_json(path, {}).get("hints") or {}
    now = time.time()
    for key in keys:
        value = hints.get(key)
        if isinstance(value, dict) and now - float(value.get("at") or 0) < HINT_TTL_SECONDS:
            name = clean_shelf_name(value.get("shelf"))
            if name:
                return name
    return None
