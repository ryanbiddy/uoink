"""Install / verify / first capture contracts. Browser and helper I/O are stubbed."""
from pathlib import Path
import re
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "extension/setup.html").read_text(encoding="utf-8-sig")
JS = (ROOT / "extension/setup.js").read_text(encoding="utf-8-sig")
DASHBOARD = (ROOT / "assets/dashboard/index.html").read_text(encoding="utf-8-sig")


def test_dashboard_extension_steps_use_chrome_and_finish_with_pin():
    card = DASHBOARD.split('id="getExtensionCard"', 1)[1].split('<div class="source-map-heading">', 1)[0]
    steps = card.split('<ol class="get-extension-steps">', 1)[1].split('</ol>', 1)[0]
    assert re.findall(r'<li>(.*?)</li>', steps, re.S) == [
        'Open <code>chrome://extensions</code> in Chrome.',
        'Turn on <strong>Developer mode</strong> in the top right.',
        'Click <strong>Load unpacked</strong> and pick the <code>extension</code> folder that just opened.',
        'Click the puzzle-piece Extensions icon in the toolbar and pin <strong>Uoink</strong>, so the Uoink button stays visible.',
    ]
    assert (
        '<p class="get-extension-note">Uoink is built and tested for Chrome. '
        'Edge and Brave are Chromium-based and may work, but are not tested.</p>'
    ) in card
    assert 'edge://extensions' not in card and 'brave://extensions' not in card


def test_dashboard_empty_state_adds_the_uoink_button_to_chrome():
    empty_state = DASHBOARD.split('function setLibraryEmptyState(mode)', 1)[1].split('const stateCopy', 1)[0]
    assert (
        'copy: "Paste a link in the box above to uoink it, or add the Uoink button to Chrome '
        'and click Uoink on any video. Each capture lands here with its transcript, '
        'screenshots when available, and creator credit."'
    ) in empty_state


def test_setup_explains_pinning_before_first_capture():
    capture = HTML.split('<section id="first-capture"', 1)[1].split('</section>', 1)[0]
    pin = (
        '<p>Click the puzzle-piece Extensions icon in the toolbar and pin '
        '<strong>Uoink</strong>, so the Uoink button stays visible.</p>'
    )
    assert pin in capture
    assert capture.index(pin) < capture.index('Try this video') < capture.index('id="uoink-suggested-btn"')


def test_installer_doc_distinguishes_tested_browser_and_explains_pinning():
    doc = (ROOT / "docs/surface-maps/installer-firstrun.md").read_text(encoding="utf-8")
    guidance = doc.split("## Browser Guidance", 1)[1].split("## Splash HTML", 1)[0]
    assert "Uoink is built and tested for Chrome." in guidance
    assert "Edge and Brave may work, but are not tested." in guidance
    assert guidance.index("**Load unpacked**") < guidance.index("puzzle-piece **Extensions** menu") < guidance.index("pin **Uoink**")


def test_setup_is_only_install_verify_and_first_capture():
    assert re.findall(r'<section id="([^"]+)"', HTML) == ["install", "verify", "first-capture"]
    assert '<main aria-labelledby="page-title">' in HTML
    assert 'aria-label="Setup steps"' in HTML
    assert 'href="brand/tokens.css"' in HTML
    assert '/dashboard#settings/capture' in HTML and '/dashboard#settings/app' in HTML
    assert 'id="uoink-suggested-btn"' in HTML and 'aria-describedby="capture-hint" disabled' in HTML
    assert 'role="status"' in HTML and 'role="alert"' in HTML
    assert not re.search(r'<(?:input|select|textarea)\b', HTML)
    for retired in ('ci-save-btn', 'anthropic-key', 'mcp-config-claude', 'tc-save-btn'):
        assert f'id="{retired}"' not in HTML
    for settings_io in ('updateSettings', 'getSettings', '/settings/mcp-config', 'uoink_settings_pending', 'uoink_taste_pending'):
        assert settings_io not in JS
    assert 'postExtract(' not in JS and 'auto_yoink' not in JS


def test_no_inert_folder_action_or_public_path_dependency():
    # F15: /diagnose no longer exposes index_db_writable.detail as a path.
    for removed in ('open-install-folder-btn', 'installFolderPath', 'file:///', 'openFolder(', 'index_db_writable'):
        assert removed not in HTML + JS
    assert not re.search(r'>\s*Open (?:output )?folder\s*<', HTML, re.I)


def test_no_remote_assets_or_decorative_effects():
    assert not re.search(r'<(?:script|link|img)\b[^>]*(?:src|href)="https?://', HTML)
    assert 'gradient(' not in HTML and '@keyframes' not in HTML
    assert 'var(--reader-width)' in HTML
    assert 'var(--on-action)' in HTML
    assert 'max-width: 600px' in HTML


@pytest.mark.parametrize("endpoint,capability", [
    ("/settings/pricing", "AI per-video cost estimate"),
    ("/taxonomy/corrections", "Hook Type correction history and its folder actions"),
    ("/skill/system-prompt", "Operator Skill system-prompt copy"),
])
def test_removed_setup_capabilities_have_dashboard_consumers(endpoint, capability):
    # A link to #settings/ai or #settings/agents is not a migration when the
    # destination cannot read the feature's data. Keep this release blocker
    # visible even when all install / verify / first-capture checks pass.
    scripts = "\n".join(re.findall(r"<script\b[^>]*>([\s\S]*?)</script>", DASHBOARD))
    scripts = re.sub(r"/\*[\s\S]*?\*/|^\s*//[^\n]*", "", scripts, flags=re.M)
    assert re.search(r'["\'`][^"\'`]*' + re.escape(endpoint) + r'(?:[?"\'`])', scripts), (
        f"Setup removed {capability}, but dashboard Settings has no {endpoint} consumer. "
        "Restore the capability before landing the setup removal."
    )


@pytest.mark.parametrize("group", ["offline", "platforms", "mac_download", "navigation_motion", "heartbeat", "visibility", "diagnostics", "routes", "capture", "capture_failure", "capture_races", "worker", "notifications"])
def test_setup_behaviour(group):
    result = subprocess.run(
        ["node", str(ROOT / "tests/js/rehaul_setup_test.mjs"), group],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS {group}" in result.stdout


@pytest.mark.parametrize("group", ["autosave", "pricing", "corrections", "prompt", "resources", "reload"])
def test_setup_capabilities_work_in_dashboard_settings(group):
    result = subprocess.run(
        ["node", str(ROOT / "tests/js/rehaul_setup_settings_test.mjs"), group],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS {group}" in result.stdout
