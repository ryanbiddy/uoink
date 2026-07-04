"""G-28 dashboard shell should not draw fake browser chrome.

Run: python tests/test_g28_remove_fake_chrome.py
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = (ROOT / "assets" / "dashboard" / "index.html").read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    for stale in (
        'class="chrome"',
        "chrome-brand",
        "window-controls",
        "window-dot",
        "private dashboard",
    ):
        require(stale not in DASHBOARD, f"fake dashboard chrome remains: {stale}")
    require(
        "grid-template-rows: minmax(0, 1fr);" in DASHBOARD,
        "main shell should give the dashboard content the full main column",
    )
    print("ok  dashboard shell has no fake chrome row or inert window dots")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
