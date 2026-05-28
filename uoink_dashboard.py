r"""uoink_dashboard.py -- pywebview dashboard window (Tier 2 GUI).

Subprocess entrypoint launched by the tray's left-click action. Standard
chrome (resizable, default decorations matching mock 3.2.1's title bar +
window controls), 1280x800, loads http://127.0.0.1:5179/dashboard.

Why a subprocess: pywebview's main loop must run on the GUI thread, and the
helper's main thread is already owning serve_forever(). Spawning a separate
process keeps both lifecycles independent -- closing the dashboard window
never touches the helper.

JsApi is intentionally small: Codex's dashboard HTML only feature-detects
window.pywebview.api, so the only call worth exposing today is open_url for
external links. Falls back to opening the URL in the default browser if
pywebview/WebView2 isn't available.
"""
from __future__ import annotations

import logging
import sys
import webbrowser

log = logging.getLogger("uoink.dashboard")

DASHBOARD_URL = "http://127.0.0.1:5179/dashboard"
WIDTH, HEIGHT = 1280, 800


class JsApi:
    """window.pywebview.api.* surface for the dashboard window. Today the
    dashboard HTML doesn't call into native; expose open_url for future
    external-link clicks so Codex's feature-detection has something to find."""

    def open_url(self, url):
        try:
            webbrowser.open(url)
        except Exception as e:
            log.debug("open_url failed: %s", e)
        return True


def main() -> int:
    try:
        import webview
    except Exception as e:
        log.debug("pywebview unavailable; opening dashboard in default browser: %s", e)
        webbrowser.open(DASHBOARD_URL)
        return 0
    webview.create_window(
        "Uoink",
        DASHBOARD_URL,
        width=WIDTH,
        height=HEIGHT,
        resizable=True,
        js_api=JsApi(),
    )
    webview.start()
    return 0


if __name__ == "__main__":
    sys.exit(main())
