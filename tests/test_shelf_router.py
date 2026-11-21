"""Shelf routing: local evidence, a wrong shelf is worse than Uncategorized."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

import shelf_router as sr

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "topics.json").read_text(encoding="utf-8"))
SOCIAL_LINKS = ("Follow me on Instagram: https://instagram.example.test/dev\n"
                "Twitter: https://x.example.test/dev\nThreads: https://threads.example.test/dev\n"
                "Join 120k subscribers!")


def lib(rows):
    return sr.Library(rows)


def row(vid, topic, title, text="", author="", **extra):
    return {"video_id": vid, "topic": topic, "title": title, "text": text, "author": author, **extra}


COOKING = [row(f"c{i}", "Cooking", title, text, "@crumb_club")
           for i, (title, text) in enumerate([
               ("Sourdough starter day three", "feeding the sourdough starter, crumb and proofing"),
               ("Cast iron pan sauce", "brown butter pan sauce in the cast iron skillet"),
               ("Weeknight ramen broth", "ramen broth with miso, quick dumplings"),
               ("Knife skills for onions", "knife skills, dice and julienne for the recipe"),
           ])]
MEMES = [row(f"m{i}", "Memes", text, "", "@laugh_track7", duration_seconds=12, source_type="x_thread")
         for i, text in enumerate(["mood", "the audacity", "this is me", "real"])]


def test_hint_wins_over_everything():
    d = sr.route({"title": "LLM fine-tuning guide"}, topics=CFG, hint="Tools to try")
    assert (d.shelf, d.source) == ("Tools to try", "hint")


def test_custom_classifier_pick_is_trusted():
    d = sr.route({"title": "anything"}, topics=CFG, keyword_topic="Video craft")
    assert d.shelf == "Video craft"


def test_creator_link_boilerplate_does_not_shelve():
    meta = {"title": "React hooks tutorial for beginners",
            "description": "Learn useState and useEffect step by step.\n\n" + SOCIAL_LINKS,
            "channel": "Tiny Tutorial Desk", "duration": 1300}
    assert sr.route(meta, topics=CFG).shelf == "Uncategorized"


def test_interview_alone_is_not_a_job_hunt():
    meta = {"title": "Rare 1992 interview with a jazz pianist", "description": "From a cassette tape.",
            "channel": "Archive Tapes", "duration": 1800}
    assert sr.route(meta, topics=CFG).shelf == "Uncategorized"


def test_specific_keyword_in_title_is_confident():
    d = sr.route({"title": "Building AI agents in 30 seconds", "duration": 30}, topics=CFG)
    assert (d.shelf, d.source) == ("AI and ML", "keywords")
    assert "AI agent" in d.reason


def test_short_media_first_save_goes_to_clips():
    d = sr.route({"title": "wait for it", "description": "#shorts #fyp", "duration": 18}, topics=CFG)
    assert (d.shelf, d.source) == ("Clips", "clip")


def test_long_or_wordy_video_is_not_a_clip():
    assert sr.route({"title": "wait for it", "duration": 400}, topics=CFG).shelf == "Uncategorized"
    words = " ".join(["word"] * 40)
    assert sr.route({"title": "x", "description": words, "duration": 30}, topics=CFG).shelf == "Uncategorized"


def test_x_post_text_and_quoted_post_count():
    meta = {"title": "@someone_hq: wow", "description": "# @someone_hq: wow\n\n**Source:** https://x.com/a/status/1",
            "channel": "@someone_hq", "url": "https://x.com/someone_hq/status/1", "source_type": "x_thread",
            "metadata": {"x_capture": {"posts": [{"text": "wow", "quote": {"text": "Our LLM fine-tuning run and a vector database"},
                                                    "media": []}]}}}
    sig = sr.signals_from_metadata(meta)
    assert "LLM" in sig.quoted and sig.body.strip() == "wow"
    assert sr.route(meta, topics=CFG).shelf == "AI and ML"


def test_x_video_length_is_read_from_the_post():
    meta = {"title": "@a_b: lol", "source_type": "x_thread",
            "metadata": {"has_video": True, "x_capture": {"posts": [
                {"text": "lol", "media": [{"type": "video", "video_info": {"duration_millis": 21000}}]}]}}}
    sig = sr.signals_from_metadata(meta)
    assert sig.duration == 21 and sig.is_video and sr.is_short_clip(sig)


def test_existing_shelves_route_thin_saves():
    d = sr.route({"title": "Sourdough crumb shot", "description": "proofing went long"},
                 topics=CFG, library=lib(COOKING))
    assert (d.shelf, d.source) == ("Cooking", "library")


def test_author_habit_beats_the_clips_default():
    meta = {"title": "@laugh_track7: lol", "channel": "@laugh_track7", "duration": 9, "has_video": True}
    assert sr.route(meta, topics=CFG).shelf == "Clips"
    d = sr.route(meta, topics=CFG, library=lib(MEMES))
    assert (d.shelf, d.source) == ("Memes", "author")


def test_conflicting_evidence_stays_put():
    # The author always lands on Memes, but the words point at Cooking:
    # neither wins, so the save is not guessed onto a shelf.
    meta = {"title": "Sourdough starter crumb proofing", "channel": "@laugh_track7"}
    d = sr.route(meta, topics=CFG, library=lib(COOKING + MEMES))
    assert d.shelf == "Uncategorized"


def test_transcript_gives_a_second_chance():
    meta = {"title": "Episode 12", "channel": "Signal Hour"}
    assert sr.route(meta, topics=CFG).shelf == "Uncategorized"
    talk = ("today fine-tuning an LLM on a laptop, then embeddings for a vector database "
            "and an AI agent that books travel")
    assert sr.route(meta, topics=CFG, transcript=talk).shelf == "AI and ML"


def test_embedding_vote_is_used_when_vectors_exist():
    rows = COOKING + [row(f"w{i}", "Woodworking", t, "", "") for i, t in
                      enumerate(["Dovetail jig", "Hand plane tune up", "Walnut slab table"])]
    vectors = {r["video_id"]: ([1.0, 0.0, 0.1] if r["topic"] == "Cooking" else [0.0, 1.0, 0.1]) for r in rows}
    library = sr.Library(rows, vectors=vectors)
    assert library.has_vectors()
    meta = {"title": "Something with no shared words at all"}
    assert sr.route(meta, topics=CFG, library=library).shelf == "Uncategorized"
    d = sr.route(meta, topics=CFG, library=library, vector=[0.98, 0.05, 0.1])
    assert (d.shelf, d.source) == ("Cooking", "embedding")


def test_tidy_proposals_group_and_name_new_shelves():
    candidates = [
        row("u1", "Uncategorized", "Sourdough starter rescue", "proofing again"),
        row("u2", "Uncategorized", "lol", "", "@laugh_track7", duration_seconds=8, source_type="x_thread"),
    ] + [row(f"g{i}", "Uncategorized", f"Tomato seedlings week {i}", "raised beds and tomato seedlings")
         for i in range(5)] + [row("z", "Uncategorized", "A quiet harbor at dawn", "")]
    out = sr.propose(candidates, topics=CFG, library=lib(COOKING + MEMES))
    groups = {g["shelf"]: g for g in out["groups"]}
    assert groups["Cooking"]["new"] is False and groups["Cooking"]["count"] == 1
    assert "Memes" in groups
    new = [g for g in out["groups"] if g["new"]]
    assert any(g["shelf"].lower().startswith("tomato") and g["count"] == 5 for g in new), out["groups"]
    assert out["stays"] == 1 and out["total"] == len(candidates)
    assert all(item["reason"] for g in out["groups"] for item in g["items"])


def test_clean_shelf_name():
    assert sr.clean_shelf_name("  Tools   to try ") == "Tools to try"
    assert sr.clean_shelf_name("") is None
    assert sr.clean_shelf_name("x" * 65) is None
    assert sr.clean_shelf_name('???') is None
    assert sr.clean_shelf_name(5) is None


@pytest.mark.parametrize("bad", ["../evil", "a/b", "a\..\b", "<script>x</script>", "foo.", "...", "..",
                                 "CON", "nul", "com1", "LPT9.txt", 'say "hi"', "a|b", "what?", "a:b",
                                 "x‮y", "xy"])
def test_clean_shelf_name_refuses_unsafe_folder_names(bad):
    assert sr.clean_shelf_name(bad) is None


def test_clean_shelf_name_keeps_real_names_in_one_unicode_form():
    assert sr.clean_shelf_name("  Café   notes ") == "Café notes"
    for good in ("C++ & Rust (2026)", "Console", ".NET", "Recipes, 2026", "🍞 Bread"):
        assert sr.clean_shelf_name(good) == good


def test_folder_names_from_other_apps_are_tidied_not_lost(tmp_path):
    assert sr.folder_shelf_name("AI/ML: notes") == "AI ML notes"
    assert sr.folder_shelf_name("Ideas...") == "Ideas"
    assert sr.folder_shelf_name("///") is None and sr.folder_shelf_name("CON") is None
    assert sr.remember_hints(tmp_path, [("https://x.com/a/status/7", "AI/ML")]) == 1
    assert sr.hint_for(tmp_path, "https://x.com/a/status/7") == "AI ML"


def test_one_shelf_for_every_case_and_unicode_spelling():
    assert sr.canonical_shelf("café", ["Cooking", "Café"]) == "Café"
    assert sr.canonical_shelf("COOKING", ["Cooking"]) == "Cooking"
    assert sr.canonical_shelf("Bread", ["Cooking"]) == "Bread"


def test_the_save_being_routed_does_not_prop_up_its_own_shelf():
    tiny = [row(f"t{i}", "Tiny", "sourdough crumb proofing", "sourdough levain crumb") for i in range(3)]
    library = lib(tiny)
    # Without t0 the shelf has two saves, under the three a shelf needs.
    assert library.nearest(sr._doc_text(tiny[0]), exclude="t0") is None
    assert library.nearest(sr._doc_text(tiny[0]))[0] == "Tiny"


def test_a_vector_of_another_size_never_scores():
    library = sr.Library([row(f"h{i}", "Hearth", "x") for i in range(3)],
                         vectors={f"h{i}": [1.0, 0.0, 0.0] for i in range(3)}, tier="static")
    assert library.embedding_nearest([1.0, 0.0]) is None
    assert library.embedding_nearest([1.0, 0.0, 0.0])[0] == "Hearth"


def test_url_keys_match_across_spellings():
    assert sr.url_key("https://youtu.be/abcdefghijk") == sr.url_key("https://www.youtube.com/watch?v=abcdefghijk")
    assert sr.url_key("https://twitter.com/a/status/123") == sr.url_key("https://x.com/b/status/123?s=20")
    assert sr.url_key("https://old.reddit.com/r/x/comments/AbC/t/") == "reddit:abc"
    assert sr.url_key("not a url at all") is None
    assert sr.url_key("https://example.com/Notes/") == "url:example.com/notes"


def test_hints_round_trip_and_expire(tmp_path, monkeypatch):
    assert sr.remember_hints(tmp_path, [("https://x.com/a/status/9", "Tools to try"), ("https://x.com/a/status/8", "")]) == 1
    assert sr.hint_for(tmp_path, "https://twitter.com/zz/status/9") == "Tools to try"
    assert sr.hint_for(tmp_path, "https://x.com/a/status/8") is None
    later = time.time() + sr.HINT_TTL_SECONDS + 5
    monkeypatch.setattr(sr.time, "time", lambda: later)
    assert sr.hint_for(tmp_path, "https://x.com/a/status/9") is None


def test_sync_files_updates_sidecar_and_note(tmp_path):
    sidecar, note = tmp_path / "a.json", tmp_path / "a.md"
    sidecar.write_text(json.dumps({"title": "t", "topic": "Uncategorized"}), encoding="utf-8")
    note.write_text("# t\n\n**Topic:** Uncategorized\n**Channel:** c\n", encoding="utf-8")
    changed = sr.sync_files(sidecar, note, "Cooking")
    assert len(changed) == 2
    assert sr.files_topic(sidecar, note) == {"sidecar": "Cooking", "corpus": "Cooking"}
    assert "**Channel:** c" in note.read_text(encoding="utf-8")
    # A page sidecar without a topic key is left exactly as it was.
    page = tmp_path / "p.json"
    page.write_text(json.dumps({"title": "p"}), encoding="utf-8")
    assert sr.sync_files(page, tmp_path / "missing.md", "Cooking") == []
    assert json.loads(page.read_text(encoding="utf-8")) == {"title": "p"}


def test_move_log_keeps_batches_for_undo(tmp_path):
    first = sr.record_batch(tmp_path, [{"video_id": "a", "from": None, "to": "Cooking"}], label="Tidy")
    second = sr.record_batch(tmp_path, [{"video_id": "b", "from": "X", "to": "Y"}])
    assert sr.find_batch(tmp_path, None)["id"] == second["id"]
    sr.mark_undone(tmp_path, second["id"])
    assert sr.find_batch(tmp_path, None)["id"] == first["id"]
    assert sr.batch_summary(first)["shelves"] == ["Cooking"]
    for _ in range(sr.MOVE_LOG_BATCHES + 5):
        sr.record_batch(tmp_path, [])
    assert len(sr.batches(tmp_path)) == sr.MOVE_LOG_BATCHES


@pytest.mark.parametrize("value, expected", [(None, True), ("", True), (" uncategorized ", True),
                                             ("Uncategorized", True), ("Clips", False), ("AI", False)])
def test_is_fallback(value, expected):
    assert sr.is_fallback(value) is expected
