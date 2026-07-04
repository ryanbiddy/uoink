"""U-01 backend enablers -- GET /open-extension + GET /hooks/guide.

Run: python tests/test_u01_backend_enablers.py  (also collected by pytest tests/)

Two routes the v3.2.6 UX overhaul needs before any UI work can land:

/open-extension  reveals the bundled extension folder (HERE/extension) in
                 the OS file manager so the dashboard's "get the extension"
                 card (UX-07) can point chrome://extensions "Load unpacked"
                 at a folder the user can actually see. Follows the
                 /open-prompts reveal pattern, NOT the sandboxed
                 /open-folder (the extension lives in the install dir,
                 which is outside DESKTOP_ROOT by design). Token-gated.

/hooks/guide     serves the nine hook-type definitions from
                 _HOOK_TYPE_GUIDE as structured JSON so the in-app hooks
                 explainer (UX-14 / U-06) can render them without an
                 external link. Public product metadata, same posture as
                 /sources/manifest: no user data in the payload.

Red on unpatched main: both routes 404.

Also pins the _HOOK_TYPE_GUIDE prompt string byte-for-byte: the JSON route
is fed from the same definitions that build the classifier system prompt,
and this assert proves the refactor didn't drift a single classifier byte.
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
import _platform  # noqa: E402
import server  # noqa: E402

# Each test opens its own server on an OS-assigned ephemeral port (port 0)
# so back-to-back rebinds of a fixed port can't race on Windows.
_PORT = 0


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _get(path, *, token=True):
    headers = {"X-Uoink-Token": server.TOKEN} if token else {}
    req = urllib.request.Request(
        f"http://127.0.0.1:{_PORT}{path}", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


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


@contextmanager
def _fake_reveal(exc=None):
    """Swap _platform.reveal_in_file_manager for a recorder so the test
    never pops a real Explorer window. Yields the call list."""
    calls = []

    def fake(path):
        calls.append(Path(path))
        if exc is not None:
            raise exc

    original = _platform.reveal_in_file_manager
    _platform.reveal_in_file_manager = fake
    try:
        yield calls
    finally:
        _platform.reveal_in_file_manager = original


# ---- /open-extension ----

def test_open_extension_token_gated():
    with _server():
        status, _res = _get("/open-extension", token=False)
        _assert(status == 403, f"no token must 403, got {status}")


def test_open_extension_reveals_bundled_folder():
    expected = server.HERE / "extension"
    _assert(expected.is_dir(),
            f"repo must ship an extension folder at {expected}")
    with _server(), _fake_reveal() as calls:
        status, res = _get("/open-extension")
        _assert(status == 200,
                f"/open-extension must exist (red on main: 404), got {status}")
        _assert(res.get("ok") is True, f"ok flag: {res}")
        _assert(res.get("path") == str(expected),
                f"path must be the bundled extension dir: {res}")
        _assert(calls == [expected],
                f"reveal_in_file_manager must get exactly {expected}: {calls}")


def test_open_extension_reveal_failure_is_reported():
    with _server(), _fake_reveal(exc=OSError("no explorer here")):
        status, res = _get("/open-extension")
        _assert(status == 200, f"failure still answers 200-json: {status}")
        _assert(res.get("ok") is False, f"ok must be False: {res}")
        _assert("no explorer here" in (res.get("error") or ""),
                f"error must carry the cause: {res}")


def test_open_extension_missing_folder():
    original_here = server.HERE
    with tempfile.TemporaryDirectory() as d:
        server.HERE = Path(d)  # no extension/ inside
        try:
            with _server(), _fake_reveal() as calls:
                status, res = _get("/open-extension")
                _assert(status == 200, f"missing folder answers 200-json: {status}")
                _assert(res.get("ok") is False, f"ok must be False: {res}")
                _assert("not found" in (res.get("error") or ""),
                        f"error must say the folder is missing: {res}")
                _assert(calls == [], f"nothing to reveal: {calls}")
        finally:
            server.HERE = original_here


# ---- /hooks/guide ----

def test_hooks_guide_is_public_structured_json():
    with _server():
        # Public product metadata, same posture as /sources/manifest.
        status, res = _get("/hooks/guide", token=False)
        _assert(status == 200,
                f"/hooks/guide must exist unauthenticated (red on main: 404), "
                f"got {status}")
        _assert(res.get("ok") is True, f"ok flag: {res}")
        hooks = res.get("hooks")
        _assert(isinstance(hooks, list) and len(hooks) == 9,
                f"exactly 9 hook types: {hooks}")
        ids = [h.get("id") for h in hooks]
        _assert(set(ids) == set(server.HOOK_TYPES),
                f"ids must match HOOK_TYPES exactly: {ids}")
        _assert(len(set(ids)) == 9, f"no duplicate ids: {ids}")
        _assert(ids[0] == "curiosity_gap" and ids[-1] == "other",
                f"guide order preserved (curiosity_gap first, other last): {ids}")
        for h in hooks:
            _assert((h.get("label") or "").strip(),
                    f"every hook carries a display label: {h}")
            _assert((h.get("description") or "").strip(),
                    f"every hook carries a one-line definition: {h}")
        by_id = {h["id"]: h for h in hooks}
        _assert("information gap" in by_id["curiosity_gap"]["description"],
                f"definitions come from the classifier guide: "
                f"{by_id['curiosity_gap']}")


def test_hook_type_guide_prompt_unchanged():
    """The classifier system prompt must not drift when the guide becomes
    structured data. Byte-for-byte pin of the pre-refactor literal."""
    expected = (
        "Hook type categories (pick exactly one):\n"
        "- curiosity_gap: teases an answer or outcome without revealing it, "
        "opening an information gap the viewer wants closed.\n"
        "- question: opens by directly asking the viewer a question.\n"
        "- contrarian: leads with a claim that challenges a common belief or "
        "consensus.\n"
        "- story_open: opens with a personal anecdote or a narrative scene.\n"
        "- promise_list: promises a specific list or count of takeaways, e.g. "
        "'5 ways to ...'.\n"
        "- demo: opens by showing the thing in action -- a visual or live "
        "demonstration.\n"
        "- authority: opens by establishing credentials, results, or proof of "
        "expertise.\n"
        "- stakes: opens by emphasizing what the viewer stands to gain or "
        "lose.\n"
        "- other: none of the above, or no identifiable hook pattern."
    )
    _assert(server._HOOK_TYPE_GUIDE == expected,
            "_HOOK_TYPE_GUIDE drifted from the pinned classifier prompt")


def main():
    for fn in (
        test_open_extension_token_gated,
        test_open_extension_reveals_bundled_folder,
        test_open_extension_reveal_failure_is_reported,
        test_open_extension_missing_folder,
        test_hooks_guide_is_public_structured_json,
        test_hook_type_guide_prompt_unchanged,
    ):
        fn()
        print(f"ok  {fn.__name__}")
    print("\nall green")


if __name__ == "__main__":
    main()
