"""Before/after shelf routing on the made-up fixture.

Run (through the isolation wrapper, from the repo root):
  python tests/fixtures/shelves/evaluate.py [--holdout] [--static] [-v]

--static adds the bundled static embedding tier; it needs
UOINK_EMBED_MODEL_DIR set to a folder with the potion-base-8M files.

"Before" is 3.17.0: the topic-word classifier on what each capture path
passes it today (podcasts were always Uncategorized, import folders were
dropped). "After" is the 3.18 router with the fixture library as the
user's existing shelves and the import folder as the hint.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
FALLBACK = "Uncategorized"


def load(holdout=False):
    prefix = "holdout-" if holdout else ""
    library = json.loads((HERE / f"{prefix}library.json").read_text(encoding="utf-8"))
    items = json.loads((HERE / f"{prefix}items.json").read_text(encoding="utf-8"))
    return library, items


def page_markdown(row):
    """What persist_page_yoink hands the classifier for X/Reddit/web saves."""
    if row["kind"] == "x":
        return f"# {row['title']}\n\n**Source:** {row['url']}\n\n## 1/1\n{row['text']}\n"
    return f"# {row['title']}\n\n**Source:** {row['url']}\n\n{row['text']}\n"


def before_metadata(row):
    if row["kind"] == "youtube":
        return {"title": row["title"], "description": row["text"], "tags": row.get("tags") or [],
                "channel": row["author"], "uploader": row["author"], "duration": row.get("duration")}
    if row["kind"] == "podcast":
        return None
    return {"title": row["title"], "description": page_markdown(row)[:2000], "channel": row["author"]}


def after_metadata(row):
    """The same save as the 3.18 capture paths describe it to the router."""
    if row["kind"] == "youtube":
        return before_metadata(row)
    if row["kind"] == "podcast":
        return {"title": row["title"], "description": "", "channel": row["author"],
                "source_type": "podcast", "duration": row.get("duration")}
    meta = {"title": row["title"], "description": page_markdown(row)[:2000], "channel": row["author"],
            "url": row["url"], "source_type": row["source_type"]}
    if row["kind"] == "x":
        media = ([{"type": "video", "duration_millis": int(row["duration"] * 1000)}]
                 if row.get("has_video") and row.get("duration") else
                 [{"type": "video"}] if row.get("has_video") else [])
        meta["metadata"] = {"has_video": bool(row.get("has_video")),
                            "x_capture": {"posts": [{"text": row["text"], "media": media}]}}
    return meta


def library_rows(library):
    rows = []
    for row in library:
        text = row["text"] + (" " + row["transcript"] if row.get("transcript") else "")
        rows.append({"video_id": row["video_id"], "topic": row["topic"], "title": row["title"],
                     "text": text, "author": row["author"], "tags": row.get("tags") or [],
                     "source_type": row["source_type"], "duration_seconds": row.get("duration")})
    return rows


def score(pairs):
    n = len(pairs)
    routed = [(t, g) for t, g in pairs if g != FALLBACK]
    right_routed = sum(1 for t, g in routed if t == g)
    # Recall: of the saves that belong on a real shelf, how many got there.
    belong = [(t, g) for t, g in pairs if t != FALLBACK]
    return {
        "recall": round(sum(1 for t, g in belong if t == g) / len(belong), 3) if belong else 1.0,
        "items": n,
        "on_uncategorized": sum(1 for _, g in pairs if g == FALLBACK),
        "correct": sum(1 for t, g in pairs if t == g),
        "correct_share": round(sum(1 for t, g in pairs if t == g) / n, 3) if n else 0.0,
        "routed": len(routed),
        "wrong_shelf": len(routed) - right_routed,
        "precision": round(right_routed / len(routed), 3) if routed else 1.0,
    }


def group_of(row):
    truth = row["truth"]
    if row.get("folder"):
        return "import folder"
    if truth == FALLBACK:
        return "no shelf fits"
    if truth == "Clips":
        return "short clip"
    if truth in ("Cooking", "Woodworking", "Music", "Memes"):
        return "user shelf"
    return "topic shelf"


def evaluate(before, after, items):
    """``before(row)`` and ``after(row)`` return a shelf name."""
    results = {"before": [], "after": []}
    groups = defaultdict(lambda: {"before": [], "after": []})
    rows = []
    for row in items:
        b, a = before(row), after(row)
        results["before"].append((row["truth"], b))
        results["after"].append((row["truth"], a))
        groups[group_of(row)]["before"].append((row["truth"], b))
        groups[group_of(row)]["after"].append((row["truth"], a))
        rows.append({"video_id": row["video_id"], "truth": row["truth"], "before": b, "after": a,
                     "title": row["title"]})
    no_folder = [(r["truth"], r["after"]) for r, item in zip(rows, items) if not item.get("folder")]
    no_folder_b = [(r["truth"], r["before"]) for r, item in zip(rows, items) if not item.get("folder")]
    return {
        "before": score(results["before"]),
        "after": score(results["after"]),
        "before_without_folders": score(no_folder_b),
        "after_without_folders": score(no_folder),
        "groups": {name: {"before": score(v["before"]), "after": score(v["after"])}
                   for name, v in sorted(groups.items())},
        "rows": rows,
    }


def server_functions(server, library, tier="lexical"):
    """before/after callables wired to the real helper functions. ``tier``
    "static" builds the library the way the helper does when the bundled
    static model is installed (set UOINK_EMBED_MODEL_DIR to its folder)."""
    import shelf_router
    if tier == "static":
        lib = server._shelf_build_library(library_rows(library))
        if lib.tier != "static" or not lib.has_vectors():
            raise SystemExit("static tier asked for, but the embedding model is not available")
    else:
        lib = shelf_router.Library(library_rows(library))

    def before(row):
        meta = before_metadata(row)
        return FALLBACK if meta is None else server._classify_topic(meta)

    def after(row):
        meta = after_metadata(row)
        original = server._shelf_library
        server._shelf_library = lambda: lib
        try:
            return server._route_topic(meta, url=row.get("url"), hint=row.get("folder"),
                                       source_type=row.get("source_type"),
                                       transcript=row.get("transcript") or None)
        finally:
            server._shelf_library = original
    return before, after


def main():
    sys.path.insert(0, str(HERE.parents[2]))
    import server
    library, items = load(holdout="--holdout" in sys.argv)
    tier = "static" if "--static" in sys.argv else "lexical"
    before, after = server_functions(server, library, tier=tier)
    print("tier:", tier)
    report = evaluate(before, after, items)
    for key in ("before", "after", "before_without_folders", "after_without_folders"):
        print(f"{key:24} {report[key]}")
    for name, value in report["groups"].items():
        print(f"  {name:14} before {value['before']}")
        print(f"  {'':14} after  {value['after']}")
    if "-v" in sys.argv:
        for row in report["rows"]:
            if row["after"] != row["truth"]:
                print(f"    MISS truth={row['truth']!r:28} after={row['after']!r:28} {row['title'][:70]}")
    wrong = Counter((r["truth"], r["after"]) for r in report["rows"]
                    if r["after"] not in (r["truth"], FALLBACK))
    print("wrong shelves:", dict(wrong))


if __name__ == "__main__":
    main()
