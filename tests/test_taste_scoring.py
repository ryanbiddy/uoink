"""V-3 -- taste_scoring: the local, no-network, no-AI candidate scorer.

Run: python tests/test_taste_scoring.py  (or via pytest tests/)

Red on unpatched main: `import taste_scoring` -> ModuleNotFoundError, so
the whole file fails to import (the module is net-new in this branch).

Green with the fix: build_taste_profile assembles the local taste model
from anchors + engagement + corpus, and score_candidate turns it into a
transparent, clamped [0,1] score with human reasons. Assertions cover:
  * an empty corpus -> empty profile -> nothing clears the threshold
    (auto-uoink stays quiet until it has real signal);
  * an admired channel scores high and captures;
  * a 0/10 (worst) channel is blocked no matter what else matches;
  * an avoid-term title is blocked;
  * make_filter honours the threshold + block.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import index as index_mod  # noqa: E402
import memory_layer  # noqa: E402
import taste_scoring  # noqa: E402


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _seed(idx, root, video_id, title, channel, topic, yoinked_at):
    folder = Path(root) / video_id
    folder.mkdir(parents=True, exist_ok=True)
    idx.upsert_yoink({
        "video_id": video_id, "slug": video_id, "channel": channel,
        "title": title, "topic": topic, "hook_type": "curiosity_gap",
        "yoinked_at": yoinked_at,
        "corpus_path": str(folder / "corpus.md"),
        "sidecar_path": "", "source_type": "youtube",
    }, content=f"{title} transcript body")


def test_taste_scoring():
    tmp = tempfile.TemporaryDirectory()
    idx = index_mod.Index.open(Path(tmp.name) / "index.db")
    try:
        # 1. Empty corpus -> empty profile -> nothing captures.
        prof = taste_scoring.build_taste_profile(idx)
        _assert(prof["has_signal"] is False,
                f"empty corpus must have no signal: {prof}")
        res = taste_scoring.score_candidate(
            prof, {"title": "Some random video", "channel": "Nobody"})
        _assert(res["score"] == 0.0, f"empty profile -> 0 score: {res}")
        filt = taste_scoring.make_filter(prof)
        _assert(filt({"title": "x", "channel": "y"})["capture"] is False,
                "empty profile must never capture")
        print("ok  empty corpus -> no signal, nothing captures")

        # Seed a corpus: two saves from 'Fireship' about AI agents, an
        # engagement event so the channel is 'engaged', plus a taste anchor.
        _seed(idx, tmp.name, "vidaaaaaaaa", "AI agents explained",
              "Fireship", "AI and ML", "2026-01-05T09:00:00")
        _seed(idx, tmp.name, "vidbbbbbbbb", "Building AI agents fast",
              "Fireship", "AI and ML", "2026-02-05T09:00:00")
        _seed(idx, tmp.name, "vidccccdddd", "Cooking pasta",
              "PastaChannel", "Food", "2026-03-05T09:00:00")
        idx.log_engagement("vidaaaaaaaa", "cite", "dashboard",
                           ts_utc="2026-06-01T10:00:00")
        # Mark the food channel's video as 0/10 (worst anchor).
        memory_layer.add_taste_anchor(idx, "vidccccdddd", "worst",
                                       "Cooking pasta")
        # Explicit admired channel + an avoid term.
        anchors = memory_layer.get_taste_anchors(idx)
        anchors["admired_channels"] = ["Fireship"]
        memory_layer._write_taste_anchors(idx, anchors)
        memory_layer.set_anchor(idx, "avoid", "- clickbait\n")

        prof = taste_scoring.build_taste_profile(idx)
        _assert(prof["has_signal"] is True, f"seeded profile has signal: {prof}")
        _assert("fireship" in prof["admired_channels"],
                f"admired channel captured: {prof['admired_channels']}")
        _assert("pastachannel" in prof["worst_channels"],
                f"worst channel captured: {prof['worst_channels']}")
        _assert("clickbait" in prof["avoid_terms"],
                f"avoid term captured: {prof['avoid_terms']}")
        print("ok  seeded profile reflects anchors + engagement + corpus")

        # 2. Admired channel -> high score, captures.
        res = taste_scoring.score_candidate(
            prof, {"title": "New AI agents deep dive", "channel": "Fireship",
                   "video_id": "newone11111"})
        _assert(res["score"] >= taste_scoring.DEFAULT_THRESHOLD,
                f"admired channel must clear threshold: {res}")
        _assert(res["blocked"] is False, f"admired not blocked: {res}")
        _assert(taste_scoring.make_filter(prof)(
            {"title": "New AI agents deep dive", "channel": "Fireship"}
        )["capture"] is True, "admired channel candidate must capture")
        print(f"ok  admired channel captures (score {res['score']})")

        # 3. Worst channel -> blocked, never captures even with keyword hits.
        res = taste_scoring.score_candidate(
            prof, {"title": "AI agents pasta recipe", "channel": "PastaChannel"})
        _assert(res["blocked"] is True, f"worst channel blocked: {res}")
        _assert(taste_scoring.make_filter(prof)(
            {"title": "AI agents pasta recipe", "channel": "PastaChannel"}
        )["capture"] is False, "worst channel must never capture")
        print("ok  0/10 channel is blocked from capture")

        # 4. Avoid-term title -> blocked.
        res = taste_scoring.score_candidate(
            prof, {"title": "This clickbait AI agents video", "channel": "New"})
        _assert(res["blocked"] is True, f"avoid term blocks: {res}")
        print("ok  avoid-term title is blocked")

        # 5. Unknown channel, weak overlap -> below threshold, no capture.
        res = taste_scoring.score_candidate(
            prof, {"title": "Totally unrelated gardening", "channel": "Green"})
        _assert(res["score"] < taste_scoring.DEFAULT_THRESHOLD,
                f"unrelated stays below threshold: {res}")
        print("ok  unrelated candidate stays below the bar")

        print("\nall green")
    finally:
        idx.close()
        tmp.cleanup()


if __name__ == "__main__":
    test_taste_scoring()
