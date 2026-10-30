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
           "preview": {"text": "Working memory holds about four chunks."}}
    monkeypatch.setattr(workflow, "run_uoink", lambda *a, **k: {"ok": True, "hits": [hit], "library_items": 1})
    [row] = workflow.filter_items("memory")
    assert row["arg"] == hit["deep_link"] and row["variables"] == {"action": "open"}
    assert row["subtitle"].startswith("1:02:05 · Learning Lab")
    assert row["mods"]["cmd"]["arg"].endswith("[How memory works @ 1:02:05](https://youtu.be/abc123?t=3725)")
    assert row["mods"]["ctrl"]["arg"] == hit["source_link"]
    assert row["text"]["copy"] == row["mods"]["cmd"]["arg"]


def test_links_capture_and_missing_app_offers_install(workflow, monkeypatch, tmp_path):
    [row] = workflow.filter_items("https://youtu.be/abc123")
    assert row["variables"] == {"action": "capture"}
    monkeypatch.setenv("uoink_app", str(tmp_path / "Uoink.app"))
    [row] = workflow.filter_items("memory")
    assert row["arg"] == workflow.INSTALL_URL
