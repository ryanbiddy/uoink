"""G-40 manual draft action contract (E2E D1).

A typed or pasted draft in the Generate composer has to unlock the same
Save/Copy/Revise/Critique path as agent output, while an untouched
credit-line seed still counts as blank (keeps the G-23 guard honest).

Run: python tests/test_g40_manual_draft_actions.py
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = (ROOT / "assets" / "dashboard" / "index.html").read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_manual_input_syncs_action_state() -> None:
    require("function syncWritingActionsFromComposer()" in DASHBOARD,
            "composer-to-actions sync helper missing")
    require("setWritingActionsEnabled(composerHasManualDraft());" in DASHBOARD,
            "manual drafts do not drive setWritingActionsEnabled")
    # Typing flows through syncThreadInput; it has to end in the sync call.
    sync_fn = DASHBOARD.split("function syncThreadInput(input)", 1)[1].split("function ", 1)[0]
    require("syncWritingActionsFromComposer();" in sync_fn,
            "syncThreadInput does not sync the action state on typing")
    # Re-renders (add tweet, split, mode change) recompute the state too.
    render_fn = DASHBOARD.split("function renderThreadBuilder()", 1)[1].split("function ", 1)[0]
    require("syncWritingActionsFromComposer();" in render_fn,
            "renderThreadBuilder does not sync the action state")
    print("ok  typed and pasted drafts drive the Save/Copy action state")


def test_untouched_seed_counts_as_blank() -> None:
    require("function isComposerSeedText(value)" in DASHBOARD,
            "seed-text detector missing")
    require('if (text === "Pick a source to build the credit line.") return true;' in DASHBOARD,
            "no-source placeholder seed is not treated as blank")
    require("return text === writingAttributionLine().trim();" in DASHBOARD,
            "credit-line seed is not treated as blank")
    print("ok  untouched credit-line seed keeps actions disabled (G-23 stays honest)")


def test_agent_output_path_still_governs() -> None:
    require("if (String(els.writingOutput.dataset.rawText || \"\").trim()) return;" in DASHBOARD,
            "composer sync should defer to on-screen agent output")
    require("setWritingActionsEnabled(Boolean(text.trim()));" in DASHBOARD,
            "agent output no longer enables the actions")
    print("ok  agent output path unchanged")


def test_save_still_fires_the_real_draft_request() -> None:
    require('await authFetch("/writing/draft", { method: "POST", body: JSON.stringify(payload) });' in DASHBOARD,
            "Save no longer POSTs /writing/draft")
    require('if (!body) return showToast("Write or generate a draft before saving.");' in DASHBOARD,
            "Save handler lost its blank-draft guard")
    print("ok  Save still posts the real /writing/draft request")


def main() -> int:
    test_manual_input_syncs_action_state()
    test_untouched_seed_counts_as_blank()
    test_agent_output_path_still_governs()
    test_save_still_fires_the_real_draft_request()
    print("\nALL G-40 MANUAL DRAFT ACTION TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
