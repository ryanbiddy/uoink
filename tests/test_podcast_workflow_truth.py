"""The podcast surfaces must not promise an automatic worker that does not exist."""

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_podcast_capture_copy_says_processing_is_on_demand():
    import server

    server_source = _text("server.py")
    dashboard = _text("assets/dashboard/index.html")
    extension_classifier = _text("extension/lib/extract.js")
    popup = _text("extension/popup.js")

    for text in (server_source, dashboard, extension_classifier, popup):
        lowered = text.lower()
        assert "new episodes transcribe locally" not in lowered
        assert "new episodes will transcribe locally" not in lowered
        assert "feed monitor" not in lowered
        assert "track new episodes locally" not in lowered

    detected = server._classify_capture_url(
        "https://example.com/podcast/feed.xml"
    )
    assert detected["note"] == (
        "Adds the RSS feed. Poll, download, and transcribe episodes on demand."
    )
    assert "Poll, download, and transcribe episodes on demand." in (
        extension_classifier
    )
    assert "Podcast feed saved. Poll, download, and transcribe on demand." in (
        dashboard
    )
    assert dashboard.count(
        "Podcast feed saved. Poll, download, and transcribe on demand."
    ) == 2
    assert "Podcast feed saved. Poll, download, and transcribe on demand." in popup
    assert "poll, download, and transcribe episodes on demand" in dashboard
    assert "Saved RSS feed; on-demand poll, download, and transcribe tools" in (
        dashboard
    )


def test_podcast_developer_docs_describe_the_live_on_demand_pipeline():
    podcasts = _text("podcasts.py")
    server = _text("server.py")
    mcp_tools = _text("uoink_mcp_tools.py")

    for stale in (
        "land in subsequent PRs",
        "polling worker lives in server.py",
        "(next PR)",
        "future background poller",
        "next PR in CC's queue",
    ):
        assert stale not in podcasts
        assert stale not in server
        assert stale not in mcp_tools

    assert "There is no background feed scheduler" in server
    assert "invoked on demand through the HTTP and MCP surfaces" in podcasts
    module = ast.parse(mcp_tools)
    download = next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "download_podcast_episode"
    )
    download_doc = " ".join((ast.get_docstring(download) or "").split())
    assert "The live transcription pipeline reads audio_local_path" in download_doc
