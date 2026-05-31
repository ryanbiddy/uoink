"""Regression tests for the v3.2.1 splash hotfix.

Run: python tests/test_splash_hotfix.py
"""
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import uoink_splash  # noqa: E402


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


class FakeWindow:
    def __init__(self):
        self.calls = []

    def destroy(self):
        self.calls.append("destroy")

    def close(self):
        self.calls.append("close")

    def minimize(self):
        self.calls.append("minimize")


def test_js_api_close_destroys_window_and_writes_sentinel():
    fake = FakeWindow()
    api = uoink_splash.JsApi()
    api.attach(fake)
    with tempfile.TemporaryDirectory() as d:
        sentinel = Path(d) / ".first-run-done"
        api._sentinel = sentinel
        api.close()
        time.sleep(0.2)
        _assert(api._dismissed is True, "close should mark the splash dismissed")
        _assert(sentinel.read_text(encoding="utf-8").strip() == uoink_splash.VERSION,
                "close should write the splash sentinel")
        _assert(fake.calls == ["destroy"], f"close should destroy, got {fake.calls}")
        api.close()
        time.sleep(0.1)
        _assert(fake.calls == ["destroy"], "close should be idempotent")
    print("ok  JsApi.close: writes sentinel + destroys window + idempotent")


def test_splash_copy_and_dismiss_order():
    html = (Path(__file__).resolve().parent.parent
            / "assets" / "splash" / "index.html").read_text(encoding="utf-8")
    _assert("Click the rust U" not in html, "old pre-positioning-lock copy remains")
    _assert("Save the source. Write in your <em>voice.</em>" in html,
            "locked splash headline missing")
    _assert("Uoink any video, audio, or article to save the source on your disk" in html,
            "locked splash body missing")
    dismiss_src = html.split("function dismiss()", 1)[1].split(
        "async function openLastYoutube", 1)[0]
    _assert(dismiss_src.index("native.close") < dismiss_src.index("native.minimize"),
            "dismiss should prefer native.close over native.minimize")
    _assert('event.key === "Escape"' in html, "Escape-to-dismiss missing")
    print("ok  splash HTML: locked copy + close-before-minimize dismiss")


def main():
    test_js_api_close_destroys_window_and_writes_sentinel()
    test_splash_copy_and_dismiss_order()
    print("\nALL SPLASH HOTFIX TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
