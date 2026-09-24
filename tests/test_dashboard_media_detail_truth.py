"""Regressions for bounded authenticated saved-media-detail read path.

Tests both the HTTP server /yoinks/<id>/details endpoint and the Node-executed
dashboard UI lifecycle, including honest refusal states and race conditions.
"""
from __future__ import annotations

import json
from http.server import ThreadingHTTPServer
from pathlib import Path
import subprocess
import threading
import urllib.error
import urllib.request

import pytest

import index as index_mod
import server

ROOT = Path(__file__).resolve().parents[1]


class _QuietHandler(server.Handler):
    def log_message(self, format: str, *args) -> None:  # noqa: A002
        pass


@pytest.fixture
def media_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    desktop = tmp_path / "desktop"
    desktop.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(server, "DESKTOP_ROOT", desktop)
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path / "data")
    monkeypatch.setattr(server, "_path_integrity_status", lambda: {"ok": True})
    monkeypatch.setattr(server, "_index_recovering", False)

    idx_path = tmp_path / "index.db"
    idx = index_mod.Index.open(idx_path)
    monkeypatch.setattr(server, "_get_index", lambda: idx)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _QuietHandler)
    httpd.daemon_threads = True
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = int(httpd.server_address[1])
    try:
        yield port, idx, desktop
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
        idx.close()


def _http_get(port: int, path: str, token: bool = True) -> tuple[int, dict]:
    headers = {"X-Uoink-Token": server.TOKEN} if token else {}
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            body = r.read().decode("utf-8")
            return r.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        return e.code, json.loads(body) if body else {}


def _insert_yoink_fixture(
    idx: index_mod.Index,
    root: Path,
    video_id: str,
    *,
    sidecar: dict | None = None,
    raw_sidecar_bytes: bytes | None = None,
    sidecar_rel: str | None = None,
    custom_sidecar_path: str | None = None,
) -> Path:
    folder = root / "videos" / video_id
    folder.mkdir(parents=True, exist_ok=True)
    corpus = folder / f"{video_id}.md"
    corpus.write_text(f"# Video {video_id}\n\nTranscript text.", encoding="utf-8")

    if custom_sidecar_path is not None:
        target_sidecar_path = custom_sidecar_path
    else:
        sidecar_file = folder / (sidecar_rel or f"{video_id}.json")
        if raw_sidecar_bytes is not None:
            sidecar_file.write_bytes(raw_sidecar_bytes)
        elif sidecar is not None:
            sidecar_file.write_text(json.dumps(sidecar), encoding="utf-8")
        target_sidecar_path = str(sidecar_file)

    idx.upsert_yoink({
        "video_id": video_id,
        "slug": video_id,
        "channel": "Science Channel",
        "title": f"Title for {video_id}",
        "topic": "science",
        "hook_type": "curiosity_gap",
        "yoinked_at": "2026-09-12T10:00:00Z",
        "corpus_path": str(corpus),
        "sidecar_path": target_sidecar_path,
        "source_type": "video",
        "platform": "youtube",
    })
    return folder


NODE_DASHBOARD_HARNESS = r"""
const fs = require('node:fs');
const vm = require('node:vm');

const page = fs.readFileSync('assets/dashboard/index.html', 'utf8');
const scriptStart = page.indexOf('<script>') + 8;
const initCall = page.indexOf('    init().catch(');
const scriptCode = page.slice(scriptStart, initCall > 0 ? initCall : undefined);

const dummyEl = {
  scrollTop: 0, disabled: false, textContent: '', innerHTML: '', title: '', dataset: {},
  classList: { add: () => {}, remove: () => {}, contains: () => false, toggle: () => {} },
  setAttribute: () => {}, getAttribute: () => null, querySelectorAll: () => [], querySelector: () => null,
};
const elements = {};
const getEl = (id) => elements[id] || (elements[id] = { ...dummyEl, id });

const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const fetchCalls = [];

const fakeFetch = async (url, opts) => {
  fetchCalls.push({ url, opts });
  if (url === '/token') {
    return {
      ok: true,
      status: 200,
      json: async () => ({ ok: true, token: 'fake-token' }),
      text: async () => JSON.stringify({ ok: true, token: 'fake-token' }),
    };
  }
  if (url.startsWith('/file')) {
    return {
      ok: false,
      status: 415,
      json: async () => ({ ok: false, error: 'unsupported file type' }),
      text: async () => 'unsupported file type',
    };
  }
  if (url.includes('/markdown')) {
    const md = input.markdown !== undefined ? input.markdown : '# Markdown';
    return {
      ok: true,
      status: 200,
      json: async () => ({ ok: true, markdown: md }),
      text: async () => JSON.stringify({ ok: true, markdown: md }),
    };
  }
  if (url.includes('/details')) {
    if (input.detailsDelayMs) {
      await new Promise((resolve) => setTimeout(resolve, input.detailsDelayMs));
    }
    if (input.detailsRefusal) {
      return {
        ok: false,
        status: input.detailsRefusal.status || 404,
        json: async () => input.detailsRefusal.body || { ok: false, error: 'sidecar file not found' },
        text: async () => JSON.stringify(input.detailsRefusal.body || { ok: false, error: 'sidecar file not found' }),
      };
    }
    const details = input.details || {
      video_id: 'vid_test',
      duration_seconds: 360,
      channel: 'Host Channel',
      screenshots: [{ path: 'shot0.png', timestamp: '00:01:00' }],
    };
    return {
      ok: true,
      status: 200,
      json: async () => ({ ok: true, video_id: 'vid_test', details }),
      text: async () => JSON.stringify({ ok: true, video_id: 'vid_test', details }),
    };
  }
  return {
    ok: true,
    status: 200,
    json: async () => ({ ok: true }),
    text: async () => JSON.stringify({ ok: true }),
  };
};

const ctx = {
  document: { getElementById: getEl, querySelector: () => dummyEl, querySelectorAll: () => [] },
  window: { addEventListener: () => {} },
  navigator: { clipboard: { writeText: () => Promise.resolve() } },
  console,
  fetch: fakeFetch,
  setTimeout,
  clearTimeout,
  URL: { createObjectURL: () => 'blob:mock', revokeObjectURL: () => {} },
};
vm.createContext(ctx);
vm.runInContext(scriptCode + '; globalThis.state = state; globalThis.els = els; globalThis.openYoinkDetail = openYoinkDetail; globalThis.yoinkFactsHtml = yoinkFactsHtml; globalThis.renderYoinkDetail = renderYoinkDetail;', ctx);

async function execute() {
  if (input.action === 'openDetail') {
    await ctx.openYoinkDetail(input.row);
    process.stdout.write(JSON.stringify({
      fetchCalls,
      selectedYoinkSidecar: ctx.state.selectedYoinkSidecar,
      selectedYoinkSidecarError: ctx.state.selectedYoinkSidecarError,
      factMetaText: ctx.els.yoinkFactMeta.textContent,
      factsHtml: ctx.els.yoinkFacts.innerHTML,
      detailHtml: ctx.els.yoinkDetail.innerHTML,
      headingHtml: ctx.els.yoinkHeading.innerHTML,
    }));
  } else if (input.action === 'selectionRace') {
    // Start opening item 1 with slow details
    const p1 = ctx.openYoinkDetail(input.row1);
    // Immediately open item 2 with fast details
    input.details = input.details2;
    input.detailsDelayMs = 0;
    const p2 = ctx.openYoinkDetail(input.row2);
    await Promise.all([p1, p2]);
    process.stdout.write(JSON.stringify({
      fetchCalls,
      selectedYoink: ctx.state.selectedYoink,
      selectedYoinkSidecar: ctx.state.selectedYoinkSidecar,
      selectedYoinkSidecarError: ctx.state.selectedYoinkSidecarError,
      factMetaText: ctx.els.yoinkFactMeta.textContent,
      subheadText: ctx.els.yoinkSubhead.textContent,
    }));
  } else {
    throw new Error('Unknown action: ' + input.action);
  }
}
execute().catch((err) => {
  console.error(err);
  process.exit(1);
});
"""


def _run_node_dashboard(payload: dict) -> dict:
    res = subprocess.run(
        ["node", "-e", NODE_DASHBOARD_HARNESS],
        input=json.dumps(payload),
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=15,
    )
    assert res.returncode == 0, f"Node failed (code {res.returncode}): {res.stderr}"
    return json.loads(res.stdout)


# ---------------------------------------------------------------------------
# HTTP /yoinks/<id>/details behavioral tests
# ---------------------------------------------------------------------------


def test_saved_media_detail_success(media_server):
    port, idx, desktop = media_server
    vid = "v_success_01"
    sidecar_data = {
        "video_id": vid,
        "title": "Quantum Physics 101",
        "duration_seconds": 1820,
        "channel": "Physics Channel",
        "host": "Dr. Feynman",
        "platform": "youtube",
        "source_type": "video",
        "secret_api_key": "SK-SUPER-SECRET-NEVER-LEAK",
        "internal_config": {"db_password": "pwd"},
        "screenshots": [
            {"index": 0, "filename": "shot_0.jpg", "path": "screenshots/shot_0.jpg", "timestamp": "00:01:00"}
        ],
        "transcript": [
            {"start": 0, "end": 20, "speaker": "Dr. Feynman", "text": "Nature isn't classical."}
        ],
        "diarization": {
            "speakers": ["Dr. Feynman"],
            "segments": [{"start": 0, "end": 20, "speaker": "Dr. Feynman"}]
        }
    }
    _insert_yoink_fixture(idx, desktop, vid, sidecar=sidecar_data)

    code, res = _http_get(port, f"/yoinks/{vid}/details", token=True)
    assert code == 200, f"Expected 200, got {code}: {res}"
    assert res["ok"] is True
    assert res["video_id"] == vid
    details = res["details"]
    assert details["duration_seconds"] == 1820
    assert details["channel"] == "Physics Channel"
    assert details["host"] == "Dr. Feynman"
    assert details["title"] == "Quantum Physics 101"
    assert len(details["screenshots"]) == 1
    assert details["screenshots"][0]["filename"] == "shot_0.jpg"
    assert len(details["transcript"]) == 1
    assert details["transcript"][0]["text"] == "Nature isn't classical."
    # Secrets must not be returned
    assert "secret_api_key" not in details
    assert "internal_config" not in details


def test_media_detail_requires_authentication(media_server):
    port, idx, desktop = media_server
    vid = "v_auth_01"
    _insert_yoink_fixture(idx, desktop, vid, sidecar={"video_id": vid, "duration_seconds": 100})

    code, res = _http_get(port, f"/yoinks/{vid}/details", token=False)
    assert code == 403
    assert res["ok"] is False
    assert "token" in res.get("error", "").lower()


def test_media_detail_unknown_id(media_server):
    port, idx, desktop = media_server
    code, res = _http_get(port, "/yoinks/v_nonexistent/details", token=True)
    assert code == 404
    assert res["ok"] is False
    assert res.get("error") == "uoink not found"


def test_media_detail_missing_sidecar_file(media_server):
    port, idx, desktop = media_server
    vid = "v_missing_file"
    missing_path = desktop / "videos" / vid / "does_not_exist.json"
    _insert_yoink_fixture(idx, desktop, vid, custom_sidecar_path=str(missing_path))

    code, res = _http_get(port, f"/yoinks/{vid}/details", token=True)
    assert code == 404
    assert res["ok"] is False
    assert "not found" in res.get("error", "").lower()


def test_media_detail_corrupt_malformed_json(media_server):
    port, idx, desktop = media_server
    vid = "v_corrupt_json"
    corrupt_bytes = b'{"duration_seconds": 120, "broken": '
    _insert_yoink_fixture(idx, desktop, vid, raw_sidecar_bytes=corrupt_bytes)

    code, res = _http_get(port, f"/yoinks/{vid}/details", token=True)
    assert code == 400
    assert res["ok"] is False
    assert "malformed" in res.get("error", "").lower() or "bad json" in res.get("error", "").lower()


def test_media_detail_oversized_json(media_server):
    port, idx, desktop = media_server
    vid = "v_oversized_json"
    # Create payload exceeding 2MB limit
    big_pad = "A" * (2 * 1024 * 1024 + 1000)
    big_json = json.dumps({"video_id": vid, "pad": big_pad}).encode("utf-8")
    _insert_yoink_fixture(idx, desktop, vid, raw_sidecar_bytes=big_json)

    code, res = _http_get(port, f"/yoinks/{vid}/details", token=True)
    assert code == 400
    assert res["ok"] is False
    assert "large" in res.get("error", "").lower()


def test_media_detail_non_object_json(media_server):
    port, idx, desktop = media_server
    vid = "v_non_object"
    _insert_yoink_fixture(idx, desktop, vid, raw_sidecar_bytes=b'["just", "a", "list"]')

    code, res = _http_get(port, f"/yoinks/{vid}/details", token=True)
    assert code == 400
    assert res["ok"] is False
    assert "object" in res.get("error", "").lower()


def test_media_detail_outside_root_refusal_without_reads(media_server, tmp_path, monkeypatch):
    port, idx, desktop = media_server
    vid = "v_outside"

    # Put a sidecar in tmp_path outside desktop root
    outside_dir = tmp_path / "outside_dir"
    outside_dir.mkdir(parents=True, exist_ok=True)
    outside_file = outside_dir / "secret_sidecar.json"
    outside_file.write_text(json.dumps({"video_id": vid, "duration_seconds": 999}), encoding="utf-8")

    _insert_yoink_fixture(idx, desktop, vid, custom_sidecar_path=str(outside_file))

    # Instrument open to ensure file is NEVER opened
    opened_paths = []
    orig_open = open

    def tracking_open(file, *args, **kwargs):
        if str(outside_file) in str(file):
            opened_paths.append(str(file))
            raise AssertionError(f"Security violation: attempted to open out-of-root path {file}")
        return orig_open(file, *args, **kwargs)

    monkeypatch.setattr("builtins.open", tracking_open)

    code, res = _http_get(port, f"/yoinks/{vid}/details", token=True)
    assert code in (400, 403)
    assert res["ok"] is False
    assert "outside" in res.get("error", "").lower() or "escapes" in res.get("error", "").lower()
    assert len(opened_paths) == 0, f"File was opened: {opened_paths}"


# ---------------------------------------------------------------------------
# Node-executed Dashboard UI regressions
# ---------------------------------------------------------------------------


def test_dashboard_node_open_detail_success():
    row = {
        "video_id": "v_test_node_01",
        "slug": "v-test-node-01",
        "title": "Node Dashboard Video",
        "channel": "Tech Explorers",
        "source_type": "video",
        "platform": "youtube",
    }
    details = {
        "video_id": "v_test_node_01",
        "duration_seconds": 1250,
        "channel": "Tech Explorers",
        "screenshots": [{"path": "shot1.png", "timestamp": "00:05:00"}],
        "transcript": [{"start": 0, "text": "Hello world segment."}],
    }
    out = _run_node_dashboard({
        "action": "openDetail",
        "row": row,
        "details": details,
    })
    urls = [c["url"] for c in out["fetchCalls"]]
    assert any("/details" in u for u in urls), f"Must fetch /details route: {urls}"
    assert not any("/file" in u for u in urls), f"/file route must NOT be called for details: {urls}"

    assert out["selectedYoinkSidecar"] is not None
    assert out["selectedYoinkSidecar"]["duration_seconds"] == 1250
    assert out["factMetaText"] == "ready"
    assert "20:50" in out["factsHtml"]  # 1250 seconds formatted as mm:ss
    assert "Tech Explorers" in out["factsHtml"]
    assert ">ready<" in out["factsHtml"]


def test_dashboard_node_open_detail_refusal_honest_error():
    row = {
        "video_id": "v_refused_01",
        "slug": "v-refused-01",
        "title": "Refused Video",
        "source_type": "video",
        "platform": "youtube",
    }
    out = _run_node_dashboard({
        "action": "openDetail",
        "row": row,
        "detailsRefusal": {"status": 404, "body": {"ok": False, "error": "sidecar file not found"}},
    })
    # Honest refusal must not claim "saved details need another moment"
    assert out["selectedYoinkSidecar"] is None
    assert out["selectedYoinkSidecarError"] != "saved details need another moment"
    assert "sidecar file not found" in out["selectedYoinkSidecarError"] or "unavailable" in out["selectedYoinkSidecarError"]
    # Must NOT be in perpetual checking state or ready
    assert out["factMetaText"] != "checking saved files"
    assert out["factMetaText"] != "ready"
    assert out["factMetaText"] == out["selectedYoinkSidecarError"]


def test_dashboard_node_selection_race_avoids_stale_overwrite():
    row1 = {
        "video_id": "v_slow_item_01",
        "slug": "v-slow-01",
        "title": "Slow Item One",
        "source_type": "video",
        "platform": "youtube",
    }
    row2 = {
        "video_id": "v_fast_item_02",
        "slug": "v-fast-02",
        "title": "Fast Item Two",
        "source_type": "video",
        "platform": "youtube",
    }
    details1 = {"video_id": "v_slow_item_01", "duration_seconds": 100, "channel": "Slow Channel"}
    details2 = {"video_id": "v_fast_item_02", "duration_seconds": 200, "channel": "Fast Channel"}

    out = _run_node_dashboard({
        "action": "selectionRace",
        "row1": row1,
        "row2": row2,
        "details": details1,
        "details2": details2,
        "detailsDelayMs": 50,  # row1 details return late
    })
    # Item 2 must remain the active selection
    assert out["selectedYoink"]["video_id"] == "v_fast_item_02"
    assert out["selectedYoinkSidecar"]["video_id"] == "v_fast_item_02"
    assert out["selectedYoinkSidecar"]["channel"] == "Fast Channel"
    assert out["subheadText"] == "Title for v_fast_item_02" or "Fast Item Two" in out["subheadText"]


def test_dashboard_node_note_readiness_preserved():
    note_row = {
        "video_id": "note_01",
        "slug": "note-01",
        "title": "Saved Thought",
        "source_type": "note",
        "platform": "note",
    }
    out = _run_node_dashboard({
        "action": "openDetail",
        "row": note_row,
        "markdown": "Here is the note body text.",
    })
    urls = [c["url"] for c in out["fetchCalls"]]
    # Notes must not call details or /file
    assert not any("/details" in u for u in urls), f"Notes should not call /details: {urls}"
    assert not any("/file" in u for u in urls), f"Notes should not call /file: {urls}"
    assert out["factMetaText"] == "ready"
    assert "Note file" in out["factsHtml"]
