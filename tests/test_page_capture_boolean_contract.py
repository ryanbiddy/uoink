"""Strict screenshot choice at every universal-page capture boundary."""
from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import page_extractor  # noqa: E402
import server  # noqa: E402
import uoink_mcp_tools  # noqa: E402


class _FakeHandler:
    _handle_extract_page = server.Handler._handle_extract_page

    def _send_json(self, status, payload):
        self.response = (status, payload)
        return self.response


@pytest.mark.parametrize("bad_value", ["false", 0, None, [], {}])
def test_http_rejects_non_boolean_screenshot_before_capture(
    monkeypatch, bad_value
):
    monkeypatch.setattr(
        server,
        "_get_index",
        lambda: pytest.fail("invalid screenshot choice reached index lookup"),
    )
    monkeypatch.setattr(
        page_extractor,
        "extract_page",
        lambda *_args, **_kwargs: pytest.fail(
            "invalid screenshot choice reached page capture"
        ),
    )
    handler = _FakeHandler()

    assert handler._handle_extract_page(
        {
            "url": "https://example.com",
            "include_screenshot": bad_value,
        }
    ) == (
        400,
        {"ok": False, "error": "include_screenshot must be a boolean"},
    )


@pytest.mark.parametrize("bad_value", ["false", 0, None, [], {}])
def test_mcp_handler_rejects_non_boolean_screenshot_before_capture(
    monkeypatch, bad_value
):
    uoink_mcp_tools.bind_backend(server)
    monkeypatch.setattr(
        server,
        "_get_index",
        lambda: pytest.fail("invalid screenshot choice reached index lookup"),
    )
    monkeypatch.setattr(
        page_extractor,
        "extract_page",
        lambda *_args, **_kwargs: pytest.fail(
            "invalid screenshot choice reached page capture"
        ),
    )

    assert uoink_mcp_tools.uoink_page(
        {
            "url": "https://example.com",
            "include_screenshot": bad_value,
        }
    ) == {
        "ok": False,
        "error": "include_screenshot must be a boolean",
    }


@pytest.mark.parametrize("bad_value", ["false", 0, None, [], {}])
def test_core_rejects_non_boolean_screenshot_before_url_or_allowlist(
    monkeypatch, bad_value
):
    monkeypatch.setattr(
        page_extractor,
        "normalize_page_url",
        lambda *_args, **_kwargs: pytest.fail(
            "invalid screenshot choice reached URL processing"
        ),
    )

    assert page_extractor.extract_page(
        None,
        "https://example.com",
        include_screenshot=bad_value,
        enforce_allowlist=False,
    ) == {
        "ok": False,
        "error": "include_screenshot must be a boolean",
    }


def test_false_screenshot_choice_reaches_http_capture_unchanged(monkeypatch):
    seen = {}
    index = object()
    monkeypatch.setattr(server, "_get_index", lambda: index)

    def _extract(*args, **kwargs):
        seen["extract"] = (args, kwargs)
        return {"ok": True, "title": "Captured"}

    monkeypatch.setattr(page_extractor, "extract_page", _extract)
    monkeypatch.setattr(
        page_extractor,
        "persist_page_yoink",
        lambda *_args, **_kwargs: "page-1",
    )
    handler = _FakeHandler()

    assert handler._handle_extract_page(
        {
            "url": "https://example.com",
            "include_screenshot": False,
        }
    ) == (
        200,
        {"ok": True, "title": "Captured", "video_id": "page-1"},
    )
    assert seen["extract"][1]["include_screenshot"] is False


def test_false_screenshot_choice_reaches_mcp_capture_unchanged(monkeypatch):
    seen = {}
    index = object()
    uoink_mcp_tools.bind_backend(server)
    monkeypatch.setattr(server, "_get_index", lambda: index)

    def _extract(*args, **kwargs):
        seen["extract"] = (args, kwargs)
        return {"ok": True, "title": "Captured"}

    monkeypatch.setattr(page_extractor, "extract_page", _extract)
    monkeypatch.setattr(
        page_extractor,
        "persist_page_yoink",
        lambda *_args, **_kwargs: "page-1",
    )

    assert uoink_mcp_tools.uoink_page(
        {
            "url": "https://example.com",
            "include_screenshot": False,
        }
    ) == {
        "ok": True,
        "title": "Captured",
        "video_id": "page-1",
    }
    assert seen["extract"][1]["include_screenshot"] is False


def test_false_screenshot_choice_reaches_core_renderer_unchanged(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        page_extractor,
        "normalize_page_url",
        lambda _url: "https://example.com/",
    )
    monkeypatch.setattr(page_extractor, "_CRAWL4AI_AVAILABLE", True)

    def _extract(_url, **kwargs):
        seen.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(page_extractor, "_extract_crawl4ai", _extract)

    assert page_extractor.extract_page(
        None,
        "https://example.com",
        include_screenshot=False,
        enforce_allowlist=False,
    ) == {"ok": True}
    assert seen["include_screenshot"] is False
