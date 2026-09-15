"""Strict regressions for the Phase 4 final instrument repair.

Does not edit the two frozen kit test files. Does not launch Inno, the
default helper, a model, Claude, or port 5179. Positive and negative
oracles measure the actual repaired behavior.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / "scripts" / "install_receipt"
sys.path.insert(0, str(KIT))

import p4_collect_evidence as collect
import p4_common as common
import p4_inspect_evidence as inspect
import p4_session as session
import p4_stdio_check as stdio_check


def _manifest(path: Path, body=None) -> Path:
    path.write_text(json.dumps(body or {
        "status": "unsealed",
        "package_sha256": None,
        "note": "Astra seals the final package hash after build",
    }) + "\n", encoding="utf-8")
    return path


def _original_local() -> Path:
    return Path(os.environ.get("P4_ORIGINAL_LOCALAPPDATA") or os.environ["LOCALAPPDATA"])


def test_installer_source_sha_is_40_hex_git_commit_not_sha256(tmp_path: Path):
    fake64 = _manifest(tmp_path / "m64.json", {
        "status": "claimed",
        "package_sha256": "a" * 64,
        "installer_source_sha": "b" * 64,
    })
    loaded64 = common.load_package_manifest(fake64)
    assert loaded64["declared_hash_is_hex64"] is True
    assert loaded64["installer_source_is_git_sha40"] is False
    assert loaded64["installer_source_sha"] is None
    assert loaded64["fabricated_64char_source_commit_rejected"] is True
    assert loaded64["invented_hash"] is False

    git40 = _manifest(tmp_path / "m40.json", {
        "status": "unsealed",
        "package_sha256": None,
        "installer_source_sha": "e86bc169952dca895854dae7c409ccd0487cfbf5",
    })
    loaded40 = common.load_package_manifest(git40)
    assert loaded40["installer_source_is_git_sha40"] is True
    assert loaded40["installer_source_sha"] == "e86bc169952dca895854dae7c409ccd0487cfbf5"
    assert loaded40["declared_package_sha256"] is None
    assert loaded40["invented_hash"] is False


def test_sealed_file_digest_mismatch_and_missing_binding_are_refusals(tmp_path: Path):
    app = tmp_path / "app"
    app.mkdir()
    (app / "uoink_mcp.py").write_text("print('mcp')\n", encoding="utf-8")
    (app / "server.py").write_text("print('server')\n", encoding="utf-8")
    (app / "index.py").write_text("print('index')\n", encoding="utf-8")
    bindings = [
        {
            "staged_path": "uoink_mcp.py",
            "source_path": "uoink_mcp.py",
            "source_git_blob": "a" * 40,
            "checkout_and_staged_sha256": "0" * 64,
        },
        {
            "staged_path": "server.py",
            "source_path": "server.py",
            "source_git_blob": "b" * 40,
            "checkout_and_staged_sha256": common.sha_file(app / "server.py"),
        },
    ]
    compared = common.compare_installed_to_sealed(app, bindings)
    assert compared["ok"] is False
    assert "uoink_mcp.py" in compared["mismatched_files"]
    assert "index.py" in compared["missing_or_unverified_bindings"]
    assert "server.py" not in compared["mismatched_files"]

    same = common.make_same_purpose_manifest_from_bytes(
        app, installer_source_sha="e86bc169952dca895854dae7c409ccd0487cfbf5")
    assert same["invented_hash"] is False
    assert same["package_sha256"] is None
    assert same["build_source"] == "e86bc169952dca895854dae7c409ccd0487cfbf5"
    mcp_row = next(r for r in same["files"] if r["staged_path"] == "uoink_mcp.py")
    assert mcp_row["checkout_and_staged_sha256"] == common.sha_file(app / "uoink_mcp.py")
    assert mcp_row["source_git_blob"] is None


def test_commented_import_site_is_not_active_and_preserves_crlf(tmp_path: Path):
    original = b"#import site\r\nLib\r\n."
    assert common.pth_active_import_site(original) is False
    written = common.append_active_import_site(original)
    assert written.startswith(original)
    assert common.pth_active_import_site(written) is True
    assert b"\r\nimport site\r\n" in written
    assert b"# p4-receipt-import-site\r\n" in written
    active = b"import site\nLib\n"
    assert common.pth_active_import_site(active) is True


def test_guard_restore_keeps_modified_prefix_and_restores_exact_bytes(tmp_path: Path):
    dest = tmp_path / "sitecustomize.py"
    payload = b"# P4 receipt guard\nowned-bytes\n"
    dest.write_bytes(payload)
    record = {
        "mutations": [{
            "action": "created",
            "path": str(dest),
            "sha256": common.sha_bytes(payload),
            "payload_b64": __import__("base64").b64encode(payload).decode("ascii"),
        }]
    }
    dest.write_bytes(payload + b"MUTATED\n")
    assert dest.read_bytes().startswith(b"# P4 receipt guard")
    out = common.restore_guard(record)
    assert dest.is_file()
    assert dest.read_bytes() == payload + b"MUTATED\n"
    assert any(row["action"] == "left_modified" for row in out["restored"])

    pth = tmp_path / "python311._pth"
    original = b"#import site\r\nLib\r\n"
    written = common.append_active_import_site(original)
    pth.write_bytes(written)
    pth_record = {
        "mutations": [{
            "action": "pth_appended",
            "path": str(pth),
            "original_b64": __import__("base64").b64encode(original).decode("ascii"),
            "written_b64": __import__("base64").b64encode(written).decode("ascii"),
        }]
    }
    restored = common.restore_guard(pth_record)
    assert pth.read_bytes() == original
    assert any(row.get("exact_original_bytes") for row in restored["restored"])


def test_ig_forbidden_live_preserved_under_redirected_localappdata(tmp_path: Path):
    receipt = tmp_path / "r"
    profile = receipt / "p"
    receipt.mkdir()
    live = r"C:\Users\hello\AppData\Local\Uoink\index.db"
    previous = os.environ.get("IG_FORBIDDEN_LIVE")
    os.environ["IG_FORBIDDEN_LIVE"] = live
    try:
        binding = common.validate_isolation(
            isolated_profile=profile,
            isolated_port=18091,
            receipt_root=receipt,
            installed_app=ROOT,
            installed_interpreter=Path(sys.executable),
            package_manifest=_manifest(tmp_path / "m.json"),
            instrument_only=True,
            original_local=_original_local(),
        )
        env = common.isolation_env(binding)
        assert env["IG_FORBIDDEN_LIVE"] == live
        assert env["P4_FORBIDDEN_INDEX"] == binding["live_index_forbidden"]
        assert env["IG_FORBIDDEN_LIVE"] != env.get("LOCALAPPDATA")
    finally:
        if previous is None:
            os.environ.pop("IG_FORBIDDEN_LIVE", None)
        else:
            os.environ["IG_FORBIDDEN_LIVE"] = previous


def test_canary_refuses_disposable_index_and_does_not_open_live(tmp_path: Path):
    receipt = tmp_path / "r"
    profile = receipt / "p"
    receipt.mkdir()
    profile.mkdir()
    common.ensure_profile_dirs(profile)
    binding = {"isolated_profile": str(profile)}
    common.write_guard(profile, binding)
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    env["P4_ISOLATED_PROFILE"] = str(profile)
    env["PYTHONPATH"] = str(profile / "guard")
    live = env.get("IG_FORBIDDEN_LIVE") or str(_original_local() / "Uoink" / "index.db")
    env["IG_FORBIDDEN_LIVE"] = live
    canary = common.prove_guard_canary(
        interpreter=Path(sys.executable), env=env, profile=profile, cwd=profile,
    )
    assert canary["refused"] is True
    assert canary["live_index_opened"] is False
    assert canary["live_index_hashed"] is False
    assert canary["ig_forbidden_live"] == live
    assert os.path.normcase(canary["canary_path"]) != os.path.normcase(live)


def test_bounded_stdin_write_when_child_does_not_read(tmp_path: Path):
    child = tmp_path / "noread.py"
    child.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    owned = session.spawn_owned(
        [sys.executable, "-B", str(child)], cwd=tmp_path, env=env, label="noread",
    )
    stdio = session.BoundedStdio(owned, default_timeout_s=1.0, retain_dir=tmp_path / "traffic-noread")
    t0 = time.perf_counter()
    parsed, elapsed_ms, raw, error = stdio.rpc(1, "initialize", timeout_s=1.0)
    waited = time.perf_counter() - t0
    cleanup = stdio.close(timeout=3.0)
    assert parsed is None
    assert error in ("timeout", "stdin_write_timeout")
    assert waited < 5.0
    assert elapsed_ms < 5000
    assert cleanup["cleaned"] is True


def test_partial_line_stdout_is_retained_in_file(tmp_path: Path):
    child = tmp_path / "partial.py"
    child.write_text(
        "import sys, time\n"
        "sys.stdout.buffer.write(b'{\"jsonrpc\":\"2.0\",\"id\":1,\"result\":{')\n"
        "sys.stdout.buffer.flush()\n"
        "time.sleep(20)\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    retain = tmp_path / "traffic-partial"
    owned = session.spawn_owned(
        [sys.executable, "-B", str(child)], cwd=tmp_path, env=env, label="partial",
    )
    stdio = session.BoundedStdio(owned, default_timeout_s=1.0, retain_dir=retain)
    parsed, elapsed_ms, raw, error = stdio.rpc(1, "initialize", timeout_s=1.0)
    cleanup = stdio.close(timeout=3.0)
    assert parsed is None
    assert error is not None
    partial = retain / "stdout.partial.bin"
    stdout = retain / "stdout.bin"
    retained = (partial.read_bytes() if partial.is_file() else b"") + (
        stdout.read_bytes() if stdout.is_file() else b"")
    assert b'"jsonrpc"' in retained
    assert b"\n" not in retained.split(b'"jsonrpc"', 1)[-1][:20] or b'"result":{' in retained
    assert stdio.partial_stdout or retained
    assert cleanup["cleaned"] is True


def test_noisy_stderr_is_retained_in_file_not_truncated(tmp_path: Path):
    child = tmp_path / "noisy.py"
    child.write_text(
        "import sys\n"
        "blob = b'X' * 200000\n"
        "for _ in range(10):\n"
        "    sys.stderr.buffer.write(blob)\n"
        "    sys.stderr.buffer.flush()\n"
        "sys.stdout.buffer.write(b'{\"jsonrpc\":\"2.0\",\"id\":1,\"result\":{}}\\n')\n"
        "sys.stdout.buffer.flush()\n"
        "for line in sys.stdin.buffer:\n"
        "    break\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    retain = tmp_path / "traffic-noisy"
    owned = session.spawn_owned(
        [sys.executable, "-B", str(child)], cwd=tmp_path, env=env, label="noisy",
    )
    stdio = session.BoundedStdio(owned, default_timeout_s=5.0, retain_dir=retain)
    parsed, elapsed_ms, raw, error = stdio.rpc(1, "initialize", timeout_s=5.0)
    cleanup = stdio.close(timeout=3.0)
    assert parsed is not None
    assert error is None
    stderr_file = retain / "stderr.bin"
    assert stderr_file.is_file()
    assert stderr_file.stat().st_size == 2_000_000
    assert len(stdio.stderr_bytes()) == 2_000_000
    assert cleanup["cleaned"] is True


def test_grandchild_hang_job_cleanup_descendants_exit(tmp_path: Path):
    grand = tmp_path / "grand.py"
    grand.write_text("import time\ntime.sleep(60)\n", encoding="utf-8")
    parent = tmp_path / "parent.py"
    parent.write_text(
        "import subprocess, sys, time\n"
        "from pathlib import Path\n"
        "child = Path(__file__).with_name('grand.py')\n"
        "proc = subprocess.Popen([sys.executable, '-B', str(child)])\n"
        "Path('grandchild.pid').write_text(str(proc.pid), encoding='utf-8')\n"
        "time.sleep(60)\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    owned = session.spawn_owned(
        [sys.executable, "-B", str(parent)], cwd=tmp_path, env=env, label="parent",
    )
    deadline = time.monotonic() + 5
    pid_file = tmp_path / "grandchild.pid"
    while time.monotonic() < deadline and not pid_file.is_file():
        time.sleep(0.05)
    assert pid_file.is_file(), "grandchild pid file was not written"
    grandchild_pid = int(pid_file.read_text(encoding="utf-8").strip())
    owned._owned_pids.add(grandchild_pid)
    snap = owned.descendant_snapshot()
    assert owned._job_assigned is True
    cleanup = owned.terminate_tree(timeout=5.0)
    assert cleanup["cleaned"] is True
    assert cleanup["parent_exited"] is True
    assert cleanup["descendants_exited"] is True
    assert not session.pid_still_active(grandchild_pid, owned_pids=set(owned._owned_pids))
    assert snap["job_assigned"] is True


def test_job_assignment_to_closed_handle_fails_closed(tmp_path: Path):
    job = session.create_kill_job()
    assert job is not None
    session._kernel32().CloseHandle(job)
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    popen = __import__("subprocess").Popen(
        [sys.executable, "-B", "-c", "import time; time.sleep(5)"],
        cwd=str(tmp_path), env=env,
        stdin=__import__("subprocess").PIPE,
        stdout=__import__("subprocess").PIPE,
        stderr=__import__("subprocess").PIPE,
    )
    try:
        assigned = session.assign_popen_to_job(job, popen)
        assert assigned is False
    finally:
        popen.kill()
        popen.wait(timeout=3)
    live = session.spawn_owned(
        [sys.executable, "-B", "-c", "import time; time.sleep(1)"],
        cwd=tmp_path, env=env, label="assign-ok",
    )
    try:
        assert live._job_assigned is True
        assert live.descendant_snapshot()["job_assigned"] is True
    finally:
        cleanup = live.terminate_tree(timeout=3.0)
        assert cleanup["cleaned"] is True


def test_inspector_requires_all_declared_pairs_not_a_nonempty_subset(tmp_path: Path):
    expected = {
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
        },
        "brief": {"uri": "uoink://brief/a", "text": "BRIEF"},
    }

    def frame(direction, message, tick):
        raw = (json.dumps(message) + "\n").encode()
        import base64, hashlib
        return {
            "kind": "frame", "direction": direction, "received_ns": tick,
            "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
            "base64": base64.b64encode(raw).decode(), "route_label": "original-installed",
        }

    rows = [{"kind": "launch", "route_label": "original-installed", "received_ns": 1}]
    uri = expected["items"]["p4fx-timed-01"]["card_uri"]
    text = expected["items"]["p4fx-timed-01"]["card_text"]
    rows.extend([
        frame("client_to_server", {"jsonrpc": "2.0", "id": 1, "method": "resources/read",
                                   "params": {"uri": uri}}, 1000),
        frame("server_to_client", {"jsonrpc": "2.0", "id": 1, "result": {
            "contents": [{"uri": uri, "text": text, "mimeType": "text/plain"}]}}, 1500),
    ])
    path = tmp_path / "events.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    report = inspect.inspect(expected, [path], required_route="original-installed")
    assert report["declared_pairs_equal"] is False
    assert report["packet_and_prompt_subset_complete"] is False
    statuses = { (c["item_id"], c["kind"], c["route"]): c["status"]
                 for c in report["exact_packet_comparisons"] }
    assert statuses[("p4fx-timed-01", "card", "resource")] == "equal"
    assert statuses[("p4fx-text-01", "card", "resource")] == "missing"
    assert statuses[("p4fx-timed-01", "excerpt", "tool")] == "missing"


def test_synthetic_records_cannot_fill_original_route_gaps(tmp_path: Path):
    expected = {
        "items": {
            "p4fx-timed-01": {
                "card_uri": "uoink://card/t", "card_text": "T-CARD",
                "excerpt_uri": "uoink://excerpt/t", "excerpt_text": "T-EX",
                "corpus_uri": "uoink://corpus/t", "corpus_text": "T-CO",
            }
        },
        "brief": {"uri": "uoink://brief/a", "text": "BRIEF"},
    }

    def frame(direction, message, tick, label):
        raw = (json.dumps(message) + "\n").encode()
        import base64, hashlib
        return {
            "kind": "frame", "direction": direction, "received_ns": tick,
            "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
            "base64": base64.b64encode(raw).decode(), "route_label": label,
        }

    def packet_rows(label, start):
        rows = [{"kind": "launch", "route_label": label, "received_ns": start}]
        i = start
        for item in expected["items"].values():
            for kind in ("card", "excerpt", "corpus"):
                uri, text = item[kind + "_uri"], item[kind + "_text"]
                i += 1
                rows.append(frame("client_to_server", {
                    "jsonrpc": "2.0", "id": i, "method": "resources/read", "params": {"uri": uri},
                }, i * 1000, label))
                rows.append(frame("server_to_client", {
                    "jsonrpc": "2.0", "id": i, "result": {
                        "contents": [{"uri": uri, "text": text, "mimeType": "text/plain"}]},
                }, i * 1000 + 500, label))
                i += 1
                env = {"ok": True, "contents": [{"uri": uri, "text": text, "mimeType": "text/plain"}]}
                rows.append(frame("client_to_server", {
                    "jsonrpc": "2.0", "id": i, "method": "tools/call",
                    "params": {"name": "read_library_resource", "arguments": {"uri": uri}},
                }, i * 1000, label))
                rows.append(frame("server_to_client", {
                    "jsonrpc": "2.0", "id": i, "result": {
                        "isError": False,
                        "content": [{"type": "text", "text": inspect.PREFIX + json.dumps(env) + inspect.SUFFIX}],
                    },
                }, i * 1000 + 500, label))
        uri, text = expected["brief"]["uri"], expected["brief"]["text"]
        i += 1
        rows.append(frame("client_to_server", {
            "jsonrpc": "2.0", "id": i, "method": "resources/read", "params": {"uri": uri},
        }, i * 1000, label))
        rows.append(frame("server_to_client", {
            "jsonrpc": "2.0", "id": i, "result": {
                "contents": [{"uri": uri, "text": text, "mimeType": "text/plain"}]},
        }, i * 1000 + 500, label))
        i += 1
        env = {"ok": True, "contents": [{"uri": uri, "text": text, "mimeType": "text/plain"}]}
        rows.append(frame("client_to_server", {
            "jsonrpc": "2.0", "id": i, "method": "tools/call",
            "params": {"name": "read_library_resource", "arguments": {"uri": uri}},
        }, i * 1000, label))
        rows.append(frame("server_to_client", {
            "jsonrpc": "2.0", "id": i, "result": {
                "isError": False,
                "content": [{"type": "text", "text": inspect.PREFIX + json.dumps(env) + inspect.SUFFIX}],
            },
        }, i * 1000 + 500, label))
        for name in ("consult-library", "reshelve-review"):
            i += 1
            rows.append(frame("client_to_server", {
                "jsonrpc": "2.0", "id": i, "method": "prompts/get", "params": {"name": name},
            }, i * 1000, label))
            rows.append(frame("server_to_client", {
                "jsonrpc": "2.0", "id": i, "result": {
                    "messages": [{"role": "user", "content": {"type": "text", "text": "prompt"}}]},
            }, i * 1000 + 500, label))
        return rows

    attached = tmp_path / "attached.jsonl"
    attached.write_text("\n".join(json.dumps(r) for r in packet_rows("fixture-attached", 10)) + "\n",
                        encoding="utf-8")
    original = tmp_path / "original.jsonl"
    original.write_text(json.dumps({"kind": "launch", "route_label": "original-installed"}) + "\n",
                        encoding="utf-8")
    filled = inspect.inspect(expected, [attached, original], required_route="original-installed")
    assert filled["packet_and_prompt_subset_complete"] is False
    assert filled["consult_library_ok"] is False
    assert any(c["status"] == "missing" for c in filled["exact_packet_comparisons"])


def test_held_index_replacement_is_preserved_and_original_restored(tmp_path: Path):
    index_path = tmp_path / "index.db"
    held = tmp_path / "index.db.held-unavail"
    keep = tmp_path / "index.db.replacement-unavail"
    held.write_bytes(b"ORIGINAL-HELD")
    index_path.write_bytes(b"REPLACEMENT")
    result = stdio_check.restore_held_index(index_path, held, keep)
    assert result["restored"] is True
    assert index_path.read_bytes() == b"ORIGINAL-HELD"
    assert keep.read_bytes() == b"REPLACEMENT"
    assert not held.exists()
    none = tmp_path / "none.db"
    held2 = tmp_path / "held2"
    keep2 = tmp_path / "keep2"
    held2.write_bytes(b"ONLY-HELD")
    result2 = stdio_check.restore_held_index(none, held2, keep2)
    assert result2["restored"] is True
    assert none.read_bytes() == b"ONLY-HELD"
    assert not keep2.exists()


def test_recall_refuses_missing_installed_script(tmp_path: Path):
    profile = tmp_path / "p"
    profile.mkdir()
    app = tmp_path / "app"
    app.mkdir()
    result = __import__("p4_execute_checks", fromlist=["*"]).recall_silent_unavailable(
        profile, app, Path(sys.executable),
    )
    assert result["status"] == "failed"
    assert result["refused_missing_input"] is True
    assert "recall_hook.py" in result["script"]


def test_operator_boolean_is_not_a_retrieve_pass_without_protocol_bytes(tmp_path: Path):
    receipt = tmp_path / "r"
    profile = receipt / "p"
    receipt.mkdir()
    profile.mkdir()
    (profile / "records").mkdir()
    (profile / "client").mkdir()
    (profile / "client" / "protected-sentinel.bin").write_bytes(common.PROTECTED_SENTINEL_BYTES)
    expected = {
        "items": {
            "p4fx-timed-01": {"card_text": "C", "excerpt_text": "E", "corpus_text": "O",
                              "timing": "timed_clip"},
            "p4fx-text-01": {"card_text": "T", "excerpt_text": "E", "corpus_text": "C",
                             "timing": "not_timed"},
            "p4fx-hostile-01": {"card_text": "H", "excerpt_text": "H", "corpus_text": "H"},
        },
        "brief": {"uri": "uoink://brief/x", "text": "BLUE", "citation_quote": "BLUE"},
        "chapter": {"title": "SYNTHETIC FIXTURE CHAPTER: Why computer use (not a source quotation)",
                    "start": 34.0},
        "protected_sentinel": {"path": str(profile / "client" / "protected-sentinel.bin")},
    }
    (profile / "expected.json").write_text(json.dumps(expected) + "\n", encoding="utf-8")
    (profile / "preparation.json").write_text(json.dumps({
        "product_findings": [],
        "package_manifest": {"package_hash_status": "unsealed_astra_owns_final_hash"},
    }) + "\n", encoding="utf-8")
    binding = {
        "isolated_profile": str(profile),
        "isolated_port": 18081,
        "instrument_only": True,
        "installed_credit": False,
    }
    result = collect.collect(binding, {
        "packets": {
            "p4fx-timed-01": {"passed": True},
        },
        "reconnect": {"old_child_pid": 1, "new_child_pid": 2},
    })
    names = {c["name"]: c for c in result["checkpoints"]}
    assert names["retrieve_timed"]["status"] == "unobserved"
    assert names["reconnect"]["status"] == "unobserved"
    assert result["operator_sequence"]["apply_enabled"] is False
    assert result["operator_sequence"]["speaker_claim"] is False
