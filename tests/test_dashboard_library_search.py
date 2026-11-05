"""Library defaults use the CLI's stored search passages on a disposable corpus."""
import json
from pathlib import Path
import subprocess
from urllib.parse import urlencode

import pytest

import index
import library_resources
import server
from tests.phase4_fixtures import seed_yoink_item


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def dashboard_query():
    result = subprocess.run(
        ["node", str(ROOT / "tests/js/dash_search_sequencing_test.mjs"), "search_modes"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    line = next(line for line in result.stdout.splitlines() if line.startswith("library_search_params: "))
    return json.loads(line.split(": ", 1)[1])


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(server, "DESKTOP_ROOT", tmp_path)
    monkeypatch.setattr(server, "_read_settings", lambda: {})
    monkeypatch.setattr(server, "_check_memory_search_rate_limit", lambda: True)
    with index.Index.open(tmp_path / "index.db") as idx:
        monkeypatch.setattr(server, "_get_index", lambda: idx)
        for vid, title, text, start, kind, day in [
            ("moon", "Moon Base episode", "A pressurized rover lets the crew explore from the Moon Base.", 92.5, "episode", 1),
            ("rovers", "Rovers video", "The pressurized rover carries supplies across the lunar surface.", 214, "video", 2),
            ("defenders", "Planetary Defenders", "A rover detects an approaching asteroid.", 18, "video", 3),
        ]:
            item = seed_yoink_item(
                idx, tmp_path, video_id=vid, slug=vid, title=title,
                corpus_text=text, source_type=kind,
                yoinked_at=f"2026-11-0{day}T12:00:00",
                clips=[{"start": start, "end": start + 12, "text": text}],
            )
            idx.upsert_yoink(item, content=text)
        yield idx


def search(params):
    handler = server.Handler.__new__(server.Handler)
    handler.path = "/memory/search?" + urlencode(params)
    replies = []
    handler._send_json = lambda code, body: replies.append((code, body))
    handler._handle_memory_search()
    code, body = replies[0]
    assert code == 200, body
    return body


def test_dashboard_narrows_to_all_words_and_reuses_cli_passages(corpus, dashboard_query):
    body = search(dashboard_query)
    assert body["total"] == 2
    rows = body["results"]
    assert {row["video_id"] for row in rows} == {"moon", "rovers"}
    reader = library_resources.LibraryReader(corpus, data_root=corpus._path.parent)
    cli = library_resources.call_tool("search_library", {
        "query": dashboard_query["q"], "match": "strict", "mode": "keyword",
    }, reader)
    assert cli["ok"], cli
    assert [row["video_id"] for row in rows] == [hit["item_id"] for hit in cli["hits"]]
    for row, hit in zip(rows, cli["hits"]):
        clip = corpus.get_clips(row["video_id"])[0]
        assert row["passage_verified"] is True
        assert row["passage"]["text"] == clip["text"] == hit["preview"]["text"]
        assert row["timestamp_seconds"] == clip["start"] == hit["start"]


@pytest.mark.parametrize("kind,expected", [("videos", "rovers"), ("podcasts", "moon")])
def test_dashboard_type_filters_keep_ranked_timed_matches(corpus, dashboard_query, kind, expected):
    body = search({**dashboard_query, "kind": kind})
    assert body["total"] == 1
    assert body["results"][0]["video_id"] == expected
    assert body["results"][0]["passage_verified"] is True
    assert body["results"][0]["timestamp_seconds"] > 0


def test_dashboard_keeps_alternate_sort_matching_and_paging(corpus, dashboard_query):
    params = {**dashboard_query, "sort": "oldest", "limit": 1}
    first = search(params)
    second = search({**params, "offset": 1})
    assert first["total"] == second["total"] == 2
    assert first["results"][0]["video_id"] == "moon"
    assert second["results"][0]["video_id"] == "rovers"
    broad = search({**dashboard_query, "match": "forgiving", "sort": "newest"})
    assert broad["total"] == 3
    assert broad["results"][0]["video_id"] == "defenders"
    browse = search({**dashboard_query, "q": "", "sort": "newest"})
    assert [row["video_id"] for row in browse["results"]] == ["defenders", "rovers", "moon"]


def test_dashboard_all_words_does_not_run_semantic_expansion(corpus, dashboard_query):
    calls = []

    class ReadySearch:
        enabled = True

        def status(self):
            return {"acceptance": True, "paused": False, "state": "ready"}

        def embedding_search(self, *args, **kwargs):
            calls.append(args)
            return []

    corpus._local_search = ReadySearch()
    body = search(dashboard_query)
    assert body["total"] == 2
    assert body["search_mode"] == "keyword"
    assert calls == []


def test_dashboard_search_browser():
    result = subprocess.run(
        ["node", str(ROOT / "tests/js/dashboard_library_search_browser.mjs")],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=120,
    )
    if result.returncode == 77 and result.stdout.startswith("SKIP Library search browser:"):
        pytest.skip(result.stdout.strip())
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS Library search browser: 4 viewport/theme combinations" in result.stdout
