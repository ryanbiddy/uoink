"""Seed an isolated Uoink library for the QA smoke suite. No network.

usage: python tests/e2e/qa_seed.py --state seeded|empty|big [--fixture-host HOST]

Runs only inside an isolated profile: UOINK_ISOLATED_PROFILE and
UOINK_ISOLATED_PORT must be set (scripts/qa_smoke.py sets them), and the
port is never 5179. Items go through the app's own save code
(server._index_yoink, page_extractor.persist_page_yoink, notes.persist_note),
so the library looks like real captures. Every title, handle, channel and
URL here is made up.

Prints one JSON line: {"ok": true, "state": ..., "items": N, "expect": {...}}.
The "expect" block tells the browser and API suites what to look for.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

PRODUCTION_PORT = 5179

# The phrase the search flow looks for, and where it sits in its transcript.
SEARCH_PHRASE = "copper kettle benchmark"
SEARCH_ITEM_TITLE = "Why local-first apps feel fast"
SEARCH_SEGMENT = 17
SEARCH_SECONDS = SEARCH_SEGMENT * 12  # 3:24, where the phrase is said
NO_TRANSCRIPT_TITLE = "Office tour with no captions"
MOVE_ITEM_TITLE = "Debugging a flaky integration test, live"
SHELVES = ("Product", "Design", "Engineering", "Marketing", "Research")


def _guard():
    """Refuse to touch anything but an isolated profile on a non-production port."""
    import uoink_install_isolation as iso

    if not (os.environ.get(iso.ENV_PROFILE) and os.environ.get(iso.ENV_PORT)):
        raise SystemExit("qa_seed: refusing to run without UOINK_ISOLATED_PROFILE and UOINK_ISOLATED_PORT")
    binding = iso.apply_from_process(argv=[], environ=os.environ)
    if binding is None or binding.port == PRODUCTION_PORT:
        raise SystemExit("qa_seed: refusing to run outside an isolated profile")
    return binding


def _vid(key: str) -> str:
    """A stable, obviously synthetic 11-character id."""
    return "qa" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:9]


def _segments(lines, *, start=0.0, step=12.0, speakers=None):
    out = []
    for i, text in enumerate(lines):
        seg = {"start": start + i * step, "end": start + i * step + step - 1, "text": text}
        if speakers:
            seg["speaker"] = speakers[i % len(speakers)]
        out.append(seg)
    return out


FILLER = [
    "Thanks for joining. Today we walk through how the team plans a release.",
    "The first step is a short list of what must ship and what can wait.",
    "We keep the list in one shared document so nobody has to ask twice.",
    "Then we pick one person to own the release notes for the week.",
    "Most of the work is cutting scope early instead of late.",
    "When something slips, we say so in the channel the same day.",
    "Testing happens on a real machine, not only in the build server.",
    "We read every support message from the last release before planning the next.",
    "A small team can move fast if the plan fits on one page.",
    "That is the whole process. Questions are welcome at the end.",
]


def _video_lines(topic_word: str, n: int = 24):
    lines = []
    for i in range(n):
        base = FILLER[i % len(FILLER)]
        lines.append(f"{base} This part is about {topic_word}.")
    return lines


class Seeder:
    def __init__(self, server, now: datetime):
        import notes
        import page_extractor

        self.server = server
        self.notes = notes
        self.page_extractor = page_extractor
        self.idx = server._get_index()
        self.root = Path(server.DESKTOP_ROOT)
        self.now = now
        self.items: list[dict] = []

    def when(self, days: float) -> str:
        return (self.now - timedelta(days=days)).replace(microsecond=0).isoformat()

    def _thumb(self, folder: Path, seed: int):
        try:
            from PIL import Image
        except ImportError:
            return
        colors = [(52, 93, 140), (140, 88, 52), (60, 120, 90), (110, 70, 130), (150, 130, 50)]
        im = Image.new("RGB", (320, 180), colors[seed % len(colors)])
        band = Image.new("RGB", (320, 40), (240, 240, 235))
        im.paste(band, (0, 140))
        im.save(folder / "thumbnail.jpg", "JPEG", quality=70)

    def media(self, title, channel, *, kind="video", topic="Uncategorized", lines=None,
              days=1.0, duration=600, url=None, speakers=None, no_transcript=None,
              thumb=True, key=None, hook=None):
        """A YouTube video or a podcast episode, written like a real capture."""
        server = self.server
        key = key or f"{kind}:{title}"
        video_id = _vid(key)
        if kind == "episode":
            url = url or f"https://podcasts.example.com/{video_id}"
        else:
            url = url or f"https://www.youtube.com/watch?v={video_id}"
        transcript = [] if no_transcript else _segments(lines or _video_lines(title.split()[0].lower()),
                                                         speakers=speakers)
        yoinked_at = self.when(days)
        metadata = {"title": title, "channel": channel, "duration": duration,
                    "description": f"A made-up {('episode' if kind == 'episode' else 'video')} for the Uoink smoke suite.",
                    "tags": ["qa", "fixture"]}
        folder = server._video_capture_folder(self.root / server._topic_folder_name(topic), url, metadata)
        folder.mkdir(parents=True, exist_ok=True)
        entries = [(s["start"], s["end"], s["text"]) for s in transcript]
        note = None
        if no_transcript == "disabled":
            note = "No captions were available, and local transcription is turned off."
        elif no_transcript:
            note = "No captions were available, and local transcription failed."
        corpus_md = server._build_yoink_md(metadata, url, entries, [], 30, {}, yoinked_at, topic,
                                           transcript_note=note)
        # Same file names a real capture writes: <slug>.md and <slug>.json.
        corpus = server._corpus_path(folder)
        corpus.write_text(corpus_md, encoding="utf-8")
        health = {"transcript": "missing" if no_transcript else "ok", "screenshots": "skipped",
                  "comments": "skipped", "hook": "ok" if hook else "skipped",
                  "comment_intelligence": "skipped"}
        sidecar = {"schema_version": 2, "video_id": video_id, "url": url, "title": title,
                   "channel": channel, "topic": topic, "yoinked_at": yoinked_at,
                   "duration_seconds": duration, "transcript": transcript,
                   "transcript_source": None if no_transcript else ("asr" if kind == "episode" else "captions"),
                   "hook_type": hook, "hook_type_confidence": 4 if hook else None,
                   "screenshots": [], "comments": [], "comments_status": "disabled", "health": health}
        if no_transcript:
            sidecar["asr_fallback"] = {"status": "disabled" if no_transcript == "disabled" else "failed"}
        if kind == "episode":
            sidecar.update(source_type="episode", platform="podcast", podcast_title=channel,
                           episode_title=title, host=None, audio_url=f"https://podcasts.example.com/{video_id}.mp3")
        sidecar_path = folder / f"{folder.name}.json"
        sidecar_path.write_text(json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8")
        if thumb and kind == "video":
            self._thumb(folder, len(self.items))
        server._index_yoink(folder, sidecar, corpus, sidecar_path)
        self.items.append({"video_id": video_id, "title": title, "kind": kind, "topic": topic,
                           "transcript": not no_transcript})
        return video_id

    def page(self, url, title, markdown, *, author=None, topic=None, days=1.0, source_type="page"):
        # A real page, X or Reddit save always stores a topic: the classifier
        # falls back to "Uncategorized" when nothing matches.
        topic = topic or "Uncategorized"
        result = {"ok": True, "url": url, "title": title, "markdown": markdown,
                  "metadata": {"author": author, "title": title},
                  "extraction_engine": "qa-fixture", "extracted_at": self.when(days)}
        pe = self.page_extractor
        if source_type == "x_thread":
            video_id = pe.persist_page_yoink(self.idx, result, data_root=self.root, topic=topic,
                                             source_type="x_thread", subfolder="X", slug_prefix="x")
        elif source_type == "reddit_thread":
            video_id = pe.persist_page_yoink(self.idx, result, data_root=self.root, topic=topic,
                                             source_type="reddit_thread", subfolder="Reddit", slug_prefix="reddit")
        else:
            video_id = pe.persist_page_yoink(self.idx, result, data_root=self.root, topic=topic)
        if not video_id:
            raise RuntimeError(f"page save failed: {url}")
        self.items.append({"video_id": video_id, "title": title, "kind": source_type,
                           "topic": topic, "transcript": False})
        return video_id

    def note(self, title, text, *, days=1.0):
        # A short note gets no topic, the same as a real save (notes.py skips
        # the classifier under 12 words). It shows as Uncategorized.
        built = self.notes.build_note(text=text, title=title)
        if not built.get("ok"):
            raise RuntimeError(built)
        built["video_id"] = "note_" + _vid("note:" + title)[2:]
        built["yoinked_at"] = self.when(days)
        video_id = self.notes.persist_note(self.idx, built, data_root=self.root, topic_classifier=None)
        if not video_id:
            raise RuntimeError(f"note save failed: {title}")
        self.items.append({"video_id": video_id, "title": title, "kind": "note",
                           "topic": "Uncategorized", "transcript": False})
        return video_id


def seed_seeded(s: Seeder) -> dict:
    lines_search = _video_lines("speed")
    lines_search[SEARCH_SEGMENT] = (f"We ran the {SEARCH_PHRASE} on an old laptop, and the local index "
                        "answered in twelve milliseconds.")
    # 12 YouTube videos.
    video_id = s.media("How we ship a release every week", "Acme Studio", topic="Product", days=0.2,
                       hook="question")
    s.media("Designing a calm dashboard for busy teams", "Example Design Club", topic="Design", days=0.5)
    search_id = s.media(SEARCH_ITEM_TITLE, "Northwind Labs", topic="Engineering", days=0.8,
                        lines=lines_search, hook="demo")
    s.media("A field guide to writing release notes", "Acme Studio", topic="Marketing", days=1.5)
    s.media("Pricing page teardown, part two", "Lumen Collective", topic="Marketing", days=2.5)
    s.media("Everything we learned moving a twelve year old monolith to small services, including "
            "the three migrations that failed, the on-call rotation we rebuilt and why we would do it again",
            "Northwind Labs", topic="Engineering", days=3, duration=5400)
    s.media("Onboarding that respects people's time", "Example Design Club", topic="Design", days=4)
    move_id = s.media(MOVE_ITEM_TITLE, "Northwind Labs", topic="Uncategorized", days=5)
    no_tx_id = s.media(NO_TRANSCRIPT_TITLE, "Acme Studio", topic="Uncategorized", days=6,
                       no_transcript="disabled")
    s.media("Search that finds the moment, not the file", "Lumen Collective", topic="Product", days=7)
    s.media("Small teams, big launches", "Acme Studio", topic="Product", days=8)
    s.media("Behind the scenes at a maker fair", "Lumen Collective", topic="Research", days=9,
            no_transcript="failed")
    # 6 podcast episodes.
    hosts = ["Host A", "Guest B"]
    s.media("Episode 41: Shipping with a tiny team", "The Example Show", kind="episode", days=1.2,
            speakers=hosts, duration=2700)
    podcast_id = s.media("Episode 42: What makes search feel trustworthy", "The Example Show", kind="episode",
                         topic="Research", days=2.2, speakers=hosts, duration=3100)
    s.media("Episode 7: Notes from a quiet launch", "Maker Minutes", kind="episode", topic="Product",
            days=3.2, speakers=hosts)
    s.media("Episode 118: A very long conversation about building developer tools, documentation that "
            "people actually read, and how small companies earn trust before they have a brand",
            "Maker Minutes", kind="episode", days=4.2, speakers=hosts, duration=7200)
    s.media("Episode 8: Designing for keyboard users", "Maker Minutes", kind="episode", topic="Design",
            days=5.2, speakers=hosts)
    s.media("Episode 9: Live from the meetup, audio pending", "Maker Minutes", kind="episode", days=6.2,
            no_transcript="failed")
    # 8 X posts.
    xs = [
        ("qa_maker_one", "Thread: five things we cut from the roadmap", "Product"),
        ("qa_maker_two", "A short post on keyboard shortcuts", "Design"),
        ("qa_maker_one", "Release day checklist, the version we actually use", "Engineering"),
        ("qa_maker_three", "Why we write the docs first", "Marketing"),
        ("qa_maker_two", "Hot take on dashboards that try to do everything", None),
        ("qa_maker_three", "Quick clip: the new search bar", None),
        ("qa_maker_one", "Weekly notes thread", "Research"),
        ("qa_maker_two", "A really long post title that goes on and on about the tradeoffs between shipping "
                         "fast, keeping quality high, and not burning out the team along the way", "Product"),
    ]
    post_ids = []
    for i, (handle, title, topic) in enumerate(xs):
        body = (f"@{handle}: {title}.\n\nPost one: we tried this for a month.\n\n"
                "Post two: here is what changed, and what we would do again.\n\n"
                "Post three: thanks for reading. Replies welcome.")
        post_ids.append(s.page(f"https://x.com/{handle}/status/{1900000000000000000 + i}", title, body,
                               author=f"@{handle}", topic=topic, days=0.3 + i * 0.9, source_type="x_thread"))
    # 5 Reddit threads.
    rs = [
        ("qa_fixture_research", "What tools do you use to save research?", "Research"),
        ("qa_fixture_dev", "Show and tell: my local-first notes app", "Engineering"),
        ("qa_fixture_research", "How do you organize saved videos?", None),
        ("qa_fixture_startups", "Feedback wanted on a pricing page", "Marketing"),
        ("qa_fixture_dev", "Ask: best way to transcribe old talks", None),
    ]
    for i, (sub, title, topic) in enumerate(rs):
        body = (f"# {title}\n\nOriginal post in r/{sub}. Asking for a friend who saves too much.\n\n"
                "## Top comments\n\n- Try a single inbox and a weekly review.\n- Tag by project, not by source.\n"
                "- Keep the original link next to the note.")
        s.page(f"https://www.reddit.com/r/{sub}/comments/qa{i:04d}/fixture_thread_{i}/", title, body,
               author=f"r/{sub}", topic=topic, days=0.6 + i * 1.3, source_type="reddit_thread")
    # 8 web pages.
    ws = [
        ("https://blog.example.com/launch-notes-v2", "Launch notes for version two", "Product"),
        ("https://docs.example.org/plain-writing", "A style guide for plain writing", "Marketing"),
        ("https://research.example.net/search-quality", "Measuring search quality without a lab", "Research"),
        ("https://design.example.com/keyboard-first", "Keyboard first design checklist", "Design"),
        ("https://blog.example.com/postmortem-queue", "Postmortem: the day the queue stopped", "Engineering"),
        ("https://research.example.net/interviews", "Field notes on customer interviews", "Research"),
        ("https://misc.example.com/late-night", "An unfiled page with a very long title about many unrelated "
                                                "things that someone saved late at night and never filed", None),
        ("https://docs.example.org/release-checklist", "Release checklist template", None),
    ]
    page_ids = []
    for i, (url, title, topic) in enumerate(ws):
        body = (f"# {title}\n\n" + ("This is a made-up article for the smoke suite. It has a few paragraphs "
                                    "so the reader has something to show. " * 4) +
                "\n\n## What we learned\n\n- Write it down the same day.\n- Keep the list short.\n"
                "- Share the draft early.\n\n> A quote that someone found useful.\n")
        page_ids.append(s.page(url, title, body, author="Example Author", topic=topic, days=1.1 + i * 1.7))
    # 2 notes.
    s.note("Idea: a weekly digest of new saves", "Send a short weekly digest of new saves.\n\nKeep it to five items "
           "and link each one back to the library.", days=0.1)
    s.note("Reminder: follow up on the search talk", "Ask about the copper pot ranking trick and "
           "whether it holds up on a big library.", days=2.7)
    kinds = {"videos": ("video",), "posts": ("x_thread", "reddit_thread", "page"), "notes": ("note",),
             "podcasts": ("episode",)}
    return {"search_phrase": SEARCH_PHRASE, "search_item_id": search_id, "search_item_title": SEARCH_ITEM_TITLE,
            "search_seconds": SEARCH_SECONDS, "no_transcript_id": no_tx_id,
            "no_transcript_title": NO_TRANSCRIPT_TITLE, "move_item_id": move_id,
            "move_item_title": MOVE_ITEM_TITLE, "shelves": list(SHELVES),
            "kinds_shown": {chip: sum(1 for i in s.items if i["kind"] in names) for chip, names in kinds.items()},
            "video_item": {"id": video_id, "title": "How we ship a release every week",
                           "text": "Thanks for joining", "transcript": True},
            "podcast_item": {"id": podcast_id, "title": "Episode 42: What makes search feel trustworthy",
                             "text": "Thanks for joining", "transcript": True},
            "post_item": {"id": post_ids[0], "title": xs[0][1], "text": "here is what changed",
                          "transcript": False},
            "page_item": {"id": page_ids[2], "title": ws[2][1], "text": "What we learned", "transcript": False}}


def seed_big(s: Seeder, count: int = 1000) -> dict:
    """A 1,000-item library: mostly videos with short transcripts, plus notes."""
    words = ["Shipping", "Scaling", "Hiring", "Pricing", "Search", "Design", "Docs", "Support"]
    shelves = list(SHELVES) + ["Uncategorized"]
    notes_n = count // 7
    videos_n = count - notes_n
    for i in range(videos_n):
        title = f"Episode {i}: {words[i % len(words)]} lessons from team {i % 97}"
        if i % 113 == 0:
            title += " and a much longer subtitle that keeps going so the card has to wrap or truncate cleanly"
        s.media(title, f"Fixture Channel {i % 40}", topic=shelves[i % len(shelves)],
                lines=[f"Short segment {j} about {words[(i + j) % len(words)].lower()}." for j in range(3)],
                days=i * 0.05, thumb=(i % 5 == 0), key=f"big:{i}")
    for i in range(notes_n):
        s.note(f"Note {i}: quick thought", f"Quick thought number {i}. We talk about the launch, the roadmap "
               "and why the plan changed.", days=i * 0.3)
    return {"count": count}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--state", choices=("seeded", "empty", "big"), required=True)
    ap.add_argument("--fixture-host", default="",
                    help="host the extension test saves a page from; added to the allowed sites")
    ap.add_argument("--count", type=int, default=1000, help="items for --state big")
    args = ap.parse_args(argv)
    binding = _guard()

    import server  # noqa: E402  (after the isolation guard)
    import page_extractor

    if Path(server.DATA_ROOT).resolve() != Path(binding.profile).resolve():
        raise SystemExit(f"qa_seed: data root {server.DATA_ROOT} is not the isolated profile")
    if server.PORT == PRODUCTION_PORT:
        raise SystemExit("qa_seed: server resolved the production port")
    # Quiet and local: no balloons and no extra fetches from this profile.
    settings = server._read_settings() or {}
    settings.update(notifications_enabled=False, auto_update_check=False)
    server._write_settings(settings)

    s = Seeder(server, datetime.now())
    expect: dict = {}
    if args.state == "seeded":
        expect = seed_seeded(s)
    elif args.state == "big":
        expect = seed_big(s, args.count)
    if args.fixture_host:
        page_extractor.add_allowed(s.idx, args.fixture_host)
    total = len(s.items)
    kinds: dict[str, int] = {}
    for item in s.items:
        kinds[item["kind"]] = kinds.get(item["kind"], 0) + 1
    expect["total"] = total
    print(json.dumps({"ok": True, "state": args.state, "items": total, "kinds": kinds,
                      "uncategorized": sum(1 for i in s.items if i["topic"] == "Uncategorized"),
                      "profile": str(binding.profile), "expect": expect}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
