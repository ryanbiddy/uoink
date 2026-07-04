"""U-03 -- Generate flow redesign (UX-10, UX-11).

Run: python tests/test_u03_generate_redesign.py  (also collected by pytest)

The Generate form was a 1450px questionnaire with the Generate button two
screens below the fold. The redesign's contract, pinned statically here
(the fold itself is proven live by handoff/qa-harness-playwright/
u03-generate-redesign-check.js):

1. First-screen order: Source picker, Output radios, script options
   (conditional, adjacent to the Output choice that reveals them), Topic,
   ONE "Advanced options" disclosure, Generate button.
2. The disclosure is a native <details> with an arrow and holds Angle,
   Channel pattern, Hook pattern, Style radios, the anchor list, and both
   Voice DNA warning checkboxes.
3. Nothing advanced sits outside it, and there is exactly one of it.
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = (ROOT / "assets" / "dashboard" / "index.html").read_text(
    encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def pos(needle: str) -> int:
    require(needle in DASHBOARD, f"marker missing: {needle}")
    return DASHBOARD.index(needle)


def test_first_screen_order() -> None:
    order = [
        'id="writingSourceCombo"',
        'id="writingModePicker"',
        'id="generateScriptOptions"',
        'id="generateTopicInput"',
        'id="generateAdvanced"',
        'id="generateWriting"',
        'id="agentSetupCard"',
    ]
    positions = [pos(marker) for marker in order]
    require(positions == sorted(positions),
            f"form order drifted: {list(zip(order, positions))}")
    print("ok  source > output > script options > topic > advanced > generate")


def test_script_options_adjacent_to_output() -> None:
    between = DASHBOARD[pos('id="writingModePicker"'):pos('id="generateScriptOptions"')]
    require('id="generateTopicInput"' not in between
            and 'id="generateAdvanced"' not in between,
            "script options must directly follow the Output picker (UX-11)")
    print("ok  script options render beside the Output choice")


def test_one_advanced_disclosure() -> None:
    require(DASHBOARD.count('class="advanced-disclosure"') == 1,
            "exactly ONE advanced-options disclosure")
    details = DASHBOARD[pos('<details class="advanced-disclosure"'):]
    details = details[:details.index("</details>")]
    require("<summary>" in details and "advanced-arrow" in details,
            "disclosure needs a summary with an arrow")
    require("Advanced options" in details, "disclosure label copy")
    for control in ('id="writingAngle"', 'id="generateChannelCombo"',
                    'id="generateHookLensPicker"', 'id="writingStyleMode"',
                    'id="writingAnchorList"', 'id="writingShowWarnings"',
                    'id="writingSkipWarnings"'):
        require(control in details,
                f"{control} must live inside the advanced disclosure")
    require(' open>' not in details.split(">", 1)[0] + ">",
            "disclosure must start closed")
    print("ok  one closed disclosure holds every advanced control")


def test_generate_outside_disclosure() -> None:
    details_start = pos('<details class="advanced-disclosure"')
    details_end = DASHBOARD.index("</details>", details_start)
    generate = pos('id="generateWriting"')
    require(generate > details_end,
            "Generate button must sit after (outside) the disclosure")
    print("ok  Generate button lands outside, right under the disclosure")


def main() -> None:
    test_first_screen_order()
    test_script_options_adjacent_to_output()
    test_one_advanced_disclosure()
    test_generate_outside_disclosure()
    print("\nall green")


if __name__ == "__main__":
    main()
