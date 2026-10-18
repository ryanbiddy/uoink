"""Strict oracles for Phase 4 evidence-completeness instrument repair.

Does not edit the three frozen kit test files. Does not launch Inno, a
model, a client, or port 5179. A passing test asserts measured success;
a refusal is not treated as a valid-preview pass.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / "scripts" / "install_receipt"
sys.path.insert(0, str(KIT))

import p4_common as common
import p4_inspect_evidence as inspect
import p4_prepare_fixture as prepare
import p4_session as session
import p4_stdio_check as stdio_check


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _manifest(path: Path, body=None) -> Path:
    path.write_text(json.dumps(body or {
        "status": "unsealed",
        "package_sha256": None,
        "note": "Astra seals the final package hash after build",
    }) + "\n", encoding="utf-8")
    return path


def _original_local() -> Path:
    return Path(os.environ.get("P4_ORIGINAL_LOCALAPPDATA") or os.environ["LOCALAPPDATA"])


def _frame(direction, message, tick, label):
    raw = (json.dumps(message) + "\n").encode()
    return {
        "kind": "frame", "direction": direction, "received_ns": tick,
        "bytes": len(raw), "sha256": _sha(raw),
        "base64": base64.b64encode(raw).decode(), "route_label": label,
    }


def _expected_one():
    return {
        "items": {
            "p4fx-timed-01": {
                "card_uri": "uoink://card/t", "card_text": "T-CARD",
                "excerpt_uri": "uoink://excerpt/t", "excerpt_text": "T-EX",
                "corpus_uri": "uoink://corpus/t", "corpus_text": "T-CO",
            },
            "p4fx-text-01": {
                "card_uri": "uoink://card/x", "card_text": "X-CARD",
                "excerpt_uri": "uoink://excerpt/x", "excerpt_text": "X-EX",
                "corpus_uri": "uoink://corpus/x", "corpus_text": "X-CO",
            },
            "p4fx-hostile-01": {
                "card_uri": "uoink://card/h", "card_text": "H-CARD",
                "excerpt_uri": "uoink://excerpt/h", "excerpt_text": "H-EX",
                "corpus_uri": "uoink://corpus/h", "corpus_text": "H-CO",
            },
        },
        "brief": {"uri": "uoink://brief/a", "text": "BRIEF"},
    }


def _inventory_rows(label, start):
    rows = []
    i = start
    tools = [{"name": n} for n in common.EXPECTED_STDIO_TOOLS]
    templates = [{"name": n} for n in common.EXPECTED_TEMPLATE_NAMES]
    prompts = [{"name": n} for n in common.EXPECTED_PROMPTS]
    i += 1
    rows.append(_frame("client_to_server", {
        "jsonrpc": "2.0", "id": i, "method": "tools/list",
    }, i * 1000, label))
    rows.append(_frame("server_to_client", {
        "jsonrpc": "2.0", "id": i, "result": {"tools": tools},
    }, i * 1000 + 500, label))
    i += 1
    rows.append(_frame("client_to_server", {
        "jsonrpc": "2.0", "id": i, "method": "resources/templates/list",
    }, i * 1000, label))
    rows.append(_frame("server_to_client", {
        "jsonrpc": "2.0", "id": i, "result": {"resourceTemplates": templates},
    }, i * 1000 + 500, label))
    i += 1
    rows.append(_frame("client_to_server", {
        "jsonrpc": "2.0", "id": i, "method": "prompts/list",
    }, i * 1000, label))
    rows.append(_frame("server_to_client", {
        "jsonrpc": "2.0", "id": i, "result": {"prompts": prompts},
    }, i * 1000 + 500, label))
    return rows, i


def _packet_rows(expected, label, start, *, include_packets=True, consult=True,
                 reshelve="success"):
    rows = []
    i = start
    if include_packets:
        for item in expected["items"].values():
            for kind in ("card", "excerpt", "corpus"):
                uri, text = item[kind + "_uri"], item[kind + "_text"]
                i += 1
                rows.append(_frame("client_to_server", {
                    "jsonrpc": "2.0", "id": i, "method": "resources/read",
                    "params": {"uri": uri},
                }, i * 1000, label))
                rows.append(_frame("server_to_client", {
                    "jsonrpc": "2.0", "id": i, "result": {
                        "contents": [{"uri": uri, "text": text, "mimeType": "text/plain"}]},
                }, i * 1000 + 500, label))
                i += 1
                env = {"ok": True, "contents": [{"uri": uri, "text": text, "mimeType": "text/plain"}]}
                rows.append(_frame("client_to_server", {
                    "jsonrpc": "2.0", "id": i, "method": "tools/call",
                    "params": {"name": "read_library_resource", "arguments": {"uri": uri}},
                }, i * 1000, label))
                rows.append(_frame("server_to_client", {
                    "jsonrpc": "2.0", "id": i, "result": {
                        "isError": False,
                        "content": [{"type": "text",
                                     "text": inspect.PREFIX + json.dumps(env) + inspect.SUFFIX}],
                    },
                }, i * 1000 + 500, label))
        uri, text = expected["brief"]["uri"], expected["brief"]["text"]
        i += 1
        rows.append(_frame("client_to_server", {
            "jsonrpc": "2.0", "id": i, "method": "resources/read", "params": {"uri": uri},
        }, i * 1000, label))
        rows.append(_frame("server_to_client", {
            "jsonrpc": "2.0", "id": i, "result": {
                "contents": [{"uri": uri, "text": text, "mimeType": "text/plain"}]},
        }, i * 1000 + 500, label))
        i += 1
        env = {"ok": True, "contents": [{"uri": uri, "text": text, "mimeType": "text/plain"}]}
        rows.append(_frame("client_to_server", {
            "jsonrpc": "2.0", "id": i, "method": "tools/call",
            "params": {"name": "read_library_resource", "arguments": {"uri": uri}},
        }, i * 1000, label))
        rows.append(_frame("server_to_client", {
            "jsonrpc": "2.0", "id": i, "result": {
                "isError": False,
                "content": [{"type": "text",
                             "text": inspect.PREFIX + json.dumps(env) + inspect.SUFFIX}],
            },
        }, i * 1000 + 500, label))
    if consult:
        i += 1
        rows.append(_frame("client_to_server", {
            "jsonrpc": "2.0", "id": i, "method": "prompts/get",
            "params": {"name": "consult-library", "arguments": {"topic": "orbit"}},
        }, i * 1000, label))
        rows.append(_frame("server_to_client", {
            "jsonrpc": "2.0", "id": i, "result": {
                "messages": [{"role": "user", "content": {"type": "text", "text": "consult"}}]},
        }, i * 1000 + 500, label))
    if reshelve == "success":
        i += 1
        rows.append(_frame("client_to_server", {
            "jsonrpc": "2.0", "id": i, "method": "prompts/get",
            "params": {"name": "reshelve-review", "arguments": {"preview_id": "ok"}},
        }, i * 1000, label))
        rows.append(_frame("server_to_client", {
            "jsonrpc": "2.0", "id": i, "result": {
                "messages": [{"role": "user", "content": {"type": "text", "text": "review"}}]},
        }, i * 1000 + 500, label))
    elif reshelve == "error":
        i += 1
        rows.append(_frame("client_to_server", {
            "jsonrpc": "2.0", "id": i, "method": "prompts/get",
            "params": {"name": "reshelve-review", "arguments": {"preview_id": "bad"}},
        }, i * 1000, label))
        rows.append(_frame("server_to_client", {
            "jsonrpc": "2.0", "id": i, "error": {
                "code": -32603,
                "message": "This revision is unavailable. Resolve the item again.",
                "data": {"error": {"code": "revision_unavailable",
                                   "details": {"reason": "preview_invalidated"}}},
            },
        }, i * 1000 + 500, label))
    return rows, i


def _write_session(path: Path, label: str, child_pid: int, expected, **kwargs):
    rows = [
        {"kind": "launch", "route_label": label, "received_ns": 1},
        {"kind": "child_started", "child_pid": child_pid, "route_label": label},
    ]
    inv, i = _inventory_rows(label, 10)
    rows.extend(inv)
    extra, _ = _packet_rows(expected, label, i, **kwargs)
    rows.extend(extra)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return path


def test_inspect_two_complete_original_sessions_is_a_valid_preview_pair(tmp_path: Path):
    expected = _expected_one()
    a = _write_session(tmp_path / "a.jsonl", "original-installed", 111, expected)
    b = _write_session(tmp_path / "b.jsonl", "original-installed", 222, expected)
    report = inspect.inspect(expected, [a, b], required_route="original-installed")
    assert report["reshelve_review_success"] is True
    assert report["consult_library_ok"] is True
    assert report["valid_preview_pair"] is True
    assert report["original_session_count"] == 2
    assert sorted(report["distinct_child_identities"]) == [111, 222]
    assert report["each_original_session_complete"] is True
    assert report["packet_and_prompt_subset_complete"] is True
    assert not report["frame_faults"]
    assert not report["unknown_or_missing_source_labels"]


def test_inspect_complete_first_partial_second_is_not_complete(tmp_path: Path):
    expected = _expected_one()
    a = _write_session(tmp_path / "a.jsonl", "original-installed", 111, expected)
    b = _write_session(
        tmp_path / "b.jsonl", "original-installed", 222, expected,
        include_packets=False, consult=True, reshelve="success",
    )
    report = inspect.inspect(expected, [a, b], required_route="original-installed")
    assert report["packet_and_prompt_subset_complete"] is False
    assert report["each_original_session_complete"] is False
    assert report["valid_preview_pair"] is False
    statuses = {row["record"]: row["pairs_equal"] for row in report["session_reports"]}
    assert statuses[str(a)] is True
    assert statuses[str(b)] is False


def test_inspect_reshelve_error_is_observed_not_valid_preview(tmp_path: Path):
    expected = _expected_one()
    a = _write_session(
        tmp_path / "a.jsonl", "original-installed", 111, expected, reshelve="error",
    )
    b = _write_session(
        tmp_path / "b.jsonl", "original-installed", 222, expected, reshelve="error",
    )
    report = inspect.inspect(expected, [a, b], required_route="original-installed")
    assert report["reshelve_review_observed"] is True
    assert report["reshelve_review_success"] is False
    assert report["valid_preview_pair"] is False
    assert report["packet_and_prompt_subset_complete"] is False
    assert "reshelve-review" in report["missing_required_native_prompts"]
    assert all(row["reshelve_review_error"] for row in report["session_reports"])


def test_inspect_one_original_session_is_not_a_pair(tmp_path: Path):
    expected = _expected_one()
    a = _write_session(tmp_path / "a.jsonl", "original-installed", 111, expected)
    report = inspect.inspect(expected, [a], required_route="original-installed")
    assert report["original_session_count"] == 1
    assert report["packet_and_prompt_subset_complete"] is False
    assert report["valid_preview_pair"] is False


def test_inspect_malformed_jsonl_fails_closed_instead_of_raising(tmp_path: Path):
    expected = _expected_one()
    path = tmp_path / "bad.jsonl"
    path.write_text("{not json\n{\"kind\":\"launch\",\"route_label\":\"original-installed\"}\n",
                    encoding="utf-8")
    report = inspect.inspect(expected, [path], required_route="original-installed")
    assert report["packet_and_prompt_subset_complete"] is False
    assert report["frame_faults"]
    assert any("malformed jsonl" in str(f.get("error")) for f in report["frame_faults"])


def test_inspect_missing_and_unknown_source_labels_fail(tmp_path: Path):
    expected = _expected_one()
    missing = tmp_path / "missing.jsonl"
    missing.write_text(json.dumps({"kind": "child_started", "child_pid": 1}) + "\n",
                       encoding="utf-8")
    unknown = tmp_path / "unknown.jsonl"
    unknown.write_text(
        json.dumps({"kind": "launch", "route_label": "not-a-source"}) + "\n",
        encoding="utf-8",
    )
    missing_report = inspect.inspect(
        expected, [missing], required_route="original-installed",
    )
    assert missing_report["packet_and_prompt_subset_complete"] is False
    assert any(r["error"] == "missing_source_label"
               for r in missing_report["unknown_or_missing_source_labels"])
    unknown_report = inspect.inspect(
        expected, [unknown], required_route="original-installed",
    )
    assert unknown_report["packet_and_prompt_subset_complete"] is False
    assert any(r["error"] == "unknown_source_label"
               for r in unknown_report["unknown_or_missing_source_labels"])


def test_multimegabyte_stdin_close_remains_bounded(tmp_path: Path):
    child = tmp_path / "noread-huge.py"
    child.write_text("import time\ntime.sleep(60)\n", encoding="utf-8")
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    owned = session.spawn_owned(
        [sys.executable, "-B", str(child)], cwd=tmp_path, env=env, label="noread-huge",
    )
    stdio = session.BoundedStdio(
        owned, default_timeout_s=1.5, retain_dir=tmp_path / "traffic-huge",
    )
    blob = "Z" * (4 * 1024 * 1024)
    t0 = time.perf_counter()
    parsed, elapsed_ms, raw, error = stdio.rpc(
        1, "initialize", {"huge": blob}, timeout_s=1.5,
    )
    cleanup = stdio.close(timeout=5.0)
    waited = time.perf_counter() - t0
    assert parsed is None
    assert error in ("timeout", "stdin_write_timeout")
    assert waited < 12.0
    assert elapsed_ms < 8000
    assert cleanup["writer_exited"] is True
    assert cleanup["stdout_drained"] is True
    assert cleanup["stderr_drained"] is True
    assert cleanup["drain_uncertain"] is False
    assert cleanup["job_query_ok"] is True
    assert cleanup["job_empty_affirmed"] is True
    assert cleanup["identity_uncertain"] is False
    assert cleanup["cleaned"] is True
    stdin_file = tmp_path / "traffic-huge" / "stdin.bin"
    assert stdin_file.is_file()
    retained = (stdio.retained or [{}])[0]
    params = retained.get("params") or {}
    assert params.get("_truncated") is True or "huge" not in params


def test_job_query_failure_is_not_cleaned_credit(tmp_path: Path, monkeypatch):
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    owned = session.spawn_owned(
        [sys.executable, "-B", "-c", "import time; time.sleep(30)"],
        cwd=tmp_path, env=env, label="query-fail",
    )
    job_handle = owned._job
    assert job_handle is not None

    def fail_query(job):
        return {
            "ok": False, "pids": None, "error": "QueryInformationJobObject:5",
            "job_empty": False, "assigned": None,
        }

    monkeypatch.setattr(session, "query_job_process_ids", fail_query)
    cleanup = owned.terminate_tree(timeout=5.0)
    assert cleanup["cleaned"] is False
    assert cleanup["job_query_ok"] is False
    assert cleanup["job_empty_affirmed"] is False
    assert cleanup["identity_uncertain"] is True
    assert cleanup["parent_exited"] is True
    assert owned.popen.poll() is not None
    assert owned._job is None


def test_failed_canary_refuses_product_launch(tmp_path: Path, monkeypatch):
    receipt = tmp_path / "r"
    profile = receipt / "p"
    receipt.mkdir()
    profile.mkdir()
    common.ensure_profile_dirs(profile)
    (profile / "kit").mkdir()
    for name in ("p4_common.py", "p4_stdio_tap.py", "p4_session.py"):
        src = KIT / name
        if src.is_file():
            (profile / "kit" / name).write_bytes(src.read_bytes())
    (profile / "expected.json").write_text("{}\n", encoding="utf-8")
    app = tmp_path / "broken-install"
    app.mkdir()
    (app / "uoink_mcp.py").write_text(
        "import sys\nprint('should not launch', file=sys.stderr)\nraise SystemExit(3)\n",
        encoding="utf-8",
    )
    binding = common.validate_isolation(
        isolated_profile=profile,
        isolated_port=18096,
        receipt_root=receipt,
        installed_app=app,
        installed_interpreter=Path(sys.executable),
        package_manifest=_manifest(tmp_path / "m.json"),
        instrument_only=True,
        original_local=_original_local(),
    )
    env = common.isolation_env(binding, extra={"route_label": "original-installed"})
    launched = []

    def fake_canary(**kwargs):
        return {
            "refused": False, "exit_code": 0, "stdout": "opened\n",
            "live_index_opened": False, "live_index_hashed": False,
        }

    def fake_launch(*args, **kwargs):
        launched.append(args)
        raise AssertionError("product launch must not run after failed canary")

    monkeypatch.setattr(stdio_check, "prove_guard_canary", fake_canary)
    monkeypatch.setattr(stdio_check, "launch", fake_launch)
    result = stdio_check.run_installed(binding, profile, env, "original-installed")
    assert launched == []
    assert result["installed_credit"] is False
    assert result.get("command") is None
    assert any(f.get("operation") == "guard_canary" for f in result["product_findings"])
    restore = result.get("guard_restore") or {}
    assert restore.get("ok") is True


def test_fixture_generator_uses_product_default_store_root():
    assert "prompt-store" not in prepare.ATTACHED_ENTRY
    assert "librarian_apply_enabled=False" in prepare.ATTACHED_ENTRY
    index_path = Path("C:/tmp/p/index.db")
    assert prepare.default_library_store_root(index_path) == Path("C:/tmp/p/library")
    assert prepare.FIXTURE_GENERATOR_VERSION.startswith("p4-evidence-completeness-v2")
    assert prepare.ARCHIVED_V1_NONDEFAULT_STORE == "prompt-store"


def test_prepare_writes_default_store_and_versioned_artifact(tmp_path: Path):
    receipt = tmp_path / "r"
    profile = receipt / "p"
    receipt.mkdir()
    binding = common.validate_isolation(
        isolated_profile=profile,
        isolated_port=18097,
        receipt_root=receipt,
        installed_app=ROOT,
        installed_interpreter=Path(sys.executable),
        package_manifest=_manifest(tmp_path / "m.json"),
        instrument_only=True,
        original_local=_original_local(),
    )
    receipt_out = prepare.prepare(binding)
    assert receipt_out["apply_enabled"] is False
    expected = json.loads((profile / "expected.json").read_text(encoding="utf-8"))
    assert expected["fixture_generator_version"] == prepare.FIXTURE_GENERATOR_VERSION
    assert expected["library_store_root_is_product_default"] is True
    versioned = profile / "expected.v2-default-library-store.json"
    assert versioned.is_file()
    archived = profile / "preview-seed-v1-nondefault-store-archived.json"
    assert archived.is_file()
    archive_body = json.loads(archived.read_text(encoding="utf-8"))
    assert archive_body["store_root"] == "prompt-store"
    store = Path(expected["library_store_root"])
    assert store == profile / "library"
    assert (store / "taxonomies").is_dir()
    assert list((store / "taxonomies").glob("*.json"))
    assert not (profile / "prompt-store" / "taxonomies").exists()
    preview = expected.get("preview") or {}
    assert preview.get("store_root_is_product_default") is True
    diagnosis = preview.get("diagnosis") or {}
    assert diagnosis.get("used_nondefault_store") is False
    assert diagnosis.get("stored_preview_unmodified") is True
    recheck = diagnosis.get("pure_reader_recheck") or {}
    assert recheck.get("ok") is True
    assert preview.get("can_apply") is False
