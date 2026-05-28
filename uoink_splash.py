r"""uoink_splash.py -- pywebview splash window (Tier 2 GUI).

Subprocess entrypoint launched by server.py on the first boot (sentinel absent)
via subprocess.Popen([pythonw, this_script]). Runs pywebview's main loop in
its OWN process so the helper's main thread (HTTP serve_forever) is untouched.

Loads Codex's HTML at http://127.0.0.1:5179/splash. The splash JS itself
fetches /diagnose to choose the success vs. failure variant, so this wrapper
doesn't need to inject state -- it just hosts the window.

Window: 480x320 frameless, on top, positioned bottom-right of primary monitor.
Slide-up over ~400ms via window.move() in a background thread (pywebview
windows don't natively animate). After an 8s linger the splash dismisses
(minimize -- so the user can still re-summon via the tray) and writes the
%LOCALAPPDATA%\Uoink\.first-run-done sentinel. JsApi method names mirror what
the shipped splash HTML calls (snake_case: open_dashboard / minimize / close).

Graceful degradation: pywebview unavailable -> log a debug line and exit 0;
the boot balloon (server.maybe_toast) remains the fallback "it's running"
affordance.
"""
from __future__ import annotations

import logging
import subprocess
import sys
import threading
import time
from pathlib import Path

log = logging.getLogger("uoink.splash")

HERE = Path(__file__).parent.resolve()
SPLASH_URL = "http://127.0.0.1:5179/splash"
WIDTH, HEIGHT = 480, 320
MARGIN = 32           # bottom-right offset
LINGER_SEC = 8.0      # mock 2.2.1: 8s linger before minimize
ANIM_MS = 400         # slide-up duration
ANIM_STEPS = 24


def _sentinel_path() -> Path:
    """Resolve %LOCALAPPDATA%\\Uoink\\.first-run-done via _platform."""
    try:
        sys.path.insert(0, str(HERE))
        import _platform  # noqa: F401 -- import for its side effect of resolving the path
        return _platform.user_data_dir() / ".first-run-done"
    except Exception:
        return HERE / ".first-run-done"


def _write_sentinel(path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("first run shown\n", encoding="utf-8")
    except OSError as e:
        log.debug("sentinel write failed: %s", e)


def _spawn_dashboard() -> None:
    """Launch the dashboard pywebview window in its OWN subprocess so the
    splash can minimize/exit without taking the dashboard with it."""
    script = str(HERE / "uoink_dashboard.py")
    try:
        creationflags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
        subprocess.Popen([sys.executable, script], creationflags=creationflags)
    except Exception as e:
        log.warning("spawn dashboard failed: %s", e)


class JsApi:
    """window.pywebview.api.* surface. Names are snake_case to match the
    shipped splash HTML (native.open_dashboard / native.minimize / native.close)."""

    def __init__(self) -> None:
        self._window = None
        self._sentinel = _sentinel_path()
        self._dismissed = False

    def attach(self, window) -> None:
        self._window = window

    # ---- IPC methods called from the splash HTML ----
    def open_dashboard(self):
        _spawn_dashboard()
        self._dismiss()
        return True

    def minimize(self):
        self._dismiss()
        return True

    def close(self):
        # Per spec: never truly close -- minimize so the user can re-summon
        # from the tray. Idempotent.
        self._dismiss()
        return True

    # ---- internal ----
    def _dismiss(self) -> None:
        if self._dismissed:
            return
        self._dismissed = True
        _write_sentinel(self._sentinel)
        try:
            if self._window is not None:
                self._window.minimize()
        except Exception as e:
            log.debug("window.minimize failed: %s", e)


def _slide_up(window, final_x: int, sh: int) -> None:
    """Animate the window from below-screen up to its final y over ANIM_MS."""
    final_y = sh - HEIGHT - MARGIN
    start_y = sh
    step_delay = (ANIM_MS / 1000.0) / ANIM_STEPS
    try:
        for i in range(1, ANIM_STEPS + 1):
            t = i / ANIM_STEPS
            # ease-out cubic: 1 - (1-t)^3
            eased = 1 - (1 - t) ** 3
            window.move(final_x, int(start_y + (final_y - start_y) * eased))
            time.sleep(step_delay)
        window.move(final_x, final_y)
    except Exception as e:
        log.debug("slide animation failed: %s", e)


def main() -> int:
    sentinel = _sentinel_path()
    # Belt-and-suspenders: if the sentinel already exists, do nothing. Server
    # also gates the spawn on this, but a double-spawn race is harmless this way.
    if sentinel.is_file():
        return 0
    try:
        import webview  # pywebview
    except Exception as e:
        log.debug("pywebview unavailable; no splash: %s", e)
        return 0

    # Best-effort screen size; pywebview.screens may be empty before start().
    sw, sh = 1920, 1080
    try:
        screens = list(getattr(webview, "screens", []) or [])
        if screens:
            sw, sh = int(screens[0].width), int(screens[0].height)
    except Exception:
        pass
    final_x = sw - WIDTH - MARGIN

    api = JsApi()
    window = webview.create_window(
        "Uoink",
        SPLASH_URL,
        frameless=True,
        on_top=True,
        resizable=False,
        width=WIDTH,
        height=HEIGHT,
        x=final_x,
        y=sh,            # start off-screen so frame-1 doesn't flash at final position
        js_api=api,
    )
    api.attach(window)

    def _after_loaded():
        _slide_up(window, final_x, sh)
        time.sleep(LINGER_SEC)
        api._dismiss()

    threading.Thread(target=_after_loaded, name="uoink-splash-anim", daemon=True).start()
    try:
        webview.start()
    finally:
        # Cover any path where start() returns without going through _dismiss.
        _write_sentinel(sentinel)
    return 0


if __name__ == "__main__":
    sys.exit(main())
