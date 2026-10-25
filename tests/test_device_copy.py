"""Copy about local work names this PC, this Mac or this computer, never just PC."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "assets/dashboard/index.html").read_text(encoding="utf-8")


def test_dashboard_says_this_device_for_the_viewer_platform():
    assert 'return { win: "this PC", mac: "this Mac", linux: "this computer" }[helperPlatform()];' in HTML
    assert 'for (const node of document.querySelectorAll("[data-this-device]")) node.textContent = thisDevice();' in HTML
    # Every other "this PC" is the Windows default inside a span the page rewrites,
    # or the helper status table, which already has a per-platform entry.
    loose = [line.strip() for line in HTML.splitlines()
             if "this PC" in line and "data-this-device" not in line
             and 'win: "this PC"' not in line and 'running: "Running on this PC"' not in line
             and not line.strip().startswith(("/*", "//", "*"))]
    assert loose == []
    assert HTML.count("<span data-this-device>this PC</span>") == 2

