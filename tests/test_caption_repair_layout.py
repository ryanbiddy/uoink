"""Repair the corpus layouts and newline conventions used by older captures."""
import json
from pathlib import Path

import pytest

import server
from tests.test_caption_repair import ROLLING, VID, library as saved_library


@pytest.mark.parametrize("held_in", ["source_chapters", "metadata.json", "missing", "mismatched"])
def test_legacy_chapter_headings_survive_repair(saved_library, held_in):
    idx, save = saved_library
    side, corpus, plain = save(legacy=True)
    chapters = [{"title": "Dusk", "start_time": 0, "end_time": 2},
                {"title": "Nightfall", "start_time": 2, "end_time": 8}]
    if held_in in ("source_chapters", "mismatched"):
        data = json.loads(side.read_bytes())
        held = [dict(chapters[0], title="Other"), chapters[1]] if held_in == "mismatched" else chapters
        side.write_text(json.dumps(dict(data, source_chapters=held)), encoding="utf-8")
    elif held_in == "metadata.json":
        (side.parent / held_in).write_text(json.dumps({"id": VID, "chapters": chapters}), encoding="utf-8")

    def render(entries):
        return server._build_yoink_md({"chapters": chapters}, "", entries, [], 30, {}, "", "")

    corpus.write_text(render(ROLLING), encoding="utf-8")
    before = {p: p.read_bytes() for p in (side, corpus, plain)}
    if held_in in ("missing", "mismatched"):
        for dry_run in (True, False):
            with pytest.raises(ValueError, match="chapter layout"):
                server.repair_rolling_captions(VID, dry_run=dry_run)
        assert all(p.read_bytes() == b for p, b in before.items()) and not list(side.parent.glob("*.bak"))
        return
    assert server.repair_rolling_captions(VID)["removed_words"] == 16
    assert all(p.read_bytes() == b for p, b in before.items())
    result = server.repair_rolling_captions(VID, dry_run=False)
    assert Path(result["original_sidecar"]).read_bytes() == before[side]
    saved = json.loads(side.read_bytes())
    assert saved["source_chapters"] == chapters
    assert [ch["title"] for ch in saved["media_depth"]["chapters"]] == ["Dusk", "Nightfall"]
    text = [ROLLING[0][2], "shows stars", "before sunset", "beyond the", "far ridge"]
    assert corpus.read_text(encoding="utf-8") == render([(s, e, t) for (s, e, _), t in zip(ROLLING, text)])
    with idx.detached_snapshot() as conn:
        indexed = conn.execute("SELECT content FROM yoinks_fts WHERE video_id=?", (VID,)).fetchone()[0]
    assert indexed.encode() == corpus.read_bytes()
    assert server.repair_rolling_captions(VID, dry_run=False)["removed_words"] == 0


def test_repair_preserves_crlf_inside_multiline_cues(saved_library):
    _, save = saved_library
    entries = [(s, e, text.replace("blue sky", "blue\nsky")) for s, e, text in ROLLING]
    _, _, plain = save(entries=entries)
    plain.write_bytes("\r\n".join(t.replace("\n", "\r\n") for _, _, t in entries).encode())
    assert server.repair_rolling_captions(VID)["removed_words"] == 16
    server.repair_rolling_captions(VID, dry_run=False)
    expected = "the blue\r\nsky above us today\r\nshows stars\r\nbefore sunset\r\nbeyond the\r\nfar ridge"
    assert plain.read_bytes() == expected.encode()
    assert server.repair_rolling_captions(VID, dry_run=False)["removed_words"] == 0
