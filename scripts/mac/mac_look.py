"""How the Mac app and its DMG look: the app icon and the Finder window layout.

Everything here is plain data or takes its tools as arguments, so the unit tests
run on Windows. The macOS tools (sips, iconutil, dmgbuild) only run in CI.
"""
from __future__ import annotations

from pathlib import Path
import os
import plistlib
import time

ICON_NAME = "Uoink.icns"
ICON_SOURCE = Path("assets/brand/app-icon-macos-1024.png")
ICNS_MAGIC = b"icns"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

# Apple's iconset names: each base size once at 1x and once at 2x.
ICONSET_BASE_SIZES = (16, 32, 128, 256, 512)

# DMG window, in points. The background art is drawn to these numbers
# (installer/mac/dmg_background.py reads the same constants).
CONTENT_SIZE = (660, 400)
# Finder's window frame includes the title bar. With the toolbar, sidebar,
# status bar and path bar off, the frame is the content plus this strip.
TITLEBAR_HEIGHT = 28
WINDOW_ORIGIN = (120, 120)
ICON_SIZE = 128
TEXT_SIZE = 13
APP_POSITION = (180, 190)
APPLICATIONS_POSITION = (480, 190)
BACKGROUND = Path("installer/mac/dmg-background.png")
BACKGROUND_2X = Path("installer/mac/dmg-background@2x.png")
DMG_FORMAT = "UDZO"
SIDE_ITEMS = {"Uoink.app", "Applications"}


def iconset_entries() -> list[tuple[int, str]]:
    """(pixel size, file name) for every image in the .iconset."""
    entries = []
    for size in ICONSET_BASE_SIZES:
        entries.append((size, f"icon_{size}x{size}.png"))
        entries.append((size * 2, f"icon_{size}x{size}@2x.png"))
    return entries


def icon_commands(source: Path, iconset: Path, icns: Path) -> list[list[str]]:
    """The exact sips and iconutil commands, in order."""
    if iconset.suffix != ".iconset":
        raise ValueError("The icon folder must end in .iconset")
    commands = [["sips", "-z", str(size), str(size), str(source), "--out", str(iconset / name)]
                for size, name in iconset_entries()]
    commands.append(["iconutil", "-c", "icns", "-o", str(icns), str(iconset)])
    return commands


def check_icon_source(source: Path) -> None:
    header = source.read_bytes()[:24]
    if not header.startswith(PNG_MAGIC) or header[12:16] != b"IHDR":
        raise ValueError(f"App icon source is not a PNG: {source}")
    width, height = int.from_bytes(header[16:20], "big"), int.from_bytes(header[20:24], "big")
    if (width, height) != (1024, 1024):
        raise ValueError(f"App icon source must be 1024 x 1024, got {width} x {height}")


def build_icns(source: Path, resources: Path, scratch: Path, run) -> Path:
    """Make Contents/Resources/Uoink.icns before anything is signed."""
    check_icon_source(source)
    iconset = scratch / "Uoink.iconset"
    iconset.mkdir(parents=True)
    target = resources / ICON_NAME
    for command in icon_commands(source, iconset, target):
        run(command)
    check_icns(target)
    return target


def check_icns(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Missing app icon: {path}")
    with path.open("rb") as stream:
        head = stream.read(8)
    if head[:4] != ICNS_MAGIC or int.from_bytes(head[4:8], "big") != path.stat().st_size:
        raise ValueError(f"Not a valid icns file: {path}")


def check_app_icon(app: Path) -> dict:
    """The icon exists, is a real icns file and is the one Info.plist names."""
    with (app / "Contents/Info.plist").open("rb") as stream:
        name = plistlib.load(stream).get("CFBundleIconFile")
    if not name:
        raise ValueError("Info.plist has no CFBundleIconFile")
    if not Path(name).suffix:
        name += ".icns"
    if name != ICON_NAME:
        raise ValueError(f"CFBundleIconFile is {name}, expected {ICON_NAME}")
    icon = app / "Contents/Resources" / name
    check_icns(icon)
    return {"path": icon.relative_to(app).as_posix(), "size": icon.stat().st_size, "plist_name": name}


def window_rect() -> tuple[tuple[int, int], tuple[int, int]]:
    return WINDOW_ORIGIN, (CONTENT_SIZE[0], CONTENT_SIZE[1] + TITLEBAR_HEIGHT)


def dmg_settings(app: Path, root: Path, icon: Path | None = None) -> dict:
    """The dmgbuild settings: one app, one Applications link, a fixed window."""
    icon = icon or app / "Contents/Resources" / ICON_NAME
    background = root / BACKGROUND
    # dmgbuild finds dmg-background@2x.png beside this file and builds the
    # multi-resolution TIFF from the pair.
    for path in (background, root / BACKGROUND_2X, icon):
        if not path.is_file():
            raise ValueError(f"Missing DMG resource: {path}")
    return {
        "format": DMG_FORMAT,
        "filesystem": "HFS+",
        "files": [str(app)],
        "symlinks": {"Applications": "/Applications"},
        "icon": str(icon),
        "background": str(background),
        "window_rect": window_rect(),
        "default_view": "icon-view",
        "icon_size": ICON_SIZE,
        "text_size": TEXT_SIZE,
        "show_status_bar": False,
        "show_tab_view": False,
        "show_toolbar": False,
        "show_pathbar": False,
        "show_sidebar": False,
        "icon_locations": {"Uoink.app": APP_POSITION, "Applications": APPLICATIONS_POSITION},
    }


def build_dmg_image(dmg: Path, volume: str, settings: dict, *, builder=None, sleep=time.sleep,
                    log=None) -> None:
    """Run dmgbuild; retry the hosted runners' intermittent "Resource busy"."""
    if builder is None:
        import dmgbuild
        builder = dmgbuild.build_dmg
    for attempt in range(1, 4):
        try:
            builder(str(dmg), volume, settings=settings)
            return
        except Exception as error:  # dmgbuild raises its own DMGError
            detail = str(error).strip()
            if log:
                log(f"dmgbuild attempt {attempt} failed: {detail}")
            if dmg.exists():
                dmg.unlink()
            if "Resource busy" not in detail or attempt == 3:
                raise
            sleep(10 * attempt)


def check_mounted_layout(mount: Path) -> dict:
    """What a user sees when the DMG opens: background, layout, link, app, icons."""
    names = {entry.name for entry in mount.iterdir()}
    if "Read Me.txt" in names:
        raise ValueError("DMG must not hold Read Me.txt; its facts are on the background")
    if ".DS_Store" not in names:
        raise ValueError("DMG has no .DS_Store, so Finder would ignore the window layout")
    background = sorted(name for name in names if name == ".background" or name.startswith(".background."))
    if not background:
        raise ValueError("DMG has no background image")
    first = mount / background[0]
    if first.is_dir():
        images = [p for p in first.iterdir() if p.is_file() and p.stat().st_size > 0]
    else:
        images = [first] if first.stat().st_size > 0 else []
    if not images:
        raise ValueError("DMG background image is empty")
    if ".VolumeIcon.icns" not in names:
        raise ValueError("DMG has no volume icon")
    check_icns(mount / ".VolumeIcon.icns")
    link = mount / "Applications"
    if not link.is_symlink() or os.readlink(link) != "/Applications":
        raise ValueError("DMG is missing its /Applications link")
    if not (mount / "Uoink.app").is_dir():
        raise ValueError("DMG is missing Uoink.app")
    icon = check_app_icon(mount / "Uoink.app")
    visible = sorted(name for name in names if not name.startswith("."))
    if set(visible) != SIDE_ITEMS:
        raise ValueError(f"DMG shows unexpected items: {visible}")
    return {"background": background, "visible": visible, "app_icon": icon,
            "volume_icon": True, "ds_store": True}
