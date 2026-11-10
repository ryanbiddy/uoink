r"""Generate the Inno Setup wizard images from the app icon at build time.

Outputs (transparent PNG; Inno 6.7 reads PNG for the wizard image directives):
  installer/assets/wizard-large-100.png  80x80   -- WizardImageFile base
  installer/assets/wizard-large-125.png  100x100
  installer/assets/wizard-large-150.png  120x120
  installer/assets/wizard-large-200.png  160x160
  installer/assets/wizard-small-100.png  55x55   -- WizardSmallImageFile base
  installer/assets/wizard-small-125.png  69x69
  installer/assets/wizard-small-150.png  83x83
  installer/assets/wizard-small-200.png  110x110
  installer/assets/wizard-large-dark-*.png, wizard-small-dark-*.png
                                         same sizes, with a thin rim for dark mode

Both families are the Uoink app icon (installer/app_icon.py: ink plate, rust U,
yellow caps) on a transparent ground, so the wizard canvas color shows around
the rounded plate in light and dark mode. The "large" image is the hero icon on
the Welcome and Finished screens; the installer script sizes it in code. The
old tall magnet-U panel is gone.

Run from anywhere: `python installer/generate_bitmaps.py`. build.ps1 invokes it
before ISCC so the images regenerate each build (no committed binary churn).
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from PIL import Image, ImageDraw  # noqa: E402

from app_icon import GRID, PLATE_RADIUS, render_app_icon  # noqa: E402

ASSETS = HERE / "assets"
SCALES = {
    100: 1.0,
    125: 1.25,
    150: 1.5,
    200: 2.0,
}
LARGE = 80   # logical px at 100%
SMALL = 55
SMALL_ICON = 40  # icon size inside the small image
SMALL_X = 5
SMALL_Y = 9


def _scaled(value: int, scale: float) -> int:
    return int(value * scale + 0.5)


RIM = (74, 62, 52, 255)   # #4A3E34: a quiet edge so the ink plate reads on the ink canvas


def _icon(side: int, dark: bool) -> Image.Image:
    """The app icon at `side` px. In the dark-mode set the plate gets a thin
    lighter rim, because the plate and the dark wizard canvas are the same ink."""
    icon = render_app_icon(side)
    if not dark:
        return icon
    k = 4
    big = Image.new("RGBA", (side * k, side * k), (0, 0, 0, 0))
    width = max(k, round(side * k * 0.016))
    ImageDraw.Draw(big).rounded_rectangle(
        (0, 0, side * k - 1, side * k - 1),
        radius=round(PLATE_RADIUS / GRID * side * k), outline=RIM, width=width)
    rim = big.resize((side, side), Image.LANCZOS)
    out = icon.copy()
    out.alpha_composite(rim)
    return out


def make_large(path: Path, scale: float = 1.0, dark: bool = False) -> tuple[int, int]:
    side = _scaled(LARGE, scale)
    _icon(side, dark).save(path, "PNG")
    return side, side


def make_small(path: Path, scale: float = 1.0, dark: bool = False) -> tuple[int, int]:
    """The header icon: the app icon at 40 of 55 logical px, with clear space
    around it so it does not hug the top-right corner of the window."""
    side = _scaled(SMALL, scale)
    icon = _scaled(SMALL_ICON, scale)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.alpha_composite(_icon(icon, dark), (_scaled(SMALL_X, scale), _scaled(SMALL_Y, scale)))
    canvas.save(path, "PNG")
    return side, side


def main() -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)
    outputs: list[tuple[Path, tuple[int, int]]] = []
    for pct, scale in SCALES.items():
        large = ASSETS / f"wizard-large-{pct}.png"
        small = ASSETS / f"wizard-small-{pct}.png"
        outputs.append((large, make_large(large, scale)))
        outputs.append((small, make_small(small, scale)))
        large_d = ASSETS / f"wizard-large-dark-{pct}.png"
        small_d = ASSETS / f"wizard-small-dark-{pct}.png"
        outputs.append((large_d, make_large(large_d, scale, dark=True)))
        outputs.append((small_d, make_small(small_d, scale, dark=True)))

    for p, expected_size in outputs:
        with Image.open(p) as im:
            assert im.size == expected_size, f"{p.name} is {im.size}, expected {expected_size}"
            assert im.mode == "RGBA", f"{p.name} must be an RGBA PNG, got {im.mode}"
        print(f"  wrote {p} ({expected_size[0]}x{expected_size[1]}, RGBA PNG)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
