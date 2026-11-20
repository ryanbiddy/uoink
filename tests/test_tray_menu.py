"""The Windows tray menu builds with saved items, and every item does something.

Bug (3.1 to 3.17): right-click on the tray icon showed nothing once the library
had one saved item. Each Recent items entry used a click handler with three
positional parameters (icon, item, folder=...). pystray 0.19.5 raises
ValueError for an action with more than two, so building the menu failed, and
on Windows pystray had already destroyed the old native menu by then.

No icon or window is created here: pystray is replaced by a stand-in that
copies pystray 0.19.5's MenuItem action rule (MenuItem._assert_action) and its
Menu evaluation (callable item lists, hidden items dropped). When the real
pystray is installed, the same menu is also built with its classes.
"""
from __future__ import annotations

import functools
import inspect
import sys
import types
from pathlib import Path

import pytest

import uoink_tray


class _MenuItem:
    """pystray 0.19.5 MenuItem: text, action, default, visible, enabled."""

    def __init__(self, text, action, checked=None, radio=False, default=False,
                 visible=True, enabled=True):
        self._text = text if callable(text) else (lambda _i, value=text or "": value)
        self._raw_action = action
        self._action = self._assert_action(action)
        self._default = default
        self._visible = visible if callable(visible) else (lambda _i, value=visible: value)
        self.enabled = enabled

    @staticmethod
    def _assert_action(action):
        # Same rule as pystray._base.MenuItem._assert_action.
        if action is None:
            return lambda *_: None
        if not hasattr(action, "__code__"):
            return action
        argcount = action.__code__.co_argcount - (1 if inspect.ismethod(action) else 0)
        if argcount == 0:
            return functools.wraps(action)(lambda *args: action())
        if argcount == 1:
            return functools.wraps(action)(lambda icon, *args: action(icon))
        if argcount == 2:
            return action
        raise ValueError(action)

    @property
    def text(self):
        return self._text(self)

    @property
    def default(self):
        return self._default

    @property
    def submenu(self):
        return self._raw_action if isinstance(self._raw_action, _Menu) else None

    @property
    def visible(self):
        if self.submenu is not None:
            return self._visible(self) and bool(self.submenu)
        return self._visible(self)

    def __call__(self, icon):
        if self.submenu is None:
            return self._action(icon, self)


class _Menu:
    """pystray 0.19.5 Menu: a tuple of items, or one callable that makes them."""
    SEPARATOR = _MenuItem("- - - -", None)

    def __init__(self, *items):
        self._items = tuple(items)

    @property
    def items(self):
        if (len(self._items) == 1 and not isinstance(self._items[0], _MenuItem)
                and callable(self._items[0])):
            return self._items[0]()
        return self._items

    def __iter__(self):
        return iter([item for item in self.items if item.visible])

    def __bool__(self):
        return any(True for _ in self)


@pytest.fixture
def fake_pystray(monkeypatch):
    module = types.ModuleType("pystray")
    module.Menu, module.MenuItem = _Menu, _MenuItem
    monkeypatch.setitem(sys.modules, "pystray", module)
    return module


def _tray(tmp_path, stopped=None):
    return uoink_tray.UoinkTray(
        host="127.0.0.1", port=18116, version="3.18.0",
        token_path=tmp_path / "token.txt", output_dir=tmp_path / "library",
        dashboard_url="http://127.0.0.1:18116/dashboard",
        stop_callback=(lambda: stopped.append(True)) if stopped is not None else (lambda: None),
    )


def _walk(menu):
    """Evaluate a menu the way pystray's win32 backend does when it builds the
    native menu: every visible item's text, and every submenu's items."""
    lines = []
    for item in menu:
        lines.append(item.text)
        if item.submenu is not None:
            lines.append([sub.text for sub in item.submenu])
    return lines


SAVED = [
    {"title": "Talk one", "folder": "C:/library/youtube/talk-one"},
    {"title": "Q&A two", "folder": "C:/library/x/qa-two"},
]


def test_menu_builds_once_the_library_has_saved_items(fake_pystray, tmp_path):
    tray = _tray(tmp_path)
    tray._recent = list(SAVED)
    lines = _walk(tray._build_menu())
    assert lines[2:7] == ["Open dashboard", "Open folder", "Recent items",
                          [uoink_tray.menu_label("Talk one"), uoink_tray.menu_label("Q&A two")],
                          "Settings"]
    assert lines[-1] == "Quit Uoink"


def test_empty_library_shows_a_disabled_placeholder(fake_pystray, tmp_path):
    tray = _tray(tmp_path)
    recent = next(item for item in tray._build_menu() if item.submenu is not None).submenu
    (only,) = list(recent)
    assert only.text == "No recent items yet" and only.enabled is False


def test_a_malformed_recent_row_does_not_break_the_menu(fake_pystray, tmp_path):
    tray = _tray(tmp_path)
    tray._recent = ["not a row", None, {"slug": "kept"}]
    recent = next(item for item in tray._build_menu() if item.submenu is not None).submenu
    assert [item.text for item in recent] == ["kept"]


def test_every_menu_item_does_something(fake_pystray, tmp_path, monkeypatch):
    stopped, spawned, opened_paths, opened_urls = [], [], [], []
    monkeypatch.setattr(uoink_tray.subprocess, "Popen", lambda args, **kw: spawned.append(args))
    monkeypatch.setattr(uoink_tray.UoinkTray, "_open_path", staticmethod(opened_paths.append))
    monkeypatch.setattr(uoink_tray.webbrowser, "open", opened_urls.append)
    tray = _tray(tmp_path, stopped)
    tray._recent = list(SAVED)
    tray._update_latest = "3.18.1"
    icon = object()
    by_text = {}
    for item in tray._build_menu():
        by_text[item.text] = item
        if item.submenu is not None:
            for sub in item.submenu:
                by_text[sub.text] = sub

    by_text["Open dashboard"](icon)
    assert len(spawned) == 1 and spawned[0][-1].endswith("uoink_dashboard.py")
    by_text["Open folder"](icon)
    assert opened_paths == [tmp_path / "library"]
    # Each recent item opens its own folder (a closure made in the loop would
    # bind every item to the last folder).
    by_text["Talk one"](icon)
    assert opened_paths[-1] == Path("C:/library/youtube/talk-one")
    by_text[uoink_tray.menu_label("Q&A two")](icon)
    assert opened_paths[-1] == Path("C:/library/x/qa-two")
    by_text["Settings"](icon)
    by_text["Update available: 3.18.1"](icon)
    assert opened_urls == ["http://127.0.0.1:18116/dashboard#settings",
                           "http://127.0.0.1:18116/dashboard#settings/app"]
    by_text["Quit Uoink"](icon)
    assert stopped == [True]
    # Left-click runs the default item, which is Open dashboard.
    assert [item.text for item in tray._build_menu() if item.default] == ["Open dashboard"]


class _Icon:
    def __init__(self, tray):
        self.tray, self.menus, self.icon, self.title = tray, [], None, ""

    def update_menu(self):
        # Like pystray's win32 backend: evaluate the whole menu now.
        self.menus.append(_walk(self.tray._build_menu()))


@pytest.mark.parametrize("clicked", [True, False], ids=["tray-in-use", "tray-idle"])
def test_poll_rebuilds_the_menu_when_a_new_save_lands(fake_pystray, tmp_path, monkeypatch, clicked):
    # Idle is the normal case: nobody clicks the tray for a minute, and saves
    # arrive from the browser, the CLI or MCP.
    tray = _tray(tmp_path)
    tray._icon = _Icon(tray)
    monkeypatch.setattr(tray, "_image", lambda: "image")
    monkeypatch.setattr(tray, "_refresh_update", lambda: None)

    def status():
        tray._state = "running"

    pages = [[SAVED[0]], [SAVED[0]], [SAVED[1], SAVED[0]]]

    def recent():
        tray._recent = [dict(row, health={"score": len(pages)}) for row in pages.pop(0)]

    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        if clicked:
            tray._last_interaction = uoink_tray.time.monotonic()
        if len(sleeps) == 3:
            tray._stopping.set()

    ticks = iter(range(0, 10_000, 20))  # Each poll sees the recent interval pass.
    monkeypatch.setattr(tray, "_refresh_status", status)
    monkeypatch.setattr(tray, "_refresh_recent", recent)
    monkeypatch.setattr(uoink_tray.time, "sleep", sleep)
    monkeypatch.setattr(uoink_tray.time, "monotonic", lambda: float(next(ticks)))
    tray._last_interaction = 0.0 if clicked else -3600.0  # Last click an hour ago.
    tray._poll_loop()

    assert sleeps == ([uoink_tray._POLL_STATUS_SEC] * 3 if clicked else [30] * 3)
    shown = [menu[5] for menu in tray._icon.menus]
    # First paint, then one rebuild for the new save. The unchanged second page
    # (only a health field moved) does not rebuild the menu.
    assert shown == [["Talk one"], [uoink_tray.menu_label("Q&A two"), "Talk one"]]


def test_real_pystray_builds_the_menu_with_saved_items(tmp_path, monkeypatch):
    pystray = pytest.importorskip("pystray")
    tray = _tray(tmp_path)
    tray._recent = list(SAVED)
    menu = tray._build_menu()
    assert isinstance(menu, pystray.Menu)
    recent = next(item for item in menu if item.submenu is not None).submenu
    assert [item.text for item in recent] == [uoink_tray.menu_label(row["title"]) for row in SAVED]
