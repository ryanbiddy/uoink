"""Flow Launcher plugin: JSON-RPC results from canned CLI payloads."""
from pathlib import Path
import importlib.util
import json

import pytest

MAIN = Path(__file__).resolve().parents[1] / "integrations" / "flow-launcher" / "main.py"


@pytest.fixture()
def plugin(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("uoink_flow_main", MAIN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "STATUS_FILE", tmp_path / "last-capture.json")
    return module


HIT = {"item_id": "abc123", "title": "How memory works", "channel": "Learning Lab", "start": 252.4,
       "deep_link": "https://www.youtube.com/watch?v=abc123&t=252s", "source_link": "https://www.youtube.com/watch?v=abc123",
       # A timed clip quotes saved transcript text; clip rows may not carry passage_verified.
       "evidence_kind": "timed_clip",
       "preview": {"text": "Working memory holds about four chunks.", "truncated": False}}


def test_search_results_open_the_moment_and_copy_a_citation(plugin, monkeypatch):
    calls = []
    def fake(settings, *args, timeout=60):
        calls.append(args)
        return {"ok": True, "hits": [HIT], "library_items": 3}
    monkeypatch.setattr(plugin, "run_uoink", fake)
    [row] = plugin.query("working memory")
    assert calls == [("search", "--limit", "15", "--", "working memory")]
    assert row["title"] == "How memory works"
    assert row["subTitle"].startswith("4:12 · Learning Lab · Working memory")
    assert row["jsonRPCAction"] == {"method": "open_url", "parameters": [HIT["deep_link"]]}
    assert row["copyText"] == ("> Working memory holds about four chunks.\n>\n"
                               "> — [How memory works @ 4:12](https://www.youtube.com/watch?v=abc123&t=252s)")
    menu = plugin.context_menu(row["contextData"])
    assert [item["title"] for item in menu] == ["Copy citation", "Copy link", "Open source", "Copy item ID"]
    assert menu[0]["jsonRPCAction"]["method"] == "Flow.Launcher.CopyToClipboard"
    assert menu[0]["jsonRPCAction"]["parameters"][1:] == [False, True]


def test_saved_source_text_is_quoted_by_evidence_kind(plugin, monkeypatch):
    cut = {**HIT, "preview": {"text": "Working memory holds about four chunks at on", "truncated": True}}
    assert "passage_verified" not in cut
    hint = {**HIT, "start": None, "deep_link": None, "evidence_kind": "discovery_hint", "passage_verified": True,
            "preview": {"text": "…memory holds about…", "truncated": False}}
    unknown = {**HIT, "evidence_kind": "shelf_membership"}
    monkeypatch.setattr(plugin, "run_uoink",
                        lambda *a, **k: {"ok": True, "hits": [cut, hint, unknown], "library_items": 3})
    timed, metadata, odd = plugin.query("memory")
    assert timed["copyText"] == ("> Working memory holds about four chunks at on…\n>\n"
                                 "> — [How memory works @ 4:12](https://www.youtube.com/watch?v=abc123&t=252s)")
    assert metadata["copyText"] == "[How memory works](https://www.youtube.com/watch?v=abc123)"
    assert metadata["contextData"]["citation"] == metadata["copyText"]
    assert odd["copyText"] == "[How memory works @ 4:12](https://www.youtube.com/watch?v=abc123&t=252s)"
    no_kind = {key: value for key, value in HIT.items() if key != "evidence_kind"}
    assert plugin.hit_citation(no_kind) == odd["copyText"]


def test_links_are_offered_for_capture_and_text_is_searched(plugin, monkeypatch):
    monkeypatch.setattr(plugin, "run_uoink", lambda *a, **k: {"ok": True, "hits": [], "library_items": 0})
    [row] = plugin.query("https://youtu.be/abc123")
    assert row["jsonRPCAction"] == {"method": "capture", "parameters": ["https://youtu.be/abc123"]}
    assert plugin.query("javascript:alert(1)")[0]["title"] == "Your library is empty"


def test_text_that_starts_with_a_dash_stays_positional(plugin, monkeypatch):
    calls = []
    def fake(settings, *args, timeout=60):
        calls.append(args)
        return {"ok": True, "hits": [], "library_items": 1}
    monkeypatch.setattr(plugin, "run_uoink", fake)
    plugin.query("-v")
    plugin.capture_worker("https://example.com/a", {})
    assert calls[0] == ("search", "--limit", "15", "--", "-v")
    assert calls[1] == ("capture", "--", "https://example.com/a")


def test_missing_install_points_to_the_install_page(plugin, tmp_path):
    [row] = plugin.query("anything", {"uoinkFolder": str(tmp_path / "nowhere")})
    assert row["title"] == "Uoink isn't installed here"
    assert row["jsonRPCAction"]["parameters"] == [plugin.INSTALL_URL]


def test_capture_worker_records_the_outcome(plugin, monkeypatch):
    def fail(*args, **kwargs):
        raise plugin.UoinkError("host is not in the allowlist")
    monkeypatch.setattr(plugin, "run_uoink", fail)
    assert plugin.capture_worker("https://example.com/a", {}) == 1
    status = json.loads(plugin.STATUS_FILE.read_text(encoding="utf-8"))
    assert status["state"] == "failed" and "allowlist" in status["error"]
    monkeypatch.setattr(plugin, "run_uoink", lambda *a, **k: {"ok": True, "slug": "how-memory-works"})
    assert plugin.capture_worker("https://example.com/a", {}) == 0
    assert plugin.last_capture_row()[0]["title"] == "Uoinked how-memory-works"


def test_uoink_runs_without_flows_pythonpath(plugin, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", r"C:\Flow\JsonRPC")
    assert "PYTHONPATH" not in plugin.uoink_env()
