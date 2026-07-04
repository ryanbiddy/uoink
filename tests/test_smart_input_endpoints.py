"""G-21 -- smart-input picker data endpoints.

Run: python tests/test_smart_input_endpoints.py

Two new corpus-answering endpoints for the smart-input pickers
(SMART-INPUT-BUILD-PLAN-CC). Topic and hook facets are intentionally NOT
rebuilt here -- those come from /library/facets (G-12). The genuine delta:

  GET /corpus/channels     channels across the corpus, with counts, a
                           representative thumbnail_url, ?q= type-ahead
  GET /writing/recent-ctas distinct CTAs from past scripts, most-recent first

Boots server.Handler against a real index.Index and asserts shape, counts,
type-ahead filtering, the thumbnail URL when a thumbnail.jpg exists, and the
token gate.
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
import server  # noqa: E402

PORT = 5200


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _get(path, token=True):
    headers = {"X-Uoink-Token": server.TOKEN} if token else {}
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}{path}", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def _seed_yoink(idx, video_id, channel, folder):
    corpus_path = str(folder / f"{video_id}.md")
    idx.upsert_yoink({
        "video_id": video_id, "slug": video_id, "channel": channel,
        "title": f"{channel} clip", "topic": "ai", "hook_type": "curiosity_gap",
        "yoinked_at": f"2026-06-0{video_id[-1]}T10:00:00",
        "corpus_path": corpus_path, "sidecar_path": "", "source_type": "youtube",
    })


def main():
    tmp = tempfile.TemporaryDirectory()
    base = Path(tmp.name)
    idx = index_mod.Index.open(base / "index.db")
    server._get_index = lambda: idx  # type: ignore
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        # Empty corpus.
        status, res = _get("/corpus/channels")
        _assert(status == 200 and res["ok"], f"empty ok: {status} {res}")
        _assert(res["channels"] == [] and res["total"] == 0,
                f"empty corpus has no channels: {res}")
        print("ok  /corpus/channels: clean empty response")

        # Seed: Karpathy x3 (one with a real thumbnail), Fireship x1.
        kfolder = base / "kar1"
        kfolder.mkdir()
        (kfolder / "thumbnail.jpg").write_bytes(b"jpeg")
        _seed_yoink(idx, "karvid001", "Karpathy", kfolder)
        _seed_yoink(idx, "karvid002", "Karpathy", base)
        _seed_yoink(idx, "karvid003", "Karpathy", base)
        _seed_yoink(idx, "firevid004", "Fireship", base)

        status, res = _get("/corpus/channels")
        chans = {c["channel"]: c for c in res["channels"]}
        _assert(set(chans) == {"Karpathy", "Fireship"},
                f"every corpus channel present: {chans}")
        _assert(chans["Karpathy"]["count"] == 3, f"counts: {chans['Karpathy']}")
        _assert(res["channels"][0]["channel"] == "Karpathy",
                "ordered by count desc")
        # Karpathy's most-recent yoink (karvid003) is in base with no
        # thumbnail; representative thumbnail resolves from the latest folder.
        # Confirm the thumbnail_url field is present (null or a /file URL).
        _assert("thumbnail_url" in chans["Karpathy"], "thumbnail_url field")
        print("ok  /corpus/channels: corpus-wide counts, count-desc order")

        # Type-ahead ?q=.
        status, res = _get("/corpus/channels?q=fire")
        _assert([c["channel"] for c in res["channels"]] == ["Fireship"],
                f"?q= filters case-insensitively: {res['channels']}")
        print("ok  /corpus/channels: ?q= type-ahead filter")

        # A representative thumbnail resolves to a /file URL when present.
        _seed_yoink(idx, "solo00001", "SoloChan", kfolder)
        status, res = _get("/corpus/channels?q=solo")
        solo = res["channels"][0]
        _assert(solo["thumbnail_url"] and solo["thumbnail_url"].startswith(
            "/file?path="), f"thumbnail resolves to /file URL: {solo}")
        print("ok  /corpus/channels: representative thumbnail_url")

        # Recent CTAs (empty scripts table -> empty list, not an error).
        status, res = _get("/writing/recent-ctas")
        _assert(status == 200 and res["ok"] and res["ctas"] == [],
                f"no scripts -> empty ctas: {status} {res}")
        idx._conn.executescript(
            """
            INSERT INTO workspaces (id, created_at, updated_at)
              VALUES ('w1', '2026-06-01T00:00:00', '2026-06-01T00:00:00');
            INSERT INTO workspaces (id, created_at, updated_at)
              VALUES ('w2', '2026-06-01T00:00:00', '2026-06-01T00:00:00');
            INSERT INTO workspaces (id, created_at, updated_at)
              VALUES ('w3', '2026-06-01T00:00:00', '2026-06-01T00:00:00');
            INSERT INTO scripts (workspace_id, version, generated_at, format,
              cta) VALUES ('w1', 1, '2026-06-01T10:00:00', 'talking-head',
              'Link in bio');
            INSERT INTO scripts (workspace_id, version, generated_at, format,
              cta) VALUES ('w1', 2, '2026-06-05T10:00:00', 'talking-head',
              'Subscribe for more');
            INSERT INTO scripts (workspace_id, version, generated_at, format,
              cta) VALUES ('w2', 1, '2026-06-03T10:00:00', 'talking-head',
              'Link in bio');
            INSERT INTO scripts (workspace_id, version, generated_at, format,
              cta) VALUES ('w3', 1, '2026-06-02T10:00:00', 'talking-head', '');
            """
        )
        idx._conn.commit()
        status, res = _get("/writing/recent-ctas")
        texts = [c["text"] for c in res["ctas"]]
        _assert(texts == ["Subscribe for more", "Link in bio"],
                f"distinct CTAs, most-recent first, blanks dropped: {texts}")
        _assert(all(c["last_used"] for c in res["ctas"]),
                "each CTA carries last_used")
        print("ok  /writing/recent-ctas: distinct, recency-ordered, blanks out")

        # Token gate.
        s1, _ = _get("/corpus/channels", token=False)
        s2, _ = _get("/writing/recent-ctas", token=False)
        _assert(s1 in (401, 403) and s2 in (401, 403),
                f"token required: {s1} {s2}")
        print("ok  token required on both endpoints")
    finally:
        httpd.shutdown()
        idx.close()
        tmp.cleanup()
    print("\nALL SMART-INPUT ENDPOINT TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
