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
    # U-02 rebuilt the writing picker around a selected-source chip: the
    # search input only exists while nothing is selected, and re-entering
    # browse mode goes through clearWritingSource(), which drops the hidden
    # id. A stale pick behind a typed query is structurally impossible, so
    # the G-01 guarantee is now: (1) the render pass never writes the
    # hidden id, and (2) every path back to the input clears it first.
    body = section("function syncWritingSourceOptions()",
                   "function syncWritingGenerateState")
    require("els.writingSource.value =" not in body,
            "writing picker render must never write the hidden source ID")
    clear = section("function clearWritingSource(",
                    "async function selectWritingSourceById")
    require('els.writingSource.value = "";' in clear,
            "clearWritingSource must clear the hidden writing source ID")
    require("state.writingSelectedSourceRow = null;" in clear,
            "clearWritingSource must clear the selected writing row")
    require("clearWritingSource({ focus: true })" in DASHBOARD,
            "chip must route back to browse mode through clearWritingSource")
    print("ok  writing picker: browse mode structurally drops stale picks")


def test_script_picker_clears_on_no_match() -> None:
    # UI re-haul: the Script Studio panel (and its own source picker) was
    # dead and is gone (SPEC "Dashboard IA"). Scripts are written from
    # Generate, whose one picker is covered above, so no second hidden
    # script pick exists to go stale.
    for leftover in ('id="scriptSource"', 'id="scriptSourceSearch"',
                     "scriptSelectedSourceRow", "data-script-source-id"):
        require(leftover not in DASHBOARD,
                f"a hidden Script Studio pick came back: {leftover}")
    print("ok  script picker: no hidden Script Studio pick is left")


def test_script_search_input_drops_stale_pick() -> None:
    # Generate's script mode grounds in the visible Writing pick and stops
    # when there is none, so it can never credit a source the user can't see.
    grounding = section("async function generateScriptGrounding()",
                        "function showGenerateResearch")
    require("const row = state.writingSelectedSourceRow;" in grounding
            and 'if (!row) throw new Error("Choose a source uoink first.");' in grounding,
            "script grounding must use the visible Writing pick")
    script = section("async function generateScriptInWriting()",
                     "async function generateWriting()")
    require("const row = state.writingSelectedSourceRow;" in script
            and "source_yoink_id: screenshotSourceId(row)" in script,
            "the script request must name the visible Writing pick")
    print("ok  script mode: grounded in the visible Writing pick only")


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
