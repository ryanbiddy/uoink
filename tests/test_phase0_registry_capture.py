from __future__ import annotations

import asyncio
import base64

import server
import uoink_mcp
import uoink_mcp_tools as tools


CAPTURE_TOOLS = {"uoink_url", "uoink_note", "uoink_image", "uoink_x"}


def test_capture_tools_are_http_only_rate_limited_and_counted():
    assert len(tools.TOOL_REGISTRY) == 81  # +6 Living Library tools (run J), +4 Phase 3 source tools (run AM)
    assert CAPTURE_TOOLS.issubset(tools.TOOL_REGISTRY)
    assert all(tools.TOOL_REGISTRY[name].rate_limiter for name in CAPTURE_TOOLS)
    stdio_names = {tool.name for tool in asyncio.run(uoink_mcp.mcp.list_tools())}
    assert CAPTURE_TOOLS.isdisjoint(stdio_names)


def test_uoink_url_reuses_extract_any_handler(monkeypatch):
    seen = []

    def fake_extract_any(self, body):
        seen.append(body)
        return self._send_json(200, {"ok": True, "mode": "generic"})

    monkeypatch.setattr(server.Handler, "_handle_extract_any", fake_extract_any)
    tools.bind_backend(server)
    result = tools.uoink_url({"url": "https://example.com/post"})
    assert result == {"ok": True, "mode": "generic"}
    assert seen == [{"url": "https://example.com/post"}]


def test_note_image_and_x_handlers_reuse_capture_modules(monkeypatch, tmp_path):
    tools.bind_backend(server)
    monkeypatch.setattr(server, "_get_index", lambda: object())
    monkeypatch.setattr(server, "DESKTOP_ROOT", tmp_path)
    monkeypatch.setattr(server, "_classify_topic", lambda _metadata: "Topic")

    import images
    import notes
    import page_extractor
    import x_extractor

    monkeypatch.setattr(notes, "build_note", lambda **_kwargs: {
        "ok": True, "slug": "note", "title": "Note", "author": "You"
    })
    monkeypatch.setattr(notes, "persist_note", lambda *_args, **_kwargs: "note_1")
    assert tools.uoink_note({"text": "remember this"})["video_id"] == "note_1"

    image_bytes = b"image-fixture"
    monkeypatch.setattr(images, "build_image", lambda raw, **_kwargs: {
        "ok": raw == image_bytes,
        "slug": "image",
        "title": "Image",
        "author": "You",
    })
    monkeypatch.setattr(images, "persist_image", lambda *_args, **_kwargs: "image_1")
    encoded = base64.b64encode(image_bytes).decode("ascii")
    assert tools.uoink_image({"image_base64": encoded})["video_id"] == "image_1"

    monkeypatch.setattr(
        server, "_read_settings", lambda: {"x_text_capture_enabled": True}
    )
    monkeypatch.setattr(x_extractor, "extract_x_thread", lambda _url: {
        "ok": True, "title": "Post", "tweets_captured": 1, "metadata": {}
    })
    monkeypatch.setattr(
        page_extractor, "persist_page_yoink", lambda *_args, **_kwargs: "x_1"
    )
    assert tools.uoink_x({"url": "https://x.com/a/status/1"})["video_id"] == "x_1"


def test_x_capture_keeps_default_off_gate(monkeypatch):
    tools.bind_backend(server)
    monkeypatch.setattr(server, "_read_settings", lambda: {})
    result = tools.uoink_x({"url": "https://x.com/a/status/1"})
    assert result["ok"] is False
    assert result["code"] == "disabled"
