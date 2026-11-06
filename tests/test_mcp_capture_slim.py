"""F31: capture tool replies carry one best MP4 per video, not every variant."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import page_extractor
import server
import test_x_capture_evidence as xt
import uoink_mcp_tools as tools
import x_extractor
from uoink_core import x_evidence


def test_slim_capture_keeps_text_author_counts_and_one_mp4_per_video():
    full = xt.extract("video")["metadata"]["x_capture"]
    slim = x_evidence.slim_capture(full)
    post = slim["posts"][-1]
    assert post["text"] == "A video and a GIF."
    assert post["author"]["handle"] == "example"
    assert "engagement" not in post or isinstance(post["engagement"], dict)
    video, gif = post["media"]
    assert video["type"] == "video"
    assert video["url"] == "https://example.invalid/video.mp4"
    assert (video["width"], video["height"], video["duration"]) == (1280, 720, 8)
    assert gif["url"] == "https://example.invalid/loop.mp4"
    blob = json.dumps(slim)
    for bulky in ("source_descriptors", "video_info", "variants", "formats", "m3u8", "video-low"):
        assert bulky not in blob
    assert len(blob) < len(json.dumps(full)) / 2


def test_uoink_x_reply_is_slim_but_the_saved_record_stays_full(monkeypatch):
    tools.bind_backend(server)
    result = xt.extract("video")
    persisted = []
    monkeypatch.setattr(server, "_read_settings", lambda: {"x_text_capture_enabled": True})
    monkeypatch.setattr(x_extractor, "extract_x_thread", lambda _url: result)
    monkeypatch.setattr(page_extractor, "persist_page_yoink",
                        lambda _idx, res, **_k: persisted.append(json.dumps(res)) or "x_1")
    monkeypatch.setattr(server, "_save_x_video_poster", lambda *_a: None)
    reply = tools.uoink_x({"url": "https://x.com/example/status/1"})
    assert reply["ok"] and reply["video_id"] == "x_1"
    assert "source_descriptors" in persisted[0] and "video-low" in persisted[0]
    text = json.dumps(reply)
    assert "source_descriptors" not in text and "video-low" not in text
    assert "https://example.invalid/video.mp4" in text


def test_uoink_url_reply_drops_the_base64_clipboard_copy(monkeypatch):
    tools.bind_backend(server)

    def fake(self, body):
        return self._send_json(200, {"ok": True, "yoink_md": "text", "corpus_md_paste": "data:image/jpeg;base64,AAAA"})
    monkeypatch.setattr(server.Handler, "_handle_extract_any", fake)
    reply = tools.uoink_url({"url": "https://example.com/v"})
    assert reply["yoink_md"] == "text" and "corpus_md_paste" not in reply


def test_slim_post_keeps_disclosures_for_a_tombstone_and_unavailable_quote():
    post = x_evidence.shape({
        "id_str": "9", "type": "tombstone", "reason": "deleted", "text": "",
        "quoted_status_id_str": "8", "in_reply_to_status_id_str": "7"})
    post["missing_parent"] = {"id": "7", "reason": "ancestor limit reached"}
    post["quote"] = dict(post["quote"] or {"id": "8"}, unavailable_reason="unavailable")
    slim = x_evidence.slim_post(post)
    assert slim["unavailable_reason"] == "deleted"
    assert slim["missing_parent"]["reason"] == "ancestor limit reached"
    assert slim["text_completeness_reason"] and slim["quote_status"] and slim["media_status"]
    assert slim["quote"]["unavailable_reason"] == "unavailable"
    plain = x_evidence.slim_post(x_evidence.shape({"id_str": "1", "text": "hi"}))
    assert "unavailable_reason" not in plain and "missing_parent" not in plain
