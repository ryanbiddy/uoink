"""Mac UI contracts without Apple frameworks, dialogs or the user's clipboard."""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

from helper import mac_ui as ui

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def darwin(monkeypatch):
    monkeypatch.setattr(ui, "sys", SimpleNamespace(platform="darwin"))
    monkeypatch.setattr(ui, "child_environment", lambda: {"fixture": "only"})


@pytest.mark.parametrize("failure, code", [
    (subprocess.TimeoutExpired("osascript", 120), "folder_picker_timeout"),
    (OSError("unavailable"), "folder_picker_unavailable"),
    (SimpleNamespace(returncode=1, stdout="", stderr="User canceled. (-128)"), "folder_picker_cancelled"),
    (SimpleNamespace(returncode=1, stdout="", stderr="Not authorized (-1743)"), "folder_access_denied"),
])
def test_folder_cancel_denial_and_timeout_are_no_change(monkeypatch, darwin, failure, code):
    fake = Mock(side_effect=failure) if isinstance(failure, Exception) else Mock(return_value=failure)
    monkeypatch.setattr(ui.subprocess, "run", fake)
    result = ui.pick_folder(Path('/Users/fixture/Documents/Quotes " and 雪'))
    assert result["ok"] is False and result["code"] == code
    assert "not changed" in result["error"]
    command = fake.call_args.args[0]
    assert command[0] == "/usr/bin/osascript" and command[-1].endswith('Quotes " and 雪')
    assert 'Quotes "' not in command[2]
    assert fake.call_args.kwargs["timeout"] == 120


def test_picker_returns_unicode_path_without_tk(monkeypatch, darwin):
    fake = Mock(return_value=SimpleNamespace(returncode=0, stdout="/Users/test/雪 & files/\n", stderr=""))
    monkeypatch.setattr(ui.subprocess, "run", fake)
    assert ui.pick_folder()["path"] == "/Users/test/雪 & files/"
    import server
    monkeypatch.setattr(server.sys, "platform", "darwin")
    monkeypatch.setattr(server, "_pick_output_folder_windows", lambda *_: pytest.fail("Windows picker"))
    monkeypatch.setitem(sys.modules, "tkinter", None)
    assert server._pick_output_folder() == "/Users/test/雪 & files/"
    assert server._pick_output_folder_tk() == "/Users/test/雪 & files/"


@pytest.mark.parametrize("selection, denied_write", [(False, False), (True, True)])
def test_picker_handler_never_saves_after_denial(monkeypatch, selection, denied_write):
    import server
    monkeypatch.setattr(server.sys, "platform", "darwin")
    settings = {"output_dir": "/original"}
    monkeypatch.setattr(server, "_read_settings", lambda: dict(settings))
    monkeypatch.setattr(server, "_public_settings", lambda data: data)
    monkeypatch.setattr(server, "_write_settings", lambda *_: pytest.fail("Must not change settings"))
    monkeypatch.setattr(ui, "pick_folder", lambda *_: {"ok": True, "path": "/denied"} if selection else
                        {"ok": False, "error": "Denied. Your output folder has not changed."})
    monkeypatch.setattr(server, "_validate_output_dir_value", lambda *_: (None, "denied"))
    handler = server.Handler.__new__(server.Handler)
    handler._send_json = lambda status, payload: (status, payload)
    status, result = handler._handle_settings_output_folder_pick({})
    assert status == 200 and result["ok"] is False
    assert result["settings"] == settings and "not changed" in result["error"]


def test_clipboard_preserves_multimodal_corpus_and_unicode(monkeypatch, darwin):
    fake = Mock()
    monkeypatch.setattr(ui.subprocess, "run", fake)
    text = '# 雪\n![frame](data:image/jpeg;base64,/9j/fixture)\n' * 10000
    assert ui.copy_text(text)
    assert fake.call_args.args == (["/usr/bin/pbcopy"],)
    assert fake.call_args.kwargs["input"] == text.encode("utf-8")
    assert fake.call_args.kwargs["timeout"] == 5
    assert fake.call_args.kwargs["env"]["LC_CTYPE"] == "en_US.UTF-8"
    assert fake.call_args.kwargs["env"]["LC_ALL"] == "en_US.UTF-8"


@pytest.mark.parametrize("error", [OSError("missing"), subprocess.TimeoutExpired("pbcopy", 5),
                                  subprocess.CalledProcessError(1, "pbcopy")])
def test_clipboard_failure_is_reported(monkeypatch, darwin, error):
    monkeypatch.setattr(ui.subprocess, "run", Mock(side_effect=error))
    assert ui.copy_text("unchanged") is False


def test_spawn_uses_bundle_python_clean_environment_and_lifeline(monkeypatch, tmp_path):
    import _platform
    contents = tmp_path / "Apps With Spaces/Uoink.app/Contents"
    python = contents / _platform.MAC_BUNDLE_PYTHON
    python.parent.mkdir(parents=True)
    python.touch()
    monkeypatch.setattr(ui, "sys", SimpleNamespace(platform="darwin"))
    monkeypatch.setattr(_platform, "mac_bundle_contents", lambda: contents)
    for key in ("DYLD_LIBRARY_PATH", "DYLD_INSERT_LIBRARIES", "PYTHONPATH", "PYTHONHOME", "PYTHONEXECUTABLE"):
        monkeypatch.setenv(key, "poison")
    fake = Mock(return_value=SimpleNamespace(pid=987, poll=lambda: None, wait=lambda **kw: 0))
    monkeypatch.setattr(ui.subprocess, "Popen", fake)
    monkeypatch.setattr(ui, "_children", [])
    ui.spawn("uoink_dashboard")
    args, kwargs = fake.call_args
    assert args[0] == [str(python), "-B", "-s", "-m", "uoink_dashboard"]
    assert kwargs["cwd"] == contents / "Resources"
    assert not any(key.startswith("DYLD_") for key in kwargs["env"])
    assert not {"PYTHONHOME", "PYTHONPATH", "PYTHONEXECUTABLE"} & kwargs["env"].keys()
    assert kwargs["pass_fds"] == (int(kwargs["env"]["UOINK_UI_LIFELINE"]),)
    writer = ui._children[0][1]
    ui.close_children()
    with pytest.raises(OSError):
        os.fstat(writer)


def test_no_path_python_and_no_ui_restart_loop(monkeypatch):
    import _platform
    monkeypatch.setattr(ui, "sys", SimpleNamespace(platform="darwin"))
    monkeypatch.setattr(_platform, "mac_bundle_contents", lambda: None)
    with pytest.raises(RuntimeError, match="bundled interpreter"):
        ui.spawn("uoink_dashboard")
    proc = SimpleNamespace(pid=88, poll=lambda: None)
    fake = Mock(return_value=proc)
    monkeypatch.setattr(ui, "spawn", fake)
    monkeypatch.setattr(ui, "_menu", None)
    monkeypatch.setattr(ui, "_connected_at", None)
    kwargs = dict(host="127.0.0.1", port=5199, version="1", token_path="fixture", output_dir="out", data_root="data")
    ui.start_menu(**kwargs)
    assert not ui.menu_connected(89)
    assert ui.menu_connected(88) and ui.menu_state()["connected"]
    proc.poll = lambda: 1
    ui.start_menu(**kwargs)
    assert fake.call_count == 1 and not ui.menu_state()["alive"]


def test_mac_dashboard_copy_bridge_covers_every_write():
    original = (ROOT / "assets/dashboard/index.html").read_bytes()
    changed = ui.dashboard_html(original)
    assert changed.count(b"window.uoinkMacCopyText(") == original.count(b"navigator.clipboard.writeText(")
    assert changed.count(b"navigator.clipboard.writeText(") == 1  # Browser fallback.
    assert b"api.copy_text(String(text))" in changed


@pytest.mark.parametrize("platform", ["win32", "linux"])
def test_dashboard_response_bytes_unchanged_off_mac(monkeypatch, platform):
    import server
    monkeypatch.setattr(server.sys, "platform", platform)
    handler = server.Handler.__new__(server.Handler)
    handler.send_response = Mock()
    handler.send_header = Mock()
    handler.end_headers = Mock()
    handler._send_cors = Mock()
    handler._cors_origin = lambda: None
    handler.wfile = io.BytesIO()
    handler._send_file(server.DASHBOARD_PATH, "text/html; charset=utf-8")
    assert handler.wfile.getvalue() == server.DASHBOARD_PATH.read_bytes()


def test_cocoa_dashboard_start_and_browser_fallback(monkeypatch):
    import uoink_dashboard as dashboard
    monkeypatch.setattr(dashboard.sys, "platform", "darwin")
    monkeypatch.setattr(ui, "watch_parent", Mock())
    webview = ModuleType("webview")
    webview.create_window = Mock()
    webview.start = Mock()
    platforms = ModuleType("webview.platforms")
    cocoa = ModuleType("webview.platforms.cocoa")
    for name, module in [("webview", webview), ("webview.platforms", platforms), ("webview.platforms.cocoa", cocoa)]:
        monkeypatch.setitem(sys.modules, name, module)
    opened = Mock()
    monkeypatch.setattr(dashboard.webbrowser, "open", opened)
    dashboard.main()
    webview.start.assert_called_once_with(gui="cocoa")
    assert isinstance(webview.create_window.call_args.kwargs["js_api"], dashboard.MacJsApi)
    opened.assert_not_called()
    webview.start.side_effect = RuntimeError("WebKit unavailable")
    dashboard.main()
    opened.assert_called_once_with(dashboard._target_url())


def test_template_images_are_monochrome_at_both_scales():
    from PIL import Image
    for size, name in [(18, "menubar-template.png"), (36, "menubar-template@2x.png")]:
        with Image.open(ROOT / "assets/brand" / name) as image:
            assert image.size == (size, size) and image.mode == "RGBA"
            assert image.convert("RGB").getextrema() == ((0, 0), (0, 0), (0, 0))
            alpha = image.getchannel("A")
            assert alpha.getextrema() == (0, 255)


def test_pyobjc_so_signed_before_app_and_universal2_kept(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT / "scripts/mac"))
    import build_bundle as bundle
    app = tmp_path / "Uoink.app"
    main = app / "Contents/MacOS/Uoink"
    extension = app / "Contents/Resources/Python/lib/python3.13/site-packages/objc/_objc.so"
    for path in [main, extension]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\xca\xfe\xba\xbe" + b"fixture universal2")
    (app / "Contents/Info.plist").write_bytes(plistlib.dumps({"CFBundleExecutable": "Uoink"}))
    order = bundle.signing_order(app)
    assert order.index(extension) < order.index(main) < order.index(app)
    monkeypatch.setattr(bundle, "run", lambda cmd, **kw: SimpleNamespace(stdout="x86_64 arm64" if cmd[0] == "lipo" else ""))
    assert all(row["architectures"] == "x86_64 arm64" for row in bundle.binary_inventory(app))


def test_reviewed_ui_pins_and_minimum_are_consistent():
    sys.path.insert(0, str(ROOT / "scripts/mac"))
    import qualify_deps as deps
    import build_bundle as bundle
    pins = deps.ui_pins()
    assert len(pins) == 5 and {pin["version"] for pin in pins.values()} == {"12.2.2"}
    deps.verify_ui_wheels(list(pins.values()), complete=True)
    with pytest.raises(ValueError, match="Missing"):
        deps.verify_ui_wheels([], complete=True)
    with pytest.raises(ValueError, match="differs"):
        deps.verify_ui_wheels([{**next(iter(pins.values())), "sha256": "0" * 64}])
    plist = plistlib.loads((ROOT / "installer/mac/Info.plist").read_bytes())
    payload = json.loads((ROOT / "scripts/mac/payload.json").read_text())
    assert plist["LSMinimumSystemVersion"] == payload["ffmpeg"]["minimum_macos"] == bundle.MINIMUM_MACOS == "15.0"


def test_installed_plist_explains_desktop_access():
    # Captures default to ~/Desktop/Uoink; without this key the macOS prompt has no reason text.
    sys.path.insert(0, str(ROOT / "scripts/mac"))
    import build_bundle as bundle
    reference = plistlib.loads((ROOT / "installer/mac/Info.plist").read_bytes())
    installed = plistlib.loads(plistlib.dumps(bundle.info_plist("3.11.1")))
    assert installed["NSDesktopFolderUsageDescription"] == reference["NSDesktopFolderUsageDescription"] == bundle.DESKTOP_USAGE
    assert installed["LSUIElement"] is True and installed["CFBundleVersion"] == "3.11.1"


def test_ui_routes_are_authenticated_before_state_or_actions(monkeypatch):
    import server
    monkeypatch.setattr(server.sys, "platform", "darwin")
    monkeypatch.setattr(ui, "menu_state", lambda: pytest.fail("unauthenticated state read"))
    monkeypatch.setattr(ui, "menu_connected", lambda *_: pytest.fail("unauthenticated connection"))
    monkeypatch.setattr(server, "_spawn_dashboard_window", lambda **kw: pytest.fail("unauthenticated launch"))
    handler = server.Handler.__new__(server.Handler)
    handler._reject_bad_host = lambda: False
    handler._require_token = lambda: False
    for route in ("/helper/ui", "/helper/dashboard", "/helper/quit"):
        handler.path = route
        handler.do_POST()
    handler.path = "/helper/ui"
    handler.do_GET()


def test_splash_once_per_version_and_cocoa_fallback(monkeypatch, tmp_path):
    import uoink_splash as splash
    monkeypatch.setattr(splash.sys, "platform", "darwin")
    monkeypatch.setattr(ui, "watch_parent", Mock())
    sentinel = tmp_path / "first-run"
    monkeypatch.setattr(splash, "_sentinel_path", lambda: sentinel)
    monkeypatch.setattr(splash, "_helper_health_ok", lambda: True)
    monkeypatch.setattr(splash.time, "sleep", lambda *_: None)
    class Event:
        def __iadd__(self, fn):
            self.fn = fn
            return self
    event = Event()
    window = SimpleNamespace(events=SimpleNamespace(loaded=event), destroy=Mock())
    webview = ModuleType("webview")
    webview.create_window = Mock(return_value=window)
    webview.start = Mock(side_effect=lambda **kw: event.fn())
    for name, module in [("webview", webview), ("webview.platforms", ModuleType("webview.platforms")),
                         ("webview.platforms.cocoa", ModuleType("webview.platforms.cocoa"))]:
        monkeypatch.setitem(sys.modules, name, module)
    splash.main()
    assert sentinel.read_text().strip() == splash.VERSION
    splash.main()
    webview.start.assert_called_once_with(gui="cocoa")
    sentinel.write_text("previous-version")
    webview.start.side_effect = RuntimeError("WebKit missing")
    opened = Mock(return_value=True)
    monkeypatch.setattr(splash.webbrowser, "open", opened)
    splash.main()
    opened.assert_called_once_with(splash._splash_url())
    assert sentinel.read_text().strip() == splash.VERSION


def test_splash_chrome_discovery_uses_mac_app_and_existing_open_action(monkeypatch):
    import uoink_splash as splash
    monkeypatch.setattr(splash.sys, "platform", "darwin")
    monkeypatch.setattr(Path, "is_file", lambda path: str(path).replace("\\", "/") ==
                        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    chrome = splash._browser_by_id("chrome")
    path = splash._browser_executable(chrome)
    assert path.replace("\\", "/") == "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    child = Mock()
    monkeypatch.setattr(splash.subprocess, "Popen", child)
    assert splash._open_extensions_page("chrome")
    assert child.call_args.args[0] == [path, "chrome://extensions/"]


def test_appkit_never_enters_a_worker_thread():
    from helper import mac_menubar
    import threading
    errors = []
    def worker():
        try:
            mac_menubar.run_menu(None)
        except RuntimeError as exc:
            errors.append(str(exc))
    thread = threading.Thread(target=worker)
    thread.start()
    thread.join(timeout=5)
    assert errors == ["AppKit must run on the process main thread"]


@pytest.mark.skipif(os.name == "nt", reason="POSIX descriptor and flock semantics")
def test_native_ui_lifeline_and_single_instance(tmp_path):
    from helper.mac_menubar import single_instance
    lock = single_instance(tmp_path)
    assert lock is not None and single_instance(tmp_path) is None
    lock.close()
    second = single_instance(tmp_path)
    assert second is not None
    second.close()
    read_fd, write_fd = os.pipe()
    proc = None
    try:
        proc = subprocess.Popen([sys.executable, "-B", "-c",
            "from helper.mac_ui import watch_parent; import time; "
            "watch_parent(); print('ready', flush=True); time.sleep(60)"],
            cwd=ROOT, env={**os.environ, "UOINK_UI_LIFELINE": str(read_fd)},
            pass_fds=(read_fd,), stdout=subprocess.PIPE, text=True)
        os.close(read_fd)
        read_fd = None
        assert proc.stdout.readline().strip() == "ready"
        os.close(write_fd)
        write_fd = None
        assert proc.wait(timeout=5) == 0
    finally:
        for descriptor in (read_fd, write_fd):
            if descriptor is not None:
                os.close(descriptor)
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)


def _screens(monkeypatch, mouse, frames):
    """Fake AppKit and pywebview screens in Cocoa's bottom-left coordinates."""
    appkit = ModuleType("AppKit")
    appkit.NSEvent = SimpleNamespace(mouseLocation=lambda: mouse)
    appkit.NSPointInRect = lambda p, r: r[0] <= p[0] < r[0] + r[2] and r[1] <= p[1] < r[1] + r[3]
    webview = ModuleType("webview")
    webview.screens = [SimpleNamespace(frame=frame, name=str(frame)) for frame in frames]
    monkeypatch.setitem(sys.modules, "AppKit", appkit)
    monkeypatch.setitem(sys.modules, "webview", webview)
    return webview.screens


def test_windows_open_on_the_screen_under_the_pointer(monkeypatch):
    # This Mac: the laptop is the primary display; two monitors sit above it.
    laptop, right, left = (0, 0, 1728, 1117), (1181, 1117, 1920, 1080), (-739, 1117, 1920, 1080)
    screens = _screens(monkeypatch, (100, 200), [laptop, right, left])
    assert ui.cursor_screen() is screens[0]
    screens = _screens(monkeypatch, (1625, 1772), [laptop, right, left])
    assert ui.cursor_screen() is screens[1]
    _screens(monkeypatch, (9999, 9999), [laptop])
    assert ui.cursor_screen() is None  # pywebview's own default then applies.
    monkeypatch.setitem(sys.modules, "AppKit", None)  # import fails off the bundle
    assert ui.cursor_screen() is None


@pytest.mark.parametrize("module_name", ["uoink_dashboard", "uoink_splash"])
def test_mac_dashboard_and_splash_pass_the_pointer_screen(monkeypatch, tmp_path, module_name):
    import importlib
    module = importlib.import_module(module_name)
    monkeypatch.setattr(module.sys, "platform", "darwin")
    monkeypatch.setattr(ui, "watch_parent", Mock())
    chosen = object()
    monkeypatch.setattr(ui, "cursor_screen", lambda: chosen)
    webview = ModuleType("webview")
    webview.create_window = Mock(return_value=SimpleNamespace(events=SimpleNamespace(loaded=Mock())))
    webview.start = Mock()
    platforms = ModuleType("webview.platforms")
    cocoa = ModuleType("webview.platforms.cocoa")
    for name, value in [("webview", webview), ("webview.platforms", platforms), ("webview.platforms.cocoa", cocoa)]:
        monkeypatch.setitem(sys.modules, name, value)
    if module_name == "uoink_splash":
        monkeypatch.setattr(module, "_sentinel_current", lambda _: False)
        monkeypatch.setattr(module, "_helper_health_ok", lambda: True)
    module.main()
    assert webview.create_window.call_args.kwargs["screen"] is chosen
