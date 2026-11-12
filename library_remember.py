"""Rediscover shelf and idea starters for the Library page.

Pure local logic over light rows from ``Index.remember_rows``. No network, no
AI calls, no file reads. Every pick is seeded by the calendar day, so a
refresh shows the same cards and tomorrow shows new ones.
"""
from __future__ import annotations

import random
from datetime import date, datetime

MIN_LIBRARY_ITEMS = 5
MAX_REDISCOVER = 4
MAX_STARTERS = 3
MAX_ITEMS_PER_STARTER = 3
# Order matters: the rarer reasons get the first slots.
BUCKETS = ("on_this_day", "month", "week", "never")
WEEK_DAYS = (6, 8)
MONTH_DAYS = (27, 35)
NEVER_MIN_AGE_DAYS = 2
_GENERIC_TOPICS = {"", "other", "others", "uncategorized", "unknown", "misc", "general", "none", "n/a"}
_KIND_LABELS = {
    "video": "video", "x_thread": "post", "x_article": "article",
    "reddit_thread": "thread", "page": "page", "episode": "episode",
    "note": "note", "image": "image",
}
_ASKS = (
    ("Compare what they say.", "Compare what they say, then point out where they agree and disagree."),
    ("Find where they disagree.", "Find where they disagree and what each one is missing."),
    ("Pull out what they have in common.", "Pull out what they have in common and one idea worth writing about."),
)


def parse_saved_date(value) -> date | None:
    """Local calendar day of a saved-at stamp. A zoned stamp is converted to
    local time, a zone-less one is already local. None when unreadable."""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        moment = datetime.fromisoformat(text)
        if moment.tzinfo is not None:
            moment = moment.astimezone()
        return moment.date()
    except (ValueError, OverflowError, OSError):
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


def kind_label(row: dict) -> str:
    return _KIND_LABELS.get(str(row.get("source_type") or "").lower(), "item")


def _title(row: dict) -> str:
    text = " ".join(str(row.get("title") or "").split())
    return text or "Untitled uoink"


def _ago(days: int, unit_days: int, unit: str) -> str:
    n = max(1, round(days / unit_days))
    return f"{n} {unit}{'' if n == 1 else 's'} ago"


def bucket_for(row: dict, today: date) -> tuple[str, str] | None:
    """(bucket, reason) for one row, or None when it has no reason to show."""
    saved = parse_saved_date(row.get("yoinked_at"))
    if saved is None or saved > today:
        return None
    age = (today - saved).days
    if saved.year < today.year and (saved.month, saved.day) == (today.month, today.day):
        return "on_this_day", f"Saved on this day in {saved.year}"
    if MONTH_DAYS[0] <= age <= MONTH_DAYS[1]:
        return "month", "Saved 1 month ago"
    if WEEK_DAYS[0] <= age <= WEEK_DAYS[1]:
        return "week", "Saved 1 week ago"
    if (age >= NEVER_MIN_AGE_DAYS and not row.get("last_opened_at")
            and not row.get("touched")):
        return "never", "You haven't opened this yet"
    return None


def _card(row: dict, reason: str, bucket: str) -> dict:
    return {
        "video_id": row.get("video_id"),
        "title": _title(row),
        "kind": kind_label(row),
        "source_type": row.get("source_type"),
        "platform": row.get("platform"),
        "author": row.get("author") or row.get("channel") or "",
        "yoinked_at": row.get("yoinked_at"),
        "reason": reason,
        "bucket": bucket,
    }


def pick_rediscover(rows: list[dict], today: date, *, limit: int = MAX_REDISCOVER,
                    min_items: int = MIN_LIBRARY_ITEMS) -> list[dict]:
    """Up to ``limit`` cards, one from each reason first, then fill. Rows the
    caller already dropped (deleted) never reach here; rows without an id or
    a readable date are skipped."""
    live = [r for r in rows if r.get("video_id")]
    if len(live) < min_items:
        return []
    pools: dict[str, list[tuple[dict, str]]] = {b: [] for b in BUCKETS}
    for row in sorted(live, key=lambda r: str(r["video_id"])):
        hit = bucket_for(row, today)
        if hit:
            pools[hit[0]].append((row, hit[1]))
    for name in BUCKETS:
        random.Random(f"{today.isoformat()}:{name}").shuffle(pools[name])
    picked: list[dict] = []
    while len(picked) < limit and any(pools.values()):
        for name in BUCKETS:
            if pools[name] and len(picked) < limit:
                row, reason = pools[name].pop()
                picked.append(_card(row, reason, name))
    return picked


def _group_topics(rows: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for row in rows:
        topic = " ".join(str(row.get("topic") or "").split())
        if topic.lower() in _GENERIC_TOPICS or not row.get("video_id"):
            continue
        groups.setdefault(topic, []).append(row)
    return groups


def build_copy_prompt(topic: str, items: list[dict], ask: str) -> str:
    lines = [f'I saved these {len(items)} things about "{topic}". {ask}', ""]
    for number, item in enumerate(items, 1):
        lines.append(f"{number}. {item['title'][:140]} ({item['kind']})")
    return "\n".join(lines)


def pick_starters(rows: list[dict], today: date, *, limit: int = MAX_STARTERS,
                  min_items: int = MIN_LIBRARY_ITEMS) -> list[dict]:
    """Up to ``limit`` idea starters. Each is a topic with two or more saved
    items, three at most per starter. An item has one topic, so no item
    appears in two starters."""
    live = [r for r in rows if r.get("video_id")]
    if len(live) < min_items:
        return []
    groups = _group_topics(sorted(live, key=lambda r: str(r["video_id"])))
    names = sorted(t for t, members in groups.items() if len(members) >= 2)
    rng = random.Random(f"{today.isoformat()}:starters")
    rng.shuffle(names)
    names.sort(key=lambda t: 0 if len(groups[t]) >= 3 else 1)  # stable: groups of 3+ first
    starters = []
    for topic in names[:limit]:
        members = list(groups[topic])
        rng.shuffle(members)
        chosen = members[:MAX_ITEMS_PER_STARTER]
        cards = [_card(m, "", "idea") for m in chosen]
        short, ask = _ASKS[rng.randrange(len(_ASKS))]
        total = len(groups[topic])
        starters.append({
            "topic": topic,
            "count": len(cards),
            "saved_count": total,
            "prompt": f"You saved {total} things about {topic}. {short}",
            "copy_prompt": build_copy_prompt(topic, cards, ask),
            "items": cards,
        })
    return starters


def build_remember(rows: list[dict], today: date | None = None) -> dict:
    today = today or date.today()
    return {
        "date": today.isoformat(),
        "library_size": len(rows),
        "rediscover": pick_rediscover(rows, today),
        "starters": pick_starters(rows, today),
    }


def parse_today(value) -> date | None:
    """A YYYY-MM-DD string, or None."""
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


__all__ = ["build_remember", "pick_rediscover", "pick_starters", "bucket_for",
           "parse_today", "MIN_LIBRARY_ITEMS"]
