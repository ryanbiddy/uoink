"""Setup must not present browser-only taste data as helper-synced."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "extension" / "setup.html").read_text(encoding="utf-8")
SCRIPT = (ROOT / "extension" / "setup.js").read_text(encoding="utf-8")


def test_unimplemented_taste_calibration_is_not_user_visible():
    match = re.search(
        r'<section id="taste-calibration-onboarding" class="([^"]+)"',
        HTML,
    )
    assert match, "taste calibration section is missing"
    assert "hidden" in match.group(1).split(), (
        "taste calibration posts a payload the helper rejects; keep it hidden "
        "until the extension/helper contract is implemented"
    )


def test_browser_fallbacks_do_not_promise_automatic_sync():
    combined = f"{HTML}\n{SCRIPT}".lower()
    forbidden = (
        "settings will sync once helper updates",
        "will sync to your helper after v2.5 lands",
        "saved locally (syncs later)",
    )
    assert not [claim for claim in forbidden if claim in combined]
    assert "stored only in this browser" in combined
    assert "not synced to the helper" in combined
