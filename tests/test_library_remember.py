"""Rediscover shelf and idea starters: selection logic, index tracking, API."""
from __future__ import annotations

import json
import sys
import threading
import urllib.error
import urllib.request
from datetime import date
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import index as index_mod  # noqa: E402
import library_remember as lr  # noqa: E402
import server  # noqa: E402

TODAY = date(2026, 11, 12)


def row(i, saved, **extra):
    base = {"video_id": f"vid{i:03d}", "title": f"Title {i}", "topic": None,
            "yoinked_at": saved + "T09:00:00", "source_type": "video",
            "platform": "youtube", "author": "Ana", "channel": "Ana",
            "last_opened_at": "2026-11-01T10:00:00", "touched": 0}
    base.update(extra)
    return base


def library(extra=()):
    """Ten opened filler saves (all outside every window) plus extras."""
    rows = [row(i, "2026-09-0%d" % (i % 9 + 1)) for i in range(10)]
    return rows + list(extra)


def test_windows_week_month_on_this_day_never():
    cases = {
        "week": row(50, "2026-11-05"),
        "month": row(51, "2026-10-13"),
        "on_this_day": row(52, "2024-11-12"),
        "never": row(53, "2026-10-01", last_opened_at=None),
    }
    for want, r in cases.items():
        assert lr.bucket_for(r, TODAY)[0] == want
    assert lr.bucket_for(row(54, "2026-11-12", last_opened_at=None), TODAY) is None  # too new
    assert lr.bucket_for(row(55, "2026-11-09"), TODAY) is None  # opened, not in a window
    assert lr.bucket_for(row(56, "2026-11-13"), TODAY) is None  # future
    assert lr.bucket_for(row(57, "not a date"), TODAY) is None
    assert lr.bucket_for(row(58, "2026-10-01", last_opened_at=None, touched=1), TODAY) is None


def test_reasons_read_plainly():
    assert lr.bucket_for(row(1, "2026-10-13"), TODAY)[1] == "Saved 1 month ago"
    assert lr.bucket_for(row(1, "2026-11-05"), TODAY)[1] == "Saved 1 week ago"
    assert lr.bucket_for(row(1, "2024-11-12"), TODAY)[1] == "Saved on this day in 2024"
    assert lr.bucket_for(row(1, "2026-10-01", last_opened_at=None), TODAY)[1] == "You haven't opened this yet"


def test_picks_one_of_each_reason_first_and_caps_at_four():
    rows = library([row(50, "2026-11-05"), row(51, "2026-10-13"), row(52, "2024-11-12"),
                    row(53, "2026-10-01", last_opened_at=None),
                    row(54, "2026-10-02", last_opened_at=None),
                    row(55, "2026-11-04"), row(56, "2026-10-12")])
    picks = lr.pick_rediscover(rows, TODAY)
    assert len(picks) == 4
    assert {p["bucket"] for p in picks} == {"on_this_day", "month", "week", "never"}
    assert len({p["video_id"] for p in picks}) == 4


def test_deterministic_per_day_and_varies_across_days():
    rows = library([row(100 + i, "2026-09-20", last_opened_at=None) for i in range(30)])
    a = lr.pick_rediscover(rows, TODAY)
    b = lr.pick_rediscover(list(reversed(rows)), TODAY)
    assert [p["video_id"] for p in a] == [p["video_id"] for p in b]
    other = lr.pick_rediscover(rows, date(2026, 11, 13))
    assert [p["video_id"] for p in a] != [p["video_id"] for p in other]


def test_small_library_hides_the_shelf():
    rows = [row(i, "2026-10-01", last_opened_at=None) for i in range(lr.MIN_LIBRARY_ITEMS - 1)]
    assert lr.pick_rediscover(rows, TODAY) == []
    assert lr.pick_starters([row(i, "2026-10-01", topic="Pricing") for i in range(4)], TODAY) == []
    rows.append(row(99, "2026-10-01", last_opened_at=None))
    assert lr.pick_rediscover(rows, TODAY)


def test_starters_share_a_topic_and_never_repeat_items():
    rows = library()
    for i in range(3):
        rows.append(row(60 + i, "2026-10-20", topic="Onboarding"))
    for i in range(2):
        rows.append(row(70 + i, "2026-10-20", topic="Pricing"))
    rows.append(row(80, "2026-10-20", topic="Solo topic"))
    rows.append(row(81, "2026-10-20", topic="Other"))
    rows.append(row(82, "2026-10-20", topic="Other"))
    starters = lr.pick_starters(rows, TODAY)
    assert {s["topic"] for s in starters} == {"Onboarding", "Pricing"}
    seen = []
    for s in starters:
        topics = {next(r["topic"] for r in rows if r["video_id"] == it["video_id"]) for it in s["items"]}
        assert topics == {s["topic"]}
        assert 2 <= len(s["items"]) <= 3
        seen += [it["video_id"] for it in s["items"]]
    assert len(seen) == len(set(seen))
    onboarding = next(s for s in starters if s["topic"] == "Onboarding")
    assert onboarding["prompt"].startswith("You saved 3 things about Onboarding.")
    assert "Title 6" in onboarding["copy_prompt"] and "Onboarding" in onboarding["copy_prompt"]
    assert "—" not in onboarding["prompt"] + onboarding["copy_prompt"]


def test_starters_capped_at_three_and_deterministic():
    rows = library()
    for t in range(6):
        for i in range(2):
            rows.append(row(200 + t * 2 + i, "2026-10-20", topic=f"Topic {t}"))
    a = lr.pick_starters(rows, TODAY)
    assert len(a) == 3
    assert a == lr.pick_starters(list(reversed(rows)), TODAY)


# ---- index + API ----------------------------------------------------------

def seed(idx, root, vid, title, saved, topic="Onboarding"):
    folder = Path(root) / vid
    folder.mkdir(parents=True, exist_ok=True)
    idx.upsert_yoink({
        "video_id": vid, "slug": vid, "channel": "Ana", "title": title, "topic": topic,
        "hook_type": "curiosity_gap", "yoinked_at": saved,
        "corpus_path": str(folder / "corpus.md"), "sidecar_path": "", "source_type": "video",
    }, content=f"{title} body")


@pytest.fixture
def idx(tmp_path):
    return index_mod.Index.open(tmp_path / "index.db")


def test_mark_opened_tracks_live_items_only(idx, tmp_path):
    seed(idx, tmp_path, "aaa", "A", "2026-10-01T09:00:00")
    seed(idx, tmp_path, "bbb", "B", "2026-10-01T09:00:00")
    assert idx.mark_opened("aaa") is True
    assert idx.mark_opened("missing") is False
    assert idx.mark_opened("") is False
    rows = {r["video_id"]: r for r in idx.remember_rows()}
    assert rows["aaa"]["last_opened_at"] and rows["bbb"]["last_opened_at"] is None
    idx.soft_delete_yoink("bbb")
    assert "bbb" not in {r["video_id"] for r in idx.remember_rows()}
    assert idx.mark_opened("bbb") is False
    # A re-save keeps the opened mark.
    seed(idx, tmp_path, "aaa", "A again", "2026-10-01T09:00:00")
    assert {r["video_id"]: r for r in idx.remember_rows()}["aaa"]["last_opened_at"]


def test_engagement_counts_as_touched(idx, tmp_path):
    seed(idx, tmp_path, "aaa", "A", "2026-10-01T09:00:00")
    seed(idx, tmp_path, "bbb", "B", "2026-10-01T09:00:00")
    idx.log_engagement("aaa", "cite", "mcp")
    idx.log_engagement("bbb", "search_hit", "mcp")
    rows = {r["video_id"]: r for r in idx.remember_rows()}
    assert rows["aaa"]["touched"] == 1 and rows["bbb"]["touched"] == 0


@pytest.fixture
def api(idx, tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    settings = {"rediscover_shelves_enabled": True}
    monkeypatch.setattr(server, "_read_settings", lambda: dict(settings))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    def call(method, path, body=None, token=True):
        headers = {"X-Uoink-Token": server.TOKEN} if token else {}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode() or "{}")
    call.settings = settings
    yield call
    httpd.shutdown()
    httpd.server_close()


def test_api_requires_token_and_validates(api):
    assert api("GET", "/library/remember", token=False)[0] == 403
    assert api("POST", "/library/opened", {"video_id": "x"}, token=False)[0] == 403
    assert api("GET", "/library/remember?today=nope")[0] == 400
    assert api("POST", "/library/opened", {})[0] == 400


def test_api_returns_picks_and_respects_setting(api, idx, tmp_path):
    for i in range(10):
        seed(idx, tmp_path, f"v{i:02d}", f"Video {i}", "2026-10-01T09:00:00",
             topic="Onboarding" if i < 3 else f"Topic {i}")
    status, data = api("GET", "/library/remember?today=2026-11-12")
    assert status == 200 and data["enabled"] is True
    assert data["rediscover"] and all(c["reason"] for c in data["rediscover"])
    assert [s["topic"] for s in data["starters"]] == ["Onboarding"]
    assert api("GET", "/library/remember?today=2026-11-12")[1] == data  # same day, same picks
    # Opening an item removes it from "never opened".
    for c in data["rediscover"]:
        api("POST", "/library/opened", {"video_id": c["video_id"]})
    _, after = api("GET", "/library/remember?today=2026-11-12")
    assert not {c["video_id"] for c in data["rediscover"]} & {c["video_id"] for c in after["rediscover"]}
    api.settings["rediscover_shelves_enabled"] = False
    status, off = api("GET", "/library/remember")
    assert status == 200 and off["enabled"] is False and off["rediscover"] == [] and off["starters"] == []


def test_setting_default_normalizes_and_is_public():
    key = "rediscover_shelves_enabled"
    assert server._default_settings()[key] is True
    assert server._normalize_settings({})[key] is True
    assert server._normalize_settings({key: False})[key] is False
    assert server._public_settings({key: False})[key] is False
    assert server._public_settings({})[key] is True


def test_deleted_items_never_picked(api, idx, tmp_path):
    for i in range(10):
        seed(idx, tmp_path, f"v{i:02d}", f"Video {i}", "2026-10-01T09:00:00", topic=f"T{i}")
    idx.soft_delete_yoink("v03")
    _, data = api("GET", "/library/remember?today=2026-11-12")
    assert "v03" not in {c["video_id"] for c in data["rediscover"]}
