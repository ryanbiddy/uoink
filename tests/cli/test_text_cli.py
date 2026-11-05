"""Human CLI output from synthetic, offline fixtures; JSON remains unchanged."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

import uoink_agent_runtime as runtime
import uoink_cli as cli
from tests.cli.test_research_cli import FakeTools, run


@pytest.fixture
def samples():
    return json.loads((Path(__file__).parents[1] / "fixtures/cli_text.json").read_text(encoding="utf-8"))


@pytest.fixture
def library(samples):
    rows = samples["library"]
    return SimpleNamespace(
        get_yoink=lambda identity: next((row for row in rows if row["video_id"] == identity), None),
        get_by_slug=lambda slug: next((row for row in rows if row.get("slug") == slug), None))


def test_search_text_timestamps_source_and_verified_passages(samples, library):
    assert cli.human(samples["search"], index=library) == (
        '3 result(s)\n'
        'Call stack walkthrough | Example channel | 4:55\u20136:05 [stack000001]\n'
        '  "A function call adds a frame to the stack."\n'
        'Fourier series | Math channel | 18:27\u201319:31 [math0000001]\n'
        'Stack notes | Example author | note [note_123456789ab]\n'
        '  "The stack keeps track of active function calls."')


def test_recent_text_uses_date_kind_source_and_canonical_id(samples, library):
    assert cli.human(samples["recent"], index=library) == (
        '2 result(s)\n'
        '2026-11-04 | article | Understanding the call stack | example.com [page_a1b2c3d4e5f]\n'
        '2026-11-03 | note | Stack notes | Example author [note_123456789ab]')


def test_quotes_are_not_json_escaped(samples):
    assert cli.human(samples["quoted_title"]) == (
        '1 result(s)\n"Simple Made Easy" | Example channel | 0:01\u20131:05 [quotes00001]')
    assert cli.human({"ok": True, "path": r'C:\Notes\"quotes".md'}) == r'C:\Notes\"quotes".md'


@pytest.mark.parametrize("start,end,expected", [
    (0, 59.99, "0:00\u20130:59"), (3599.9, 3665.9, "59:59\u20131:01:05"),
    (3600, 7200, "1:00:00\u20132:00:00"), (295.86, None, "4:55"),
    (295.86, 200, "4:55"), (None, None, "article"),
    (-1, 20, "article"), (float("nan"), 20, "article"),
    (float("inf"), 20, "article"), ("unknown", 20, "article"), (False, 20, "article"),
])
def test_text_timing_boundaries_and_missing_values(start, end, expected):
    payload = {"ok": True, "hits": [{"item_id": "page_abc", "title": "Timing fixture",
               "source_type": "page", "channel": "Example", "start": start, "end": end}]}
    assert cli.human(payload).splitlines()[1] == f"Timing fixture | Example | {expected} [page_abc]"


@pytest.mark.parametrize("verified", [False, None, "true", True])
def test_only_verified_passages_become_quotes(samples, verified):
    payload = deepcopy(samples["search"])
    payload["hits"] = [payload["hits"][0]]
    payload["hits"][0]["passage_verified"] = verified
    text = cli.human(payload)
    assert ('  "A function call' in text) is (verified is True)


def test_quote_is_one_bounded_line_and_can_use_verified_preview(samples):
    row = deepcopy(samples["search"]["hits"][0])
    row.pop("passage")
    row["preview"] = {"text": 'A "frame"\n\treturns control. ' * 15, "truncated": True}
    text = cli.human({"ok": True, "hits": [row]})
    assert len(text.splitlines()) == 3
    quote = text.splitlines()[2]
    assert quote.startswith('  "A "frame" returns control.') and quote.endswith('\u2026"')
    assert len(quote[3:-1]) <= 140
    row["preview"] = {"text": "A short preview", "truncated": True}
    assert '  "A short preview\u2026"' in cli.human({"ok": True, "hits": [row]})


def test_terminal_controls_remain_escaped_in_all_row_fields():
    row = {"item_id": "note_abc\x1b[31m", "title": '"Title"\nextra row',
           "channel": "Source\r\x9b31m", "source_type": "note\x1b[0m",
           "passage_verified": True, "passage": {"text": "Passage\x1b[31m\nnext"}}
    text = cli.human({"ok": True, "hits": [row]})
    assert len(text.splitlines()) == 3
    assert all(char not in text for char in ("\x1b", "\x9b", "\r"))
    assert '"Title"\\nextra row' in text and "\\u001b" in text and "\\u009b" in text


def test_missing_metadata_keeps_the_full_slug_and_never_guesses_a_source(samples):
    text = cli.human(samples["recent"])
    assert "2026-11-04 | item | Understanding the call stack | source unknown" in text
    assert text.splitlines()[1].endswith("[2026-11-04-an-article-about-the-call-stack]")
    def unavailable(_):
        raise sqlite3.OperationalError("index unavailable")
    assert cli.human(samples["recent"], index=SimpleNamespace(get_by_slug=unavailable)) == text


def test_empty_and_bounded_results_keep_existing_limits(samples, library):
    assert cli.human({"ok": True, "hits": []}) == "0 result(s)"
    rows = samples["recent"]["yoinks"] * 6
    text = cli.human({"ok": True, "yoinks": rows}, index=library)
    assert text.startswith("12 result(s)\n") and text.endswith("More results in JSON output.")
    assert len(text.splitlines()) == 12


@pytest.mark.parametrize("name,args", [("search", ["search", "call stack"]),
                                       ("recent", ["recent"]),
                                       ("quoted_title", ["search", "simple"])])
def test_main_text_and_exact_json_output_are_separate(samples, library, monkeypatch, capsys, name, args):
    payload, original = samples[name], deepcopy(samples[name])
    stored = deepcopy(samples["library"])
    def no_index():
        pytest.fail("JSON output must not fetch display metadata")
    server = SimpleNamespace(_get_index=no_index)
    monkeypatch.setattr(cli, "backend", lambda: server)
    monkeypatch.setattr(cli.isolation, "apply_from_process", lambda raw: None)
    monkeypatch.setattr(runtime, "call_tool", lambda name, args, backend: payload)
    expected = (json.dumps(original, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    assert cli.main(args) == 0
    captured = capsys.readouterr()
    assert captured.out.encode("utf-8") == expected and captured.err == ""
    server._get_index = lambda: library
    assert cli.main([*args, "--text"]) == 0
    captured = capsys.readouterr()
    assert captured.out == cli.human(payload, index=library) + "\n" and captured.err == ""
    assert payload == original and samples["library"] == stored
    assert cli.emit(payload) == 0
    assert capsys.readouterr().out.encode("utf-8") == expected


def test_research_compact_scores_and_explain_preserve_payload(tmp_path, samples, capsys):
    candidates = samples["research_candidates"]
    original = deepcopy(candidates)
    def discover_with_fixtures():
        fake = FakeTools()
        def tool(name, args):
            result = fake(name, args)
            if name == "research_discover":
                result["candidates"] = candidates
            return result
        return tool
    args = ["call stack", "--sources", "library", "--yes", "--text"]
    result, _, messages = run(tmp_path, args, discover_with_fixtures())
    assert messages[:2] == [
        '1. "Simple Made Easy" | Example channel | 1:00:50 | saved in library\n'
        '   Why: BM25 relevance: +2.75; Length: +0.50; Library or captions: +0.30',
        '2. Short guide | Another channel | 3:20 | no captions; asr ~4 min\n'
        '   Why: BM25 relevance: +1.01; Length: -0.50']
    explained, _, verbose = run(tmp_path, [*args, "--explain"], discover_with_fixtures())
    assert 'HN points: +0.000000' in verbose[0] and 'BM25 relevance: +2.754240' in verbose[0]
    assert candidates == original and result == explained
    cli.emit(result)
    compact_bytes = capsys.readouterr().out.encode("utf-8")
    cli.emit(explained)
    assert capsys.readouterr().out.encode("utf-8") == compact_bytes
    assert result["discovery"]["candidates"] == original


@pytest.mark.parametrize("changes,status", [
    ({"duration_s": None, "est_capture": "unknown", "has_captions": None}, "captions unknown"),
    ({"has_captions": True}, "captions available"),
    ({"has_captions": False, "est_capture": "unknown"}, "no captions"),
])
def test_research_status_and_zero_scores_do_not_add_empty_lines(samples, changes, status):
    candidate = {**samples["research_candidates"][1], **changes,
                 "why_ranked": ["HN points: +0.000000", "Length: -0.000000", "Recency: +0.000001"]}
    text = cli.research_candidate_text(1, candidate)
    assert len(text.splitlines()) == 1 and text.endswith(status)
    if changes.get("duration_s", 1) is None:
        assert "duration unknown" in text
