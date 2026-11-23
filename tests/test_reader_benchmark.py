"""Reader benchmark floors: web pages must keep saving as clean, complete text.

The fixtures, scorer and both capture paths live in tests/reader_bench.py and
tests/fixtures/reader. These tests fail when recall, precision, structure,
metadata or the honest outcome (article, wall, shell) drops below the floors in
tests/fixtures/reader/thresholds.json. Raise the floors on purpose with
`python tests/reader_bench.py --update-thresholds` after a real improvement.
"""
from __future__ import annotations

import importlib.util
import json
import re
import socket
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import reader_bench as bench  # noqa: E402

THRESHOLDS = json.loads(bench.THRESHOLDS.read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("The reader benchmark must not touch the network")
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)


def _generator():
    spec = importlib.util.spec_from_file_location("reader_make_fixtures", bench.FIXTURES / "make_fixtures.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fixture_files_match_their_generator():
    module = _generator()
    built = module.build()
    assert 25 <= len(module.FIXTURES) <= 40
    for name, text in built.items():
        path = bench.FIXTURES / name
        assert path.is_file(), f"{name} missing: run python tests/fixtures/reader/make_fixtures.py"
        assert path.read_text(encoding="utf-8") == text, f"{name} is stale: rerun make_fixtures.py"


def test_fixtures_only_use_example_domains():
    hosts = set()
    for path in bench.FIXTURES.glob("*.html"):
        hosts.update(re.findall(r"https?://([^/\"'\s)<>]+)", path.read_text(encoding="utf-8")))
    # Vocabulary URLs (schema.org, the MathML namespace) are not links to real pages.
    allowed = re.compile(r"(^|\.)example(\.[a-z]+)?$|\.test$|^www\.w3\.org$|^schema\.org$")
    assert hosts and all(allowed.search(host.split(":")[0]) for host in hosts), sorted(hosts)
    for path in bench.FIXTURES.glob("*.gold.json"):
        gold = json.loads(path.read_text(encoding="utf-8"))
        assert re.search(r"(^|\.)example(\.[a-z]+)?$", re.match(r"https?://([^/]+)", gold["url"]).group(1))


def test_scorer_rewards_gold_and_punishes_loss_and_junk():
    fixture = bench.load_fixtures(["docs-code"])[0]
    gold = fixture["gold"]
    perfect = "\n\n".join(gold["keep"])  # the title is already the first kept block
    row = bench.score_fixture(gold, {"outcome": "article", "title": "", "markdown": perfect,
                                     "metadata": {"title": gold["title"]}}, "article")
    assert row["recall"] == pytest.approx(1.0) and row["precision"] == pytest.approx(1.0)
    assert row["junk_leaks"] == 0
    lossy = "\n\n".join(gold["keep"][: len(gold["keep"]) // 2] + gold["junk"][:2])
    worse = bench.score_fixture(gold, {"outcome": "article", "title": gold["title"], "markdown": lossy,
                                       "metadata": {}}, "article")
    assert worse["recall"] < 0.8 and worse["precision"] < 1.0 and worse["junk_leaks"] == 2
    missing = bench.score_fixture(gold, {"outcome": "wall", "markdown": ""}, "article")
    assert missing["recall"] == 0.0 and not missing["outcome_ok"]


def test_structure_checks_read_markdown_forms():
    md = ("# Title\n\n## Part one\n\n- first item\n1. second item\n\n```python\nx = 1\n```\n\n"
          "| a | b |\n| --- | --- |\n| 1 | 2 |\n\n[docs](https://x.example/d) ![a cat](https://x.example/c.jpg)\n\n"
          "> quoted words\n\nText[^1] and $E = mc^2$.\n\n[^1]: The note text.\n")
    structure = {"headings": ["Part one"], "list_items": ["first item", "second item"],
                 "code": [{"text": "x = 1", "lang": "python"}], "tables": [[["a", "b"], ["1", "2"]]],
                 "links": [{"text": "docs", "href": "https://x.example/d"}],
                 "images": [{"alt": "a cat", "src": "https://x.example/c.jpg"}], "quotes": ["quoted words"],
                 "footnotes": ["The note text."], "math": ["E = mc^2"], "captions": []}
    scores = bench.structure_scores(structure, md)
    assert all(found == total for found, total in scores.values()), scores
    assert bench.structure_scores(structure, "plain words only")["code"] == (0, 1)


def _assert_floors(path, rows, agg):
    assert path in THRESHOLDS, f"no floors for {path}: run reader_bench.py --update-thresholds"
    problems = bench.check_floors(rows, agg, THRESHOLDS[path])
    assert not problems, f"{path} reader benchmark dropped:\n" + "\n".join(problems)


def test_pasted_link_path_meets_its_floors(monkeypatch):
    import page_extractor
    monkeypatch.setattr(page_extractor, "_CRAWL4AI_AVAILABLE", False)
    rows, agg = bench.run("helper", bench.load_fixtures())
    _assert_floors("helper", rows, agg)


def test_extension_path_meets_its_floors():
    if not bench.extension_available():
        bench.jsdom_gate("The Uoink this page benchmark")
    rows, agg = bench.run("extension", bench.load_fixtures())
    _assert_floors("extension", rows, agg)


def test_a_missing_jsdom_never_hides_behind_a_green_job(monkeypatch):
    for key in ("UOINK_READER_BENCH_REQUIRED", "UOINK_READER_BENCH_SKIP", "CI"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(pytest.skip.Exception, match="npm ci"):
        bench.jsdom_gate("checks")  # a dev machine: a named skip
    monkeypatch.setenv("CI", "true")
    with pytest.raises(pytest.fail.Exception, match="missing in CI"):
        bench.jsdom_gate("checks")  # CI that does not say where they run: fails
    monkeypatch.setenv("UOINK_READER_BENCH_SKIP", "they run in ci.yml stdlib-tests")
    with pytest.raises(pytest.skip.Exception, match="stdlib-tests"):
        bench.jsdom_gate("checks")
    monkeypatch.setenv("UOINK_READER_BENCH_REQUIRED", "1")
    with pytest.raises(pytest.fail.Exception, match="required"):
        bench.jsdom_gate("checks")  # the job that owns them always fails without jsdom
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    mac = (ROOT / ".github/workflows/mac-qualify.yml").read_text(encoding="utf-8")
    assert 'UOINK_READER_BENCH_REQUIRED: "1"' in ci and "npm ci --prefix tests/js/reader" in ci
    assert "UOINK_READER_BENCH_SKIP:" in mac


def test_a_capture_that_changes_the_page_calls_out_or_crashes_scores_as_an_error(monkeypatch):
    import types
    names = ["short-post", "spanish-article", "recipe"]
    fake = {"results": {
        "short-post": {"ok": True, "mutated": True, "net_calls": 0, "payload": {}},
        "spanish-article": {"ok": False, "code": "reader_failed", "error": "boom"},
        "recipe": {"ok": True, "mutated": False, "net_calls": 2, "payload": {}}}}
    monkeypatch.setattr(bench.shutil, "which", lambda _name: "node")
    monkeypatch.setattr(bench.subprocess, "run", lambda *_a, **_k: types.SimpleNamespace(
        returncode=0, stdout=json.dumps(fake), stderr=""))
    out = bench.run_extension_all(bench.load_fixtures(names))
    assert {name: row["outcome"] for name, row in out.items()} == dict.fromkeys(names, "error")
