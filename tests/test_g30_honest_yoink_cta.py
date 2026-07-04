"""G-30 YouTube-only capture entry points should say what they do.

Run: python tests/test_g30_honest_yoink_cta.py
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = (ROOT / "assets" / "dashboard" / "index.html").read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    require("+ Uoink" not in DASHBOARD, "generic Uoink CTA still labels the YouTube-only action")
    require(DASHBOARD.count(">Open YouTube</button>") == 3, "expected 3 explicit YouTube CTAs")
    require('document.getElementById("newYoink").addEventListener("click", openLastYoutube)' in DASHBOARD, "Library CTA should still use the YouTube handler")
    require('document.getElementById("openYouTubeForYou").addEventListener("click", openLastYoutube)' in DASHBOARD, "For You CTA should still use the YouTube handler")
    require('event.target.closest("[data-open-youtube]")' in DASHBOARD, "Sources CTA should still use the YouTube handler")
    print("ok  YouTube-only CTAs are labeled Open YouTube")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
