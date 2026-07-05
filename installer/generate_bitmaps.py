r"""Generate the Inno Setup wizard bitmaps from source at build time.

Outputs (24-bit BMP, the format Inno requires):
  installer/assets/wizard-large-100.bmp  164x314  -- WizardImageFile base
  installer/assets/wizard-large-125.bmp  205x393
  installer/assets/wizard-large-150.bmp  246x471
  installer/assets/wizard-large-200.bmp  328x628
  installer/assets/wizard-small-100.bmp   58x58   -- WizardSmallImageFile base
  installer/assets/wizard-small-125.bmp   73x73
  installer/assets/wizard-small-150.bmp   87x87
  installer/assets/wizard-small-200.bmp  116x116

Variant A ("Minimalist Magnet-U", WIZARD-COPY-AND-BITMAPS.md §5): solid ink
ground, a large rust+cream magnet-U with a soft vermillion glow, and the
cream "UOINK" Bungee-style wordmark on the large panel.

Brand v3.1 + AG's contrast catch (§6): rust #C2410C on ink fails AA at 3.8:1,
so rust appears ONLY as the large U glyph shape (a large shape, not text) and
the wordmark is cream (#FFF4EC on #0A0A0A = 20.4:1, AAA). No rust text on ink.

Run from anywhere: `python installer/generate_bitmaps.py`. build.ps1 invokes it
before ISCC so the bitmaps regenerate each build (no committed binary churn).
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

INK = (10, 10, 10)
RUST = (194, 65, 12)        # #C2410C -- large glyph shape only
CREAM = (255, 244, 236)     # #FFF4EC
VERMILLION = (255, 61, 0)   # #FF3D00 -- glow only
ACID = (255, 210, 63)       # #FFD23F -- magnet tips (brand v3.1)

ASSETS = Path(__file__).resolve().parent / "assets"
SCALES = {
    100: 1.0,
    125: 1.25,
    150: 1.5,
    200: 2.0,
}

# Magnet-U on a 100x100 grid (favicon glyph): blocky horseshoe, cream tips.
_U_OUTLINE = [
    (0, 0), (32, 0), (32, 60), (68, 60), (68, 0), (100, 0),
    (100, 84), (84, 100), (16, 100), (0, 84),
]
_U_TIPS = [(0, 0, 32, 16), (68, 0, 100, 16)]


def _draw_magnet_u(target: Image.Image, ox: int, oy: int, side: int,
                   glow: bool = True) -> None:
    """Draw the magnet-U at (ox,oy) sized `side` px onto `target` (RGBA)."""
    s = side / 100.0

    def pts(seq):
        return [(ox + x * s, oy + y * s) for x, y in seq]

    if glow:
        # Soft vermillion glow: blurred silhouette behind the glyph.
        pad = side // 2
        glow_img = Image.new("RGBA", (side + pad * 2, side + pad * 2), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow_img)
        gd.polygon([(pad + x * s, pad + y * s) for x, y in _U_OUTLINE],
                   fill=VERMILLION + (170,))
        glow_img = glow_img.filter(ImageFilter.GaussianBlur(side * 0.12))
        target.alpha_composite(glow_img, (ox - pad, oy - pad))

    layer = Image.new("RGBA", target.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    # Finding 1.2 (creative review v2.2, AG): the brand spec calls for a
    # cream interior inside the horseshoe loop. Without this fill the gap
    # between the prongs shows through to the INK background, leaving the
    # mark hollowed out. Drawn before the polygon so the RUST outline
    # paints over any spill outside the inner rectangle; the polygon path
    # routes around (32..68, 0..60) anyway so cream stays visible there.
    ld.rectangle([ox + 32 * s, oy + 0 * s, ox + 68 * s, oy + 60 * s],
                 fill=CREAM + (255,))
    ld.polygon(pts(_U_OUTLINE), fill=RUST + (255,))
    # Finding 1.1 (creative review v2.2, AG): tips are ACID (#FFD23F),
    # not CREAM. Brand v3.1 spec -- "acid tips at 14% glyph height, rust
    # body, cream interior."
    for x0, y0, x1, y1 in _U_TIPS:
        ld.rectangle([ox + x0 * s, oy + y0 * s, ox + x1 * s, oy + y1 * s],
                     fill=ACID + (255,))
    target.alpha_composite(layer)


def _load_font(size: int):
    for name in ("Bungee-Regular.ttf", "segoeuib.ttf", "arialbd.ttf", "Arial Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _centered_text(d: ImageDraw.ImageDraw, cx: int, y: int, text: str, font,
                   fill) -> None:
    try:
        l, t, r, b = d.textbbox((0, 0), text, font=font)
        w = r - l
    except Exception:
        w = d.textlength(text, font=font)
    d.text((cx - w / 2, y), text, font=font, fill=fill)


def _scaled(value: int, scale: float) -> int:
    return int(value * scale + 0.5)


def make_large(path: Path, scale: float = 1.0) -> tuple[int, int]:
    W, H = _scaled(164, scale), _scaled(314, scale)
    img = Image.new("RGBA", (W, H), INK + (255,))
    side = _scaled(96, scale)
    _draw_magnet_u(img, (W - side) // 2, _scaled(70, scale), side, glow=True)
    d = ImageDraw.Draw(img)
    # Cream wordmark near the bottom (cream on ink = AAA).
    _centered_text(d, W // 2, H - _scaled(70, scale), "UOINK", _load_font(_scaled(34, scale)), CREAM)
    _centered_text(d, W // 2, H - _scaled(34, scale), "uoink.app", _load_font(_scaled(13, scale)), CREAM)
    img.convert("RGB").save(path, "BMP")
    return W, H


def make_small(path: Path, scale: float = 1.0) -> tuple[int, int]:
    W = H = _scaled(58, scale)
    img = Image.new("RGBA", (W, H), INK + (255,))
    side = _scaled(50, scale)  # 4px padding all round at 100% (AG spec)
    _draw_magnet_u(img, (W - side) // 2, (H - side) // 2, side, glow=False)
    img.convert("RGB").save(path, "BMP")
    return W, H


def main() -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)
    outputs: list[tuple[Path, tuple[int, int]]] = []
    for pct, scale in SCALES.items():
        large = ASSETS / f"wizard-large-{pct}.bmp"
        small = ASSETS / f"wizard-small-{pct}.bmp"
        outputs.append((large, make_large(large, scale)))
        outputs.append((small, make_small(small, scale)))

    for p, expected_size in outputs:
        with Image.open(p) as im:
            assert im.size == expected_size, f"{p.name} is {im.size}, expected {expected_size}"
            assert im.mode == "RGB", f"{p.name} must be 24-bit RGB BMP, got {im.mode}"
        print(f"  wrote {p} ({expected_size[0]}x{expected_size[1]}, 24-bit BMP)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
