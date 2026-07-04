"""Regenerate Uoink Chrome Web Store assets from the source brand files.

Inputs (must exist in assets/):
    logo-mark-dark.png - square light mark (used for extension icon sizes)

Outputs:
    extension/icons/icon-16.png, icon-32.png, icon-48.png, icon-128.png
    assets/store/promo-small-440x280.png   (required)
    assets/store/promo-large-920x680.png   (recommended)
    assets/store/promo-marquee-1400x560.png (optional)

Run with:
    python assets/build_store_assets.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
ICONS_OUT = ROOT / "extension" / "icons"
STORE_OUT = ASSETS / "store"

ICON_SIZES = [16, 32, 48, 128]
PROMO_SIZES = {
    "promo-small-440x280.png": (440, 280),
    "promo-large-920x680.png": (920, 680),
    "promo-marquee-1400x560.png": (1400, 560),
}

WORDMARK = "UOINK"
TAGLINE = "Local corpus for AI writing."
SUBLINE = "Videos, podcasts, articles. Your disk."
BG_COLOR = (255, 244, 236, 255)     # cream
INK = (10, 10, 10, 255)
RUST = (194, 65, 12, 255)
OXBLOOD = (123, 45, 14, 255)
ACID = (255, 210, 63, 255)
TAGLINE_COLOR = INK
SUBLINE_COLOR = (72, 52, 42, 255)
BTN_BG = RUST
BTN_TEXT = BG_COLOR
BTN_ACCENT = ACID


# ---------- helpers ----------------------------------------------------------
def _load_font(size: int) -> ImageFont.FreeTypeFont:
    """Try a few common Windows fonts so the placeholder isn't pixel-bitmap."""
    candidates = [
        r"C:\Windows\Fonts\segoeuib.ttf",  # Segoe UI Bold
        r"C:\Windows\Fonts\arialbd.ttf",   # Arial Bold
        r"C:\Windows\Fonts\segoeui.ttf",   # Segoe UI
        r"C:\Windows\Fonts\arial.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def _fit_font(text: str, max_w: int, max_h: int, start_size: int) -> ImageFont.FreeTypeFont:
    """Return the largest available font that fits text in the box."""
    size = max(12, start_size)
    probe = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    d = ImageDraw.Draw(probe)
    while size > 12:
        font = _load_font(size)
        bbox = d.textbbox((0, 0), text, font=font)
        if (bbox[2] - bbox[0]) <= max_w and (bbox[3] - bbox[1]) <= max_h:
            return font
        size -= 2
    return _load_font(size)


# ---------- icon rendering ---------------------------------------------------
# Pairs of (source filename, output suffix). Most users have dark-mode
# toolbars where the black Y disappears, so the default icon renders from
# the white mark. The "-dark" suffix variant exists so manifest.theme_icons
# keeps a working reference (currently identical content).
_ICON_VARIANTS = [
    ("logo-mark-dark.png", ""),       # white Y, default toolbar icon
    ("logo-mark-dark.png", "-dark"),  # white Y, dark-theme variant
]


def render_icons() -> None:
    ICONS_OUT.mkdir(parents=True, exist_ok=True)
    for source_name, suffix in _ICON_VARIANTS:
        src_path = ASSETS / source_name
        if not src_path.exists():
            raise FileNotFoundError(f"missing source: {src_path}")
        src = Image.open(src_path).convert("RGBA")
        for size in ICON_SIZES:
            out = src.resize((size, size), Image.LANCZOS)
            out.save(ICONS_OUT / f"icon-{size}{suffix}.png", optimize=True)


# ---------- mock YouTube "Uoink" button --------------------------------------
def render_mock_button(width: int, height: int) -> Image.Image:
    """A pill-shaped button mimicking the in-page Uoink button on YouTube."""
    btn = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(btn)
    radius = height // 2
    d.rounded_rectangle((0, 0, width - 1, height - 1), radius=radius, fill=BTN_BG)

    # Sparkle/star mark to the left of the label.
    star_cx = radius
    star_cy = height // 2
    star_r = max(6, height // 5)
    pts = []
    import math
    for i in range(8):
        angle = math.pi / 4 * i - math.pi / 2
        r = star_r if i % 2 == 0 else star_r // 2
        pts.append((star_cx + r * math.cos(angle), star_cy + r * math.sin(angle)))
    d.polygon(pts, fill=BTN_ACCENT)

    # Label.
    label = "Uoink"
    font = _load_font(int(height * 0.45))
    bbox = d.textbbox((0, 0), label, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    text_x = star_cx + star_r + max(8, height // 8)
    text_y = (height - text_h) // 2 - bbox[1]
    d.text((text_x, text_y), label, font=font, fill=BTN_TEXT)
    return btn


# ---------- promo tile composition -------------------------------------------
def render_promo_tile(out_path: Path, width: int, height: int) -> None:
    canvas = Image.new("RGBA", (width, height), BG_COLOR)

    # Subtle brand glow so the tile reads as styled, not flat.
    glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    glow_r = int(min(width, height) * 0.6)
    gd.ellipse(
        (-glow_r // 2, height - glow_r,
         glow_r + width // 3, height + glow_r // 2),
        fill=(OXBLOOD[0], OXBLOOD[1], OXBLOOD[2], 70),
    )
    glow = glow.filter(ImageFilter.GaussianBlur(radius=width // 18))
    canvas.alpha_composite(glow)

    # --- right side first: mock Uoink pill anchored top-right ---
    # Cap the button so it stays a tasteful chip on the bigger tiles instead
    # of dominating the canvas. Anchored upper-right so it doesn't collide
    # with the tagline below the wordmark.
    btn_w = min(int(width * 0.28), 260)
    btn_h = max(36, min(int(height * 0.16), 60))
    btn_x = width - btn_w - int(width * 0.06)
    btn_y = int(height * 0.18)
    btn = render_mock_button(btn_w, btn_h)
    canvas.alpha_composite(btn, (btn_x, btn_y))

    hint_font = _load_font(max(11, int(height * 0.035)))
    hint = "Capture the source. Keep the credit."
    hd = ImageDraw.Draw(canvas)
    hint_bbox = hd.textbbox((0, 0), hint, font=hint_font)
    hint_w = hint_bbox[2] - hint_bbox[0]
    hint_x = min(width - hint_w - int(width * 0.04),
                 btn_x + (btn_w - hint_w) // 2)
    hd.text(
        (hint_x, btn_y + btn_h + int(height * 0.035)),
        hint, font=hint_font, fill=(92, 59, 43, 255),
    )
    right_block_left = btn_x

    # --- left side: wordmark, then tagline + sub ---
    wm_x = int(width * 0.06)
    wm_y = int(height * 0.18)
    max_wm_w = min(int(width * 0.42), right_block_left - wm_x - int(width * 0.04))
    max_wm_h = int(height * 0.32)
    wordmark_font = _fit_font(WORDMARK, max_wm_w, max_wm_h, max_wm_h)
    d = ImageDraw.Draw(canvas)
    wb = d.textbbox((0, 0), WORDMARK, font=wordmark_font)
    d.text((wm_x, wm_y - wb[1]), WORDMARK, font=wordmark_font, fill=RUST)

    # Tagline below the wordmark, capped so it never runs into the button area.
    tag_font = _load_font(max(14, int(height * 0.055)))
    tag_x = int(width * 0.06)
    tag_y = int(height * 0.62)
    ImageDraw.Draw(canvas).text((tag_x, tag_y), TAGLINE, font=tag_font,
                                 fill=TAGLINE_COLOR)

    sub_font = _load_font(max(11, int(height * 0.04)))
    sub_y = tag_y + int(height * 0.10)
    ImageDraw.Draw(canvas).text(
        (tag_x, sub_y),
        SUBLINE,
        font=sub_font, fill=SUBLINE_COLOR,
    )

    canvas.convert("RGB").save(out_path, "PNG", optimize=True)


def render_promos() -> None:
    STORE_OUT.mkdir(parents=True, exist_ok=True)
    for filename, (w, h) in PROMO_SIZES.items():
        render_promo_tile(STORE_OUT / filename, w, h)


# ---------- entry ------------------------------------------------------------
def main() -> None:
    render_icons()
    render_promos()
    print("Generated icons:")
    for _src, suffix in _ICON_VARIANTS:
        for size in ICON_SIZES:
            p = ICONS_OUT / f"icon-{size}{suffix}.png"
            print(f"  {p}  ({p.stat().st_size:,} bytes)")
    print("Generated promo tiles:")
    for filename in PROMO_SIZES:
        p = STORE_OUT / filename
        print(f"  {p}  ({p.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
