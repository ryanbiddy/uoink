r"""Regenerate installer/uoink.ico from the app icon at build time.

Build-time step (mirrors installer/generate_bitmaps.py). Outputs the multi-size
.ico Windows uses for Setup.exe, the uninstaller, the Start menu and desktop
shortcuts, and the taskbar/Alt-Tab entry. The source is installer/app_icon.py
(ink plate, rust U, yellow caps), the same mark uoink.app shows on its download
page, so Setup.exe, the shortcuts and the site match. Each size is drawn from
the geometry rather than shrunk from one bitmap, so the small sizes stay crisp.

The tray glyph is a separate mark (assets/logo-mark-color.png) and is not
touched here.

Sizes embedded: 16, 20, 24, 32, 40, 48, 64, 96, 128, 256.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from app_icon import render_app_icon  # noqa: E402

SIZES = [(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48),
         (64, 64), (96, 96), (128, 128), (256, 256)]
ROOT = HERE.parent
DST = ROOT / "installer" / "uoink.ico"


def main() -> int:
    DST.parent.mkdir(parents=True, exist_ok=True)
    frames = [render_app_icon(w) for w, _ in SIZES]
    frames[-1].save(DST, format="ICO", sizes=SIZES, append_images=frames[:-1])
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
