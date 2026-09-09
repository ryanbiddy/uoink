"""The setup page must use the helper's real channel registry contract."""

from __future__ import annotations

import json
from http.server import ThreadingHTTPServer
from pathlib import Path
import threading
import urllib.error
import urllib.request

import channels
import index as index_mod
import server


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "extension" / "setup.js").read_text(encoding="utf-8")


def _section(start: str, end: str) -> str:
    assert start in SCRIPT, f"missing section start: {start}"
    body = SCRIPT.split(start, 1)[1]
    assert end in body, f"missing section end: {end}"
    return body.split(end, 1)[0]


def _request(base: str, method: str, path: str, body=None, *, token=True):
    headers = {"X-Uoink-Token": server.TOKEN} if token else {}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        f"{base}{path}", data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, json.loads(response.read().decode() or "{}")
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode() or "{}")


def test_helper_channel_routes_share_one_persisted_registry(tmp_path):
    idx = index_mod.Index.open(tmp_path / "index.db")
    old_get_index = server._get_index
    old_fetch_name = channels.fetch_channel_name
    server._get_index = lambda: idx
    channels.fetch_channel_name = lambda handle, channel_id=None: {
        "ok": True,
        "name": "Ryan Biddy",
        "source_url": f"https://www.youtube.com/@{handle}",
    }
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        status, _ = _request(base, "GET", "/channels", token=False)
        assert status == 403

        idx.upsert_yoink(
            {
                "video_id": "self-video",
                "slug": "self-video",
                "channel": "Ryan Biddy",
                "title": "Own upload",
                "topic": "AI and ML",
                "hook_type": "demo",
                "yoinked_at": "2026-07-01T00:00:00Z",
                "corpus_path": str(tmp_path / "self-video" / "corpus.md"),
                "sidecar_path": "",
                "source_type": "youtube",
            },
            content="own transcript",
        )

        status, added = _request(
            base, "POST", "/channels", {"handle": "@ryanbiddy"}
        )
        assert status == 200 and added["channel"]["handle"] == "ryanbiddy"

        status, listed = _request(base, "GET", "/channels")
        assert status == 200 and listed["count"] == 1
        assert listed["channels"][0]["handle"] == "ryanbiddy"

        status, verified = _request(
            base, "POST", "/channels/verify", {"handle": "ryanbiddy"}
        )
        assert status == 200 and verified["verified"] is True
        assert verified["channel"]["name"] == "Ryan Biddy"

        status, recognized = _request(
            base, "POST", "/channels/recognize-now", {}
        )
        assert status == 200
        assert recognized["scanned"] == 1 and recognized["tagged"] == 1

        status, removed = _request(
            base, "POST", "/channels/remove", {"handle": "ryanbiddy"}
        )
        assert status == 200 and removed["removed"] is True
        assert _request(base, "GET", "/channels")[1]["count"] == 0
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
        channels.fetch_channel_name = old_fetch_name
        server._get_index = old_get_index
        idx.close()


def test_setup_crud_uses_channel_routes_not_generic_settings():
    load = _section(
        "async function loadYourChannels()",
        "async function removeYourChannel",
    )
    remove = _section(
        "async function removeYourChannel",
        "function renderYcList",
    )
    add = _section(
        "const addChannel = async () =>",
        "ycAddBtn.addEventListener",
    )
    settings = _section(
        "async function saveV3Settings()",
        "async function loadPendingV3Settings()",
    )

    assert 'fetch(`${SERVER}/channels`' in load
    assert "yourChannelsList = Array.isArray(data.channels)" in load
    assert 'fetch(`${SERVER}/channels/remove`' in remove
    assert "JSON.stringify({ handle })" in remove
    assert 'fetch(`${SERVER}/channels`' in add
    assert "JSON.stringify({ handle: val })" in add
    assert "your_channels:" not in settings


def test_setup_verify_and_recognize_report_real_contract_results():
    verify = _section(
        "async function verifyChannel",
        "async function saveV3Settings()",
    )
    recognize = _section(
        'ycRecognizeBtn.addEventListener("click", async () =>',
        "if (ctTargetLength)",
    )
    on_up = _section(
        "function onServerUp()",
        "// ---- Comment Intelligence settings",
    )
    render_settings = _section(
        "function renderCISettings(settings)",
        "async function fetchPricingWithToken",
    )

    assert "JSON.stringify({ handle })" in verify
    assert "JSON.stringify({ channel:" not in verify
    assert "data.scanned" in recognize and "data.tagged" in recognize
    assert "recognition started" not in recognize.lower()
    assert "loadYourChannels();" in on_up
    assert "settings.your_channels" not in render_settings
