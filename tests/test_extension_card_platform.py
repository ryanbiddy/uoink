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


def test_mac_open_copies_the_real_path_and_failures_name_this_os():
    handler = _between(HTML, 'authFetch("/open-extension").then(', "return;\n        }")
    # The helper's answer is the real (possibly isolated) path, not the default.
    assert "const path = res && res.path;" in handler
    assert "navigator.clipboard.writeText(path).then(() => true, () => false)" in handler
    assert "setTimeout(() => resolve(false), 1500)" in handler  # Never waits forever.
    assert 'platform !== "mac"' in handler
    assert "EXTENSION_PATH_COPY[platform]" in handler
    assert "%LOCALAPPDATA%" not in handler
