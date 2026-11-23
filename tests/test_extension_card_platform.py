"""The dashboard's Get the extension card names this OS's folder and picker."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "assets/dashboard/index.html").read_text(encoding="utf-8")


def _between(text: str, start: str, end: str) -> str:
    head = text.index(start)
    return text[head:text.index(end, head)]


def test_card_path_and_mac_picker_hint_follow_the_platform():
    card = _between(HTML, '<div class="get-extension" id="getExtensionCard">', "</ol>")
    assert '<code id="extensionPathText">' in card
    assert '<li id="extensionMacPickerHint" hidden>' in card
    assert "<kbd>⌘</kbd><kbd>⇧</kbd><kbd>G</kbd>" in card
    paths = _between(HTML, "const EXTENSION_PATH_COPY = {", "};")
    assert '"~/Library/Application Support/Uoink/extension"' in paths
    assert "%LOCALAPPDATA%" in paths
    init = _between(HTML, "const extensionPlatform = helperPlatform();", "const emptyPasteUrl")
    assert "els.extensionPathText.textContent = EXTENSION_PATH_COPY[extensionPlatform]" in init
    assert 'els.extensionMacPickerHint.hidden = extensionPlatform !== "mac"' in init


def test_dashboard_uses_first_run_browser_selection(monkeypatch):
    import uoink_browser
    from tests.test_library_adapters import Probe
    monkeypatch.setattr(uoink_browser, "_default_browser_prog_id", lambda: "MSEdgeHTM")
    monkeypatch.setattr(uoink_browser, "_browser_executable", lambda browser: "")
    request = Probe("GET", "/extension/browser")
    request.do_GET()
    assert request.status == 200
    assert request.payload == {"ok": True, "name": "Microsoft Edge", "url": "edge://extensions/"}


def test_browser_route_works_without_importing_the_splash(monkeypatch):
    import sys
    from tests.test_library_adapters import Probe
    monkeypatch.setitem(sys.modules, "uoink_splash", None)
    request = Probe("GET", "/extension/browser")
    request.do_GET()
    assert request.status == 200 and request.payload["name"] and request.payload["url"]


def test_popup_offline_hint_sends_mac_users_to_the_app():
    popup = (ROOT / "extension/popup.js").read_text(encoding="utf-8")
    hint = _between(popup, "function popupOfflineHint() {", "\n}\n")
    assert 'if (/mac|darwin/.test(os)) return "Open Uoink from Applications or Spotlight, then try again.";' in hint
    assert "Windows only" not in hint
    assert "Start Uoink from the Start menu, then try again." in hint


def test_mac_open_copies_the_real_path_and_failures_name_this_os():
    handler = _between(HTML, 'authFetch("/open-extension").then(', "return;\n        }")
    # The helper's answer is the real (possibly isolated) path, not the default.
    assert "const path = res && res.path;" in handler
    assert "navigator.clipboard.writeText(path).then(() => true, () => false)" in handler
    assert "setTimeout(() => resolve(false), 1500)" in handler  # Never waits forever.
    assert 'platform !== "mac"' in handler
    assert "EXTENSION_PATH_COPY[platform]" in handler
    assert "%LOCALAPPDATA%" not in handler
