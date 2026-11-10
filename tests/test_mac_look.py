"""The Mac app icon and DMG window: commands, settings, art and smoke checks (no macOS needed)."""
from __future__ import annotations

import plistlib
import re
import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/mac"))
import mac_look  # noqa: E402


def fake_icns(path: Path) -> Path:
    body = b"ic12" + struct.pack(">I", 12) + b"\0" * 4
    path.write_bytes(b"icns" + struct.pack(">I", 8 + len(body)) + body)
    return path


def fake_app(root: Path, icon_key="Uoink.icns", with_icon=True) -> Path:
    app = root / "Uoink.app"
    (app / "Contents/Resources").mkdir(parents=True)
    plist = {"CFBundleExecutable": "Uoink"}
    if icon_key:
        plist["CFBundleIconFile"] = icon_key
    (app / "Contents/Info.plist").write_bytes(plistlib.dumps(plist))
    if with_icon:
        fake_icns(app / "Contents/Resources/Uoink.icns")
    return app


def sub(tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    path.mkdir()
    return path


def test_iconset_has_every_apple_name_once():
    entries = mac_look.iconset_entries()
    assert [name for _, name in entries] == [
        "icon_16x16.png", "icon_16x16@2x.png", "icon_32x32.png", "icon_32x32@2x.png",
        "icon_128x128.png", "icon_128x128@2x.png", "icon_256x256.png", "icon_256x256@2x.png",
        "icon_512x512.png", "icon_512x512@2x.png"]
    assert [px for px, _ in entries] == [16, 32, 32, 64, 128, 256, 256, 512, 512, 1024]


def test_icon_commands_resize_with_sips_then_iconutil():
    iconset, icns = Path("w/Uoink.iconset"), Path("out/Uoink.icns")
    commands = mac_look.icon_commands(Path("src.png"), iconset, icns)
    assert commands[0][:5] == ["sips", "-z", "16", "16", "src.png"]
    assert commands[-2] == ["sips", "-z", "1024", "1024", "src.png", "--out", str(iconset / "icon_512x512@2x.png")]
    assert commands[-1] == ["iconutil", "-c", "icns", "-o", str(icns), str(iconset)]
    assert len(commands) == 11
    with pytest.raises(ValueError, match="iconset"):
        mac_look.icon_commands(Path("a.png"), Path("w/plain"), Path("o.icns"))


def test_build_icns_runs_every_command_and_checks_the_result(tmp_path):
    resources = sub(tmp_path, "Resources")
    seen = []

    def run(command):
        seen.append(command)
        if command[0] == "iconutil":
            fake_icns(Path(command[4]))

    target = mac_look.build_icns(ROOT / mac_look.ICON_SOURCE, resources, tmp_path / "scratch", run)
    assert target == resources / "Uoink.icns" and len(seen) == 11
    assert (tmp_path / "scratch/Uoink.iconset").is_dir()
    # A run that leaves no valid icns fails loudly instead of shipping a blank icon.
    with pytest.raises(ValueError, match="Missing app icon"):
        mac_look.build_icns(ROOT / mac_look.ICON_SOURCE, sub(tmp_path, "Other"), tmp_path / "s2", lambda c: None)


def test_icon_source_must_be_the_1024_png(tmp_path):
    mac_look.check_icon_source(ROOT / mac_look.ICON_SOURCE)
    bad = tmp_path / "x.png"
    bad.write_bytes(b"not a png at all, just some bytes here")
    with pytest.raises(ValueError, match="not a PNG"):
        mac_look.check_icon_source(bad)


def test_app_icon_check(tmp_path):
    assert mac_look.check_app_icon(fake_app(sub(tmp_path, "a")))["path"] == "Contents/Resources/Uoink.icns"
    with pytest.raises(ValueError, match="Missing app icon"):
        mac_look.check_app_icon(fake_app(sub(tmp_path, "b"), with_icon=False))
    with pytest.raises(ValueError, match="no CFBundleIconFile"):
        mac_look.check_app_icon(fake_app(sub(tmp_path, "c"), icon_key=None))
    with pytest.raises(ValueError, match="expected Uoink.icns"):
        mac_look.check_app_icon(fake_app(sub(tmp_path, "d"), icon_key="Other.icns"))
    # CFBundleIconFile may omit the extension.
    assert mac_look.check_app_icon(fake_app(sub(tmp_path, "e"), icon_key="Uoink"))["plist_name"] == "Uoink.icns"
    bad = fake_app(sub(tmp_path, "f"))
    (bad / "Contents/Resources/Uoink.icns").write_bytes(b"not an icon")
    with pytest.raises(ValueError, match="Not a valid icns"):
        mac_look.check_app_icon(bad)


def test_built_plist_and_reference_plist_name_the_same_icon():
    import build_bundle
    reference = plistlib.loads((ROOT / "installer/mac/Info.plist").read_bytes())
    assert build_bundle.info_plist("3.17.0")["CFBundleIconFile"] == reference["CFBundleIconFile"] == mac_look.ICON_NAME


def test_dmg_settings_are_the_agreed_layout(tmp_path):
    app = fake_app(tmp_path)
    settings = mac_look.dmg_settings(app, ROOT)
    assert settings["format"] == "UDZO"
    assert settings["files"] == [str(app)] and settings["symlinks"] == {"Applications": "/Applications"}
    assert settings["icon_locations"] == {"Uoink.app": (180, 190), "Applications": (480, 190)}
    assert settings["icon_size"] == 128 and settings["text_size"] == 13
    (x, y), (w, h) = settings["window_rect"]
    assert w == 660 and h == 400 + mac_look.TITLEBAR_HEIGHT and x < 300 and y < 300
    for key in ("show_status_bar", "show_tab_view", "show_toolbar", "show_pathbar", "show_sidebar"):
        assert settings[key] is False
    assert settings["default_view"] == "icon-view"
    assert settings["icon"] == str(app / "Contents/Resources/Uoink.icns")
    assert Path(settings["background"]) == ROOT / "installer/mac/dmg-background.png"
    assert not any("Read Me" in str(v) for v in settings.values())


def test_dmg_settings_refuse_missing_resources(tmp_path):
    with pytest.raises(ValueError, match="Missing DMG resource"):
        mac_look.dmg_settings(fake_app(sub(tmp_path, "a"), with_icon=False), ROOT)
    with pytest.raises(ValueError, match="Missing DMG resource"):
        mac_look.dmg_settings(fake_app(sub(tmp_path, "b")), tmp_path)


def test_dmgbuild_retries_only_resource_busy(tmp_path):
    dmg = tmp_path / "x.dmg"
    sleeps, calls = [], []

    def flaky(filename, volume, settings):
        calls.append(volume)
        dmg.write_bytes(b"partial")
        if len(calls) < 3:
            raise RuntimeError("Unable to create disk image: hdiutil: create failed - Resource busy")

    mac_look.build_dmg_image(dmg, "Uoink 1.0.0", {"a": 1}, builder=flaky, sleep=sleeps.append)
    assert len(calls) == 3 and sleeps == [10, 20] and dmg.read_bytes() == b"partial"

    calls.clear()

    def broken(filename, volume, settings):
        calls.append(1)
        dmg.write_bytes(b"x")
        raise RuntimeError("Unable to attach disk image")

    with pytest.raises(RuntimeError, match="attach"):
        mac_look.build_dmg_image(dmg, "v", {}, builder=broken, sleep=sleeps.append)
    assert len(calls) == 1 and not dmg.exists()

    def always_busy(filename, volume, settings):
        calls.append(1)
        raise RuntimeError("Resource busy")

    calls.clear()
    with pytest.raises(RuntimeError, match="Resource busy"):
        mac_look.build_dmg_image(dmg, "v", {}, builder=always_busy, sleep=lambda s: None)
    assert len(calls) == 3


def mounted(tmp_path, *, readme=False, background=True, ds=True, volume_icon=True, link=True, app=True, extra=None):
    mount = sub(tmp_path, "mnt")
    if ds:
        (mount / ".DS_Store").write_bytes(b"\0\0\0\1Bud1")
    if background:
        (mount / ".background.tiff").write_bytes(b"II*\0 fake tiff")
    if volume_icon:
        fake_icns(mount / ".VolumeIcon.icns")
    if link:
        try:
            (mount / "Applications").symlink_to("/Applications")
        except OSError:
            pytest.skip("symlinks need privileges on this Windows account")
    if app:
        fake_app(mount)
    if readme:
        (mount / "Read Me.txt").write_text("hi")
    if extra:
        (mount / extra).write_text("x")
    return mount


def test_mounted_layout_accepts_the_finished_volume(tmp_path):
    report = mac_look.check_mounted_layout(mounted(tmp_path))
    assert report["visible"] == ["Applications", "Uoink.app"] and report["background"] == [".background.tiff"]


@pytest.mark.parametrize("kwargs,message", [
    ({"readme": True}, "Read Me"), ({"background": False}, "no background"), ({"ds": False}, r"\.DS_Store"),
    ({"volume_icon": False}, "volume icon"), ({"link": False}, "Applications"), ({"app": False}, "Uoink.app"),
    ({"extra": "stray.txt"}, "unexpected items")])
def test_mounted_layout_rejects_each_gap(tmp_path, kwargs, message):
    with pytest.raises(ValueError, match=message):
        mac_look.check_mounted_layout(mounted(tmp_path, **kwargs))


def test_mounted_layout_accepts_a_background_folder(tmp_path):
    mount = mounted(tmp_path, background=False)
    (mount / ".background").mkdir()
    (mount / ".background/dmg-background.png").write_bytes(b"png")
    assert mac_look.check_mounted_layout(mount)["background"] == [".background"]


def test_background_art_matches_the_layout():
    Image = pytest.importorskip("PIL.Image")
    one, two = (Image.open(ROOT / p) for p in (mac_look.BACKGROUND, mac_look.BACKGROUND_2X))
    assert one.size == (660, 400) and two.size == (1320, 800)
    # tiffutil -cathidpicheck needs 72 and 144 dpi.
    assert round(one.info["dpi"][0]) == 72 and round(two.info["dpi"][0]) == 144
    cream = (255, 244, 236)
    rgb = one.convert("RGB")
    assert rgb.getpixel((5, 5)) == cream and two.convert("RGB").getpixel((5, 5)) == cream
    # Nothing but cream inside either 128 pt icon box; the arrow sits between them.
    half = mac_look.ICON_SIZE // 2
    for cx, cy in (mac_look.APP_POSITION, mac_look.APPLICATIONS_POSITION):
        assert [c for _, c in rgb.crop((cx - half, cy - half, cx + half, cy + half)).getcolors()] == [cream]
    arrow = [x for x in range(660) if rgb.getpixel((x, 190)) != cream]
    assert arrow and min(arrow) > 244 and max(arrow) < 416
    assert abs((min(arrow) + max(arrow)) / 2 - 330) <= 6


def test_background_art_regenerates_identically():
    pytest.importorskip("PIL")
    sys.path.insert(0, str(ROOT / "installer/mac"))
    import dmg_background
    from PIL import Image, ImageChops
    for scale, relative in ((1, mac_look.BACKGROUND), (2, mac_look.BACKGROUND_2X)):
        assert ImageChops.difference(dmg_background.render(scale), Image.open(ROOT / relative).convert("RGB")).getbbox() is None


def test_tooling_file_is_hash_pinned_and_pure_python():
    lines = [l for l in (ROOT / "scripts/mac/dmg-tooling.txt").read_text().splitlines() if l and not l.startswith("#")]
    assert {l.split("==")[0] for l in lines} == {"dmgbuild", "ds_store", "mac_alias"}
    for line in lines:
        assert re.fullmatch(r"[a-z_]+==\d+(\.\d+)+ --hash=sha256:[0-9a-f]{64}", line), line


def test_workflow_installs_dmg_tooling_before_the_dmg_is_built():
    text = (ROOT / ".github/workflows/mac-qualify.yml").read_text()
    install = "python -m pip install --require-hashes --only-binary=:all: -r scripts/mac/dmg-tooling.txt"
    assert text.count(install) == 2
    build = text[text.index("  mac-build:"):text.index("  mac-sign:")]
    assert build.index(install) < build.index("build-mac.sh")
    sign = text[text.index("  mac-sign:"):text.index("  import-smoke:")]
    assert sign.index(install) < sign.index("sign_notarize.py prepare")
    step = sign[sign.index("- name: Install hash-pinned DMG layout tooling"):sign.index("- name: Extract the existing app")]
    assert "secrets." not in step
