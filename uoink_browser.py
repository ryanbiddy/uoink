"""Chromium browser discovery shared by first-run setup and the dashboard."""
from __future__ import annotations

import logging
import os
from pathlib import Path
import shutil
import sys

log = logging.getLogger(__name__)


BROWSER_CATALOG = [
    # Chrome first: it is the tested browser, and the first installed entry
    # is the fallback when the default browser is not in this list.
    {
        "id": "chrome",
        "name": "Chrome",
        "url": "chrome://extensions/",
        "commands": ["chrome", "chrome.exe"],
        "progids": ["chrome"],
        "paths": [
            ("PROGRAMFILES", "Google/Chrome/Application/chrome.exe"),
            ("PROGRAMFILES(X86)", "Google/Chrome/Application/chrome.exe"),
            ("LOCALAPPDATA", "Google/Chrome/Application/chrome.exe"),
        ],
    },
    {
        "id": "comet",
        "name": "Comet",
        "url": "comet://extensions/",
        "commands": ["comet", "comet.exe"],
        "progids": ["comethtm", "comet"],
        "paths": [
            ("LOCALAPPDATA", "Perplexity/Comet/Application/comet.exe"),
        ],
    },
    {
        "id": "edge",
        "name": "Microsoft Edge",
        "url": "edge://extensions/",
        "commands": ["msedge", "msedge.exe"],
        "progids": ["msedge", "microsoftedge"],
        "paths": [
            ("PROGRAMFILES(X86)", "Microsoft/Edge/Application/msedge.exe"),
            ("PROGRAMFILES", "Microsoft/Edge/Application/msedge.exe"),
            ("LOCALAPPDATA", "Microsoft/Edge/Application/msedge.exe"),
        ],
    },
    {
        "id": "brave",
        "name": "Brave",
        "url": "brave://extensions/",
        "commands": ["brave", "brave.exe", "brave-browser"],
        "progids": ["brave"],
        "paths": [
            ("PROGRAMFILES", "BraveSoftware/Brave-Browser/Application/brave.exe"),
            ("PROGRAMFILES(X86)", "BraveSoftware/Brave-Browser/Application/brave.exe"),
            ("LOCALAPPDATA", "BraveSoftware/Brave-Browser/Application/brave.exe"),
        ],
    },
    {
        "id": "vivaldi",
        "name": "Vivaldi",
        "url": "vivaldi://extensions/",
        "commands": ["vivaldi", "vivaldi.exe"],
        "progids": ["vivaldi"],
        "paths": [
            ("PROGRAMFILES", "Vivaldi/Application/vivaldi.exe"),
            ("PROGRAMFILES(X86)", "Vivaldi/Application/vivaldi.exe"),
            ("LOCALAPPDATA", "Vivaldi/Application/vivaldi.exe"),
        ],
    },
    {
        "id": "opera-gx",
        "name": "Opera GX",
        "url": "opera://extensions/",
        "commands": ["opera", "launcher.exe"],
        "progids": ["operagx", "opera gx"],
        "paths": [
            ("LOCALAPPDATA", "Programs/Opera GX/launcher.exe"),
            ("PROGRAMFILES", "Opera GX/launcher.exe"),
        ],
    },
    {
        "id": "arc",
        "name": "Arc",
        "url": "arc://extensions/",
        "commands": ["arc", "arc.exe"],
        "progids": ["arc"],
        "paths": [
            ("LOCALAPPDATA", "Microsoft/WindowsApps/Arc.exe"),
            ("LOCALAPPDATA", "The Browser Company/Arc/Application/Arc.exe"),
        ],
    },
]


def _browser_by_id(browser_id: str | None):
    wanted = (browser_id or "").lower()
    return next((browser for browser in BROWSER_CATALOG if browser["id"] == wanted), None)


def _default_browser_prog_id() -> str:
    if sys.platform != "win32":
        return ""
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "ProgId")
            return str(value or "")
    except Exception as e:
        log.debug("default browser lookup failed: %s", e)
        return ""


def _browser_from_prog_id(prog_id: str):
    needle = (prog_id or "").lower()
    if not needle:
        return None
    for browser in BROWSER_CATALOG:
        if any(token in needle for token in browser["progids"]):
            return browser
    return None


def _browser_executable(browser) -> str:
    if sys.platform == "darwin":
        names = {"chrome": "Google Chrome", "comet": "Comet", "edge": "Microsoft Edge", "brave": "Brave Browser",
                 "vivaldi": "Vivaldi", "opera-gx": "Opera GX", "arc": "Arc", "chromium": "Chromium"}
        name = names.get(browser["id"])
        if name:
            for root in (Path("/Applications"), Path.home() / "Applications"):
                candidate = root / (name + ".app") / "Contents/MacOS" / name
                if candidate.is_file():
                    return str(candidate)
        return ""
    for env_name, relative in browser["paths"]:
        root = os.environ.get(env_name)
        if not root:
            continue
        path = Path(root) / Path(relative)
        if path.is_file():
            return str(path)
    for command in browser["commands"]:
        found = shutil.which(command)
        if found:
            return found
    return ""


def _browser_descriptor(browser, *, is_default: bool = False) -> dict:
    executable = _browser_executable(browser)
    return {
        "id": browser["id"],
        "name": browser["name"],
        "url": browser["url"],
        "executable": executable,
        "installed": bool(executable),
        "is_default": is_default,
    }


def _available_browsers() -> list[dict]:
    default = _browser_from_prog_id(_default_browser_prog_id())
    browsers = []
    for browser in BROWSER_CATALOG:
        descriptor = _browser_descriptor(browser, is_default=browser is default)
        if descriptor["installed"] or descriptor["is_default"]:
            browsers.append(descriptor)
    return browsers


def _preferred_browser() -> dict:
    browsers = _available_browsers()
    default = next((browser for browser in browsers if browser["is_default"]), None)
    if default:
        return default
    installed = next((browser for browser in browsers if browser["installed"]), None)
    if installed:
        return installed
    return {
        "id": "chromium",
        "name": "your Chromium browser",
        "url": "chrome://extensions/",
        "executable": "",
        "installed": False,
        "is_default": False,
    }
