"""G-20 dashboard copy contract.

Run: python tests/test_g20_humanized_copy.py
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = (ROOT / "assets" / "dashboard" / "index.html").read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_recheck_stale_copy_removed() -> None:
    stale_phrases = (
        "local helper dashboard",
        "localhost:5179",
        "Uoink is running",
        "Stop helper",
        "Local signals only",
        "Engagement Memory + S1 facets",
        "Selected uoink",
        "Claims section",
        "supports / contradicts / mixed / inconclusive",
        "Open /features",
        "Tune the helper",
        "Whisper model",
        "local Whisper",
        "whisper-timestamped",
        "video detail.",
        "local detail",
        "reading from library",
        "extract_claims",
        "source URL missing",
        "check-worthiness",
        "Unknown channel",
        "Agent config",
        "screen_recording",
        "broll_heavy",
        "one_shot",
        "talking_head",
    )
    for phrase in stale_phrases:
        require(phrase not in DASHBOARD, f"stale G-20 copy remains: {phrase}")
    print("ok  stale raw dashboard copy removed")


def test_advanced_details_are_disclosed() -> None:
    for marker in (
        "private dashboard",
        "Ready on this device",
        "Advanced: local address",
        "Advanced: connection JSON",
        "Advanced: page detail",
        "Saved work and recent signals",
        "signals, not verdicts",
        "Transcript checker",
        "sourceStatusLabel",
        "evidenceSignalLabel",
        "transcriptModelLabel",
    ):
        require(marker in DASHBOARD, f"humanized copy marker missing: {marker}")
    require('href="/settings/mcp-config"' not in DASHBOARD, "About still links to token-gated agent config")
    print("ok  technical details sit behind disclosures")


def main() -> int:
    test_recheck_stale_copy_removed()
    test_advanced_details_are_disclosed()
    print("\nALL G-20 HUMANIZED COPY TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
