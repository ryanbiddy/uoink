r"""uoink_splash.py -- pywebview splash window (Tier 2 GUI).

Subprocess entrypoint launched by server.py on the first boot for each installed
version (sentinel absent or containing an older version) via
subprocess.Popen([pythonw, this_script]). Runs pywebview's main loop in its OWN
process so the helper's main thread (HTTP serve_forever) is untouched.

Loads Codex's HTML at http://127.0.0.1:5179/splash. The splash JS itself
fetches /diagnose to choose the success vs. failure variant, so this wrapper
doesn't need to inject state -- it just hosts the window.

Window: 640x450 frameless, on top, positioned bottom-right of primary monitor.
Slide-up over ~400ms via window.move() in a background thread (pywebview
windows don't natively animate). After an 8s linger the splash dismisses,
closes its own webview process, and writes the current version to the
%LOCALAPPDATA%\Uoink\.first-run-done sentinel. JsApi
method names mirror what the shipped splash HTML calls (snake_case:
open_dashboard / minimize / close). First-run extension setup can hold the
window open until the user marks the unpacked extension as loaded.

Graceful degradation: pywebview unavailable -> log a debug line and exit 0;
the boot balloon (server.maybe_toast) remains the fallback "it's running"
affordance.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

log = logging.getLogger("uoink.splash")

HERE = Path(__file__).parent.resolve()
SPLASH_URL = "http://127.0.0.1:5179/splash"
DASHBOARD_SETTINGS_URL = "http://127.0.0.1:5179/dashboard#settings/byo-key"
WIDTH, HEIGHT = 640, 450
MARGIN = 32           # bottom-right offset
LINGER_SEC = 8.0      # mock 2.2.1: 8s linger before minimize
ANIM_MS = 400         # slide-up duration
ANIM_STEPS = 24


def _read_version() -> str:
    try:
        from helper._version import __version__ as version
    except Exception:
        try:
            version = (HERE / "VERSION").read_text(encoding="utf-8").strip()
        except OSError:
            return "0.0.0-unknown"
    return version or "0.0.0-unknown"


VERSION = _read_version()


def _sentinel_path() -> Path:
    """Resolve %LOCALAPPDATA%\\Uoink\\.first-run-done via _platform."""
    try:
        sys.path.insert(0, str(HERE))
        import _platform  # noqa: F401 -- import for its side effect of resolving the path
        return _platform.user_data_dir() / ".first-run-done"
    except Exception:
        return HERE / ".first-run-done"


def _extension_sentinel_path() -> Path:
    """Resolve %LOCALAPPDATA%\\Uoink\\.extension-loaded for the load hint."""
    try:
        sys.path.insert(0, str(HERE))
        import _platform
        return _platform.user_data_dir() / ".extension-loaded"
    except Exception:
        return HERE / ".extension-loaded"


def _extension_dir() -> Path:
    return HERE / "extension"


BROWSER_CATALOG = [
    {
        "id": "edge",
        "name": "Microsoft Edge",
        "url": "edge://extensions/",
        "commands": ["msedge", "msedge.exe"],
        "progids": ["msedge", "microsoftedge"],
        "paths": [
            ("PROGRAMFILES(X86)", "Microsoft/Edge/Application/msedge.exe"),
            ("PROGRAMFILES", "Microsoft/Edge/Application/msedge.exe"),
            ("LOCALAPPDATA", "Microsoft/Edge/Application/msedge.exe"),
        ],
    },
    {
        "id": "chrome",
        "name": "Chrome",
        "url": "chrome://extensions/",
        "commands": ["chrome", "chrome.exe"],
        "progids": ["chrome"],
        "paths": [
            ("PROGRAMFILES", "Google/Chrome/Application/chrome.exe"),
            ("PROGRAMFILES(X86)", "Google/Chrome/Application/chrome.exe"),
            ("LOCALAPPDATA", "Google/Chrome/Application/chrome.exe"),
        ],
    },
    {
        "id": "brave",
        "name": "Brave",
        "url": "brave://extensions/",
        "commands": ["brave", "brave.exe", "brave-browser"],
        "progids": ["brave"],
        "paths": [
            ("PROGRAMFILES", "BraveSoftware/Brave-Browser/Application/brave.exe"),
            ("PROGRAMFILES(X86)", "BraveSoftware/Brave-Browser/Application/brave.exe"),
            ("LOCALAPPDATA", "BraveSoftware/Brave-Browser/Application/brave.exe"),
        ],
    },
    {
        "id": "vivaldi",
        "name": "Vivaldi",
        "url": "vivaldi://extensions/",
        "commands": ["vivaldi", "vivaldi.exe"],
        "progids": ["vivaldi"],
        "paths": [
            ("PROGRAMFILES", "Vivaldi/Application/vivaldi.exe"),
            ("PROGRAMFILES(X86)", "Vivaldi/Application/vivaldi.exe"),
            ("LOCALAPPDATA", "Vivaldi/Application/vivaldi.exe"),
        ],
    },
    {
        "id": "opera-gx",
        "name": "Opera GX",
        "url": "opera://extensions/",
        "commands": ["opera", "launcher.exe"],
        "progids": ["operagx", "opera gx"],
        "paths": [
            ("LOCALAPPDATA", "Programs/Opera GX/launcher.exe"),
            ("PROGRAMFILES", "Opera GX/launcher.exe"),
        ],
    },
    {
        "id": "arc",
        "name": "Arc",
        "url": "arc://extensions/",
        "commands": ["arc", "arc.exe"],
        "progids": ["arc"],
        "paths": [
            ("LOCALAPPDATA", "Microsoft/WindowsApps/Arc.exe"),
            ("LOCALAPPDATA", "The Browser Company/Arc/Application/Arc.exe"),
        ],
    },
]


def _write_sentinel(path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{VERSION}\n", encoding="utf-8")
    except OSError as e:
        log.debug("sentinel write failed: %s", e)


def _sentinel_current(path: Path) -> bool:
    try:
        return path.read_text(encoding="utf-8").strip() == VERSION
    except OSError:
        return False


def _helper_health_ok() -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:5179/health", timeout=1.0) as res:
            payload = json.loads(res.read().decode("utf-8"))
            return bool(payload.get("ok", True))
    except Exception:
        return False


def _failed_splash_html(detail: str) -> str:
    try:
        html = (HERE / "assets" / "splash" / "index.html").read_text(encoding="utf-8")
    except OSError:
        html = "<!doctype html><title>Uoink</title><body>Uoink failed to start.</body>"
    injected = (
        "<script>window.UOINK_SPLASH_BOOT_FAILED = "
        + json.dumps(detail)
        + ";</script>"
    )
    if "</head>" in html:
        return html.replace("</head>", f"{injected}\n</head>", 1)
    return injected + html


def _browser_by_id(browser_id: str | None):
    wanted = (browser_id or "").lower()
    return next((browser for browser in BROWSER_CATALOG if browser["id"] == wanted), None)


def _default_browser_prog_id() -> str:
    if sys.platform != "win32":
        return ""
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "ProgId")
            return str(value or "")
    except Exception as e:
        log.debug("default browser lookup failed: %s", e)
        return ""


def _browser_from_prog_id(prog_id: str):
    needle = (prog_id or "").lower()
    if not needle:
        return None
    for browser in BROWSER_CATALOG:
        if any(token in needle for token in browser["progids"]):
            return browser
    return None


def _browser_executable(browser) -> str:
    for env_name, relative in browser["paths"]:
        root = os.environ.get(env_name)
        if not root:
            continue
        path = Path(root) / Path(relative)
        if path.is_file():
            return str(path)
    for command in browser["commands"]:
        found = shutil.which(command)
        if found:
            return found
    return ""


def _browser_descriptor(browser, *, is_default: bool = False) -> dict:
    executable = _browser_executable(browser)
    return {
        "id": browser["id"],
        "name": browser["name"],
        "url": browser["url"],
        "executable": executable,
        "installed": bool(executable),
        "is_default": is_default,
    }


def _available_browsers() -> list[dict]:
    default = _browser_from_prog_id(_default_browser_prog_id())
    browsers = []
    for browser in BROWSER_CATALOG:
        descriptor = _browser_descriptor(browser, is_default=browser is default)
        if descriptor["installed"] or descriptor["is_default"]:
            browsers.append(descriptor)
    return browsers


def _preferred_browser() -> dict:
    browsers = _available_browsers()
    default = next((browser for browser in browsers if browser["is_default"]), None)
    if default:
        return default
    installed = next((browser for browser in browsers if browser["installed"]), None)
    if installed:
        return installed
    return {
        "id": "chromium",
        "name": "your Chromium browser",
        "url": "chrome://extensions/",
        "executable": "",
        "installed": False,
        "is_default": False,
    }


def _open_extensions_page(browser_id: str | None = None) -> bool:
    selected = _browser_by_id(browser_id)
    browser = _browser_descriptor(selected) if selected else _preferred_browser()
    try:
        if browser.get("executable"):
            creationflags = 0x08000000 if sys.platform == "win32" else 0
            subprocess.Popen([str(browser["executable"]), str(browser["url"])],
                             creationflags=creationflags)
            return True
        webbrowser.open(str(browser["url"]))
        return True
    except Exception as e:
        log.debug("open extensions page failed: %s", e)
        return False


def _copy_to_clipboard(text: str) -> bool:
    if not text:
        return False
    if sys.platform != "win32":
        return False
    creationflags = 0x08000000
    try:
        subprocess.run(
            ["clip.exe"],
            input=text,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
            creationflags=creationflags,
        )
        return True
    except Exception as e:
        log.debug("clip.exe copy failed: %s", e)
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value $args[0]", text],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
            creationflags=creationflags,
        )
        return True
    except Exception as e:
        log.debug("copy extension path failed: %s", e)
        return False


def _spawn_dashboard(url: str | None = None) -> None:
    """Launch the dashboard pywebview window in its OWN subprocess so the
    splash can minimize/exit without taking the dashboard with it."""
    script = str(HERE / "uoink_dashboard.py")
    try:
        creationflags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
        cmd = [sys.executable, script]
        if url:
            cmd.append(url)
        subprocess.Popen(cmd, creationflags=creationflags)
    except Exception as e:
        log.warning("spawn dashboard failed: %s", e)


class JsApi:
    """window.pywebview.api.* surface. Names are snake_case to match the
    shipped splash HTML (native.open_dashboard / native.minimize / native.close)."""

    def __init__(self) -> None:
        self._window = None
        self._sentinel = _sentinel_path()
        self._extension_sentinel = _extension_sentinel_path()
        self._hold_open = False
        self._dismissed = False

    def attach(self, window) -> None:
        self._window = window

    # ---- IPC methods called from the splash HTML ----
    def open_dashboard(self):
        _spawn_dashboard()
        self._dismiss()
        return True

    def open_settings(self):
        _spawn_dashboard(DASHBOARD_SETTINGS_URL)
        self._dismiss()
        return True

    def open_url(self, url):
        try:
            webbrowser.open(str(url))
        except Exception as e:
            log.debug("open_url failed: %s", e)
        return True

    def set_window_title(self, title):
        try:
            if self._window is not None:
                self._window.title = str(title)
        except Exception as e:
            log.debug("set_window_title failed: %s", e)
        return True

    def extension_status(self):
        extension_dir = _extension_dir()
        manifest_exists = (extension_dir / "manifest.json").is_file()
        sentinel_exists = self._extension_sentinel.is_file()
        sentinel_current = _sentinel_current(self._extension_sentinel)
        should_show = (not sentinel_current) or (not manifest_exists)
        if should_show:
            self._hold_open = True
        return {
            "path": str(extension_dir),
            "manifest_exists": manifest_exists,
            "sentinel_exists": sentinel_exists,
            "sentinel_current": sentinel_current,
            "should_show": should_show,
            "browser": _preferred_browser(),
            "browsers": _available_browsers(),
        }

    def open_chrome_extensions(self):
        return _open_extensions_page("chrome")

    def open_extensions_page(self, browser_id=None):
        return _open_extensions_page(str(browser_id or "") or None)

    def copy_extension_path(self):
        path = str(_extension_dir())
        return {"ok": _copy_to_clipboard(path), "path": path}

    def mark_extension_loaded(self):
        _write_sentinel(self._extension_sentinel)
        self._hold_open = False
        self._dismiss()
        return True

    def should_hold_open(self) -> bool:
        return self._hold_open and not self._dismissed

    def minimize(self):
        self._dismiss()
        return True

    def close(self):
        # The splash is a one-shot subprocess. Closing it should end this
        # webview process while the real helper keeps running in the tray.
        self._dismiss()
        return True

    # ---- internal ----
    def _dismiss(self) -> None:
        if self._dismissed:
            return
        self._dismissed = True
        _write_sentinel(self._sentinel)
        self._close_window()

    def _auto_close(self) -> None:
        if self._dismissed:
            return
        self._close_window()

    def _close_window(self) -> None:
        """Best-effort close for pywebview variants.

        pywebview's JS bridge may still be returning when this is called from
        the HTML X button. Defer the native destroy by a tick so the bridge can
        finish cleanly, then prefer destroy/close over minimize so the splash
        subprocess exits instead of sitting around as a hidden window.
        """
        window = self._window
        if window is None:
            return

        def _close() -> None:
            time.sleep(0.05)
            for method in ("destroy", "close", "hide", "minimize"):
                fn = getattr(window, method, None)
                if not callable(fn):
                    continue
                try:
                    fn()
                    return
                except Exception as e:
                    log.debug("window.%s failed: %s", method, e)

        threading.Thread(
            target=_close, name="uoink-splash-close", daemon=True).start()


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
    # Belt-and-suspenders: if this version already showed the splash, do
    # nothing. Server also gates the spawn on this, but a double-spawn race is
    # harmless this way.
    if _sentinel_current(sentinel):
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
    window_kwargs = {"url": SPLASH_URL}
    if not _helper_health_ok():
        window_kwargs = {
            "html": _failed_splash_html("Uoink failed to start. Check the helper log."),
        }
    window = webview.create_window(
        "Uoink",
        frameless=True,
        on_top=True,
        resizable=False,
        width=WIDTH,
        height=HEIGHT,
        x=final_x,
        y=sh,            # start off-screen so frame-1 doesn't flash at final position
        js_api=api,
        **window_kwargs,
    )
    api.attach(window)

    def _after_loaded():
        _slide_up(window, final_x, sh)
        time.sleep(LINGER_SEC)
        if not api.should_hold_open():
            api._auto_close()

    threading.Thread(target=_after_loaded, name="uoink-splash-anim", daemon=True).start()
    try:
        webview.start()
    finally:
        log.debug("splash webview exited")
    return 0


if __name__ == "__main__":
    sys.exit(main())
