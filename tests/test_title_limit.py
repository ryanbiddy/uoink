"""One shared title limit (300 characters), enforced where items are saved."""
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

import images
import notes
from provenance import MAX_TITLE_CHARS, clamp_title

LIMIT = 300


def _ok_len(t):
    return len(t) <= LIMIT


def test_limit_is_300_everywhere():
    assert MAX_TITLE_CHARS == 300
    assert notes.MAX_TITLE_CHARS == 300
    assert images.MAX_TITLE_CHARS == 300


def test_exact_boundary_and_empty():
    exact = "a" * 300
    assert clamp_title(exact) == exact
    assert clamp_title("") == ""
    assert clamp_title(None) is None
    cut = clamp_title("a" * 301)
    assert len(cut) == 300 and cut.endswith("…") and cut[:-1] == "a" * 299


def test_trailing_space_trimmed_before_ellipsis():
    out = clamp_title("a" * 295 + "     " + "b" * 50)
    assert out == "a" * 295 + "…"


def test_zwj_emoji_not_split():
    family = "\U0001F468‍\U0001F469‍\U0001F467"  # 5 code points
    for pad in range(285, 300):
        title = "a" * pad + family + "tail" * 10
        out = clamp_title(title)
        assert _ok_len(out)
        body = out[:-1]
        # either the whole family is kept or none of it
        assert family in body or ("\U0001F468" not in body[pad:] and "‍" not in body[pad:])
        assert not body.endswith("‍")


def test_combining_marks_not_split():
    title = "a" * 298 + "é̂" + "zzz"
    out = clamp_title(title)
    assert _ok_len(out)
    assert "́" not in out[:-1] or "é̂" in out[:-1]
    assert not out[:-1].endswith("e")


def test_skin_tone_variation_and_flags_not_split():
    thumbs = "\U0001F44D\U0001F3FD"
    out = clamp_title("a" * 298 + thumbs + "zzz")
    assert "\U0001F44D" not in out[:-1] or thumbs in out[:-1]
    flag = "\U0001F1FA\U0001F1F8"
    out = clamp_title("a" * 298 + flag + "zzz")
    assert "\U0001F1FA" not in out[:-1] or flag in out[:-1]


def test_lone_surrogates_do_not_crash_or_split():
    pair_like = "😀"  # unpaired halves as JSON \u escapes can leave
    out = clamp_title("a" * 298 + pair_like + "zzz")
    assert _ok_len(out)
    assert not out[:-1].endswith("\ud83d")


def test_one_long_cluster_still_cut():
    out = clamp_title("e" + "́" * 500)
    assert _ok_len(out) and out.endswith("…")


def test_note_and_image_builders():
    long = "word " * 200
    built = notes.build_note("body text", title=long)
    assert built["ok"] and len(built["title"]) <= LIMIT and built["title"].endswith("…")
    assert len(notes.derive_title("# " + long)) <= LIMIT
    assert notes.derive_title("x" * 300) == "x" * 300
    assert len(images.derive_title(long, None)) <= LIMIT
    assert len(images.derive_title(None, "n" * 400 + ".png")) <= LIMIT


@pytest.fixture()
def idx():
    import index
    d = tempfile.mkdtemp()
    ix = index.Index.open(Path(d) / "t.db")
    if ix is None:
        pytest.skip("Index class not found")
    yield ix
    try:
        ix.close()
    except Exception:
        pass


# Every source passes through upsert_yoink, so one check per source type
# proves the shared boundary.
SOURCES = [
    ("youtube", "yt1", "youtube"),
    ("podcast", "pod1", "podcast"),
    ("page", "pg1", "web"),
    ("x", "x1", "x"),
    ("reddit", "r1", "reddit"),
    ("import", "imp1", "import"),
    ("note", "note_1", "note"),
]


@pytest.mark.parametrize("name,vid,platform", SOURCES)
def test_store_boundary_clamps_every_source(idx, name, vid, platform):
    long = "T" * 500
    idx.upsert_yoink({"video_id": vid, "slug": vid, "title": long, "platform": platform, "yoinked_at": "2026-11-12T00:00:00Z", "corpus_path": "c", "sidecar_path": "s"})
    got = idx.get_yoink(vid)["title"]
    assert len(got) == 300 and got.endswith("…")
    idx.upsert_yoink({"video_id": vid + "x", "slug": vid + "x", "title": "T" * 300, "platform": platform, "yoinked_at": "2026-11-12T00:00:00Z", "corpus_path": "c", "sidecar_path": "s"})
    assert idx.get_yoink(vid + "x")["title"] == "T" * 300
    idx.upsert_yoink({"video_id": vid + "y", "slug": vid + "y", "title": "T" * 301, "platform": platform, "yoinked_at": "2026-11-12T00:00:00Z", "corpus_path": "c", "sidecar_path": "s"})
    assert len(idx.get_yoink(vid + "y")["title"]) == 300
    idx.upsert_yoink({"video_id": vid + "z", "slug": vid + "z", "title": "", "platform": platform, "yoinked_at": "2026-11-12T00:00:00Z", "corpus_path": "c", "sidecar_path": "s"})
    assert idx.get_yoink(vid + "z")["title"] == ""


def test_store_title_limit_survives_provenance_stub(idx, monkeypatch):
    monkeypatch.setitem(sys.modules, "provenance", SimpleNamespace())
    idx.upsert_yoink({
        "video_id": "stubbed", "slug": "stubbed", "title": "T" * 500,
        "source_type": "youtube", "yoinked_at": "2026-11-12T00:00:00Z",
        "corpus_path": "c", "sidecar_path": "s",
    })
    assert idx.get_yoink("stubbed")["title"] == "T" * 299 + "…"
