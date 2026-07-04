"""G-43 frontend contract (E2E D4): exhausted retries say so.

Jobs from /jobs carry retry_exhausted + attempt_count (PR #133). The
Activity rows render honest gave-up copy for those, and terminal rows
never show "Retrying..." even when their error text matches the
rate-limit patterns (covers jobs that predate the field).

Run: python tests/test_g43_retry_exhausted_copy.py
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = (ROOT / "assets" / "dashboard" / "index.html").read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _body(marker: str) -> str:
    return DASHBOARD.split(marker, 1)[1].split("\n    function ", 1)[0]


def test_exhausted_jobs_render_gave_up_copy() -> None:
    body = _body("function activityErrorMessage(raw, phase, context = {})")
    require("if (context.retryExhausted) {" in body,
            "activityErrorMessage does not key off retry_exhausted")
    require(body.index("context.retryExhausted") < body.index("normalizePhase(phase)"),
            "retry_exhausted check has to run before the text translation")
    require("Uoink gave up after ${attempts} attempts. It won't retry this one on its own." in DASHBOARD,
            "attempt-count gave-up copy missing")
    require("Uoink gave up on this one. It won't retry it on its own." in DASHBOARD,
            "countless gave-up copy missing")
    print("ok  retry_exhausted jobs render gave-up copy")


def test_terminal_rows_never_say_retrying() -> None:
    body = _body("function translateMachineMessage(value, context = {})")
    require(body.count("if (context.terminal)") == 2,
            "both Retrying... branches need the terminal guard")
    require(body.count('"Uoink needs a minute. Retrying..."') == 2,
            "non-terminal rows should keep the honest Retrying... copy")
    require("kept refusing this one. Give it a few minutes, then retry it yourself." in body,
            "terminal rate-limit rows need actionable stopped copy")
    for guard, retrying in zip(
        _indexes(body, "if (context.terminal)"),
        _indexes(body, '"Uoink needs a minute. Retrying..."'),
    ):
        require(guard < retrying, "terminal guard has to run before the Retrying... return")
    print("ok  terminal rows never promise a retry")


def _indexes(text: str, needle: str) -> list[int]:
    out, start = [], 0
    while True:
        idx = text.find(needle, start)
        if idx < 0:
            return out
        out.append(idx)
        start = idx + 1


def test_rows_pass_the_new_job_fields() -> None:
    require("const exhausted = job.retry_exhausted === true;" in DASHBOARD,
            "jobRowHtml ignores retry_exhausted")
    require("const exhausted = row.retry_exhausted === true;" in DASHBOARD,
            "queueRowHtml ignores retry_exhausted")
    require(DASHBOARD.count("retryExhausted: exhausted,") == 2,
            "both row renderers should pass retryExhausted")
    require("attempts: job.attempt_count," in DASHBOARD,
            "jobRowHtml does not pass attempt_count")
    require("row.retry_after && !exhausted" in DASHBOARD,
            "exhausted queue rows still advertise a scheduled retry")
    print("ok  row renderers pass retry_exhausted and attempt_count through")


def main() -> int:
    test_exhausted_jobs_render_gave_up_copy()
    test_terminal_rows_never_say_retrying()
    test_rows_pass_the_new_job_fields()
    print("\nALL G-43 FRONTEND RETRY-EXHAUSTED TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
