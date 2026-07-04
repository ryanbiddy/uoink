"""G-24 dashboard recovery UI contract.

Run: python tests/test_g24_recovery_ui.py
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = (ROOT / "assets" / "dashboard" / "index.html").read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_recovery_actions_exist() -> None:
    for marker in (
        'id="yoinkOpenMarkdown"',
        'id="yoinkRetryCapture"',
        'id="runEvidenceClaims"',
        "Open transcript file",
        "Re-capture source",
        "Run claim scan",
    ):
        require(marker in DASHBOARD, f"missing recovery UI marker: {marker}")
    print("ok  detail and Evidence recovery actions render")


def test_backend_contracts_are_wired() -> None:
    for marker in (
        "/markdown`)",
        "/open-markdown`)",
        "/reyoink`",
        'authFetch("/claims/extract"',
    ):
        require(marker in DASHBOARD, f"missing recovery endpoint wiring: {marker}")
    require("state.selectedYoinkMarkdown" in DASHBOARD,
            "detail view does not keep markdown preview state")
    print("ok  markdown, re-capture, and claim-scan endpoints are wired")


def test_dead_end_copy_removed() -> None:
    for stale in (
        "video detail.",
        "Claims section",
        "supports / contradicts / mixed / inconclusive",
        "extract_claims",
        "local detail needs another moment",
    ):
        require(stale not in DASHBOARD, f"stale dead-end copy remains: {stale}")
    print("ok  raw dead-end copy removed from visible templates")


def main() -> int:
    test_recovery_actions_exist()
    test_backend_contracts_are_wired()
    test_dead_end_copy_removed()
    print("\nALL G-24 RECOVERY UI TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
