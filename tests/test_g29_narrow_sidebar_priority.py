"""G-29 narrow screens should tuck dangerous app controls behind a disclosure.

Run: python tests/test_g29_narrow_sidebar_priority.py
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = (ROOT / "assets" / "dashboard" / "index.html").read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    require('id="sidebarControls" open' in DASHBOARD, "sidebar control disclosure missing")
    require("More controls" in DASHBOARD, "compact sidebar disclosure label missing")
    require('id="stopHelper">Stop Uoink</button>' in DASHBOARD, "stop control missing")
    require('class="sidebar-more-actions"' in DASHBOARD, "sidebar secondary action group missing")
    require("function syncSidebarControlsDensity()" in DASHBOARD, "sidebar density sync missing")
    require('window.addEventListener("resize", syncSidebarControlsDensity)' in DASHBOARD, "resize sync missing")
    require("const compact = window.matchMedia(\"(max-width: 1080px)\").matches;" in DASHBOARD, "compact breakpoint missing")
    require('if (compact) controls.removeAttribute("open");' in DASHBOARD, "compact sidebar should start closed")
    print("ok  narrow sidebar puts Stop Uoink behind More controls")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
