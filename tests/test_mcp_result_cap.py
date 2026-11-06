"""F32: one big tool reply must not kill the MCP session."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uoink_mcp_tools as tools

CAP = 60 * 1024


def _size(value):
    return len(json.dumps(value, ensure_ascii=False).encode("utf-8"))


def _bulky_record():
    variants = [{"url": f"https://video.example/v{i}.mp4", "bitrate": i} for i in range(600)]
    return {
        "ok": True, "video_id": "x_1", "title": "A post",
        "metadata": {"author_handle": "someone", "x_capture": {"posts": [
            {"text": "hello", "media": [{"variants": variants, "formats": variants,
                                          "source_descriptors": [{"variants": variants}]}]}]}},
    }


def test_small_reply_is_untouched():
    reply = {"ok": True, "video_id": "x_1", "title": "short"}
    assert tools.cap_tool_result(reply, CAP) is reply


def test_bulky_lists_are_dropped_first_and_json_stays_valid():
    reply = _bulky_record()
    assert _size(reply) > CAP
    out = tools.cap_tool_result(reply, CAP)
    assert _size(out) <= CAP
    json.loads(json.dumps(out))
    post = out["metadata"]["x_capture"]["posts"][0]
    assert post["text"] == "hello"
    assert "variants" not in post["media"][0]
    assert "sidecar" in out["truncated"]
    # The caller's object is not mutated.
    assert "variants" in reply["metadata"]["x_capture"]["posts"][0]["media"][0]


def test_long_text_and_lists_shrink_without_cutting_structure():
    reply = {"ok": True, "video_id": "p_1", "transcript": "word " * 20000,
             "rows": [{"n": i, "text": "line " * 50} for i in range(2000)]}
    out = tools.cap_tool_result(reply, CAP)
    assert _size(out) <= CAP
    assert out["video_id"] == "p_1"
    assert out["ok"] is True
    assert isinstance(out["rows"], list)
    assert "truncated" in out


def test_error_envelopes_pass_through():
    err = {"ok": False, "error": "nope"}
    assert tools.cap_tool_result(err, CAP) is err


def test_server_cap_constant_and_hook():
    source = (Path(__file__).resolve().parent.parent / "uoink_mcp.py").read_text(encoding="utf-8")
    assert "MCP_RESULT_TEXT_CAP = 60 * 1024" in source
    assert "cap_tool_result(envelope, MCP_RESULT_TEXT_CAP)" in source
