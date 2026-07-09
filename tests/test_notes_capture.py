"""Context-layer item 1 -- quick notes / musings capture.

A note is a first-class uoink: the user jots text, it lands in the same corpus
as everything else (source_type='note', platform='note', author='You'),
classified for a topic, and queryable by their AI over MCP and by them via
search + facets, with no special-casing.

Run: python tests/test_notes_capture.py  (also collected by pytest tests/)

Red on unpatched main: notes.py doesn't exist, POST /notes 404s, and the
platform/source-type facet has no 'note' label.

Coverage:
- notes.build_note: derives a title from the first line, defaults author to
  You, and fails honestly on empty text (nothing saved).
- notes.persist_note: writes the corpus UNDER THE OUTPUT ROOT (not
  %LOCALAPPDATA%) as source_type='note', author='You', with a classified or
  Uncategorized topic; corpus file is named <slug>.md so the disk-walk
  fallback finds it.
- Route POST /notes: token-gated, persists a note, relays honest empty error.
- The note surfaces in /recent, /memory/search, and /library/facets (as a
  filterable platform + source-type), and the MCP tools read it with no
  special-casing.
"""
from __future__ import annotations

import json
import tempfile
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import notes  # noqa: E402
import index as index_mod  # noqa: E402
import server  # noqa: E402
import uoink_mcp_tools  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
_PORT = 0


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


# ---- pure note logic ------------------------------------------------------

def test_build_note_derives_title_and_author():
    note = notes.build_note(
        text="# First musing\n\nA thought worth keeping about local AI context.")
    _assert(note.get("ok"), f"valid note should build: {note}")
    _assert(note["title"] == "First musing",
            f"title from first line, marker stripped: {note['title']}")
    _assert(note["author"] == "You", f"default author is You: {note}")
    _assert(note["video_id"].startswith("note_"), f"note id shape: {note}")
    _assert(note["slug"].startswith("first-musing-"),
            f"readable slug from title: {note['slug']}")

    # No title given, no heading marker: first non-blank line becomes the title.
    plain = notes.build_note(text="just a raw jotting\nsecond line")
    _assert(plain["title"] == "just a raw jotting",
            f"first line title: {plain['title']}")

    # Explicit title + author override both win.
    over = notes.build_note(text="body", title="Custom", author="Ryan")
    _assert(over["title"] == "Custom" and over["author"] == "Ryan",
            f"explicit title/author honoured: {over}")
    print("ok  build_note derives title + defaults author to You")


def test_build_note_rejects_empty():
    for bad in ("", "   ", "\n\t \n"):
        res = notes.build_note(text=bad)
        _assert(res.get("ok") is False and res.get("code") == "empty",
                f"empty note must fail honestly: {bad!r} -> {res}")
    print("ok  build_note rejects empty text (nothing saved)")


def test_persist_note_writes_under_output_root():
    with tempfile.TemporaryDirectory() as out_root, \
            tempfile.TemporaryDirectory() as d:
        out_root = Path(out_root).resolve()
        idx = index_mod.Index.open(Path(d) / "index.db")
        try:
            note = notes.build_note(
                text="Kubernetes autoscaling notes for the platform migration.")
            # A trivial classifier so topic isn't None (proves the hook fires).
            vid = notes.persist_note(
                idx, note, data_root=out_root,
                topic_classifier=lambda ctx: "DevOps")
            _assert(vid == note["video_id"], f"returns the video_id: {vid}")
            row = idx.get_yoink(vid)
            _assert(row and row.get("source_type") == "note",
                    f"row source_type=note: {row}")
            _assert(row.get("platform") == "note", f"row platform=note: {row}")
            _assert(row.get("author") == "You", f"row author=You: {row}")
            _assert(row.get("topic") == "DevOps", f"topic classified: {row}")
            corpus = Path((row or {}).get("corpus_path") or "").resolve()
            _assert(str(corpus).startswith(str(out_root)),
                    f"corpus under output root {out_root}: {corpus}")
            _assert(server.DATA_ROOT.resolve() not in corpus.parents,
                    f"corpus must NOT be under %LOCALAPPDATA% "
                    f"({server.DATA_ROOT}): {corpus}")
            _assert(corpus.exists(), f"corpus file exists: {corpus}")
            # Named <slug>.md under Notes/ so the disk-walk fallback finds it.
            _assert(corpus.name == f"{row['slug']}.md",
                    f"corpus named after slug: {corpus.name}")
            _assert(corpus.parent.parent.name == "Notes",
                    f"corpus under Notes/: {corpus}")
            text = corpus.read_text(encoding="utf-8")
            _assert("Kubernetes autoscaling" in text, "body in corpus")
        finally:
            idx.close()
    print("ok  persist_note writes source_type=note under the output root")


def test_persist_note_topic_falls_back_when_unclassified():
    with tempfile.TemporaryDirectory() as out_root, \
            tempfile.TemporaryDirectory() as d:
        idx = index_mod.Index.open(Path(d) / "index.db")
        try:
            note = notes.build_note(text="a plain thought")
            vid = notes.persist_note(
                idx, note, data_root=Path(out_root),
                topic_classifier=lambda ctx: None)
            row = idx.get_yoink(vid)
            # topic None reads as Uncategorized in the UI; the row just carries
            # no topic, which is the honest state.
            _assert(row and row.get("topic") in (None, "", "Uncategorized"),
                    f"unclassified topic is empty/Uncategorized: {row}")
        finally:
            idx.close()
    print("ok  persist_note leaves topic empty when the classifier declines")


# ---- route ---------------------------------------------------------------

def _post(path, payload, *, token=True):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Uoink-Token"] = server.TOKEN
    req = urllib.request.Request(
        f"http://127.0.0.1:{_PORT}{path}",
        data=json.dumps(payload).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def _get(path, *, token=True):
    headers = {}
    if token:
        headers["X-Uoink-Token"] = server.TOKEN
    req = urllib.request.Request(
        f"http://127.0.0.1:{_PORT}{path}", headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


@contextmanager
def _server(settings=None):
    global _PORT
    original_read = server._read_settings
    server._read_settings = lambda: dict(settings or {})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    _PORT = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield
    finally:
        httpd.shutdown()
        server._read_settings = original_read


def test_route_token_gated():
    with _server():
        status, _res = _post("/notes", {"text": "hi"}, token=False)
        _assert(status == 403, f"no token must 403 (red on main: 404): {status}")
    print("ok  /notes is token-gated")


def test_route_relays_empty_error():
    with _server():
        status, res = _post("/notes", {"text": "   "})
        _assert(status == 200 and res.get("ok") is False
                and res.get("code") == "empty",
                f"empty note must relay honest failure: {status} {res}")
    print("ok  route relays the honest empty-note error")


def test_route_persists_and_surfaces_everywhere():
    with tempfile.TemporaryDirectory() as out_root, \
            tempfile.TemporaryDirectory() as d:
        out_root = Path(out_root).resolve()
        idx = index_mod.Index.open(Path(d) / "index.db")
        original_get_index = server._get_index
        original_root = server.DESKTOP_ROOT
        original_mcp_base = getattr(uoink_mcp_tools, "_backend", None)
        server._get_index = lambda: idx
        server.DESKTOP_ROOT = out_root
        # Point the MCP tools at the same server module + index.
        uoink_mcp_tools.bind_backend(server)
        try:
            with _server():
                status, res = _post("/notes", {
                    "text": "Zettelkasten thoughts on capturing fleeting ideas.",
                    "title": "On fleeting notes"})
                _assert(status == 200 and res.get("ok") is True,
                        f"note capture failed: {status} {res}")
                vid = res.get("video_id")
                slug = res.get("slug")
                _assert(vid and slug, f"persisted id/slug missing: {res}")
                _assert(res.get("source_type") == "note"
                        and res.get("platform") == "note"
                        and res.get("author") == "You",
                        f"response taxonomy: {res}")

                # /recent includes the note.
                st, recent = _get("/recent")
                ids = {r.get("video_id") or r.get("slug")
                       for r in (recent.get("recent") or [])}
                _assert(st == 200 and (vid in ids or slug in ids),
                        f"note must show in /recent: {recent}")

                # /memory/search finds it by body text + filters to it.
                st, ms = _get("/memory/search?q=Zettelkasten")
                vids = {r.get("video_id") for r in (ms.get("results") or [])}
                _assert(st == 200 and vid in vids,
                        f"note must be searchable: {ms}")
                st, msf = _get("/memory/search?source_type=note")
                fvids = {r.get("video_id") for r in (msf.get("results") or [])}
                _assert(vid in fvids,
                        f"note must filter by source_type=note: {msf}")

                # /library/facets exposes it as a filterable platform + type.
                st, facets = _get("/library/facets")
                blob = json.dumps(facets)
                _assert(st == 200 and '"note"' in blob,
                        f"facets must include note: {facets}")

                # MCP reads it with no special-casing (FTS search + corpus read).
                mcp_search = uoink_mcp_tools.search_uoinks(
                    {"query": "Zettelkasten"})
                mslugs = {r.get("slug")
                          for r in (mcp_search.get("results") or [])}
                _assert(slug in mslugs,
                        f"MCP search must find the note: {mcp_search}")
                mcp_corpus = uoink_mcp_tools.get_uoink_corpus({"slug": slug})
                _assert(mcp_corpus.get("ok") is not False
                        and "Zettelkasten" in json.dumps(mcp_corpus),
                        f"MCP must read the note corpus: {mcp_corpus}")
        finally:
            server._get_index = original_get_index
            server.DESKTOP_ROOT = original_root
            if original_mcp_base is not None:
                uoink_mcp_tools.bind_backend(original_mcp_base)
            idx.close()
    print("ok  note persists + surfaces in /recent, /memory/search, facets, MCP")


def main() -> int:
    test_build_note_derives_title_and_author()
    test_build_note_rejects_empty()
    test_persist_note_writes_under_output_root()
    test_persist_note_topic_falls_back_when_unclassified()
    test_route_token_gated()
    test_route_relays_empty_error()
    test_route_persists_and_surfaces_everywhere()
    print("\nall notes-capture tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
