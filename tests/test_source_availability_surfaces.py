"""Availability surfaces use local indexes, handler probes and mocked browser I/O."""

from datetime import datetime, timedelta
from pathlib import Path
import re
import subprocess
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest

import uoink_mcp_tools as tools
from tests.test_source_availability import T0, helper, idx, iso, no_network, save  # noqa: F401


ROOT = Path(__file__).resolve().parents[1]
GONE = {"deleted", "private", "region_blocked"}
STATUSES = ("deleted", "private", "region_blocked", "available", "unknown", "never", "pending", "trash")


@pytest.fixture
def library(idx, helper, tmp_path, monkeypatch):
    for n, status in enumerate(STATUSES):
        row = save(idx, status)
        row.update(title=f"Needle {status}", channel="Saved channel",
                   source_type="x_thread" if status == "private" else "video",
                   yoinked_at=iso(T0 + timedelta(minutes=n)))
        idx.upsert_yoink(row, content=f"Needle passage from {status}.")
        idx.insert_citations(status, [{
            "kind": "transcript_chunk", "seq": seq,
            "timestamp_start": seq * 60, "timestamp_end": seq * 60 + 50,
            "text": f"Needle passage {seq} from {status}.",
        } for seq in range(2)])
        if status != "never":
            tracked = "deleted" if status == "trash" else "unknown" if status == "pending" else status
            idx.record_availability(status, status=tracked, last_checked_at=iso(),
                                    gone_since=iso() if tracked in GONE else None,
                                    pending_status="deleted" if status == "pending" else None)
    idx.soft_delete_yoink("trash")
    monkeypatch.setattr(helper, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(helper, "_get_index", lambda: idx)
    monkeypatch.setattr(helper, "_check_memory_search_rate_limit", lambda: True)
    monkeypatch.setattr(helper, "_read_settings", lambda: {"source_availability_check_enabled": True})
    monkeypatch.setattr(tools, "_backend", SimpleNamespace(_get_index=lambda: idx))
    return idx


def probe(helper, path, *, token=True):
    handler = helper.Handler.__new__(helper.Handler)
    handler.path = path
    handler.command = "GET"
    handler.headers = {"X-Uoink-Token": helper.TOKEN} if token else {}
    sent = []
    handler._send_json = lambda status, payload: sent.append((status, payload))
    return handler, sent


def search(helper, **params):
    # Same direct handler pattern as test_rehaul_library_reader; no HTTP server.
    handler, sent = probe(helper, "/memory/search?" + urlencode(params))
    handler._handle_memory_search()
    return sent[-1]


def spy_availability(monkeypatch, idx, *, broken=False):
    calls = []
    original = idx.availability_for

    def read(ids):
        calls.append(list(ids))
        if broken:
            raise RuntimeError("availability lookup unavailable")
        return original(ids)

    monkeypatch.setattr(idx, "availability_for", read)
    return calls


@pytest.mark.parametrize("broken", [False, True])
def test_enrich_adds_public_status_in_one_batch(library, helper, monkeypatch, broken):
    rows = library.search_yoinks_for_memory()["results"]
    calls = spy_availability(monkeypatch, library, broken=broken)
    enriched = helper._enrich_yoink_rows(library, rows)
    assert len(calls) == 1
    assert set(calls[0]) == {row["video_id"] for row in rows}
    assert len(enriched) == len(rows)
    for row in enriched:
        vid = row["video_id"]
        assert row["source_status"] == {
            "status": vid if not broken and vid in GONE | {"available"} else "unknown",
            "last_checked_at": iso() if not broken and vid != "never" else None,
            "gone_since": iso() if not broken and vid in GONE else None,
        }


def test_empty_enrichment_needs_no_lookup(library, helper, monkeypatch):
    calls = spy_availability(monkeypatch, library)
    assert helper._enrich_yoink_rows(library, []) == []
    assert calls == []


@pytest.mark.parametrize("query", [None, "needle"])
@pytest.mark.parametrize("match", ["forgiving", "strict"])
def test_index_filter_counts_all_matches_before_paging(library, query, match):
    all_rows = library.search_yoinks_for_memory(q=query, match=match, availability="gone")
    expected = [r["video_id"] for r in all_rows["results"]]
    assert set(expected) == GONE
    assert all_rows["total"] == 3
    for offset in (0, 1, 2, 3, 200):
        page = library.search_yoinks_for_memory(q=query, match=match, availability="gone", limit=1, offset=offset)
        assert page["total"] == 3
        assert [r["video_id"] for r in page["results"]] == expected[offset:offset + 1]
    assert library.search_yoinks_for_memory(q=query, match=match)["total"] == 7


def test_index_filter_composes_with_other_filters(library):
    page = library.search_yoinks_for_memory(q="needle", availability="gone", source_type="x_thread",
                                           channel="Saved channel", date_from="2026-11-03", date_to="2026-11-03")
    assert page["total"] == 1 and page["results"][0]["video_id"] == "private"
    assert library.search_yoinks_for_memory(availability="gone", channel="Other")["total"] == 0
    assert library.search_yoinks_for_memory(q="unmatched", availability="gone")["total"] == 0
    with pytest.raises(ValueError, match="availability must be gone"):
        library.search_yoinks_for_memory(availability="available")


@pytest.mark.parametrize("value", ["available", "deleted", "private", "unknown", "Gone", "gone,private"])
def test_memory_search_rejects_invalid_availability(library, helper, value):
    assert search(helper, availability=value) == (400, {"ok": False, "error": "availability must be gone"})


@pytest.mark.parametrize("value,total", [("", 7), ("gone", 3)])
def test_memory_search_accepts_empty_or_gone(library, helper, value, total):
    status, page = search(helper, availability=value)
    assert status == 200 and page["total"] == total and page["corpus_total"] == 7
    assert len(page["results"]) == total


@pytest.mark.parametrize("mode", ["auto", "semantic", "hybrid", "keyword"])
@pytest.mark.parametrize("sort,kind,total", [
    ("relevance", "", 3), ("title", "", 3), ("oldest", "videos", 2), ("newest", "posts", 1),
])
def test_memory_filter_composes_and_never_uses_unfiltered_semantics(library, helper, monkeypatch, mode, sort, kind, total):
    def forbidden(*args, **kwargs):
        pytest.fail("Semantic retrieval cannot honor availability")

    engine = SimpleNamespace(enabled=True, status=lambda: {"acceptance": True, "paused": False, "state": "ready"},
                             embedding_search=forbidden)
    monkeypatch.setattr(library, "_local_search", engine)
    params = dict(q="needle", availability="gone", sort=sort, kind=kind, mode=mode, limit=1)
    status, page = search(helper, **params)
    assert status == 200 and page["total"] == total and page["corpus_total"] == 7
    assert len(page["results"]) == 1 and page["results"][0]["video_id"] in GONE
    assert page["results"][0]["source_status"]["status"] in GONE
    assert page["search_mode"] == "keyword" and page["requested_mode"] == mode
    if mode != "keyword":
        assert "availability" in page["fallback_reason"].lower()
    status, empty = search(helper, **params, offset=100)
    assert status == 200 and empty["total"] == total and empty["results"] == []


@pytest.mark.parametrize("enabled", [True, False])
def test_availability_route_payload(library, helper, monkeypatch, enabled):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return T0

    monkeypatch.setattr(helper, "datetime", Clock)
    monkeypatch.setattr(helper, "_read_settings", lambda: {"source_availability_check_enabled": enabled})
    library.set_availability_run_state(last_run_finished_at=iso())
    handler, sent = probe(helper, "/library/availability")
    handler.do_GET()
    assert sent == [(200, {
        "ok": True, "enabled": enabled, "gone_total": 3, "gone_this_month": 3, "checked_total": 6,
        "by_status": {"available": 1, "deleted": 1, "private": 1, "region_blocked": 1, "unknown": 2},
        "last_run_finished_at": iso(),
    })]


def test_availability_route_defaults_and_empty_library(idx, helper, monkeypatch):
    monkeypatch.setattr(helper, "_get_index", lambda: idx)
    monkeypatch.setattr(helper, "_read_settings", lambda: {})
    handler, sent = probe(helper, "/library/availability")
    handler.do_GET()
    assert sent == [(200, {
        "ok": True, "enabled": True, "gone_total": 0, "gone_this_month": 0, "checked_total": 0,
        "by_status": dict.fromkeys(("available", "deleted", "private", "region_blocked", "unknown"), 0),
        "last_run_finished_at": None,
    })]


def test_availability_route_is_token_gated(helper, monkeypatch):
    monkeypatch.setattr(helper, "_get_index", lambda: pytest.fail("Private data read before authentication"))
    for direct in (True, False):
        handler, sent = probe(helper, "/library/availability", token=False)
        (handler._handle_library_availability if direct else handler.do_GET)()
        assert sent == [(403, {"ok": False, "error": "missing or invalid token"})]


def test_availability_route_reports_unavailable(helper, monkeypatch):
    def broken():
        raise RuntimeError("index unavailable")

    monkeypatch.setattr(helper, "_get_index", broken)
    handler, sent = probe(helper, "/library/availability")
    handler.do_GET()
    assert sent == [(503, {"ok": False, "error": "availability unavailable", "state": "unavailable"})]


@pytest.mark.parametrize("tool", [tools.search_uoinks, tools.search_clips])
@pytest.mark.parametrize("broken", [False, True])
def test_mcp_search_statuses_use_one_lookup_per_page(library, monkeypatch, tool, broken):
    calls = spy_availability(monkeypatch, library, broken=broken)
    page = tool({"query": "needle", "limit": 50, "mode": "keyword"})
    assert page["ok"] and len(calls) == 1
    assert set(calls[0]) == set(STATUSES) - {"trash"}
    assert len(page["results"]) == (14 if tool is tools.search_clips else 7)
    for row in page["results"]:
        vid = row["video_id"]
        assert row["source_status"] == (vid if not broken and vid in GONE | {"available"} else "unknown")
        assert row["source_last_checked"] == (iso() if not broken and vid != "never" else None)
        assert row["passage_verified"] is True
    calls.clear()
    limited = tool({"query": "needle", "limit": 1, "mode": "keyword"})
    assert len(limited["results"]) == 1 and len(calls) == 1 and len(calls[0]) == 1


def test_dashboard_availability_surfaces_and_setting():
    page = (ROOT / "assets/dashboard/index.html").read_text(encoding="utf-8")
    assert 'id="libraryAvailabilityFilter" data-library-availability="gone" aria-pressed="false"' in page
    assert 'aria-label="Gone from the web, still in your library"' in page
    assert '${sourceAvailabilityBadge(row)}' in page
    for label in ("Gone from the web", "Now private", "Blocked in your region"):
        assert label in page
    assert 'title="${label}, still in your library"' in page
    assert 'authFetch("/library/availability")' in page
    assert "1 source you saved went offline this month. You still have it." in page
    assert "${count} sources you saved went offline this month. You still have them." in page
    assert page.index('id="auto-uoink"') < page.index('id="source-availability"') < page.index("<h2>Podcast feeds</h2>")
    assert '<h2>Check if saved sources go offline</h2>' in page
    assert 'sourceAvailabilityToggle: ["source_availability_check_enabled", true]' in page
    assert 'id="sourceAvailabilityToggle" type="checkbox" checked' in page
    assert re.search(r"try \{ localStorage.setItem\(AVAILABILITY_DISMISSED_KEY, availabilityDismissedMonth\); \} catch", page)


def test_dashboard_availability_behaviour():
    result = subprocess.run(["node", str(ROOT / "tests/js/rehaul_library_reader_test.mjs"), "availability"],
                            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "group availability:" in result.stdout and "0 failures" in result.stdout
