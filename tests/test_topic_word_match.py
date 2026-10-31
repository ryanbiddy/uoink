"""Topic keywords match whole words, not fragments of other words or links."""
from __future__ import annotations

import pytest

from tests.test_finance_topic import classify_topic  # noqa: F401 -- shared fixture


SOCIAL = "Social Media Research"
AI = "AI and ML"


def route(classify, metadata, topics=None):
    scope = classify.__globals__
    if topics is None:
        return classify(metadata)
    original = scope["_load_topics"]
    scope["_load_topics"] = lambda: {"topics": topics, "fallback": "Uncategorized"}
    try:
        return classify(metadata)
    finally:
        scope["_load_topics"] = original


@pytest.mark.parametrize("metadata", [
    # A fact sheet: "RAG" sits inside "average", "storage" and "coverage".
    {"title": "Moon Fact Sheet",
     "description": "Mean orbital velocity 1.022 km/s. The average distance from Earth "
                    "is 384,400 km. Archive storage and coverage notes follow.",
     "channel": "example.gov"},
    # A lecture whose description ends in the channel's link list.
    {"title": "Photosynthesis: Light Reactions and the Calvin Cycle",
     "description": "How chloroplasts turn light into sugar.\n\n"
                    "Facebook - https://www.facebook.com/example\n"
                    "Twitter - https://twitter.com/example\n"
                    "► Instagram: https://www.instagram.com/example",
     "tags": ["biology", "photosynthesis"], "channel": "Example Science"},
    # Platform names that appear only inside URLs.
    {"title": "The Moon: Phases, Tides and Eclipses (Lecture 4)",
     "description": "Why we only ever see one face of the Moon. Clips from this lecture "
                    "are at https://www.tiktok.com/@example and www.instagram.com/example/reels",
     "tags": ["astronomy", "moon"]},
    # Antiviral is not viral; a shortstop is not Shorts.
    {"title": "Antiviral defenses in plant leaves",
     "description": "The shortstop analogy for innate immunity."},
])
def test_science_items_stay_uncategorized(classify_topic, metadata):
    assert route(classify_topic, metadata) == "Uncategorized"


@pytest.mark.parametrize("metadata, expected", [
    ({"title": "Creators share their best Instagram growth tips"}, SOCIAL),
    ({"title": "Top LLMs ranked for coding"}, AI),
    ({"title": "Build a RAG pipeline in an afternoon"}, AI),
    ({"title": "GPT-4o vs Claude's new model"}, AI),
    ({"title": "Why #shorts work", "tags": ["youtube shorts"]}, SOCIAL),
    ({"title": "My week", "description": "I compare TikTok and Instagram growth "
                                         "for new accounts: https://example.com/notes"}, SOCIAL),
    ({"title": "How I use Notion for deep work"}, "Productivity and Workflows"),
])
def test_intended_matches_still_route(classify_topic, metadata, expected):
    assert route(classify_topic, metadata) == expected


SHORT = [{"name": "AI", "keywords": ["AI", "ML"]}]


@pytest.mark.parametrize("title", [
    "She said the main detail was certain",
    "Hawaii trip: rain again",
    "HTML and XML basics",
    "OpenAI DevDay recap",
])
def test_short_tokens_do_not_match_inside_words(classify_topic, title):
    assert route(classify_topic, {"title": title}, SHORT) == "Uncategorized"


@pytest.mark.parametrize("title", [
    "AI-powered search",
    "#AI tools I use",
    "The AI's answer",
    "AIs and agents",
    "Intro to ML",
    "(ML) models explained",
])
def test_short_tokens_match_as_words(classify_topic, title):
    assert route(classify_topic, {"title": title}, SHORT) == "AI"
