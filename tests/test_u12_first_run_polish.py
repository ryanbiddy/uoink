"""U-12 first-run splash and tray polish contract.

Run: python tests/test_u12_first_run_polish.py
"""
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import uoink_splash  # noqa: E402


SPLASH_HTML = (ROOT / "assets" / "splash" / "index.html").read_text(encoding="utf-8")
TRAY = (ROOT / "uoink_tray.py").read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class FakeWindow:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def destroy(self) -> None:
        self.calls.append("destroy")

    def close(self) -> None:
        self.calls.append("close")

    def minimize(self) -> None:
        self.calls.append("minimize")


def test_browser_catalog_maps_common_chromium_extension_pages() -> None:
    expected = {
        "edge": "edge://extensions/",
        "chrome": "chrome://extensions/",
        "brave": "brave://extensions/",
        "vivaldi": "vivaldi://extensions/",
        "opera-gx": "opera://extensions/",
        "arc": "arc://extensions/",
    }
    actual = {browser["id"]: browser["url"] for browser in uoink_splash.BROWSER_CATALOG}
    for browser_id, url in expected.items():
        require(actual.get(browser_id) == url, f"{browser_id} extension URL missing")
    require(uoink_splash._browser_from_prog_id("MSEdgeHTM")["id"] == "edge",
            "default-browser ProgId detection misses Edge")
    require(uoink_splash._browser_from_prog_id("BraveHTML")["id"] == "brave",
            "default-browser ProgId detection misses Brave")


def test_extension_status_returns_browser_metadata() -> None:
    status = uoink_splash.JsApi().extension_status()
    browser = status.get("browser") or {}
    require(browser.get("id"), "extension_status missing browser id")
    require(browser.get("name"), "extension_status missing browser name")
    require(str(browser.get("url", "")).endswith("://extensions/"),
            f"extension_status browser URL wrong: {browser}")
    require(isinstance(status.get("browsers"), list), "extension_status missing browser list")


def test_auto_close_does_not_write_splash_sentinel() -> None:
    fake = FakeWindow()
    api = uoink_splash.JsApi()
    api.attach(fake)
    with tempfile.TemporaryDirectory() as d:
        sentinel = Path(d) / ".first-run-done"
        api._sentinel = sentinel
        api._auto_close()
        time.sleep(0.2)
        require(not sentinel.exists(), "auto-close should not write the splash sentinel")
        require(fake.calls == ["destroy"], f"auto-close should destroy, got {fake.calls}")
        api.close()
        time.sleep(0.2)
        require(sentinel.read_text(encoding="utf-8").strip() == uoink_splash.VERSION,
                "explicit close should write the splash sentinel")


def test_splash_extension_copy_is_browser_aware() -> None:
    for stale in (
        "load into Chrome",
        "Open Chrome to chrome://extensions/",
        "Open chrome://extensions/ in Chrome",
    ):
        require(stale not in SPLASH_HTML, f"Chrome-only splash copy remains: {stale}")
    require("extensionBrowser" in SPLASH_HTML, "splash does not store browser metadata")
    require("open_extensions_page" in SPLASH_HTML, "splash does not call browser-aware native opener")
    require("your Chromium browser" in SPLASH_HTML, "splash missing generic browser fallback")


def test_tray_menu_has_one_quit_action() -> None:
    require('"Stop Helper"' not in TRAY, "tray still shows duplicate Stop Helper item")
    require(TRAY.count('"Quit Uoink"') == 1, "tray should show one Quit Uoink item")


def main() -> int:
    test_browser_catalog_maps_common_chromium_extension_pages()
    test_extension_status_returns_browser_metadata()
    test_auto_close_does_not_write_splash_sentinel()
    test_splash_extension_copy_is_browser_aware()
    test_tray_menu_has_one_quit_action()
    print("ALL U-12 FIRST-RUN POLISH TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
