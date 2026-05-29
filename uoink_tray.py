r"""Uoink system-tray icon -- Tier 1 install experience (v2.1.1).

Runs *inside* the helper process (server.py) on installed Windows builds and
gives the otherwise-headless helper an ambient, clickable presence: a magnet-U
glyph in the system tray whose status dot reflects health, plus a right-click
menu that opens the dashboard, the output folder, recent uoinks, and stops the
helper.

Design (per SCOPE-CC-install.md, Tier 1):
- The tray is a thin *client* of the same loopback API the extension popup uses
  (``/diagnose`` public; ``/queue/status`` + ``/recent`` token-gated -- the
  token is read straight from ``token.txt`` next to this module, since we run
  in-process). No new server surface, no new process, no new window.
- pystray + Pillow are imported lazily inside ``start()`` so ``import
  uoink_tray`` never fails in environments without them (e.g. the build's
  staged ``import`` smoke).
- Graceful degradation: if pystray/Pillow are missing, or the OS has no system
  tray (Server Core, some headless RDP), ``start()`` logs a warning and returns
  False; the helper keeps running. The boot balloon (server.maybe_toast) is the
  fallback "it's running" affordance.
- Runs its message loop in a daemon thread, so it never blocks server shutdown;
  when the helper process exits, the tray goes with it.

Brand v3.1 + AG's contrast catch: rust ``#C2410C`` is used only as the large U
glyph shape (allowed), never as small text on ink. Status-dot colours are
standalone fills with an ink outline so they read on any wallpaper.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

log = logging.getLogger("uoink.tray")

# ---- Brand palette (RGB) --------------------------------------------------
_INK = (10, 10, 10)            # #0A0A0A
_RUST = (194, 65, 12)          # #C2410C  -- large glyph shape only
_CREAM = (255, 244, 236)       # #FFF4EC
_DOT_GREEN = (46, 160, 67)     # running
_DOT_AMBER = (255, 210, 63)    # uoinking (acid #FFD23F-ish)
_DOT_GREY = (122, 117, 105)    # offline / degraded

# ---- Poll cadences (SCOPE-CC-install.md) ----------------------------------
_POLL_STATUS_SEC = 5
_POLL_RECENT_SEC = 10
_IDLE_AFTER_SEC = 60           # back off polling after this much menu inactivity

# Magnet-U path on a 100x100 grid (same glyph as the favicon), as polygon
# points -- rounded bottom corners are approximated by clipped corners, which
# reads cleanly at tray size.
_U_OUTLINE = [
    (0, 0), (32, 0), (32, 60), (68, 60), (68, 0), (100, 0),
    (100, 84), (84, 100), (16, 100), (0, 84),
]
_U_TIPS = [(0, 0, 32, 16), (68, 0, 100, 16)]  # cream tips (x0,y0,x1,y1)


class UoinkTray:
    def __init__(self, *, host: str, port: int, version: str,
                 token_path: Path, output_dir: Path, dashboard_url: str,
                 stop_callback) -> None:
        self.host = host
        self.port = port
        self.version = version
        self.token_path = Path(token_path)
        self.output_dir = Path(output_dir)
        self.dashboard_url = dashboard_url
        self._stop_callback = stop_callback
        self._base = f"http://{host}:{port}"
        self._icon = None
        self._state = "offline"          # offline | running | uoinking | degraded
        self._recent: list[dict] = []
        self._last_interaction = time.monotonic()
        self._stopping = threading.Event()
        # cache one rendered image per state so update is cheap
        self._images: dict = {}

    # ---- HTTP helpers (loopback client, like the popup) -------------------
    def _token(self) -> str:
        try:
            return self.token_path.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    def _get(self, path: str, *, auth: bool, timeout: float = 2.0):
        req = urllib.request.Request(self._base + path)
        if auth:
            tok = self._token()
            if tok:
                req.add_header("X-Uoink-Token", tok)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                if r.status != 200:
                    return None, r.status
                return json.loads(r.read().decode("utf-8")), 200
        except Exception:
            return None, None

    # ---- status + recent refresh ------------------------------------------
    def _refresh_status(self) -> None:
        diag, code = self._get("/diagnose", auth=False)
        if diag is None:
            self._state = "offline"
            return
        ok = bool(diag.get("ok", True)) and all(
            c.get("status") != "error" for c in diag.get("checks", [])
        )
        # Amber when the rate-limit queue has live (non-terminal) work.
        active = False
        q, _ = self._get("/queue/status", auth=True)
        if isinstance(q, dict):
            live = q.get("live") or q.get("rows") or []
            counts = q.get("counts") or {}
            active = bool(live) or bool(counts.get("running") or counts.get("pending"))
        if not ok:
            self._state = "degraded"
        elif active:
            self._state = "uoinking"
        else:
            self._state = "running"

    def _refresh_recent(self) -> None:
        data, _ = self._get("/recent", auth=True)
        if isinstance(data, dict) and isinstance(data.get("recent"), list):
            self._recent = data["recent"][:5]

    # ---- presentation ------------------------------------------------------
    def _status_text(self) -> str:
        return {
            "running": "Uoink: Running ✓",
            "uoinking": "Uoink: Uoinking…",
            "degraded": "Uoink: Degraded health!",
            "offline": "Uoink: Offline",
        }[self._state]

    def _dot_color(self):
        return {
            "running": _DOT_GREEN,
            "uoinking": _DOT_AMBER,
            "degraded": _DOT_GREY,
            "offline": _DOT_GREY,
        }[self._state]

    def _image(self):
        from PIL import Image, ImageDraw  # lazy
        key = self._state
        if key in self._images:
            return self._images[key]
        # v2.2.0 brand fix: load the canonical rust-U PNG so the tray renders
        # the SAME artwork as the installer .ico (both sourced from
        # assets/logo-mark-color.png). The previous polygon-drawn glyph
        # downscaled to a yellow-ish blob in the tray at 16 px because
        # rust+cream alpha-blended with the transparent ground that way --
        # Ryan's "yellow Y in the tray" screenshot. 32 px base gives the OS a
        # clean downscale; per the size-aware rule (<=32 px) the source mark's
        # cream tips are what we want.
        size = 32
        img = self._load_base_glyph(size).copy()
        d = ImageDraw.Draw(img)
        # status dot, bottom-right, ink-outlined for contrast on any wallpaper
        r = int(size * 0.26)
        cx, cy = size - r - 2, size - r - 2
        d.ellipse([cx - r - 2, cy - r - 2, cx + r + 2, cy + r + 2], fill=_INK + (255,))
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=self._dot_color() + (255,))
        self._images[key] = img
        return img

    def _load_base_glyph(self, size: int):
        """Load assets/logo-mark-color.png (the canonical rust-U mark, same
        source the installer .ico is generated from) and resize to `size` px
        with Lanczos. Cached for the life of the tray. Falls back to the
        polygon-drawn glyph if the PNG is missing or unreadable -- a broken
        install still gets a usable tray icon rather than no icon at all."""
        cached = getattr(self, "_base_glyph_cache", None)
        if cached is not None and cached[0] == size:
            return cached[1]
        from PIL import Image, ImageDraw  # lazy
        src = Path(__file__).parent / "assets" / "logo-mark-color.png"
        try:
            with Image.open(src) as im:
                base = im.convert("RGBA").resize((size, size), Image.LANCZOS)
        except Exception as e:
            log.warning("tray: PNG glyph load failed (%s); using fallback polygon", e)
            base = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            d = ImageDraw.Draw(base)
            scale = size / 100.0
            d.polygon([(x * scale, y * scale) for x, y in _U_OUTLINE],
                      fill=_RUST + (255,))
            for x0, y0, x1, y1 in _U_TIPS:
                d.rectangle([x0 * scale, y0 * scale, x1 * scale, y1 * scale],
                            fill=_CREAM + (255,))
        self._base_glyph_cache = (size, base)
        return base

    # ---- menu actions ------------------------------------------------------
    def _touch(self) -> None:
        self._last_interaction = time.monotonic()

    def _open_dashboard(self, *_):
        """Left-click action (default=True on the menu item makes this the
        single-click target on Windows). Tier 2 GUI: spawn the pywebview
        dashboard window in a subprocess so the helper's main thread /
        serve_forever isn't blocked by pywebview's GUI loop. Falls back to
        opening the URL in the default browser if the subprocess fails -- the
        v2.1.1 'click to see the dashboard' guarantee stays intact."""
        self._touch()
        self._spawn_dashboard_window()

    def _spawn_dashboard_window(self) -> None:
        script = str(Path(__file__).parent / "uoink_dashboard.py")
        try:
            creationflags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
            subprocess.Popen([sys.executable, script], creationflags=creationflags)
            return
        except Exception as e:
            log.debug("dashboard subprocess failed (%s); falling back to browser tab", e)
        try:
            webbrowser.open(self.dashboard_url)
        except Exception as e:
            log.debug("dashboard browser fallback failed: %s", e)

    def _open_folder(self, *_):
        self._touch()
        self._open_path(self.output_dir)

    def _open_settings(self, *_):
        # Tier 1 fallback: the extension owns the setup page and we don't know
        # its id from here, and the helper serves no setup.html, so point at the
        # dashboard (Codex's /dashboard, where settings live). Best-effort.
        self._touch()
        webbrowser.open(self.dashboard_url)

    @staticmethod
    def _open_path(path: Path) -> None:
        try:
            if sys.platform == "win32":
                os.startfile(str(path))  # noqa: S606 -- intended shell open
            elif sys.platform == "darwin":
                import subprocess
                subprocess.Popen(["open", str(path)])
            else:
                import subprocess
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as e:
            log.debug("tray: open path failed (%s): %s", path, e)

    def _recent_items(self):
        from pystray import MenuItem  # lazy
        items = []
        for row in self._recent:
            title = (row.get("title") or row.get("slug") or "untitled")[:48]
            folder = row.get("folder") or row.get("path")

            def _open(_icon, _item, folder=folder):
                self._touch()
                if folder:
                    self._open_path(Path(folder))
            items.append(MenuItem(title, _open))
        if not items:
            items.append(MenuItem("No recent uoinks yet", None, enabled=False))
        return items

    def _build_menu(self):
        import pystray
        from pystray import MenuItem, Menu
        return Menu(
            MenuItem(lambda _i: self._status_text(), None, enabled=False),
            Menu.SEPARATOR,
            MenuItem("Open Dashboard", self._open_dashboard, default=True),
            MenuItem("Open Uoink Folder", self._open_folder),
            MenuItem("Recent Uoinks", Menu(lambda: self._recent_items())),
            MenuItem("Settings…", self._open_settings),
            Menu.SEPARATOR,
            MenuItem("Stop Helper", self._on_stop),
            MenuItem("Quit Uoink", self._on_stop),
        )

    def _on_stop(self, *_):
        self._touch()
        self._stopping.set()
        try:
            if self._icon is not None:
                self._icon.visible = False
                self._icon.stop()
        except Exception:
            pass
        try:
            self._stop_callback()
        except Exception as e:
            log.warning("tray: stop callback failed: %s", e)

    # ---- poll loop ---------------------------------------------------------
    def _poll_loop(self) -> None:
        last_recent = 0.0
        # Prime once so the first menu open is populated.
        self._refresh_status()
        self._refresh_recent()
        self._apply()
        while not self._stopping.is_set():
            idle = (time.monotonic() - self._last_interaction) > _IDLE_AFTER_SEC
            # When idle, slow the status poll right down (battery/CPU) but keep
            # a heartbeat so a state change is still noticed within ~30 s.
            time.sleep(_POLL_STATUS_SEC if not idle else 30)
            if self._stopping.is_set():
                break
            prev = self._state
            self._refresh_status()
            now = time.monotonic()
            if not idle and (now - last_recent) >= _POLL_RECENT_SEC:
                self._refresh_recent()
                last_recent = now
            if self._state != prev:
                self._apply()

    def _apply(self) -> None:
        if self._icon is None:
            return
        try:
            self._icon.icon = self._image()
            self._icon.title = f"Uoink v{self.version} — {self._status_text()}"
            self._icon.update_menu()
        except Exception as e:
            log.debug("tray: apply failed: %s", e)

    # ---- lifecycle ---------------------------------------------------------
    def _run(self) -> None:
        try:
            import pystray
        except Exception as e:
            log.warning("tray: pystray unavailable, no tray icon (%s)", e)
            return
        try:
            self._icon = pystray.Icon(
                "uoink", icon=self._image(),
                title=f"Uoink v{self.version}", menu=self._build_menu())
        except Exception as e:
            log.warning("tray: could not create icon (%s)", e)
            return
        poller = threading.Thread(target=self._poll_loop, name="uoink-tray-poll",
                                  daemon=True)
        poller.start()
        try:
            self._icon.run()  # blocks this (daemon) thread's message loop
        except Exception as e:
            log.warning("tray: icon loop exited (%s)", e)
        finally:
            self._stopping.set()


def start(*, host: str, port: int, version: str, token_path, output_dir,
          dashboard_url: str, stop_callback) -> bool:
    """Start the tray in a daemon thread. Returns True if the thread launched,
    False on graceful degradation (no pystray/Pillow, no display). Never raises
    -- a tray failure must never take down the helper."""
    try:
        import pystray  # noqa: F401
        import PIL  # noqa: F401
    except Exception as e:
        log.warning("tray: dependencies unavailable, running without tray (%s)", e)
        return False
    tray = UoinkTray(host=host, port=port, version=version,
                     token_path=token_path, output_dir=output_dir,
                     dashboard_url=dashboard_url, stop_callback=stop_callback)
    t = threading.Thread(target=tray._run, name="uoink-tray", daemon=True)
    t.start()
    log.info("tray: started (daemon thread)")
    return True
