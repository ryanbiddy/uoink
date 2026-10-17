"""Offline C22 child evidence races and survivor failure injection."""
from __future__ import annotations

import ast
import io
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from install_receipt.guards import SITECUSTOMIZE_SOURCE
from install_receipt import scenarios
from install_receipt.validation import C22ValidationError


def _load_functions(source, names, scope):
    nodes = [node for node in ast.parse(source).body
             if isinstance(node, ast.FunctionDef) and node.name in names]
    assert {node.name for node in nodes} == names
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "child-fixture", "exec"), scope)


@pytest.fixture
def guarded_child(tmp_path, monkeypatch):
    events = []

    class Process:
        def __init__(self, *args, **kwargs):
            self.pid, self.returncode = 12345, None
            self.stdin, self.stdout, self.stderr = io.BytesIO(), io.BytesIO(), io.BytesIO()

        def terminate(self):
            self.returncode = -15

        def kill(self):
            self.returncode = -9

        def wait(self, **kwargs):
            return self.returncode

        def poll(self):
            return self.returncode

    sources = SimpleNamespace(
        current_capture_context=lambda: {"start_id": "start-1", "instance": "instance-1"},
        record_child_launch_intent=Mock(), resolve_child_launch_intent=Mock(),
        record_child_start=Mock(), record_child_end=Mock(),
    )
    monkeypatch.setitem(sys.modules, "source_subscriptions", sources)
    monkeypatch.setattr(subprocess, "Popen", Process)
    monkeypatch.setattr(subprocess, "_c22_popen_wrapped", False, raising=False)
    scope = {
        "os": os, "sys": sys, "json": json, "PROFILE": str(tmp_path),
        "INJECT": "registration_failure", "_wrap_urlopen": lambda: None,
        "_event": lambda event, **kw: events.append({"event": event, **kw}),
    }
    _load_functions(SITECUSTOMIZE_SOURCE,
                    {"_record_inject_child", "_wrap_popen", "_wrap_subscriptions"}, scope)
    scope["_wrap_subscriptions"](sources)
    wrapped = subprocess.Popen
    return SimpleNamespace(scope=scope, sources=sources, process=wrapped,
                           events=events, profile=tmp_path)


def test_survivor_injection_exercises_product_registration_and_failed_cleanup(guarded_child):
    fixture = guarded_child
    proc = fixture.process(["synthetic-child"])
    spawn = Mock(return_value=proc)
    scope = {
        "subprocess": SimpleNamespace(Popen=spawn, TimeoutExpired=subprocess.TimeoutExpired,
                                      CompletedProcess=subprocess.CompletedProcess),
        "source_subscriptions": fixture.sources, "DATA_ROOT": fixture.profile,
        "SUBPROCESS_KW": {}, "threading": threading, "time": time,
        "log": logging.getLogger(__name__),
    }
    _load_functions((ROOT / "server.py").read_text(encoding="utf-8"),
                    {"_run_subprocess", "_terminate_process", "_raise_if_cancelled"}, scope)
    with pytest.raises(OSError, match="declared registration failure"):
        scope["_run_subprocess"](["synthetic-child"])
    spawn.assert_called_once()
    fixture.sources.record_child_launch_intent.assert_called_once()
    fixture.sources.resolve_child_launch_intent.assert_not_called()
    fixture.sources.record_child_end.assert_not_called()
    assert proc.poll() is None
    assert all(getattr(proc, name).closed for name in ("stdin", "stdout", "stderr"))
    assert [event["operation"] for event in fixture.events] == ["terminate", "kill"]
    note = json.loads((fixture.profile / "c22-inject-child.json").read_text())
    assert note["pid"] == proc.pid
    assert note["registration_failed"] is True
    assert note["cleanup_failure_injected"] is True
    assert not (fixture.profile / "c22-inject-child.json.tmp").exists()


@pytest.mark.parametrize("inject,has_context", [("spawn_child", True), ("registration_failure", False), ("", True)])
def test_cleanup_failure_injection_leaves_other_children_terminable(guarded_child, inject, has_context):
    fixture = guarded_child
    fixture.scope["INJECT"] = inject
    if not has_context:
        fixture.sources.current_capture_context = lambda: None
    proc = fixture.process(["synthetic-child"])
    proc.terminate()
    assert proc.poll() == -15
    proc.kill()
    assert proc.poll() == -9
    assert fixture.events == []


@pytest.mark.parametrize("inject", ["spawn_child", "registration_failure"])
def test_observation_waits_past_intent_and_spawn_note(tmp_path, monkeypatch, inject):
    runner = object.__new__(scenarios.ScenarioRunner)
    monkeypatch.setattr(runner, "_synthetic_url", lambda variant: "http://fixture.invalid/feed.xml")
    monkeypatch.setattr(runner, "_identity_for_variant", lambda variant: ("guid", "title"))
    monkeypatch.setattr(runner, "_register_and_consent", lambda *a, **kw: {})
    monkeypatch.setattr(runner, "_wait_standing", lambda *a, **kw: {"standing_charge_count": 1})
    monkeypatch.setattr(scenarios, "helper_ownership_state", lambda profile: {})
    intent = {"unresolved_launch": True, "children": []}
    registered = {"unresolved_launch": False, "children": [{"pid": 12345}]}
    note_path = tmp_path / "c22-inject-child.json"
    note_path.write_text(json.dumps({"pid": 12345, "registration_failed": False}))
    records = Mock(side_effect=[[intent], [intent], [registered if inject == "spawn_child" else intent]])
    monkeypatch.setattr(scenarios, "child_ownership_records", records)
    sleeps = []

    def advance(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 2:
            note_path.write_text(json.dumps({"pid": 12345, "registration_failed": True}))

    monkeypatch.setattr(scenarios.time, "sleep", advance)
    result = runner._drive_helper_capture(None, tmp_path, variant="child",
                                         operation_key="fixture", inject=inject)
    assert records.call_count == 3
    assert len(sleeps) == 2
    assert result["ownership"] == [registered if inject == "spawn_child" else intent]
    assert result["inject_child_file"]["registration_failed"] is True


def test_missing_registered_child_evidence_fails_visibly(tmp_path, monkeypatch):
    runner = object.__new__(scenarios.ScenarioRunner)
    monkeypatch.setattr(scenarios, "child_ownership_records", lambda path: [
        {"unresolved_launch": True, "children": []}])
    clock = iter([0, 0, 26])
    monkeypatch.setattr(scenarios.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(scenarios.time, "sleep", lambda seconds: None)
    with pytest.raises(C22ValidationError, match="spawn_child child evidence did not arrive"):
        runner._wait_child_evidence(tmp_path, inject="spawn_child")
