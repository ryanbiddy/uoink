"""Deterministic storage and SDK-independent expectations for wire tests."""
from pathlib import Path


def seed_library(directory):
    import index
    import library_resources
    from tests.phase4_fixtures import build_test_card, seed_yoink_item

    profile = Path(directory) / "profile"
    profile.mkdir(parents=True, exist_ok=True)
    idx = index.Index.open(profile / "index.db")
    try:
        seed_yoink_item(idx, profile, video_id="m2-wire", slug="m2-wire",
                        title="M2 wire fixture", channel="Fixture channel", topic="Wire",
                        corpus_text="A deterministic local corpus for the wire fixture.\n",
                        clips=[{"seq": 0, "start": 0.0, "end": 12.0,
                                "text": "A deterministic local evidence clip."}])
        card = build_test_card(idx, "m2-wire")
        return library_resources.card_uri("m2-wire", card)
    finally:
        idx.close()
