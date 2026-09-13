"""Passive before/after hook probe for this synthetic directory only."""
import json
import os
from pathlib import Path
import pytest

DEST = Path(os.environ["SUBTEST_PROBE_RECEIPT"])
assert not DEST.exists()
DEST.mkdir()
ROWS = []
STREAM = (DEST / 'reports.jsonl').open('x', encoding='utf-8')


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_logreport(report):
    context = getattr(report, "context", None)
    row = {"index": len(ROWS), "nodeid": report.nodeid, "when": report.when,
           "class": type(report).__module__ + "." + type(report).__name__,
           "before": report.outcome, "context": context._to_json() if context else None,
           "duration": report.duration, "wasxfail": getattr(report, "wasxfail", None)}
    yield
    row["after"] = report.outcome
    row["longrepr_after"] = str(report.longrepr) if report.longrepr is not None else None
    ROWS.append(row)
    STREAM.write(json.dumps(row) + "\n")
    STREAM.flush()


def pytest_collection_finish(session):
    (DEST / "membership.json").write_text(json.dumps([i.nodeid for i in session.items], indent=2), encoding="utf-8")
    hooks = [{"plugin": h.plugin_name, "function": h.function.__qualname__, "hookwrapper": h.hookwrapper, "wrapper": h.wrapper, "tryfirst": h.tryfirst, "trylast": h.trylast} for h in session.config.hook.pytest_runtest_logreport.get_hookimpls()]
    (DEST / "hooks.json").write_text(json.dumps(hooks, indent=2), encoding="utf-8")


def pytest_sessionfinish(session, exitstatus):
    (DEST / "session.json").write_text(json.dumps({"exit": int(exitstatus), "tests_collected": session.testscollected, "tests_failed": session.testsfailed, "reports": len(ROWS)}, indent=2), encoding="utf-8")
    STREAM.close()
