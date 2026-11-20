"""Before/after routing on 366 made-up saves (tests/fixtures/shelves).

Before = 3.17.0 (topic words only, import folders dropped). After = the
3.18 router through server._route_topic with the fixture library as the
user's shelves. The holdout set uses different wording that was never used
while tuning, so it guards against the router learning the fixture.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures" / "shelves"))
import evaluate  # noqa: E402

import server  # noqa: E402


@pytest.fixture(autouse=True)
def _no_hints(tmp_path, monkeypatch):
    # Folder hints come from the fixture rows, never from a real data folder.
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path)


@pytest.mark.parametrize("holdout", [False, True])
def test_router_halves_uncategorized_without_wrong_shelves(holdout):
    library, items = evaluate.load(holdout=holdout)
    assert len(items) >= 300
    before, after = evaluate.server_functions(server, library)
    report = evaluate.evaluate(before, after, items)
    b, a = report["before"], report["after"]
    assert a["on_uncategorized"] <= 0.6 * b["on_uncategorized"], report
    assert a["correct_share"] >= b["correct_share"] + 0.3, report
    assert a["precision"] >= 0.94 and a["precision"] > b["precision"], report
    # Every wrong shelf left is the soft Clips default, never another topic.
    topical_wrong = [r for r in report["rows"]
                     if r["after"] not in (r["truth"], "Uncategorized", "Clips")]
    assert len(topical_wrong) <= 1, topical_wrong
    groups = report["groups"]
    assert groups["import folder"]["after"]["correct_share"] == 1.0
    assert groups["no shelf fits"]["after"]["wrong_shelf"] <= 1
    assert groups["short clip"]["after"]["correct_share"] >= 0.95


def test_hand_written_cases():
    library, items = evaluate.load()
    before, after = evaluate.server_functions(server, library)
    by_title = {row["title"]: row for row in items}
    react = by_title["React hooks tutorial for beginners"]
    assert before(react) == "Social Media Research"   # 3.17.0 misread the creator's links
    assert after(react) == "Uncategorized"
    jazz = by_title["Rare 1992 interview: a jazz pianist on improvising"]
    assert before(jazz) == "Social Media Research"    # "Subscribe for more threads"
    assert after(jazz) == "Music"
    for title in ("@pixel_loop7: ", "@moss_desk11: 🤯", "wait for it"):
        assert before(by_title[title]) == "Uncategorized"
        assert after(by_title[title]) == "Clips"
