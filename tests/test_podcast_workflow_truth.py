"""Product surfaces must describe the live podcast watch boundary exactly."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_capture_copy_promises_metadata_watch_not_default_transcription():
    import server

    server_source = _text("server.py")
    dashboard = _text("assets/dashboard/index.html")
    extension_classifier = _text("extension/lib/extract.js")
    popup = _text("extension/popup.js")

    for text in (server_source, dashboard, extension_classifier, popup):
        lowered = text.lower()
        assert "new episodes transcribe locally" not in lowered
        assert "new episodes will transcribe locally" not in lowered

    detected = server._classify_capture_url(
        "https://example.com/podcast/feed.xml")
    assert detected["note"] == (
        "Adds the RSS feed and watches for new episode metadata. "
        "Audio processing stays off until Auto-ingest is enabled."
    )
    assert "Audio stays off by default." in extension_classifier
    assert dashboard.count(
        "Podcast feed saved. Uoink will watch for new episodes; audio stays off by default."
    ) == 1
    assert popup.count(
        "Podcast feed saved. Uoink will watch metadata; audio stays off."
    ) == 2
    assert "Per-feed Auto-ingest can download, transcribe, and publish locally." in dashboard


def test_developer_docs_and_code_describe_the_live_scheduler():
    podcasts_source = _text("podcasts.py")
    server_source = _text("server.py")
    mcp_tools = _text("uoink_mcp_tools.py")
    api_docs = _text("docs/v2-api.md")
    mcp_docs = _text("docs/v2-mcp.md")

    for stale in (
        "land in subsequent PRs",
        "(next PR)",
        "future background poller",
        "next PR in CC's queue",
        "There is no background feed scheduler",
    ):
        assert stale not in podcasts_source
        assert stale not in server_source
        assert stale not in mcp_tools

    assert "_PODCAST_FEED_TICK_SEC = 30" in server_source
    assert "_start_podcast_feed_scheduler_thread()" in server_source
    assert "auto_ingest" in podcasts_source
    assert "defaults off" in mcp_tools
    assert "every 30 seconds" in api_docs
    assert "defaults to `false`" in mcp_docs


def test_podcast_timestamp_docs_do_not_promise_player_seeking():
    schema_docs = _text("docs/schema.md")
    normalized_schema = " ".join(schema_docs.split())
    assert (
        "Fragment seeking depends on the target player; the visible "
        "`HH:MM:SS` label is the authoritative reference."
    ) in normalized_schema

    developer_docs = "\n".join([
        schema_docs,
        _text("docs/v2-api.md"),
        _text("docs/v2-mcp.md"),
        _text("docs/surface-maps/source-taxonomy.md"),
    ]).lower()
    for unsupported_claim in (
        "opens at the exact timestamp",
        "jumps to the timestamp",
        "seeks directly to",
    ):
        assert unsupported_claim not in developer_docs
