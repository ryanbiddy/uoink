"""G-21 dashboard smart-input picker contract.

Run: python tests/test_g21_smart_inputs_ui.py
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = (ROOT / "assets" / "dashboard" / "index.html").read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def section(start: str, end: str) -> str:
    body = DASHBOARD.split(start, 1)[1]
    return body.split(end, 1)[0]


def test_endpoint_contracts() -> None:
    for endpoint in (
        'authFetch("/library/facets")',
        'authFetch("/corpus/channels?limit=80")',
        'authFetch("/writing/recent-ctas?limit=20")',
    ):
        require(endpoint in DASHBOARD, f"missing smart-input endpoint: {endpoint}")
    print("ok  smart inputs load corpus facets, channels, and recent CTAs")


def test_generate_controls_render() -> None:
    for marker in (
        'id="generateTopicInput"',
        'id="generateTopicChips"',
        'id="generateChannelInput"',
        'id="generateChannelOptions"',
        'id="generateLengthPresets"',
        'id="generateCtaChips"',
        'data-generate-topic',
        'data-generate-channel',
        'data-generate-length',
        'data-generate-cta',
    ):
        require(marker in DASHBOARD, f"Generate smart control missing: {marker}")
    print("ok  Generate renders topic, channel, length, and CTA pickers")


def test_generation_payload_uses_picks() -> None:
    body = section("async function generateAssemblyBody()", "async function generateScriptGrounding()")
    require("els.generateTopicInput.value.trim()" in body,
            "selected topic is not sent into workspace assembly")
    require("els.generateChannel.value || els.generateChannelInput.value" in body,
            "selected channel is not sent into workspace assembly")
    script = section("async function generateScriptInWriting()", "async function generateWriting()")
    require("target_length_sec: Number(els.generateScriptLength.value || 120)" in script,
            "script length input is not sent")
    require("cta: els.generateScriptCta.value.trim() || undefined" in script,
            "CTA input is not sent")
    print("ok  Generate payload consumes the selected smart-input values")


def main() -> int:
    test_endpoint_contracts()
    test_generate_controls_render()
    test_generation_payload_uses_picks()
    print("\nALL G-21 SMART-INPUT UI TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
