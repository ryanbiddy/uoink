"""V-4 -- GET /discovery: the local discovery digest composition.

Run: python tests/test_discovery_route.py  (or via pytest tests/)

Red on unpatched main: GET /discovery -> 404 (route is net-new), so the
first assert fails.

Green with the fix: /discovery composes the R-01 resurface payload with
the V-3 auto-uoinked captures into one ranked 'attention' stream. Every
resurface + auto-uoink entry that has a video_id can offer Write-from-this
(video_id is the write-from deep-link key). Asserts token gate, the
composed shape, that a taste-captured item shows up labelled + joined to
its corpus row, and that the resurface passthrough keys stay intact so the
existing renderForYou() keeps working.
"""
from __future__ import annotations

import json
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import index as index_mod  # noqa: E402
import mobile_playlists  # noqa: E402
import server  # noqa: E402

PORT = 5262


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _get(path, *, token=True):
    headers = {"X-Uoink-Token": server.TOKEN} if token else {}
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}{path}", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def _seed(idx, root, video_id, title):
    folder = Path(root) / video_id
    folder.mkdir(parents=True, exist_ok=True)
    idx.upsert_yoink({
        "video_id": video_id, "slug": video_id, "channel": "Fireship",
        "title": title, "topic": "AI and ML", "hook_type": "curiosity_gap",
        "yoinked_at": "2026-01-05T09:00:00",
        "corpus_path": str(folder / "corpus.md"),
        "sidecar_path": "", "source_type": "youtube",
    }, content=f"{title} transcript body")


def test_discovery_route():
    tmp = tempfile.TemporaryDirectory()
    idx = index_mod.Index.open(Path(tmp.name) / "index.db")
    server._get_index = lambda: idx  # type: ignore
    server.SETTINGS_PATH = Path(tmp.name) / "settings.json"  # type: ignore
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        # Token gate.
        status, _ = _get("/discovery", token=False)
        _assert(status == 403, f"discovery without token -> 403, got {status}")
        print("ok  /discovery is token-gated")

        # Empty corpus -> valid empty-ish shape, not an error.
        status, res = _get("/discovery")
        _assert(status == 200, f"discovery route exists (404 on main): {status}")
        d = res["discovery"]
        for key in ("attention", "auto_uoinked", "worth_revisiting",
                    "connections", "corpus_gaps", "anchors", "auto_uoink"):
            _assert(key in d, f"discovery carries {key}: {list(d)}")
        _assert(d["auto_uoinked"] == [], f"no captures yet: {d['auto_uoinked']}")
        print("ok  empty corpus -> valid composed shape")

        # Seed a corpus item that also has a taste-capture event pointing at
        # it (simulating a finished auto-uoink capture).
        _seed(idx, tmp.name, "captured111", "Auto AI agents pick")
        _seed(idx, tmp.name, "oldsavexxxx", "Old deep dive to resurface")
        pl = mobile_playlists.add_playlist(
            idx, "https://youtube.com/playlist?list=PLd",
            name="watch", normalize_playlist_url=lambda u: u)
        # Record a taste-capture event straight into the log (as a finished
        # auto-uoink would): capture_reason + taste_score set.
        with idx._lock:
            idx._conn.execute(
                "INSERT INTO mobile_queue_events "
                "(playlist_id, video_id, video_title, discovered_at, status, "
                " pending_id, capture_reason, taste_score) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (pl["id"], "captured111", "Auto AI agents pick",
                 "2026-07-06T09:00:00", "queued", None,
                 "auto_uoink:taste", 0.72))
            idx._conn.commit()

        status, res = _get("/discovery")
        d = res["discovery"]
        auto = d["auto_uoinked"]
        _assert(len(auto) == 1, f"one auto-uoinked item: {auto}")
        item = auto[0]
        _assert(item["video_id"] == "captured111", f"correct id: {item}")
        _assert(item["in_corpus"] is True,
                f"joined to corpus row -> Write-from-this eligible: {item}")
        _assert(item["label"] == "auto-uoinked (taste match)",
                f"clearly labelled: {item}")
        _assert(abs((item["taste_score"] or 0) - 0.72) < 1e-6,
                f"carries taste score: {item}")
        print("ok  taste capture surfaces, labelled + corpus-joined")

        # The ranked attention stream leads with the auto-uoink then the
        # resurfaced save; every entry with a video_id can write-from.
        kinds = [a["kind"] for a in d["attention"]]
        _assert("auto_uoink" in kinds, f"attention has auto_uoink: {kinds}")
        _assert(all(a.get("video_id") for a in d["attention"]),
                "every attention item has a write-from id")
        print("ok  ranked attention stream composed with write-from ids")

        print("\nall green")
    finally:
        httpd.shutdown()
        idx.close()
        tmp.cleanup()


if __name__ == "__main__":
    test_discovery_route()
