r"""Draw the DMG window background and, on request, review images.

    python installer/mac/dmg_background.py
writes installer/mac/dmg-background.png (660 x 400, 72 dpi) and
installer/mac/dmg-background@2x.png (1320 x 800, 144 dpi). dmgbuild pairs the
two files into one multi-resolution TIFF; tiffutil needs the dpi to match.

    python installer/mac/dmg_background.py --review OUTPUT_DIR
also writes dmg-mock@2x.png (the window as Finder would draw it) and
icon-sizes.png (the app icon at 16, 32, 64 and 128 px) for a look before CI.

Layout numbers come from scripts/mac/mac_look.py, so the art and the Finder
positions cannot drift apart. Needs Pillow.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/mac"))
import mac_look  # noqa: E402

CREAM = (255, 244, 236)   # #FFF4EC
INK = (10, 10, 10)        # #0A0A0A
RUST = (194, 65, 12)      # #C2410C
MUTED = (122, 111, 102)   # ink at about 55% on cream
FONT = ROOT / "assets/brand/fonts/inter.woff"

TITLE = "Drag Uoink to Applications"
FOOTER = "Apple silicon · macOS 15 or later"
TITLE_CENTER_Y = 52
FOOTER_CENTER_Y = 364
TITLE_PT = 18
FOOTER_PT = 12

# Arrow, in points. The icons' 128 pt boxes end at x=244 and start at x=416.
ARROW_TAIL_X = 280
ARROW_TIP_X = 380
ARROW_THICKNESS = 6
ARROW_HEAD_LENGTH = 24
ARROW_HEAD_HALF = 15


def font(size_px: float, weight: int) -> ImageFont.FreeTypeFont:
    face = ImageFont.truetype(str(FONT), max(1, round(size_px)))
    face.set_variation_by_axes([min(32, max(14, size_px)), weight])  # optical size, weight
    return face


def centered_text(draw: ImageDraw.ImageDraw, center: tuple[float, float], text: str, face, fill) -> None:
    draw.text(center, text, font=face, fill=fill, anchor="mm")


def render(scale: int) -> Image.Image:
    """Draw at 4x the target for smooth edges, then reduce."""
    ss = 4
    k = scale * ss
    width, height = (mac_look.CONTENT_SIZE[0] * k, mac_look.CONTENT_SIZE[1] * k)
    image = Image.new("RGB", (width, height), CREAM)
    draw = ImageDraw.Draw(image)
    centered_text(draw, (width / 2, TITLE_CENTER_Y * k), TITLE, font(TITLE_PT * k, 600), INK)
    centered_text(draw, (width / 2, FOOTER_CENTER_Y * k), FOOTER, font(FOOTER_PT * k, 400), MUTED)

    y = mac_look.APP_POSITION[1] * k
    assert y == mac_look.APPLICATIONS_POSITION[1] * k
    half = ARROW_THICKNESS * k / 2
    head_start = (ARROW_TIP_X - ARROW_HEAD_LENGTH) * k
    draw.rounded_rectangle((ARROW_TAIL_X * k, y - half, head_start + 2 * k, y + half), radius=half, fill=RUST)
    draw.polygon([(head_start, y - ARROW_HEAD_HALF * k), (ARROW_TIP_X * k, y),
                  (head_start, y + ARROW_HEAD_HALF * k)], fill=RUST)
    return image.resize((width // ss, height // ss), Image.LANCZOS)


def write_backgrounds(root: Path = ROOT) -> list[Path]:
    paths = []
    for scale, relative in ((1, mac_look.BACKGROUND), (2, mac_look.BACKGROUND_2X)):
        path = root / relative
        render(scale).save(path, dpi=(72 * scale, 72 * scale), optimize=True)
        paths.append(path)
    return paths


def folder_square(size: int) -> Image.Image:
    """A plain stand-in for Finder's Applications folder icon."""
    tile = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(tile)
    d.rounded_rectangle((size * 0.06, size * 0.20, size * 0.94, size * 0.88), radius=size * 0.08, fill=(96, 165, 232, 255))
    d.rounded_rectangle((size * 0.06, size * 0.12, size * 0.42, size * 0.30), radius=size * 0.05, fill=(96, 165, 232, 255))
    d.rounded_rectangle((size * 0.06, size * 0.28, size * 0.94, size * 0.88), radius=size * 0.08, fill=(130, 190, 245, 255))
    return tile


def write_mock(out: Path, root: Path = ROOT) -> Path:
    """The 2x window with icons and labels where Finder will put them."""
    canvas = Image.open(root / mac_look.BACKGROUND_2X).convert("RGBA")
    icon = Image.open(root / mac_look.ICON_SOURCE).convert("RGBA").resize((256, 256), Image.LANCZOS)
    box = 2 * mac_look.ICON_SIZE
    label = font(2 * mac_look.TEXT_SIZE, 400)
    d = ImageDraw.Draw(canvas)
    for (cx, cy), tile, name in ((mac_look.APP_POSITION, icon, "Uoink"),
                                 (mac_look.APPLICATIONS_POSITION, folder_square(box), "Applications")):
        cx, cy = cx * 2, cy * 2
        canvas.alpha_composite(tile, (cx - box // 2, cy - box // 2))
        # Finder draws the label about 10 pt under the icon box.
        d.text((cx, cy + box // 2 + 20), name, font=label, fill=INK, anchor="mt")
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(out)
    return out


def write_icon_sizes(out: Path, root: Path = ROOT) -> Path:
    """Real size on the top row, the same pixels enlarged 4x (no smoothing) below."""
    source = Image.open(root / mac_look.ICON_SOURCE).convert("RGBA")
    sizes = (16, 32, 64, 128)
    gap, pad = 40, 40
    width = pad * 2 + sum(s * 4 for s in sizes) + gap * (len(sizes) - 1)
    canvas = Image.new("RGBA", (width, pad * 3 + 128 + 128 * 4), CREAM + (255,))
    x = pad
    for size in sizes:
        small = source.resize((size, size), Image.LANCZOS)
        canvas.alpha_composite(small, (x, pad + (128 - size)))
        canvas.alpha_composite(small.resize((size * 4, size * 4), Image.NEAREST), (x, pad * 2 + 128))
        x += size * 4 + gap
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(out)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--review", type=Path, help="also write dmg-mock@2x.png and icon-sizes.png here")
    args = parser.parse_args()
    for path in write_backgrounds():
        print(path)
    if args.review:
        print(write_mock(args.review / "dmg-mock@2x.png"))
        print(write_icon_sizes(args.review / "icon-sizes.png"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
