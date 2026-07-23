"""Keep MCP slug lookup inside its deliberately narrow identifier grammar."""

from __future__ import annotations

from typing import Any

import pytest

import uoink_mcp_tools


INVALID_SLUGS: tuple[Any, ...] = (
    None,
    {"slug": "nested"},
    "",
    ".",
    "..",
    "../outside",
    r"..\outside",
    "/absolute",
    r"C:\absolute",
    "nested/child",
    "nested\\child",
    "%2e%2e%2foutside",
    "résumé",
    "a" * 161,
)


@pytest.mark.parametrize("slug", INVALID_SLUGS)
def test_invalid_slug_is_rejected_before_index_or_disk_walk(
    monkeypatch: pytest.MonkeyPatch,
    slug: Any,
) -> None:
    monkeypatch.setattr(
        uoink_mcp_tools,
        "_b",
        lambda: pytest.fail("invalid slug reached the index"),
    )
    monkeypatch.setattr(
        uoink_mcp_tools,
        "_iter_yoink_folders",
        lambda: pytest.fail("invalid slug reached the disk walk"),
    )

    assert uoink_mcp_tools._find_yoink(slug) == (None, None)


@pytest.mark.parametrize(
    "handler",
    (
        uoink_mcp_tools.get_uoink_corpus,
        uoink_mcp_tools.get_citation_map,
        uoink_mcp_tools.get_uoink_health,
        uoink_mcp_tools.analyze_comments_tool,
        uoink_mcp_tools.classify_hook,
    ),
)
def test_every_slug_mcp_handler_uses_the_guarded_lookup(
    monkeypatch: pytest.MonkeyPatch,
    handler,
) -> None:
    class Backend:
        @staticmethod
        def _get_index():
            pytest.fail("traversal reached the index")

    monkeypatch.setattr(
        uoink_mcp_tools,
        "_b",
        lambda: Backend(),
    )
    monkeypatch.setattr(uoink_mcp_tools, "_saved_key", lambda: "test-key")
    monkeypatch.setattr(
        uoink_mcp_tools,
        "_iter_yoink_folders",
        lambda: pytest.fail("traversal reached the disk walk"),
    )

    result = handler({"slug": "../outside"})

    assert result["ok"] is False
    assert result["error"] == "uoink not found"
