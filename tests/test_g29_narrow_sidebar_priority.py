"""G-29 narrow screens should not put dangerous app controls in the sidebar.

Since the UI re-haul, Stop Uoink lives in Settings > App, not the sidebar.

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
    # UI re-haul (SPEC "Dashboard IA"): the dangerous app control left the
    # sidebar altogether. Stop Uoink lives in Settings > App, behind its
    # confirm, so no narrow-screen disclosure is needed to tuck it away.
    sidebar = DASHBOARD.split('<aside class="sidebar"', 1)[1].split("</aside>", 1)[0]
    require("Stop Uoink" not in sidebar, "Stop Uoink must not sit in the sidebar")
    require('id="sidebarControls"' not in DASHBOARD, "the More controls disclosure should be gone")
    app = DASHBOARD.split('id="settings-app"', 1)[1].split("</section>", 1)[0]
    require('id="stopHelperSettings">Stop Uoink</button>' in app, "stop control missing from Settings > App")
    require('getElementById("stopHelperSettings").addEventListener("click", stopHelperWithConfirm)' in DASHBOARD,
            "Stop Uoink must keep its confirm")
    require('id="stopHelperConfirm" role="dialog"' in DASHBOARD, "stop confirm dialog missing")
    print("ok  Stop Uoink lives in Settings > App behind its confirm")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
