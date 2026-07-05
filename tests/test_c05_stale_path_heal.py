"""C-05 (CRIT-5) -- stale-path integrity + heal.

Run: python tests/test_c05_stale_path_heal.py  (also collected by pytest)

When the output folder moves (the Yoink->Uoink rename, a OneDrive shuffle,
a user reorganizing), every yoinks row keeps pointing at the dead root:
each content action fails while /health reports green. On the machine that
motivated this fix, 31 of 31 corpus paths were dead.

Red on unpatched main: _path_integrity_status / heal_stale_corpus_paths
don't exist and /health has no path_integrity key.

Coverage:
- integrity status counts missing files over every non-deleted row.
- /health carries path_integrity (cached), honest when rows are dead.
- the heal relinks rows to their real new location under the current
  output root (Topic\\slug\\file structure preserved), fixes sidecars,
  and leaves truly-gone rows in `unresolved` instead of guessing.
- the boot pass runs the heal when something is missing.
- doctor carries path_integrity so support triage sees it.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import threading
import urllib.request
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import index as index_mod  # noqa: E402
import server  # noqa: E402

_PORT = 0


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _seed(idx, root: Path, video_id: str, topic: str, slug: str) -> Path:
    folder = root / topic / slug
    folder.mkdir(parents=True, exist_ok=True)
    corpus = folder / f"{slug}.md"
    corpus.write_text(f"# {slug}\n", encoding="utf-8")
    sidecar = folder / f"{slug}.json"
    sidecar.write_text("{}", encoding="utf-8")
    idx.upsert_yoink({
        "video_id": video_id, "slug": slug, "channel": "TestChannel",
        "title": slug, "topic": topic, "hook_type": "demo",
        "yoinked_at": "2026-07-01T10:00:00",
        "corpus_path": str(corpus), "sidecar_path": str(sidecar),
        "source_type": "youtube",
    }, content=f"{slug} body")
    return folder


@contextmanager
def _fresh_state(idx, root: Path):
    original_index = server._get_index
    original_root = server.DESKTOP_ROOT
    server._get_index = lambda: idx
    server.DESKTOP_ROOT = root
    server._path_integrity_cache["result"] = None
    try:
        yield
    finally:
        server._get_index = original_index
        server.DESKTOP_ROOT = original_root
        server._path_integrity_cache["result"] = None


def _get(path):
    req = urllib.request.Request(f"http://127.0.0.1:{_PORT}{path}")
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.status, json.loads(r.read().decode())


@contextmanager
def _server():
    global _PORT
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    _PORT = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield
    finally:
        httpd.shutdown()


def test_integrity_heal_and_health():
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        old_root = base / "Yoink"
        idx = index_mod.Index.open(base / "index.db")
        try:
            _seed(idx, old_root, "vidaaaaaaaa", "AI and ML", "First_Video")
            _seed(idx, old_root, "vidbbbbbbbb", "AI and ML", "Second_Video")
            _seed(idx, old_root, "vidcccccccc", "Career", "Third_Video")
            _seed(idx, old_root, "vidgoneeeee", "Career", "Deleted_Video")

            # The move that breaks everything: rename the whole root.
            new_root = base / "Uoink"
            old_root.rename(new_root)
            # ...and one uoink's files are gone for good.
            shutil.rmtree(new_root / "Career" / "Deleted_Video")

            with _fresh_state(idx, new_root):
                # 1. Integrity sees every dead row.
                status = server._path_integrity_status(force=True)
                _assert(status["ok"] is False, f"must not be ok: {status}")
                _assert(status["checked"] == 4 and status["missing"] == 4,
                        f"4/4 rows are dead after the move: {status}")
                _assert("hint" in status, "failing status carries a hint")
                print("ok  integrity check sees the dead paths")

                # 2. /health stops green-lying.
                with _server():
                    _status, health = _get("/health")
                    integrity = health.get("path_integrity")
                    _assert(integrity and integrity["ok"] is False
                            and integrity["missing"] == 4,
                            f"/health must surface the failure: {integrity}")
                print("ok  /health surfaces path_integrity failure")

                # 3. Heal relinks what exists, reports what doesn't.
                report = server.heal_stale_corpus_paths()
                _assert(report["relinked"] == 3,
                        f"3 rows have new homes: {report}")
                _assert(report["unresolved"] == ["vidgoneeeee"],
                        f"the deleted one stays unresolved: {report}")
                _assert(report["ok"] is False,
                        "unresolved rows keep the report honest")
                row = idx.get_yoink("vidaaaaaaaa")
                _assert(str(new_root) in row["corpus_path"]
                        and Path(row["corpus_path"]).exists(),
                        f"row must point at the new root: {row['corpus_path']}")
                _assert(Path(row["sidecar_path"]).exists(),
                        f"sidecar relinked too: {row['sidecar_path']}")
                print("ok  heal relinks 3, reports 1 unresolved, never guesses")

                # 4. Integrity after heal: only the truly-gone row remains.
                status = server._path_integrity_status(force=True)
                _assert(status["missing"] == 1, f"after heal: {status}")
                with _server():
                    _status, health = _get("/health")
                    _assert(health["path_integrity"]["missing"] == 1,
                            f"/health after heal: {health['path_integrity']}")
                print("ok  post-heal integrity counts only the deleted row")
        finally:
            idx.close()


def test_boot_pass_heals():
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        old_root = base / "Yoink"
        idx = index_mod.Index.open(base / "index.db")
        try:
            _seed(idx, old_root, "vidbootaaaa", "AI and ML", "Boot_Video")
            new_root = base / "Uoink"
            old_root.rename(new_root)
            with _fresh_state(idx, new_root):
                server._heal_stale_corpus_paths_at_boot()
                row = idx.get_yoink("vidbootaaaa")
                _assert(Path(row["corpus_path"]).exists(),
                        f"boot pass must relink: {row['corpus_path']}")
                status = server._path_integrity_status(force=True)
                _assert(status["ok"] is True, f"clean after boot heal: {status}")
            print("ok  boot pass heals a moved library on launch")
        finally:
            idx.close()


def test_doctor_and_diagnose_carry_integrity():
    server_src = (Path(__file__).resolve().parent.parent / "server.py").read_text(
        encoding="utf-8")
    _assert('"path_integrity": _path_integrity_status(force=True)' in server_src,
            "doctor must carry path_integrity")
    _assert('add("path_integrity", "error"' in server_src,
            "/diagnose must surface the failing check with a warning")
    _assert('"--heal-paths" in argv' in server_src,
            "--heal-paths CLI entry missing")
    print("ok  doctor, /diagnose, and --heal-paths wired")


def main():
    test_integrity_heal_and_health()
    test_boot_pass_heals()
    test_doctor_and_diagnose_carry_integrity()
    print("\nall green")


if __name__ == "__main__":
    main()
