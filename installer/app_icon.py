r"""The Uoink app icon, drawn from geometry so every platform shows the same mark.

This is the icon uoink.app shows on its download page (`/assets/icon-512.png`):
a warm-ink rounded plate, a rust U and two yellow caps. The geometry below was
measured from that 512 px file, so the site, the Windows installer and the Mac
app all draw one mark.

Units are on a 512 x 512 grid:
  plate      the full grid, corner radius 92, #15110D
  U body     (92, 92)-(420, 420), bottom corners radius 58, #C2410C
  notch      (197, 92)-(315, 288), cut back to the plate (square corners)
  caps       (92, 92)-(197, 138) and (315, 92)-(420, 138), #FFD23F

render_app_icon(size)              full-bleed plate, as on the site.
render_app_icon(size, macos=True)  Apple's icon grid: the plate is 824/1024 of
                                   the canvas, centred, with a soft shadow.

Run directly to rewrite the committed masters:
    python installer/app_icon.py
writes assets/brand/app-icon-1024.png (full bleed) and
assets/brand/app-icon-macos-1024.png (Apple grid).
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

PLATE = (21, 17, 13, 255)      # #15110D
RUST = (194, 65, 12, 255)      # #C2410C
ACID = (255, 210, 63, 255)     # #FFD23F

GRID = 512
PLATE_RADIUS = 92
U_BOX = (92, 92, 420, 420)
U_RADIUS = 58
NOTCH = (197, 92, 315, 288)
CAPS = ((92, 92, 197, 138), (315, 92, 420, 138))

# Apple's macOS icon grid: 1024 canvas, 824 plate, 100 px margin.
MACOS_CANVAS = 1024
MACOS_PLATE = 824

SUPERSAMPLE = 4
ROOT = Path(__file__).resolve().parent.parent


def _draw_mark(size: int) -> Image.Image:
    """Draw the full-bleed mark at `size` px with 4x supersampling."""
    big = size * SUPERSAMPLE
    k = big / GRID

    def box(b):
        return tuple(round(v * k) for v in b)

    im = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, big - 1, big - 1), radius=round(PLATE_RADIUS * k), fill=PLATE)
    x0, y0, x1, y1 = box(U_BOX)
    r = round(U_RADIUS * k)
    # U body: square top corners, rounded bottom corners.
    d.rounded_rectangle((x0, y0, x1, y1), radius=r, fill=RUST)
    d.rectangle((x0, y0, x1, y0 + r), fill=RUST)
    d.rectangle(box(NOTCH), fill=PLATE)
    for cap in CAPS:
        d.rectangle(box(cap), fill=ACID)
    return im.resize((size, size), Image.LANCZOS)


def render_app_icon(size: int, macos: bool = False) -> Image.Image:
    """Return the icon as an RGBA image `size` px square."""
    if not macos:
        return _draw_mark(size)
    big = MACOS_CANVAS * SUPERSAMPLE // 2   # 2x is plenty for the shadow pass
    k = big / MACOS_CANVAS
    plate_px = round(MACOS_PLATE * k)
    offset = (big - plate_px) // 2
    canvas = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    # Soft drop shadow under the plate (Apple grid: blur ~28, y offset ~12).
    shadow = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    radius = round(PLATE_RADIUS / GRID * plate_px)
    dy = round(12 * k)
    sd.rounded_rectangle((offset, offset + dy, offset + plate_px, offset + plate_px + dy),
                         radius=radius, fill=(0, 0, 0, 90))
    shadow = shadow.filter(ImageFilter.GaussianBlur(round(28 * k)))
    canvas.alpha_composite(shadow)
    canvas.alpha_composite(_draw_mark(plate_px), (offset, offset))
    return canvas.resize((size, size), Image.LANCZOS)


def write_masters() -> list[Path]:
    out = ROOT / "assets" / "brand"
    out.mkdir(parents=True, exist_ok=True)
    flat = out / "app-icon-1024.png"
    mac = out / "app-icon-macos-1024.png"
    render_app_icon(1024).save(flat, optimize=True)
    render_app_icon(1024, macos=True).save(mac, optimize=True)
    return [flat, mac]


if __name__ == "__main__":
    for path in write_masters():
        print(path)
    sys.exit(0)
