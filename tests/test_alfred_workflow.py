"""Alfred workflow: generated plist is current and Script Filter rows are well formed."""
from pathlib import Path
import importlib.util
import plistlib
import subprocess
import sys

import pytest

ALFRED = Path(__file__).resolve().parents[1] / "integrations" / "alfred"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_info_plist_matches_generator():
    result = subprocess.run([sys.executable, str(ALFRED / "build_workflow.py"), "--check"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    info = plistlib.loads((ALFRED / "src" / "info.plist").read_bytes())
    for obj in info["objects"]:
        script = obj["config"].get("script", "")
        # The query arrives as $1 (argv mode); it must never be spliced into script text.
        assert "{query}" not in script
        if script:
            assert obj["config"]["scriptargtype"] == 1


@pytest.fixture()
def workflow():
    return load("uoink_alfred", ALFRED / "src" / "uoink_alfred.py")


def test_search_rows_open_moments_and_copy_citations(workflow, monkeypatch):
    hit = {"item_id": "abc123", "title": "How memory works", "channel": "Learning Lab", "start": 3725,
           "deep_link": "https://youtu.be/abc123?t=3725", "source_link": "https://youtu.be/abc123",
           "evidence_kind": "timed_clip", "passage_verified": True,
           "preview": {"text": "Working memory holds about four chunks.", "truncated": False}}
    monkeypatch.setattr(workflow, "run_uoink", lambda *a, **k: {"ok": True, "hits": [hit], "library_items": 1})
    [row] = workflow.filter_items("memory")
    assert row["arg"] == hit["deep_link"] and row["variables"] == {"action": "open"}
    assert row["subtitle"].startswith("1:02:05 · Learning Lab")
    assert row["mods"]["cmd"]["arg"] == ("> Working memory holds about four chunks.\n>\n"
                                         "> — [How memory works @ 1:02:05](https://youtu.be/abc123?t=3725)")
    assert row["mods"]["ctrl"]["arg"] == hit["source_link"]
    assert row["text"]["copy"] == row["mods"]["cmd"]["arg"]


def test_saved_source_text_is_quoted_by_evidence_kind(workflow):
    base = {"item_id": "abc123", "title": "How memory works", "start": 252.9,
            "deep_link": "https://youtu.be/abc123?t=252", "source_link": "https://youtu.be/abc123"}
    # Timed clips quote saved transcript text; clip rows may not carry passage_verified.
    clip = {**base, "evidence_kind": "timed_clip",
            "preview": {"text": "Working memory holds about\nfour chunks at on", "truncated": True}}
    assert "passage_verified" not in clip
    assert workflow.hit_citation(clip) == ("> Working memory holds about\n> four chunks at on…\n>\n"
                                           "> — [How memory works @ 4:12](https://youtu.be/abc123?t=252)")
    assert workflow.hit_citation({**clip, "passage_verified": False}) == workflow.hit_citation(clip)
    prose = {**base, "start": None, "deep_link": "https://ex.com/p", "evidence_kind": "text_only",
             "preview": {"text": "Saved prose.", "truncated": False}}
    assert workflow.hit_citation(prose) == "> Saved prose.\n>\n> — [How memory works](https://ex.com/p)"
    # A title or metadata match is never quoted, whatever passage_verified says.
    hint = {**base, "start": None, "deep_link": None, "evidence_kind": "discovery_hint",
            "passage_verified": True, "preview": {"text": "…memory holds about…", "truncated": False}}
    assert workflow.hit_citation(hint) == "[How memory works](https://youtu.be/abc123)"
    assert workflow.hit_citation({**hint, "source_link": None}) == "How memory works"
    # Neither is an unknown or missing kind.
    for kind in ("shelf_membership", None):
        odd = {**clip, "evidence_kind": kind}
        assert workflow.hit_citation(odd) == "[How memory works @ 4:12](https://youtu.be/abc123?t=252)"


def test_links_capture_and_missing_app_offers_install(workflow, monkeypatch, tmp_path):
    [row] = workflow.filter_items("https://youtu.be/abc123")
    assert row["variables"] == {"action": "capture"}
    monkeypatch.setenv("uoink_app", str(tmp_path / "Uoink.app"))
    [row] = workflow.filter_items("memory")
    assert row["arg"] == workflow.INSTALL_URL


def test_text_that_starts_with_a_dash_stays_positional(workflow, monkeypatch):
    calls = []
    def fake(*args, **kwargs):
        calls.append(args)
        return {"ok": True, "hits": [], "library_items": 1}
    monkeypatch.setattr(workflow, "run_uoink", fake)
    monkeypatch.setattr(workflow, "notify", lambda *a: None)
    workflow.filter_items("-v")
    workflow.act("capture", "https://example.com/a")
    assert calls[0] == ("search", "--limit", "20", "--", "-v")
    assert calls[1] == ("capture", "--", "https://example.com/a")
