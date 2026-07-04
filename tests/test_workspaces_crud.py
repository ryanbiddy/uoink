"""G-91 coverage sweep — workspaces.py CRUD + critique log.

Run: python tests/test_workspaces_crud.py  (also collected by pytest tests/)

workspaces.py was the lowest-covered testable backend module (~15%). The
assembler had a surface guard already; the create/get/list/delete lifecycle
and the critique-log writer/reader were untested. This adds happy-path and
error-path coverage for both, against a real index.Index (migration 0007
creates the workspaces + workspace_critique_log tables).

Each test is self-contained (opens its own temp index) so it runs the same
way standalone or under pytest — no shared fixture required.
"""
from __future__ import annotations

import tempfile
from contextlib import contextmanager
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import index as index_mod  # noqa: E402
import workspaces  # noqa: E402


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


@contextmanager
def _index():
    with tempfile.TemporaryDirectory() as d:
        idx = index_mod.Index.open(Path(d) / "index.db")
        try:
            yield idx
        finally:
            idx.close()


def test_crud_lifecycle():
    with _index() as idx:
        ws = workspaces.create_workspace(
            idx, format="talking_head", topic="AI agents",
            hook_target="curiosity_gap", your_channel="@me",
            n_examples=8, notes="test ws")
        wid = ws["id"]
        _assert(wid.startswith("ws_"), f"workspace id shape: {wid}")
        _assert(ws["assembled_yoinks"] == [], "assembled starts empty")
        _assert(ws["n_examples"] == 8, "n_examples persisted")

        got = workspaces.get_workspace(idx, wid)
        _assert(got is not None and got["topic"] == "AI agents",
                "get round-trips")
        _assert(got["format"] == "talking_head" and got["your_channel"] == "@me",
                f"fields persisted: {got}")

        listed = workspaces.list_workspaces(idx)
        _assert(any(r["id"] == wid for r in listed),
                "list includes the workspace")

        _assert(workspaces.delete_workspace(idx, wid) is True,
                "delete returns True")
        _assert(workspaces.get_workspace(idx, wid) is None, "gone after delete")
    print("ok  workspace create/get/list/delete lifecycle")


def test_n_examples_clamped():
    with _index() as idx:
        lo = workspaces.create_workspace(idx, n_examples=0)
        hi = workspaces.create_workspace(idx, n_examples=9999)
        _assert(lo["n_examples"] == 1, f"n_examples floor 1: {lo['n_examples']}")
        _assert(hi["n_examples"] == 100, f"n_examples cap 100: {hi['n_examples']}")
    print("ok  n_examples clamped to [1, 100]")


def test_crud_error_paths():
    with _index() as idx:
        _assert(workspaces.get_workspace(idx, "ws_nope") is None,
                "unknown workspace -> None")
        _assert(workspaces.delete_workspace(idx, "ws_nope") is False,
                "delete unknown -> False")
    print("ok  unknown ids: get None, delete False")


def test_critique_log():
    with _index() as idx:
        ws = workspaces.create_workspace(idx, topic="hooks")
        wid = ws["id"]
        findings = {"hook_strength": "weak", "pacing_issues": ["slow open"]}
        row_id = workspaces.log_critique(
            idx, wid, draft_text="my draft hook", findings=findings)
        _assert(isinstance(row_id, int) and row_id > 0,
                f"critique row id: {row_id}")

        log = workspaces.critique_log_for(idx, wid)
        _assert(len(log) == 1, f"one critique logged: {len(log)}")
        _assert(log[0]["findings"] == findings, "findings JSON round-trips")
        _assert(log[0]["draft_text"] == "my draft hook", "draft text persisted")
        _assert(workspaces.get_workspace(idx, wid) is not None,
                "parent workspace intact after critique")
    print("ok  log_critique -> critique_log_for round-trip")


def test_critique_error_paths():
    with _index() as idx:
        ws = workspaces.create_workspace(idx, topic="x")
        try:
            workspaces.log_critique(idx, ws["id"], draft_text="d", mode="bogus")
            raise AssertionError("bad mode should raise ValueError")
        except ValueError as e:
            _assert("mode must be" in str(e), f"mode error message: {e}")
        try:
            workspaces.log_critique(idx, "ws_missing", draft_text="d")
            raise AssertionError("missing workspace should raise ValueError")
        except ValueError as e:
            _assert("workspace not found" in str(e), f"missing error message: {e}")
    print("ok  log_critique rejects bad mode + missing workspace")


def main():
    test_crud_lifecycle()
    test_n_examples_clamped()
    test_crud_error_paths()
    test_critique_log()
    test_critique_error_paths()
    print("\nALL WORKSPACES CRUD/CRITIQUE TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
