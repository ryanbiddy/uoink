r"""Regenerate installer/uoink.ico from assets/logo-mark-color.png at build time.

Build-time step (mirrors installer/generate_bitmaps.py). Outputs a multi-size
.ico Windows uses for the wizard top-left icon, the installed .exe icon, the
uninstaller, the Start Menu shortcut, and the taskbar/Alt-Tab entry. Single
source of truth = the rust-U PNG at assets/logo-mark-color.png, so the icon
can never go stale during a rebrand (as it did through v2.1.x, where the
installer kept shipping the legacy Yoink-Y until v2.2.0 visual smoke caught it).

Sizes embedded: 16, 24, 32, 48, 64, 128, 256 -- Windows picks the closest match
per-context (16/24 for tray, 32 for shortcuts, 48 for Explorer detail view, 256
for the modern Vista+ jumbo icons). Source PNG should ideally have an alpha
channel for clean tray rendering on any wallpaper; if it's solid RGB the .ico
will show the background colour (still infinitely better than the yellow Y).
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets" / "logo-mark-color.png"
DST = ROOT / "installer" / "uoink.ico"


def main() -> int:
    if not SRC.is_file():
        print(f"ERROR: source PNG not found: {SRC}", file=sys.stderr)
        return 1
    img = Image.open(SRC).convert("RGBA")
    DST.parent.mkdir(parents=True, exist_ok=True)
    img.save(DST, format="ICO", sizes=SIZES)
    # Sanity-check: reopen + confirm the embedded sizes match what we asked for.
    with Image.open(DST) as ico:
        got = sorted(ico.info.get("sizes", set()))
    expected = sorted(SIZES)
    if got != expected:
        print(f"ERROR: ICO sizes mismatch. expected {expected}, got {got}",
              file=sys.stderr)
        return 2
    print(f"  wrote {DST} ({len(SIZES)} sizes: {got[0][0]}x..{got[-1][0]}x)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
