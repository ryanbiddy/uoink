"""T8/F45/F57: execute the shipped dashboard with mocked I/O and no helper."""
from pathlib import Path
import re
import socket
import subprocess
import urllib.request

import pytest


ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / "assets/dashboard/index.html").read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("discovery UI tests must not use the network")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)


@pytest.mark.parametrize("scenario", [
    "settings", "settings_failure", "settings_stale", "balance", "invalid_key",
    "plan", "intent_failure", "run", "paid_failure", "partial_failure",
    "save_failure", "save_retry_failure", "save_retry_bad_response", "selection", "queue", "states",
])
def test_dashboard_discovery_behavior(scenario):
    result = subprocess.run(
        ["node", str(ROOT / "tests/js/dashboard_discovery_test.cjs"), scenario],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_disclosure_keyboard_theme_and_no_remote_resources():
    markup, script = PAGE.split("<script>", 1)
    disclosure = (
        "Discovery sends the creator handle or search words you type, with your key, "
        "to api.scrapecreators.com. Each request uses ScrapeCreators credits "
        "(most endpoints: 1 credit per request, per their docs). Nothing from your "
        "library is sent. Results are saved on <span data-this-device>this PC</span>."
    )
    assert disclosure in markup
    for control in ("scrapecreatorsKey", "scrapecreatorsDisclosure", "scrapecreatorsEnabled",
                    "scrapecreatorsCap", "scrapecreatorsAgents", "discoveryMode",
                    "discoveryPlatform", "discoveryTerm", "discoveryPages"):
        assert f'for="{control}"' in markup
    assert 'id="scrapecreatorsKey" type="password" maxlength="4096"' in markup
    assert 'id="scrapecreatorsEnabled" type="checkbox" disabled' in markup
    assert 'id="scrapecreatorsCap" type="number" min="1" max="500" step="1" value="25"' in markup
    for status in ("discoveryCreditPlan", "discoveryStatus", "scrapecreatorsTestStatus"):
        assert f'id="{status}" role="status" aria-live="polite"' in markup
    css = markup.split(".discovery-panel {", 1)[1].split(".get-extension {", 1)[0]
    for token in ("--text", "--text-2", "--action", "--surface", "--line-strong"):
        assert f"var({token})" in css
    assert "min-height: 44px" in css and "min-height: 32px" in css
    assert "outline: 2px solid var(--action); outline-offset: 2px" in css
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b|https?://|@import", css)
    discovery = script.split("const discoveryState =", 1)[1].split("function renderSources()", 1)[0]
    assert not re.search(r"<img|<iframe|<video|url\(|setTimeout|setInterval", discovery)
    assert 'bindDiscoveryControls();' in script
    assert not re.search(r'<(?:link|script)[^>]+(?:href|src)="https?://', markup)
