"""G-23 dashboard no-op action contract.

Run: python tests/test_g23_noop_actions.py
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = (ROOT / "assets" / "dashboard" / "index.html").read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_blank_copy_is_disabled_and_guarded() -> None:
    require('id="copyWriting" disabled>Copy</button>' in DASHBOARD, "Copy starts enabled on a blank draft")
    require("if (els.copyWriting) els.copyWriting.disabled = !enabled;" in DASHBOARD,
            "Copy is not tied to the draft action state")
    require('if (!text) return showToast("Write or generate a draft before copying.");' in DASHBOARD,
            "Copy handler does not guard blank drafts")
    require("await navigator.clipboard.writeText(text);" in DASHBOARD,
            "Copy handler should copy the guarded nonblank draft text")
    print("ok  blank Copy is disabled and guarded")


def test_false_use_as_is_action_removed() -> None:
    stale = (
        'id="useWritingAsIs"',
        "Use as-is",
        "Marked for use in this session.",
        "use it anyway",
    )
    for marker in stale:
        require(marker not in DASHBOARD, f"stale no-op remains: {marker}")
    require('id="reviseWriting" disabled>Regenerate from source</button>' in DASHBOARD,
            "Revise action is no longer visibly disabled until a draft exists")
    require('document.getElementById("reviseWriting").addEventListener("click", generateWriting);' in DASHBOARD,
            "Revise action is not wired to the real generation path")
    print("ok  false Use-as-is no-op removed and Revise stays real")


def test_screenshot_setting_is_explicit() -> None:
    require("Show screenshot picker in composer" in DASHBOARD,
            "screenshot picker setting copy is not explicit")
    require("saveSettingsPatch({ writing_show_screenshot_picker: els.writingScreenshotPickerToggle.checked }, \"Screenshot picker setting updated.\");" in DASHBOARD,
            "screenshot picker setting does not save through the settings API")
    print("ok  screenshot picker setting is explicit and real")


def main() -> int:
    test_blank_copy_is_disabled_and_guarded()
    test_false_use_as_is_action_removed()
    test_screenshot_setting_is_explicit()
    print("\nALL G-23 NO-OP ACTION TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
