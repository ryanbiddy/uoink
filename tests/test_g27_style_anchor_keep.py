"""G-27 style-anchor default controls should not show fake actions.

Run: python tests/test_g27_style_anchor_keep.py
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = (ROOT / "assets" / "dashboard" / "index.html").read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    require(
        'disabled title="Default anchors can be deactivated, not deleted.">Keep</button>'
        not in DASHBOARD,
        "default style anchors should not render disabled Keep buttons",
    )
    require(
        'data-toggle-style-anchor="${htmlEscape(id)}" data-anchor-active="${active ? "true" : "false"}">${toggleLabel}</button>'
        in DASHBOARD,
        "default style anchors should keep the real activate/deactivate toggle",
    )
    require(
        '${isDefault ? (active ? " | deactivate to free the slot" : " | default anchor") : ""}'
        in DASHBOARD,
        "inactive default anchors should not ask users to deactivate them",
    )
    print("ok  default style anchors expose one real toggle and no disabled Keep action")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
