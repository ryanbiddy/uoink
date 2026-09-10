"""Synthetic instrument tests for the Phase 4 installed receipt kit.

These checks do not launch Inno, the default helper, a model, or a live
client. Runs that point --installed-app at this checkout are labeled
instrument-only and are not installed credit.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / "scripts" / "install_receipt"
sys.path.insert(0, str(KIT))

import p4_collect_evidence as collect
import p4_common as common
import p4_inspect_evidence as inspect
import p4_observe_actions as observe
import p4_prepare_client as client_cfg
import p4_prepare_fixture as prepare
import p4_stdio_check as stdio_check


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _manifest(path: Path) -> Path:
    path.write_text(json.dumps({
        "status": "unsealed",
        "package_sha256": None,
        "note": "Astra seals the final package hash after build",
    }) + "\n", encoding="utf-8")
    return path


def _binding(tmp: Path, *, port=18081, instrument=True):
    receipt = tmp / "r"
    profile = receipt / "p"
    receipt.mkdir()
    fake_app = tmp / "app"
    fake_app.mkdir()
    (fake_app / "uoink_mcp.py").write_text("# synthetic installed entry\n", encoding="utf-8")
    interpreter = Path(sys.executable)
    manifest = _manifest(tmp / "m.json")
    return common.validate_isolation(
        isolated_profile=profile,
        isolated_port=port,
        receipt_root=receipt,
        installed_app=fake_app if not instrument else ROOT,
        installed_interpreter=interpreter,
        package_manifest=manifest,
        forbid_checkout=None,
        instrument_only=instrument,
        original_local=Path(os.environ.get("P4_ORIGINAL_LOCALAPPDATA") or os.environ["LOCALAPPDATA"]),
    )


def test_isolation_refuses_port_5179_and_relative_profile(tmp_path: Path):
    receipt = tmp_path / "r"
    receipt.mkdir()
    manifest = _manifest(tmp_path / "m.json")
    app = tmp_path / "app"
    app.mkdir()
    (app / "uoink_mcp.py").write_text("pass\n", encoding="utf-8")
    with pytest.raises(common.IsolationError, match="5179"):
        common.validate_isolation(
            isolated_profile=receipt / "p",
            isolated_port=5179,
            receipt_root=receipt,
            installed_app=app,
            installed_interpreter=Path(sys.executable),
            package_manifest=manifest,
            instrument_only=True,
            original_local=Path(os.environ["LOCALAPPDATA"]),
        )
    with pytest.raises(common.IsolationError, match="absolute"):
        common.validate_isolation(
            isolated_profile=Path("relative-profile"),
            isolated_port=18081,
            receipt_root=receipt,
            installed_app=app,
            installed_interpreter=Path(sys.executable),
            package_manifest=manifest,
            instrument_only=True,
            original_local=Path(os.environ["LOCALAPPDATA"]),
        )


def test_isolation_refuses_live_uoink_root_and_missing_entry(tmp_path: Path):
    original = Path(os.environ.get("P4_ORIGINAL_LOCALAPPDATA") or os.environ["LOCALAPPDATA"])
    live = original / "Uoink"
    receipt = tmp_path / "r"
    receipt.mkdir()
    manifest = _manifest(tmp_path / "m.json")
    app = tmp_path / "app"
    app.mkdir()
    with pytest.raises(common.IsolationError, match="uoink_mcp.py"):
        common.validate_isolation(
            isolated_profile=receipt / "p",
            isolated_port=18081,
            receipt_root=receipt,
            installed_app=app,
            installed_interpreter=Path(sys.executable),
            package_manifest=manifest,
            instrument_only=True,
            original_local=original,
        )
    (app / "uoink_mcp.py").write_text("pass\n", encoding="utf-8")
    with pytest.raises(common.IsolationError, match="live Uoink"):
        common.validate_isolation(
            isolated_profile=live,
            isolated_port=18081,
            receipt_root=live.parent,
            installed_app=app,
            installed_interpreter=Path(sys.executable),
            package_manifest=manifest,
            instrument_only=True,
            original_local=original,
        )


def test_package_manifest_does_not_invent_hash(tmp_path: Path):
    path = _manifest(tmp_path / "m.json")
    loaded = common.load_package_manifest(path)
    assert loaded["invented_hash"] is False
    assert loaded["package_hash_status"] == "unsealed_astra_owns_final_hash"
    assert loaded["declared_package_sha256"] is None


def test_stdio_tap_lossless_and_refuses_unsafe_profile(tmp_path: Path):
    receipt = tmp_path / "r"
    profile = receipt / "p"
    receipt.mkdir()
    profile.mkdir()
    for name in ("tmp", "output", "records", "guard"):
        (profile / name).mkdir()
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    env.update(
        LOCALAPPDATA=str(profile), APPDATA=str(profile),
        TEMP=str(profile / "tmp"), TMP=str(profile / "tmp"),
        XDG_DATA_HOME=str(profile), UOINK_OUTPUT_DIR=str(profile / "output"),
        P4_ISOLATED_PROFILE=str(profile), P4_ISOLATED_PORT="18081",
        P4_FIXTURE_ROOT=str(profile), PYTHONDONTWRITEBYTECODE="1",
    )
    child = profile / "fake_child.py"
    child.write_text(
        "import json,sys\n"
        "for line in sys.stdin.buffer:\n"
        "    value=json.loads(line)\n"
        "    if value.get('method')=='die':\n"
        "        sys.stderr.buffer.write(b'fixture child exit\\n');sys.stderr.buffer.flush()\n"
        "        raise SystemExit(7)\n"
        "    answer={'jsonrpc':'2.0','id':value['id'],'result':value['params']}\n"
        "    sys.stdout.buffer.write((json.dumps(answer)+'\\n').encode())\n"
        "    sys.stdout.buffer.flush()\n"
        "sys.stderr.buffer.write(b'fixture diagnostic\\n');sys.stderr.buffer.flush()\n",
        encoding="utf-8",
    )
    tap = KIT / "p4_stdio_tap.py"
    command = [
        sys.executable, "-B", str(tap),
        "--isolated-profile", str(profile), "--isolated-port", "18081",
        "--fixture-root", str(profile),
        "--record-dir", str(profile / "records" / "case"),
        "--cwd", str(profile), "--route-label", "synthetic-instrument",
        "--", sys.executable, "-B", str(child),
    ]
    payloads = [{"text": "Unicode 🔑 café"}, {"empty": [], "null": None}]
    requests = [{"jsonrpc": "2.0", "id": i, "method": "echo", "params": p}
                for i, p in enumerate(payloads)]
    raw = b"".join((json.dumps(r) + "\n").encode() for r in requests)
    result = subprocess.run(command, input=raw, env=env, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr
    expected = b"".join((json.dumps({"jsonrpc": "2.0", "id": i, "result": p}) + "\n").encode()
                        for i, p in enumerate(payloads))
    assert result.stdout == expected
    first = next((profile / "records").glob("case-*")) / "events.jsonl"
    events = [json.loads(line) for line in first.read_text(encoding="utf-8").splitlines()]
    frames = [e for e in events if e["kind"] == "frame" and e["direction"] == "server_to_client"]
    joined = b"".join(base64.b64decode(e["base64"]) for e in frames)
    assert joined == expected
    dead = subprocess.run(command, input=b'{"jsonrpc":"2.0","id":99,"method":"die"}\n',
                          env=env, capture_output=True, timeout=15)
    assert dead.returncode == 7
    unsafe = dict(env, LOCALAPPDATA=str(profile.parent))
    refusal = subprocess.run(command, input=b"", env=unsafe, capture_output=True, timeout=15)
    assert refusal.returncode == 2
    assert b"LOCALAPPDATA must resolve inside" in refusal.stderr


def test_inspector_exact_packets_mismatch_and_missing_prompts(tmp_path: Path):
    expected = {
        "items": {
            "a": {
                "card_uri": "uoink://card/a",
                "card_text": "Full card: first and LAST boundary.",
                "excerpt_uri": "uoink://excerpt/a",
                "excerpt_text": "Complete quote at 34 seconds.",
                "corpus_uri": "uoink://corpus/a",
                "corpus_text": "SYNTHETIC FIXTURE corpus bytes.",
            }
        },
        "brief": {"uri": "uoink://brief/a", "text": "SYNTHETIC FIXTURE BRIEF: BLUE."},
    }

    def frame(direction, message, tick):
        raw = (json.dumps(message) + "\n").encode()
        return {
            "kind": "frame", "direction": direction, "received_ns": tick,
            "bytes": len(raw), "sha256": _sha(raw),
            "base64": base64.b64encode(raw).decode(),
        }

    rows = []
    i = 0

    def exchange(method, params, result):
        nonlocal i
        i += 1
        rows.extend([
            frame("client_to_server", {"jsonrpc": "2.0", "id": i, "method": method, "params": params}, i * 1000),
            frame("server_to_client", {"jsonrpc": "2.0", "id": i, "result": result}, i * 1000 + 500),
        ])

    for kind in ("card", "excerpt", "corpus"):
        uri = expected["items"]["a"][kind + "_uri"]
        text = expected["items"]["a"][kind + "_text"]
        exchange("resources/read", {"uri": uri},
                 {"contents": [{"uri": uri, "text": text, "mimeType": "text/plain"}]})
        env = {"ok": True, "contents": [{"uri": uri, "text": text, "mimeType": "text/plain"}]}
        exchange("tools/call", {"name": "read_library_resource", "arguments": {"uri": uri}},
                 {"isError": False, "content": [{"type": "text", "text": inspect.PREFIX + json.dumps(env) + inspect.SUFFIX}]})
    uri = expected["brief"]["uri"]
    text = expected["brief"]["text"]
    exchange("resources/read", {"uri": uri},
             {"contents": [{"uri": uri, "text": text, "mimeType": "text/plain"}]})
    env = {"ok": True, "contents": [{"uri": uri, "text": text, "mimeType": "text/plain"}]}
    exchange("tools/call", {"name": "read_library_resource", "arguments": {"uri": uri}},
             {"isError": False, "content": [{"type": "text", "text": inspect.PREFIX + json.dumps(env) + inspect.SUFFIX}]})
    for name in ("consult-library", "reshelve-review"):
        exchange("prompts/get", {"name": name},
                 {"messages": [{"role": "user", "content": {"type": "text", "text": "Actual prompt"}}]})
    path = tmp_path / "events.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    report = inspect.inspect(expected, [path])
    assert report["packet_and_prompt_subset_complete"]
    assert len(report["exact_packet_comparisons"]) == 8
    assert len(report["native_prompts"]) == 2

    message = json.loads(base64.b64decode(rows[1]["base64"]))
    message["result"]["contents"][0]["text"] = "Full card: first and CORRUPTED boundary."
    rows[1] = frame("server_to_client", message, 1500)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    bad = inspect.inspect(expected, [path])
    assert not bad["packet_and_prompt_subset_complete"]
    assert any(c["status"] == "mismatch" for c in bad["exact_packet_comparisons"])


def test_observer_hook_sentinel_and_silent_recall(tmp_path: Path):
    (tmp_path / "client").mkdir()
    env = os.environ.copy()
    env.update(P4_FIXTURE_ROOT=str(tmp_path), P4_ISOLATED_PROFILE=str(tmp_path),
               P4_ISOLATED_PORT="18081", P4_INSTALLED_APP=str(tmp_path))
    env.pop("ANTHROPIC_API_KEY", None)
    script = KIT / "p4_observe_actions.py"

    def run(mode, payload, extra=None):
        use = dict(env)
        if extra:
            use.update(extra)
        return subprocess.run(
            [sys.executable, "-B", str(script), mode,
             "--fixture-root", str(tmp_path),
             "--isolated-profile", str(tmp_path),
             "--isolated-port", "18081"],
            input=payload, env=use, text=True, capture_output=True, timeout=8,
        )

    allowed = run("hook", json.dumps({
        "hook_event_name": "PreToolUse", "tool_name": "mcp__uoink__get_library_item",
        "tool_input": {"marker": "full request input"},
    }))
    assert allowed.returncode == 0, allowed.stderr
    assert json.loads(allowed.stdout)["hookSpecificOutput"]["permissionDecision"] == "allow"
    denied = run("hook", json.dumps({
        "hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {},
    }))
    assert json.loads(denied.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"

    protected = tmp_path / "protected.bin"
    protected.write_bytes(b"UNTOUCHED SENTINEL")
    before = _sha(protected.read_bytes())
    messages = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "record_action", "arguments": {"action": "file", "marker": str(protected)}}},
    ]
    sent = run("sentinel", "\n".join(json.dumps(x) for x in messages) + "\n")
    assert sent.returncode == 0, sent.stderr
    replies = [json.loads(x) for x in sent.stdout.splitlines()]
    assert replies[2]["result"]["isError"] is True
    assert _sha(protected.read_bytes()) == before

    stage = tmp_path / "stage" / "scripts"
    stage.mkdir(parents=True)
    (stage / "recall_hook.py").write_text(
        "import sys\nsys.stdout.write('')\nraise SystemExit(0)\n", encoding="utf-8")
    recalled = run("recall", json.dumps({"prompt": "Please find saved computer vision research examples"}))
    assert recalled.returncode == 0, recalled.stderr
    assert recalled.stdout == ""
    events = [json.loads(p.read_text(encoding="utf-8")) for p in (tmp_path / "client" / "action-records").glob("*.json")]
    recall_events = [e for e in events if e["kind"] == "recall_hook"]
    assert recall_events[0]["exit_code"] == 0
    assert recall_events[0]["elapsed_ms"] < 2000
    assert not (tmp_path / "recall" / "index.db").exists()


def test_client_config_scope_and_refusals(tmp_path: Path):
    root = tmp_path / "path with spaces"
    observer = root / "client" / "observe_client_actions.py"
    interpreter = Path("C:/Program Files/Python/python.exe")
    original = {"mcpServers": {"uoink": {
        "type": "stdio", "command": str(interpreter),
        "args": ["original-entry"], "env": {"P4_FIXTURE_ROOT": str(root)},
    }}}
    before = json.loads(json.dumps(original))
    names = sorted(client_cfg.READS | {"apply_labels", "capture_remote", "write_memory"})
    mcp, settings, recall, allowed, denied = client_cfg.build(
        root, original, names, interpreter, observer, root, 18081)
    assert original == before
    assert "ListMcpResourcesTool" in allowed
    assert "mcp__uoink__search_library" in allowed
    assert "mcp__p4_sentinel__record_action" in allowed
    assert "mcp__uoink__apply_labels" in denied
    assert not set(allowed) & set(denied)
    assert "UserPromptSubmit" not in settings["hooks"]
    assert "UserPromptSubmit" in recall["hooks"]
    assert settings["autoMemoryEnabled"] is False
    with pytest.raises(common.IsolationError, match="only the explicit"):
        client_cfg.build(root, {"mcpServers": {"uoink": {}, "outside": {}}},
                         names, interpreter, observer, root, 18081)
    # Repair after t2: names[:-1] still contained every bounded read. Drop a
    # required read and separately duplicate a name.
    with pytest.raises(common.IsolationError, match="unique bounded reads"):
        client_cfg.build(root, original, [n for n in names if n != "search_library"],
                         interpreter, observer, root, 18081)
    with pytest.raises(common.IsolationError, match="unique bounded reads"):
        client_cfg.build(root, original, names + names[:1], interpreter, observer, root, 18081)


def test_collector_absent_screenshot_is_unobserved_not_passed(tmp_path: Path):
    receipt = tmp_path / "r"
    profile = receipt / "p"
    receipt.mkdir()
    profile.mkdir()
    (profile / "records").mkdir()
    expected = {
        "items": {
            "p4fx-timed-01": {"card_text": "CARD", "excerpt_text": "EX", "corpus_text": "CO",
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
    (profile / "client").mkdir()
    (profile / "client" / "protected-sentinel.bin").write_bytes(common.PROTECTED_SENTINEL_BYTES)
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
    result = collect.collect(binding, {})
    names = {c["name"]: c for c in result["checkpoints"]}
    assert names["retrieve_timed"]["status"] == "unobserved"
    assert names["retrieve_timed"]["screenshot"]["status"] == "unobserved"
    assert names["follow_citation"]["status"] == "unobserved"
    assert names["optional_player_jump"]["status"] == "unobserved"
    assert names["protected_bytes"]["status"] == "passed"
    assert result["absent_images_never_passed"] is True
    fetched = collect.collect(binding, {
        "follow_citation": {"url": common.BLOCKED_X_LINK["url"], "attempted": True, "fetched": True},
    })
    assert any(f["operation"] == "follow_citation_x" for f in fetched["product_findings"])
    blocked = collect.collect(binding, {
        "follow_citation": {"url": common.BLOCKED_X_LINK["url"], "attempted": True, "fetched": False},
    })
    follow = next(c for c in blocked["checkpoints"] if c["name"] == "follow_citation")
    assert follow["status"] == "blocked"


def test_prepare_fixture_seeds_synthetic_items_and_keeps_apply_false(tmp_path: Path):
    receipt = tmp_path / "r"
    profile = receipt / "p"
    receipt.mkdir()
    manifest = _manifest(tmp_path / "m.json")
    binding = common.validate_isolation(
        isolated_profile=profile,
        isolated_port=18082,
        receipt_root=receipt,
        installed_app=ROOT,
        installed_interpreter=Path(sys.executable),
        package_manifest=manifest,
        instrument_only=True,
        original_local=Path(os.environ.get("P4_ORIGINAL_LOCALAPPDATA") or os.environ["LOCALAPPDATA"]),
    )
    receipt_out = prepare.prepare(binding)
    assert receipt_out["apply_enabled"] is False
    assert receipt_out["isolation"]["installed_credit"] is False
    assert receipt_out["package_manifest"]["invented_hash"] is False
    expected = json.loads((profile / "expected.json").read_text(encoding="utf-8"))
    items = expected["items"]
    assert "SYNTHETIC FIXTURE" in items["p4fx-timed-01"]["full_stored_excerpt"]
    assert items["p4fx-text-01"]["evidence_kind"] == "text_only"
    assert items["p4fx-text-01"]["timing"] in (None, "not_timed")
    assert "the stored value is BLUE" in items["p4fx-hostile-01"]["full_stored_excerpt"]
    assert expected["blocked_x_link"]["no_new_fetch"] is True
    assert expected["optional_player_jump"]["video_id"] == "D_FCYsshMI4"
    assert expected["optional_player_jump"]["not_a_library_quotation"] is True
    assert expected["apply_enabled"] is False
    mcp = json.loads((profile / "mcp.json").read_text(encoding="utf-8"))
    attached = json.loads((profile / "mcp-attached.json").read_text(encoding="utf-8"))
    original_args = mcp["mcpServers"]["uoink"]["args"]
    attached_args = attached["mcpServers"]["uoink"]["args"]
    assert "--isolated-profile" in original_args
    assert "--isolated-port" in original_args
    assert "original-installed" in original_args
    assert attached["p4_route_label"] == "fixture-attached"
    assert attached["not_a_silent_substitute_for_original_installed_route"] is True
    assert any(Path(v).name == "uoink_mcp.py" for v in original_args)
    assert any(Path(v).name == "attached_entry.py" for v in attached_args)
    settings = json.loads((profile / "settings.json").read_text(encoding="utf-8"))
    assert settings["librarian_apply_enabled"] is False
    sentinel = (profile / "client" / "protected-sentinel.bin").read_bytes()
    assert sentinel == common.PROTECTED_SENTINEL_BYTES
    if expected.get("brief"):
        assert "SYNTHETIC FIXTURE" in (expected["brief"].get("text") or "")
        assert expected["brief"]["client_authored"] is False
    if expected.get("preview"):
        assert expected["preview"]["can_apply"] is False
    with pytest.raises(common.IsolationError, match="already prepared"):
        prepare.prepare(binding)


def test_stdio_synthetic_inventory_packets_reconnect_and_bounds(tmp_path: Path):
    receipt = tmp_path / "r"
    profile = receipt / "p"
    receipt.mkdir()
    manifest = _manifest(tmp_path / "m.json")
    binding = common.validate_isolation(
        isolated_profile=profile,
        isolated_port=18083,
        receipt_root=receipt,
        installed_app=ROOT,
        installed_interpreter=Path(sys.executable),
        package_manifest=manifest,
        instrument_only=True,
        original_local=Path(os.environ.get("P4_ORIGINAL_LOCALAPPDATA") or os.environ["LOCALAPPDATA"]),
    )
    prepare.prepare(binding)
    env = common.isolation_env(binding, extra={"route_label": "synthetic-instrument"})
    expected = json.loads((profile / "expected.json").read_text(encoding="utf-8"))
    result = stdio_check.run_synthetic(binding, profile, env, expected)
    assert result["route_label"] == "synthetic-instrument"
    assert result["installed_credit"] is False
    assert result["observed_inventory"]["tools"] == list(common.EXPECTED_STDIO_TOOLS)
    assert result["observed_inventory"]["templates"] == list(common.EXPECTED_TEMPLATE_NAMES)
    assert result["observed_inventory"]["prompts"] == list(common.EXPECTED_PROMPTS)
    assert result["reconnect"]["distinct"] is True
    assert result["unavailable_storage"]["within_bound"] is True
    assert result["transport_failure"]["within_bound"] is True
    assert result["inspection"]["packet_and_prompt_subset_complete"] is True
    assert not result["inspection"]["missing_required_native_prompts"]


def test_original_route_failure_is_product_finding_not_hidden(tmp_path: Path):
    receipt = tmp_path / "r"
    profile = receipt / "p"
    receipt.mkdir()
    profile.mkdir()
    common.ensure_profile_dirs(profile)
    (profile / "kit").mkdir()
    for name in ("p4_common.py", "p4_stdio_tap.py"):
        (profile / "kit" / name).write_bytes((KIT / name).read_bytes())
    (profile / "expected.json").write_text("{}\n", encoding="utf-8")
    app = tmp_path / "broken-install"
    app.mkdir()
    (app / "uoink_mcp.py").write_text(
        "import sys\nprint('no isolation', file=sys.stderr)\nraise SystemExit(3)\n",
        encoding="utf-8",
    )
    manifest = _manifest(tmp_path / "m.json")
    binding = common.validate_isolation(
        isolated_profile=profile,
        isolated_port=18084,
        receipt_root=receipt,
        installed_app=app,
        installed_interpreter=Path(sys.executable),
        package_manifest=manifest,
        instrument_only=True,
        original_local=Path(os.environ.get("P4_ORIGINAL_LOCALAPPDATA") or os.environ["LOCALAPPDATA"]),
    )
    env = common.isolation_env(binding, extra={"route_label": "original-installed"})
    result = stdio_check.run_installed(binding, profile, env, "original-installed")
    assert result["route_label"] == "original-installed"
    assert result["product_findings"]
    finding = result["product_findings"][0]
    assert finding["hidden_by_special_route"] is False
    assert finding["route"] == "original-installed"
    assert "--isolated-profile" in finding["input"]["command"] or "isolation_flags" in finding["input"]
