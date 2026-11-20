"""Uoink this page: vendored Defuddle, the DOM capture payload and its route."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
DEFUDDLE = ROOT / "extension" / "lib" / "defuddle.js"
DEFUDDLE_SHA256 = "f40075dc7b7b0460c16f77b9486a0ee66907a19677d2984e198e94356116a1e8"
LICENSE_SHA256 = "c63e6774d9c9da3de01428e0809080c4758de3636c8e9e6fe51525c9ab4cd092"
ESLINT_LINE = b"/* eslint-disable */\n"


def test_vendored_defuddle_is_the_pinned_upstream_file():
    raw = DEFUDDLE.read_bytes()
    header, sep, upstream = raw.partition(ESLINT_LINE)
    assert sep and header.startswith(b"/*! Defuddle 0.19.6, https://github.com/kepano/defuddle")
    assert DEFUDDLE_SHA256.encode() in header
    assert hashlib.sha256(upstream).hexdigest() == DEFUDDLE_SHA256
    assert b"sourceMappingURL" not in raw and b"importScripts" not in raw
    for path in (ROOT / "extension/lib/defuddle-LICENSE.txt", ROOT / "third-party-notices/defuddle-0.19.6-MIT-LICENSE.txt"):
        data = path.read_bytes()
        assert hashlib.sha256(data).hexdigest() == LICENSE_SHA256, path
        assert data.startswith(b"MIT License") and b"Steph Ango" in data


def test_defuddle_notice_ships_everywhere_the_extension_does():
    sys.path.insert(0, str(ROOT / "scripts"))
    import gen_third_party_notices as notices
    assert (ROOT / "THIRD-PARTY-NOTICES.md").read_text(encoding="utf-8").count(notices.DEFUDDLE_BLOCK) == 1
    for rel in ("build.ps1", "installer/uoink.iss", "third-party-notices/README.md"):
        assert "defuddle-0.19.6-MIT-LICENSE.txt" in (ROOT / rel).read_text(encoding="utf-8"), rel
    assert LICENSE_SHA256 in (ROOT / "build.ps1").read_text(encoding="utf-8")
    payload = json.loads((ROOT / "scripts" / "mac" / "payload.json").read_text(encoding="utf-8"))
    assert "extension" in payload["paths"] and "third-party-notices" in payload["paths"]
    import build_cws
    assert {"lib/defuddle.js", "lib/defuddle-LICENSE.txt", "lib/page-capture.js"} <= build_cws.ALLOWLIST


def test_extension_page_capture_node_tests():
    import shutil
    import subprocess
    node = shutil.which("node")
    assert node, "Node.js is required for the extension page capture tests"
    proc = subprocess.run([node, "--test", str(ROOT / "tests/js/page_capture_test.mjs")], cwd=ROOT,
                          capture_output=True, text=True, encoding="utf-8", timeout=300)
    assert proc.returncode == 0, proc.stdout[-4000:] + proc.stderr[-4000:]


def test_page_dom_capture_ships_with_the_helper():
    for rel in ("build.ps1", "installer/uoink.iss", "installer/verify_install.ps1", "scripts/mac/payload.json"):
        assert "page_dom_capture.py" in (ROOT / rel).read_text(encoding="utf-8"), rel


# ---- payload -> extract_result -------------------------------------------------
sys.path.insert(0, str(ROOT))
import page_dom_capture as dom  # noqa: E402

BODY = ("The ferry ramp at the north quay was rebuilt by volunteer crews after the autumn storm, and the "
        "work took six weeks. Records from April show the crews measured the quay wall at least ten times. ")


def payload(**over):
    data = {"url": "https://news.example.org/2026/ferry-ramp#top", "title": "The ferry ramp is rebuilt",
            "author": "Pell Ashgrove", "published": "2026-07-22T08:00:00Z", "site": "Coast Courier",
            "image": "https://news.example.org/i/ramp.jpg", "language": "en", "word_count": 60,
            "markdown": f"## What changed\n\n{BODY * 2}\n\n```python\nx = 1\n```\n\n[trust](https://trust.example.org/s)",
            "engine": "defuddle", "engine_version": "0.19.6", "capture_version": 1}
    data.update(over)
    return data


def test_capture_becomes_a_page_result_with_its_provenance():
    res = dom.build_extract_result(payload())
    assert res["ok"] and res["url"] == "https://news.example.org/2026/ferry-ramp"
    assert res["title"] == "The ferry ramp is rebuilt" and "```python\nx = 1\n```" in res["markdown"]
    assert res["extraction_engine"] == "defuddle" and res["extraction_version"] == "0.19.6"
    meta = res["metadata"]
    assert meta["author"] == "Pell Ashgrove" and meta["published_date"].startswith("2026-07-22")
    assert meta["site_name"] == "Coast Courier" and meta["capture_source"] == "browser_dom"
    assert res["article_status"] == "found" and res["output_truncated"] is False


def test_capture_drops_script_and_data_targets_but_keeps_code():
    md = (f"{BODY}\n\n[click](javascript:alert(1)) ![x](data:image/png;base64,AAAA) "
          "[ok](https://a.example/b)\n\n```\n[keep](javascript:void(0))\n```")
    res = dom.build_extract_result(payload(markdown=md))
    assert "javascript:alert" not in res["markdown"].split("```")[0] and "data:image" not in res["markdown"]
    assert "click" in res["markdown"] and "[ok](https://a.example/b)" in res["markdown"]
    assert "[keep](javascript:void(0))" in res["markdown"]


def test_wall_and_empty_tabs_are_refused_honestly():
    wall = dom.build_extract_result(payload(markdown=(
        "Subscribe to continue reading. Already a subscriber? Sign in to continue.\n\n"
        "Subscribers get every story. Subscribe to continue reading.")))
    assert not wall["ok"] and wall["page_state"] == "wall" and "nothing was saved" in wall["error"]
    thin = dom.build_extract_result(payload(title="", markdown="Menu Home"))
    assert not thin["ok"] and thin["page_state"] == "thin"
    assert dom.build_extract_result(payload(url="file:///c/x.html"))["code"] == "bad_url"
    assert dom.build_extract_result(payload(markdown=None))["code"] == "bad_payload"
    assert dom.build_extract_result(["not", "an", "object"])["code"] == "bad_payload"


def test_oversized_capture_is_cut_and_flagged():
    big = BODY * 5000 + "\n\n```\n" + "code line\n" * 10
    res = dom.build_extract_result(payload(markdown="```\nopen\n" + big))
    assert res["ok"] and res["output_truncated"] and len(res["markdown"]) <= dom.MAX_MARKDOWN + 10
    assert res["markdown"].count("```") % 2 == 0


# ---- route ----------------------------------------------------------------------
def _route(settings_allow=("news.example.org",)):
    import index as index_mod
    import page_extractor
    import server
    from http.server import ThreadingHTTPServer
    import tempfile
    import threading
    import urllib.error
    import urllib.request
    from contextlib import contextmanager

    @contextmanager
    def running():
        with tempfile.TemporaryDirectory() as out_root, tempfile.TemporaryDirectory() as d:
            idx = index_mod.Index.open(Path(d) / "index.db")
            for host in settings_allow:
                page_extractor.add_allowed(idx, host)
            saved = server._get_index, server.DESKTOP_ROOT
            server._get_index, server.DESKTOP_ROOT = (lambda: idx), Path(out_root).resolve()
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()

            def post(path, body, token=True):
                data = body if isinstance(body, bytes) else json.dumps(body).encode()
                headers = {"Content-Type": "application/json"}
                if token:
                    headers["X-Uoink-Token"] = server.TOKEN
                req = urllib.request.Request(f"http://127.0.0.1:{httpd.server_address[1]}{path}", data=data,
                                             headers=headers, method="POST")
                try:
                    with urllib.request.urlopen(req, timeout=20) as r:
                        return r.status, json.loads(r.read().decode())
                except urllib.error.HTTPError as e:
                    return e.code, json.loads(e.read().decode() or "{}")
                except (ConnectionError, urllib.error.URLError):
                    # The helper answered 413 and closed before the client finished sending.
                    return "closed", {}
            try:
                yield post, idx, Path(out_root).resolve()
            finally:
                httpd.shutdown()
                server._get_index, server.DESKTOP_ROOT = saved
                idx.close()
    return running()


def test_route_saves_a_large_tab_capture_under_the_output_root():
    md = "## Notes\n\n" + (BODY * 800)  # about 150 KB, past the 64 KB JSON cap
    with _route() as (post, idx, out_root):
        assert post("/extract/page/dom", payload(markdown=md), token=False)[0] == 403
        status, res = post("/extract/page/dom", payload(markdown=md))
        assert status == 200 and res["ok"] and res["video_id"], res
        row = idx.get_yoink(res["video_id"])
        assert row["source_type"] == "page"
        corpus = Path(row["corpus_path"]).resolve()
        assert out_root in corpus.parents
        text = corpus.read_text(encoding="utf-8")
        assert text.startswith("# The ferry ramp is rebuilt\n") and "## Notes" in text
        assert json.loads(row["metadata_json"])["extraction_engine"] == "defuddle"


def test_route_keeps_the_site_allowlist_and_body_cap():
    with _route(settings_allow=()) as (post, _idx, _root):
        status, res = post("/extract/page/dom", payload())
        assert status == 403 and res["code"] == "host_not_allowed"
    with _route() as (post, _idx, _root):
        status, res = post("/extract/page/dom", payload(markdown="x" * (dom.MAX_BODY_BYTES + 10)))
        assert status in (413, "closed")
        status, res = post("/extract/page/dom", payload(markdown="Subscribe to continue reading. "
                                                                 "Already a subscriber? Sign in to continue."))
        assert status == 400 and res["page_state"] == "wall"
        status, _res = post("/extract/page", {"url": "https://news.example.org/a", "pad": "x" * 70000})
        assert status in (413, "closed")  # every other route keeps the 64 KB cap
