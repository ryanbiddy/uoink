"""CX-57 -- destructive delete boundaries must reject wrong-type IDs.

On unpatched main both delete boundaries coerced their ID with `int()`.
Because `int(True) == 1`, `int("1") == 1`, and `int(1.9) == 1`, a JSON
`true`, a numeric string, or a float selected record 1 and deleted it
together with every cascaded child row.

Each rejection case below asserts *no work before validation*: the row
counts for both parents and both child tables are byte-identical after
the call, and the shared error is returned. The positive controls prove a
real integer 1 still deletes the row and cascades.

Both real boundaries are exercised:
  - direct MCP dispatch via `uoink_mcp_tools.call_tool` (which does not
    apply the advertised input schema)
  - the authenticated HTTP endpoints `/podcasts/feeds/remove` and
    `/playlists/monitored/remove` on a live `server.Handler`

Every case runs against a throwaway SQLite database in a temporary
directory. No user database is opened.
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import index as index_mod  # noqa: E402
import record_id_contract  # noqa: E402
import server  # noqa: E402
import uoink_mcp_tools  # noqa: E402

NOW = "2026-07-26T00:00:00Z"

# The alias shapes that reached the delete on unpatched main, plus the
# non-positive integers that a strict contract must also refuse.
BAD_IDS = [
    pytest.param(True, id="true"),
    pytest.param("1", id="str-1"),
    pytest.param(1.0, id="float-1.0"),
    pytest.param(-1, id="negative-1"),
    pytest.param(0, id="zero"),
]
# JSON wire forms of the same aliases, so the HTTP leg sends the real
# bytes a client would send rather than a Python object.
BAD_IDS_JSON = [
    pytest.param("true", id="true"),
    pytest.param('"1"', id="str-1"),
    pytest.param("1.0", id="float-1.0"),
    pytest.param("-1", id="negative-1"),
    pytest.param("0", id="zero"),
]


def _seed(tmp_path: Path):
    """Feed id=1 with 2 episodes and playlist id=1 with 2 events."""
    idx = index_mod.Index.open(tmp_path / "index.db")
    with idx._lock:
        conn = idx._conn
        conn.execute(
            "INSERT INTO podcast_feeds (id, feed_url, added_at) "
            "VALUES (1, 'https://example.com/feed.xml', ?)", (NOW,))
        for guid in ("ep-guid-1", "ep-guid-2"):
            conn.execute(
                "INSERT INTO podcast_episodes (feed_id, guid, title, "
                "discovered_at) VALUES (1, ?, 'Episode', ?)", (guid, NOW))
        conn.execute(
            "INSERT INTO monitored_playlists (id, playlist_url, added_at) "
            "VALUES (1, 'https://www.youtube.com/playlist?list=PLcx57', ?)",
            (NOW,))
        for vid in ("vidcx57aaaa", "vidcx57bbbb"):
            conn.execute(
                "INSERT INTO mobile_queue_events (playlist_id, video_id, "
                "discovered_at) VALUES (1, ?, ?)", (vid, NOW))
        conn.commit()
    return idx


def _counts(idx) -> tuple[int, int, int, int]:
    conn = idx._conn
    return (
        conn.execute("SELECT COUNT(*) FROM podcast_feeds").fetchone()[0],
        conn.execute("SELECT COUNT(*) FROM podcast_episodes").fetchone()[0],
        conn.execute("SELECT COUNT(*) FROM monitored_playlists").fetchone()[0],
        conn.execute("SELECT COUNT(*) FROM mobile_queue_events").fetchone()[0],
    )


SEEDED = (1, 2, 1, 2)


@pytest.fixture
def idx(tmp_path, monkeypatch):
    database = _seed(tmp_path)
    monkeypatch.setattr(server, "_get_index", lambda: database)
    uoink_mcp_tools.bind_backend(server)
    assert _counts(database) == SEEDED
    try:
        yield database
    finally:
        database.close()


@pytest.fixture
def http_port(idx):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield httpd.server_address[1]
    finally:
        httpd.shutdown()


def _post(port: int, path: str, raw_body: str, *, token: bool = True):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Uoink-Token"] = server.TOKEN
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data=raw_body.encode("utf-8"),
        headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


# ---- the shared validator itself ---------------------------------------
@pytest.mark.parametrize("value", [True, False, "1", 1.0, 1.9, -1, 0, None,
                                    [1], {"id": 1}])
def test_validator_rejects_non_positive_integers(value):
    record_id, error = record_id_contract.parse_record_id(value, "feed_id")
    assert record_id is None
    assert error == "feed_id must be a positive integer"


@pytest.mark.parametrize("value", [1, 2, 999])
def test_validator_accepts_positive_integers(value):
    assert record_id_contract.parse_record_id(value, "feed_id") == (value, None)


# ---- boundary (a): direct MCP call_tool dispatch -----------------------
@pytest.mark.parametrize("bad", BAD_IDS)
def test_mcp_remove_feed_rejects_alias_without_deleting(idx, bad):
    result = uoink_mcp_tools.call_tool("remove_podcast_feed",
                                       {"feed_id": bad})
    assert result == {"ok": False,
                      "error": "feed_id must be a positive integer"}
    assert _counts(idx) == SEEDED


@pytest.mark.parametrize("bad", BAD_IDS)
def test_mcp_remove_playlist_rejects_alias_without_deleting(idx, bad):
    result = uoink_mcp_tools.call_tool("remove_monitored_playlist",
                                       {"playlist_id": bad})
    assert result == {"ok": False,
                      "error": "playlist_id must be a positive integer"}
    assert _counts(idx) == SEEDED


def test_mcp_missing_feed_id_rejected(idx):
    assert uoink_mcp_tools.call_tool("remove_podcast_feed", {}) == {
        "ok": False, "error": "feed_id must be a positive integer"}
    assert _counts(idx) == SEEDED


def test_mcp_missing_playlist_id_rejected(idx):
    assert uoink_mcp_tools.call_tool("remove_monitored_playlist", {}) == {
        "ok": False, "error": "playlist_id must be a positive integer"}
    assert _counts(idx) == SEEDED


def test_mcp_integer_feed_id_still_deletes_and_cascades(idx):
    assert uoink_mcp_tools.call_tool("remove_podcast_feed",
                                     {"feed_id": 1})["ok"] is True
    # Feed 1 and its 2 episodes are gone; the playlist side is untouched.
    assert _counts(idx) == (0, 0, 1, 2)


def test_mcp_integer_playlist_id_still_deletes_and_cascades(idx):
    assert uoink_mcp_tools.call_tool("remove_monitored_playlist",
                                     {"playlist_id": 1})["ok"] is True
    assert _counts(idx) == (1, 2, 0, 0)


def test_mcp_absent_feed_id_reports_not_removed(idx):
    result = uoink_mcp_tools.call_tool("remove_podcast_feed", {"feed_id": 42})
    assert result == {"ok": True, "removed": False}
    assert _counts(idx) == SEEDED


# ---- boundary (b): authenticated HTTP endpoints ------------------------
@pytest.mark.parametrize("bad_json", BAD_IDS_JSON)
def test_http_remove_feed_rejects_alias_without_deleting(idx, http_port,
                                                          bad_json):
    status, payload = _post(http_port, "/podcasts/feeds/remove",
                            '{"feed_id": %s}' % bad_json)
    assert status == 400
    assert payload == {"ok": False,
                       "error": "feed_id must be a positive integer"}
    assert _counts(idx) == SEEDED


@pytest.mark.parametrize("bad_json", BAD_IDS_JSON)
def test_http_remove_playlist_rejects_alias_without_deleting(idx, http_port,
                                                              bad_json):
    status, payload = _post(http_port, "/playlists/monitored/remove",
                            '{"playlist_id": %s}' % bad_json)
    assert status == 400
    assert payload == {"ok": False,
                       "error": "playlist_id must be a positive integer"}
    assert _counts(idx) == SEEDED


def test_http_remove_feed_still_token_gated(idx, http_port):
    status, payload = _post(http_port, "/podcasts/feeds/remove",
                            '{"feed_id": 1}', token=False)
    assert status == 403
    assert payload["ok"] is False
    assert _counts(idx) == SEEDED


def test_http_remove_playlist_still_token_gated(idx, http_port):
    status, payload = _post(http_port, "/playlists/monitored/remove",
                            '{"playlist_id": 1}', token=False)
    assert status == 403
    assert payload["ok"] is False
    assert _counts(idx) == SEEDED


def test_http_integer_feed_id_still_deletes_and_cascades(idx, http_port):
    status, payload = _post(http_port, "/podcasts/feeds/remove",
                            '{"feed_id": 1}')
    assert (status, payload) == (200, {"ok": True, "removed": True})
    assert _counts(idx) == (0, 0, 1, 2)


def test_http_integer_playlist_id_still_deletes_and_cascades(idx, http_port):
    status, payload = _post(http_port, "/playlists/monitored/remove",
                            '{"playlist_id": 1}')
    assert (status, payload) == (200, {"ok": True, "removed": True})
    assert _counts(idx) == (1, 2, 0, 0)


def test_http_absent_feed_id_reports_not_removed(idx, http_port):
    status, payload = _post(http_port, "/podcasts/feeds/remove",
                            '{"feed_id": 42}')
    assert (status, payload) == (200, {"ok": True, "removed": False})
    assert _counts(idx) == SEEDED
