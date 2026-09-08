"""Tests for Card Contract v2 in library_cards.py (Phase 2 Stage 4, run AP).

Validates every specification rule from PHASE2-STAGE4-SKETCH-2026-09-07.md and
PHASE2-STAGE4-BRIEF-2026-09-07.md:
1. SELECTION_VERSION == "spread-longest-v2"
2. Full profile untouched in behaviour except version string
3. Bounded librarian limits: 6 excerpts max, 240 chars, 8192 byte budget
4. Prose reservation for prose-eligible sources (page, x_article, x_thread, reddit_thread, note)
5. Video-origin prose not promoted when clips exist
6. Deterministic timed selection (up to 5) with disclosed displacement
7. Unchanged excerpt_id derivation for identical source excerpts
8. Unchanged source_revision inputs between old and new builder rules
9. All 548 card hashes change due to global selection_version bump
10. Byte accounting: drop hints before evidence, protect reserved prose slot
11. Freeze failure signal (CardFreezeError) when mixed evidence cannot fit
12. Deterministic diff helper: metadata-only, added prose, displaced timed excerpt, truncation change, other
13. Replay over all 548 archived stage 1 packet cards (no database required)
"""
from __future__ import annotations

import copy
import json
from collections import Counter
from pathlib import Path

import pytest

import library_cards as cards

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_RECEIPTS = ROOT / "docs/library/proof/run-2026-09-05/receipts.json"
HOLDOUT_V3 = ROOT / "docs/library/proof/holdout-v3-2026-09-07.json"


def synthetic_item(**kwargs) -> dict:
    defaults = {
        "video_id": "test_video_123",
        "slug": "test_video_slug",
        "title": "Synthetic Test Item Title",
        "channel": "Test Channel",
        "platform": "x",
        "source_type": "x_thread",
        "topic": "Testing",
        "yoinked_at": "2026-09-07T00:00:00",
        "metadata_json": json.dumps({"url": "https://x.com/example/status/123"}),
    }
    defaults.update(kwargs)
    return defaults


def synthetic_clips(count: int = 10, start_step: int = 60) -> list[dict]:
    return [
        {
            "seq": i,
            "start": float(i * start_step),
            "end": float(i * start_step + 45),
            "text": f"Timed clip {i}: " + ("admissible evidence text " * (10 + i)),
            "source_deep_link": f"https://x.com/example/status/123#t={i * start_step}",
        }
        for i in range(count)
    ]


# ---------------------------------------------------------------------------
# 1. Version and Constants
# ---------------------------------------------------------------------------

def test_selection_version_and_eligible_sources():
    assert cards.SELECTION_VERSION == "spread-longest-v2"
    assert cards.PROSE_ELIGIBLE_SOURCES == frozenset({
        "page", "x_article", "x_thread", "reddit_thread", "note"
    })
    assert issubclass(cards.CardFreezeError, ValueError)


# ---------------------------------------------------------------------------
# 2. Full profile untouched in behaviour except version string
# ---------------------------------------------------------------------------

def test_full_profile_untouched_in_behaviour():
    item = synthetic_item(source_type="x_thread")
    clips = synthetic_clips(15)
    corpus = "# Opening Header\nThis is eligible opening prose."

    full = cards.build_card(item, clips, corpus_text=corpus, profile="full")

    assert full["selection_version"] == "spread-longest-v2"
    assert full["profile"] == "full"
    # Full retains 10 untruncated timed clips by default
    assert len(full["clips"]) == 10
    assert len(full["excerpts"]) == 10
    assert all(e["evidence_kind"] == "timed_clip" for e in full["excerpts"])
    # Opening prose was not added as an excerpt because clips exist
    assert not any(e["evidence_kind"] == "text_only" for e in full["excerpts"])
    # Summary hint and hint still capture opening prose
    assert full["summary_hint"] == "This is eligible opening prose."
    assert full["hint"]["kind"] == "opening_prose"


# ---------------------------------------------------------------------------
# 3. Source revision inputs unchanged
# ---------------------------------------------------------------------------

def test_source_revision_inputs_unchanged():
    item = synthetic_item(source_type="x_thread")
    clips = synthetic_clips(6)
    corpus = "Identical opening prose across builder versions."

    card_v2 = cards.build_card(item, clips, corpus_text=corpus, profile="librarian")

    # Manually compute old v1 revision using identical inputs
    meta = json.loads(item["metadata_json"])
    url = cards._web_link(meta.get("url"))
    prose = cards.opening_prose(corpus)
    item_cols = {k: item[k] for k in (
        "video_id", "slug", "title", "channel", "platform", "source_type",
        "topic", "yoinked_at"
    )}
    from clips import timing_kind
    evidence = [{"start": c.get("start"), "end": c.get("end"),
                 "text": c.get("text") or "", "deep_link": cards._web_link(c.get("source_deep_link")),
                 "seq": c.get("seq", i), "timing": timing_kind(c)}
                for i, c in enumerate(clips) if cards._string(c.get("text"))]
    evidence.sort(key=lambda c: (c["seq"], c["start"] or 0))
    expected_revision = cards._hash({"item": item_cols, "url": url, "evidence": evidence, "opening_prose": prose})

    assert card_v2["source_revision"] == expected_revision


# ---------------------------------------------------------------------------
# 4. Reserved slot and prose eligibility for librarian profile
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("source_type", ["page", "x_article", "x_thread", "reddit_thread", "note"])
def test_prose_eligible_sources_emit_prose_excerpt_with_clips(source_type):
    item = synthetic_item(source_type=source_type)
    clips = synthetic_clips(8)
    corpus = "# Header\nVerbatim original prose that must become evidence."

    card = cards.build_card(item, clips, corpus_text=corpus, profile="librarian")

    assert len(card["excerpts"]) == 6  # 5 timed clips + 1 prose
    assert len(card["clips"]) == 5
    assert card["evidence_kind"] == "timed_clip"

    # Verify timed excerpts
    timed = [e for e in card["excerpts"] if e["evidence_kind"] == "timed_clip"]
    assert len(timed) == 5
    assert all(e["start"] is not None for e in timed)

    # Verify reserved prose excerpt at the end
    prose_exc = card["excerpts"][-1]
    assert prose_exc["evidence_kind"] == "text_only"
    assert prose_exc["start"] is None
    assert prose_exc["end"] is None
    assert prose_exc["timing"] == "not_timed"
    assert prose_exc["text"] == "Verbatim original prose that must become evidence."
    assert prose_exc["truncated"] is False
    assert prose_exc["deep_link"] == "https://x.com/example/status/123"

    # Excerpt ID follows unchanged derivation
    expected_id = cards._hash([item["video_id"], "opening_prose", "Verbatim original prose that must become evidence."])
    assert prose_exc["excerpt_id"] == expected_id


@pytest.mark.parametrize("source_type", ["video", "episode", "short_video"])
def test_video_origin_prose_not_promoted_when_clips_exist(source_type):
    item = synthetic_item(source_type=source_type)
    clips = synthetic_clips(8)
    corpus = "# Video Description\nThis is a video summary that must NOT become evidence."

    card = cards.build_card(item, clips, corpus_text=corpus, profile="librarian")

    # Ineligible source retains up to 6 timed excerpts, no prose excerpt
    assert len(card["excerpts"]) == 6
    assert len(card["clips"]) == 6
    assert all(e["evidence_kind"] == "timed_clip" for e in card["excerpts"])
    assert not any(e["evidence_kind"] == "text_only" for e in card["excerpts"])
    # But hint / summary_hint still records the description
    assert card["summary_hint"] == "This is a video summary that must NOT become evidence."


# ---------------------------------------------------------------------------
# 5. Deterministic timed selection and displacement
# ---------------------------------------------------------------------------

def test_displaced_timed_excerpt_when_clips_exceed_five():
    item = synthetic_item(source_type="x_thread")
    clips = synthetic_clips(6)  # 6 clips
    corpus = "Original prose."

    # Build without prose (or with ineligible source) -> 6 clips
    card_v1_shape = cards.build_card(synthetic_item(source_type="video"), clips, corpus_text=corpus, profile="librarian")
    assert len(card_v1_shape["excerpts"]) == 6
    v1_timed_starts = [e["start"] for e in card_v1_shape["excerpts"]]

    # Build with prose -> 5 timed clips + 1 prose
    card_v2 = cards.build_card(item, clips, corpus_text=corpus, profile="librarian")
    assert len(card_v2["excerpts"]) == 6
    v2_timed_starts = [e["start"] for e in card_v2["clips"]]
    assert len(v2_timed_starts) == 5

    # Exactly 1 timed excerpt was displaced
    displaced = set(v1_timed_starts) - set(v2_timed_starts)
    assert len(displaced) == 1

    # Diff helper detects and discloses displacement
    # Simulate old v1 card
    old_card = copy.deepcopy(card_v1_shape)
    old_card["source_type"] = "x_thread"
    old_card["selection_version"] = "spread-longest-v1"
    old_card["card_hash"] = cards._hash({k: v for k, v in old_card.items() if k != "card_hash"})

    diff = cards.diff_cards(old_card, card_v2)
    assert diff.classification == "displaced timed excerpt"
    assert len(diff["displaced_timed_excerpts"]) == 1
    assert len(diff["added_prose_excerpts"]) == 1


def test_added_prose_without_displacement_when_clips_at_most_five():
    item = synthetic_item(source_type="x_thread")
    clips = synthetic_clips(3)
    corpus = "Original prose."

    # Build old card with 3 clips and spread-longest-v1
    old_card = cards.build_card(synthetic_item(source_type="video"), clips, corpus_text="", profile="librarian")
    old_card["source_type"] = "x_thread"
    old_card["selection_version"] = "spread-longest-v1"
    old_card["summary_hint"] = "Original prose."
    old_card["hint"] = {"kind": "opening_prose", "text": "Original prose.", "truncated": False}
    old_card["card_hash"] = cards._hash({k: v for k, v in old_card.items() if k != "card_hash"})

    card_v2 = cards.build_card(item, clips, corpus_text=corpus, profile="librarian")
    assert len(card_v2["clips"]) == 3
    assert len(card_v2["excerpts"]) == 4  # 3 timed + 1 prose

    diff = cards.diff_cards(old_card, card_v2)
    assert diff.classification == "added prose"
    assert len(diff["displaced_timed_excerpts"]) == 0
    assert len(diff["added_prose_excerpts"]) == 1


# ---------------------------------------------------------------------------
# 6. Excerpt bounding and truncation flags
# ---------------------------------------------------------------------------

def test_excerpts_bounded_to_240_chars_in_librarian():
    long_prose = "word " * 100  # 500 chars
    long_clip = [{"seq": 0, "start": 0.0, "end": 10.0, "text": "clip " * 100, "source_deep_link": "https://x.com"}]
    item = synthetic_item(source_type="x_thread")

    card = cards.build_card(item, long_clip, corpus_text=long_prose, profile="librarian")

    timed_exc = card["clips"][0]
    prose_exc = card["excerpts"][-1]

    assert len(timed_exc["text"]) == 240
    assert timed_exc["truncated"] is True
    assert len(prose_exc["text"]) == 240
    assert prose_exc["truncated"] is True
    assert card["truncated"] is True


# ---------------------------------------------------------------------------
# 7. Byte accounting and failure signal (CardFreezeError)
# ---------------------------------------------------------------------------

def test_byte_pressure_drops_hints_before_evidence_and_protects_prose():
    # Long title and huge opening prose to trigger byte budget pressure
    huge_prose = "Important opening prose. " + ("extra filler text " * 100)
    clips = synthetic_clips(4)
    item = synthetic_item(
        source_type="x_thread",
        title="T" * 150,  # over 80 chars
        channel="C" * 150,
    )

    # Budget tight enough to force dropping hints, truncating title/channel, and dropping 2 clips
    card = cards.build_card(item, clips, corpus_text=huge_prose, profile="librarian", byte_budget=3000)

    # Hints dropped
    assert card["hint"] is None
    assert card["summary_hint"] is None
    assert "hint" in card["truncation"]["fields"]
    # Long fields truncated
    assert len(card["title"]) <= 80
    assert len(card["channel"]) <= 80
    # Reserved prose slot protected
    assert any(e["evidence_kind"] == "text_only" for e in card["excerpts"])
    # Timed clips retained
    assert any(e["evidence_kind"] == "timed_clip" for e in card["excerpts"])
    assert len(cards.card_text(card).encode("utf-8")) <= 3000


def test_mixed_evidence_freeze_failure_signal_when_cannot_fit():
    # Attempt to build mixed card with byte_budget so small that 1 clip + 1 prose cannot fit
    item = synthetic_item(
        source_type="x_thread",
        video_id="impossible_fit_item_999",
        title="X" * 80,
    )
    clips = synthetic_clips(3)
    corpus = "Real prose."

    with pytest.raises(cards.CardFreezeError, match="impossible_fit_item_999") as exc_info:
        cards.build_card(item, clips, corpus_text=corpus, profile="librarian", byte_budget=2048)

    assert "mixed evidence cannot fit" in str(exc_info.value)
    assert "impossible_fit_item_999" in str(exc_info.value)


def test_mixed_evidence_freeze_failure_when_n_clips_too_small():
    item = synthetic_item(source_type="x_thread", video_id="slot_starved_item_111")
    clips = synthetic_clips(2)
    corpus = "Real prose."

    with pytest.raises(cards.CardFreezeError, match="slot_starved_item_111") as exc_info:
        cards.build_card(item, clips, corpus_text=corpus, profile="librarian", n_clips=1)

    assert "mixed evidence cannot fit in n_clips=1" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 8. Deterministic diff helper classifications
# ---------------------------------------------------------------------------

def test_diff_helper_classifications():
    # 1. Metadata-only
    c1 = cards.build_card(synthetic_item(source_type="video"), synthetic_clips(2), corpus_text="", profile="librarian")
    c2 = copy.deepcopy(c1)
    c2["selection_version"] = "spread-longest-v1"
    c2["card_hash"] = cards._hash({k: v for k, v in c2.items() if k != "card_hash"})
    diff_meta = cards.diff_cards(c2, c1)
    assert diff_meta.classification == "metadata-only"
    assert diff_meta == "metadata-only"

    # 2. Added prose
    c_added = cards.build_card(synthetic_item(source_type="x_thread"), synthetic_clips(2), corpus_text="Prose", profile="librarian")
    diff_added = cards.diff_cards(c2, c_added)
    assert diff_added.classification == "added prose"

    # 3. Displaced timed excerpt
    c_displaced = cards.build_card(synthetic_item(source_type="x_thread"), synthetic_clips(6), corpus_text="Prose", profile="librarian")
    c_base6 = cards.build_card(synthetic_item(source_type="video"), synthetic_clips(6), corpus_text="", profile="librarian")
    c_base6["selection_version"] = "spread-longest-v1"
    diff_disp = cards.diff_cards(c_base6, c_displaced)
    assert diff_disp.classification == "displaced timed excerpt"
    assert len(diff_disp["displaced_timed_excerpts"]) > 0

    # 4. Truncation change
    c_trunc1 = cards.build_card(synthetic_item(source_type="video"), synthetic_clips(2), corpus_text="", profile="librarian")
    c_trunc2 = copy.deepcopy(c_trunc1)
    c_trunc2["truncated"] = not c_trunc1["truncated"]
    diff_trunc = cards.diff_cards(c_trunc1, c_trunc2)
    assert diff_trunc.classification == "truncation change"

    # 5. Other (mismatched content / source revision)
    c_other = copy.deepcopy(c1)
    c_other["title"] = "Completely Altered Title"
    diff_other = cards.diff_cards(c1, c_other)
    assert diff_other.classification == "other"

    # Mismatched video_id raises ValueError
    c_wrong_id = copy.deepcopy(c1)
    c_wrong_id["video_id"] = "different_id"
    with pytest.raises(ValueError, match="matching video_id"):
        cards.diff_cards(c1, c_wrong_id)


# ---------------------------------------------------------------------------
# 9. Replay over the 548 archived Stage 1 cards (receipts.json; no DB)
# ---------------------------------------------------------------------------

def test_replay_over_archived_stage1_cards():
    assert ARCHIVE_RECEIPTS.exists(), f"Archive receipts not found at {ARCHIVE_RECEIPTS}"
    receipts_data = json.loads(ARCHIVE_RECEIPTS.read_text(encoding="utf-8"))

    # Extract all 548 unique packet cards from stage 1 receipts
    archived_cards = {
        a["video_id"]: a["packet"]["card"]
        for a in receipts_data["attempts"]
        if "packet" in a and "card" in a["packet"]
    }
    assert len(archived_cards) == 548

    # Replay each card to Card Contract v2
    v2_cards = {vid: cards.replay_card_v2(card) for vid, card in archived_cards.items()}
    assert len(v2_cards) == 548

    # Check rule: global version bump changes ALL 548 card hashes
    hashes_differ = [v2_cards[vid]["card_hash"] != archived_cards[vid]["card_hash"] for vid in archived_cards]
    assert all(hashes_differ), "Every single card hash must change due to selection_version update"

    # Check rule: source_revision remains 100% identical
    revisions_match = [v2_cards[vid]["source_revision"] == archived_cards[vid]["source_revision"] for vid in archived_cards]
    assert all(revisions_match), "Source revisions must remain strictly unchanged"

    # Classify all diffs with diff_cards
    diffs = [cards.diff_cards(archived_cards[vid], v2_cards[vid]) for vid in sorted(archived_cards)]
    breakdown = Counter(d.classification for d in diffs)

    # Exactly 452 metadata-only and 96 added prose
    assert breakdown == Counter({"metadata-only": 452, "added prose": 96}), (
        f"Expected Counter({{'metadata-only': 452, 'added prose': 96}}), got {breakdown}"
    )

    # Verify hold-out v3 alignment (sketch line 21: 'including 21 v3 cards')
    if HOLDOUT_V3.exists():
        holdout_data = json.loads(HOLDOUT_V3.read_text(encoding="utf-8"))
        holdout_ids = {row["video_id"] for stratum in holdout_data["strata"].values() for row in stratum}
        assert len(holdout_ids) == 60

        v3_added_prose = [
            d for d in diffs
            if d["video_id"] in holdout_ids and d.classification == "added prose"
        ]
        assert len(v3_added_prose) == 21, (
            f"Expected exactly 21 hold-out v3 cards to have added prose, got {len(v3_added_prose)}"
        )
