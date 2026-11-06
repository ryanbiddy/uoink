"""Capture markdown leaves out fields it does not know, with no dash placeholders."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import server


def _build(metadata, channel_ctx=None):
    return server._build_yoink_md(metadata, "https://example.com/v", [], [], 30,
                                  channel_ctx or {}, "2026-11-01", "Test")


def test_unknown_channel_stats_and_counts_are_omitted():
    markdown = _build({"title": "T", "uploader": "Someone"})
    assert "**Channel:** Someone\n" in markdown
    assert "subscribers" not in markdown
    assert "Views" not in markdown and "Uploaded" not in markdown and "Duration" not in markdown
    assert "—" not in markdown.split("---")[0]


def test_known_fields_still_show():
    markdown = _build({"title": "T", "channel": "Show", "channel_follower_count": 1500,
                       "upload_date": "20261101", "duration": 245, "view_count": 29142})
    assert "**Channel:** Show (1.5K subscribers)" in markdown
    assert "**Uploaded:** 2026-11-01 | **Duration:** 04:05 | **Views:** 29,142" in markdown


def test_no_channel_and_unknown_recent_video_facts_leave_no_dash():
    markdown = _build({"title": "T"}, {"recent_videos": [{"title": "Older"}]})
    assert "**Channel:**" not in markdown
    assert "**About this channel:**" in markdown
    assert "- Older\n" in markdown
    assert "—" not in markdown


def test_likes_line_only_when_the_count_is_known():
    assert "Likes" not in _build({"title": "T", "view_count": 5})
    assert "not exposed" not in _build({"title": "T"})
    assert "**Likes:** 7" in _build({"title": "T", "like_count": 7})
    assert "**Likes:** 0" in _build({"title": "T", "like_count": 0})
