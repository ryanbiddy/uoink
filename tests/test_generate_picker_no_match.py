"""Static UI contract checks for G-01 -- source pickers drop a stale hidden
pick after a no-match query, and Generate stays blocked until a real pick
exists (QA #26, #31).

Run: python tests/test_generate_picker_no_match.py

Red on the pre-fix dashboard: typing a no-match query in the Script or
Writing source picker kept the old hidden source ID selected, so Generate
could ground output in a source the user couldn't see and credit the wrong
creator.
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = (ROOT / "assets" / "dashboard" / "index.html").read_text(
    encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def section(start: str, end: str) -> str:
    require(start in DASHBOARD, f"marker missing: {start}")
    body = DASHBOARD.split(start, 1)[1]
    require(end in body, f"end marker missing after {start}: {end}")
    return body.split(end, 1)[0]


def test_writing_picker_clears_on_no_match() -> None:
    body = section("function syncWritingSourceOptions()",
                   "async function selectWritingSourceById")
    require("if (query && !filtered.length)" in body,
            "writing picker keeps a stale pick after a no-match query")
    clear = body.split("if (query && !filtered.length)", 1)[1]
    require('els.writingSource.value = "";' in clear,
            "no-match query must clear the hidden writing source ID")
    require("state.writingSelectedSourceRow = null;" in clear,
            "no-match query must clear the selected writing row")
    print("ok  writing picker: no-match query clears the hidden source ID")


def test_script_picker_clears_on_no_match() -> None:
    body = section("function syncScriptSourceOptions()",
                   "async function selectScriptSourceById")
    require("if (query && !filtered.length)" in body,
            "script picker keeps a stale pick after a no-match query")
    clear = body.split("if (query && !filtered.length)", 1)[1]
    require('els.scriptSource.value = "";' in clear,
            "no-match query must clear the hidden script source ID")
    require("state.scriptSelectedSourceRow = null;" in clear,
            "no-match query must clear the selected script row")
    print("ok  script picker: no-match query clears the hidden source ID")


def test_script_search_input_drops_stale_pick() -> None:
    handler = section('els.scriptSourceSearch.addEventListener("input"',
                      "});")
    require('els.scriptSource.value = ""' in handler,
            "typing away from the picked script source must clear the "
            "hidden ID")
    require("state.scriptSelectedSourceRow = null" in handler,
            "typing away from the picked script source must clear the "
            "selected row")
    print("ok  script picker: typing a different query drops the stale pick")


def test_generate_blocked_without_pick() -> None:
    require('id="generateWriting" disabled' in DASHBOARD,
            "Generate must start blocked until a source pick exists")
    body = section("function syncWritingGenerateState()",
                   "async function selectWritingSourceById")
    require(".disabled = !hasPick" in body,
            "Generate disabled state must follow the source pick")
    require(DASHBOARD.count("syncWritingGenerateState();") >= 2,
            "Generate state must resync when the picker changes and on an "
            "explicit pick")
    print("ok  Generate: blocked until an explicit source pick exists")


def main() -> int:
    test_writing_picker_clears_on_no_match()
    test_script_picker_clears_on_no_match()
    test_script_search_input_drops_stale_pick()
    test_generate_blocked_without_pick()
    print("\nALL G-01 PICKER NO-MATCH CONTRACT TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
