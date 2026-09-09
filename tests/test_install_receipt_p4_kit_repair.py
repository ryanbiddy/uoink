"""Process/contract regressions for the Phase 4 kit repair.

Does not edit tests/test_install_receipt_p4_kit.py. Does not launch Inno,
the default helper, a model, Claude, or port 5179.
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
import p4_prepare_fixture as prepare
import p4_provision_isolation as provision
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


def test_hex64_string_is_not_sealed_without_package_bytes(tmp_path: Path):
    path = _manifest(tmp_path / "m.json", {
        "status": "claimed",
        "package_sha256": "a" * 64,
        "installer_source_sha": "b" * 64,
    })
    loaded = common.load_package_manifest(path)
    assert loaded["declared_hash_is_hex64"] is True
    assert loaded["package_hash_status"] == "unsealed_astra_owns_final_hash"
    assert loaded["hex64_alone_is_not_sealed"] is True
    assert loaded["package_bytes"] is None


def test_installed_mode_fails_closed_without_package_bytes(tmp_path: Path):
    receipt = tmp_path / "r"
    receipt.mkdir()
    app = tmp_path / "app"
    app.mkdir()
    (app / "uoink_mcp.py").write_text("pass\n", encoding="utf-8")
    (app / "server.py").write_text("pass\n", encoding="utf-8")
    manifest = _manifest(tmp_path / "m.json", {
        "package_sha256": "a" * 64,
        "installer_source_sha": "b" * 64,
    })
    with pytest.raises(common.IsolationError, match="package-path"):
        common.validate_isolation(
            isolated_profile=receipt / "p",
            isolated_port=18081,
            receipt_root=receipt,
            installed_app=app,
            installed_interpreter=Path(sys.executable),
            package_manifest=manifest,
            forbid_checkout=tmp_path / "not-the-app",
            runtime_mode="installed",
            original_local=_original_local(),
        )


def test_not_instrument_only_is_not_installed_credit(tmp_path: Path):
    receipt = tmp_path / "r"
    receipt.mkdir()
    app = tmp_path / "app"
    app.mkdir()
    (app / "uoink_mcp.py").write_text("pass\n", encoding="utf-8")
    manifest = _manifest(tmp_path / "m.json")
    binding = common.validate_isolation(
        isolated_profile=receipt / "p",
        isolated_port=18081,
        receipt_root=receipt,
        installed_app=app,
        installed_interpreter=Path(sys.executable),
        package_manifest=manifest,
        instrument_only=False,
        runtime_mode="source-runtime",
        original_local=_original_local(),
    )
    assert binding["runtime_mode"] == "source-runtime"
    assert binding["installed_credit"] is False
    assert binding["installed_eligibility"]["inferred_from_not_instrument_only"] is False
    assert binding["installed_eligibility"]["eligible"] is False


def test_isolation_root_is_profile_index_not_uoink_subdir(tmp_path: Path):
    receipt = tmp_path / "r"
    profile = receipt / "p"
    receipt.mkdir()
    binding = common.validate_isolation(
        isolated_profile=profile,
        isolated_port=18082,
        receipt_root=receipt,
        installed_app=ROOT,
        installed_interpreter=Path(sys.executable),
        package_manifest=_manifest(tmp_path / "m.json"),
        instrument_only=True,
        original_local=_original_local(),
    )
    assert binding["index_path"] == str(profile / "index.db")
    assert binding["settings_path"] == str(profile / "settings.json")
    assert binding["token_path"] == str(profile / "token.txt")
    env = common.isolation_env(binding)
    assert env["UOINK_INDEX_PATH"] == str(profile / "index.db")
    assert "Uoink" not in Path(env["UOINK_INDEX_PATH"]).parts[-2:]
    assert env["UOINK_OUTPUT_DIR"] == str(profile / "output")
    captured = Path(binding["original_localappdata"])
    assert captured == _original_local()
    redirected = dict(os.environ, LOCALAPPDATA=str(profile))
    # Live capture must not follow the redirected LOCALAPPDATA after bind.
    assert Path(binding["original_localappdata"]) != profile


def test_c22_guard_conflict_is_refused(tmp_path: Path):
    receipt = tmp_path / "r"
    profile = receipt / "p"
    receipt.mkdir()
    profile.mkdir()
    common.ensure_profile_dirs(profile)
    dest = profile / "guard" / "sitecustomize.py"
    dest.write_text("# C22 receipt guard. do not clobber\n", encoding="utf-8")
    binding = {"isolated_profile": str(profile)}
    with pytest.raises(common.IsolationError, match="C22"):
        common.write_guard(profile, binding)


def test_bounded_rpc_hang_fails_closed_with_retained_traffic_and_cleanup(tmp_path: Path):
    child = tmp_path / "hang.py"
    child.write_text(
        "import sys, time\n"
        "for line in sys.stdin.buffer:\n"
        "    time.sleep(30)\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    owned = session.spawn_owned(
        [sys.executable, "-B", str(child)], cwd=tmp_path, env=env, label="hang",
    )
    stdio = session.BoundedStdio(owned, default_timeout_s=1.0)
    t0 = time.perf_counter()
    parsed, elapsed_ms, raw, error = stdio.rpc(1, "initialize", timeout_s=1.0)
    waited = time.perf_counter() - t0
    cleanup = stdio.close(timeout=3.0)
    assert parsed is None
    assert error == "timeout"
    assert waited < 5.0
    assert elapsed_ms < 5000
    assert stdio.retained
    assert cleanup["cleaned"] is True
    assert owned.popen.poll() is not None


def test_collector_operator_boolean_reconnect_is_not_a_pass(tmp_path: Path):
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
        "reconnect": {"old_child_pid": 1, "new_child_pid": 2},
        "mirror": {"disconnected": True, "reconnected": True,
                   "user_edit": {"bytes_unchanged": True},
                   "deletion": {"accounted": {"owned": 0, "temp": 0, "pending": 0, "conflict": 0}}},
        "recall": {"stdout": "", "exit_code": 0, "elapsed_ms": 10},
    })
    names = {c["name"]: c for c in result["checkpoints"]}
    assert names["reconnect"]["status"] == "unobserved"
    assert names["mirror_disconnect_reconnect"]["status"] == "unobserved"
    assert names["user_edit_preservation"]["status"] == "unobserved"
    assert names["deletion_cleanup"]["status"] == "unobserved"
    assert names["recall_silent_unavailable"]["status"] == "unobserved"


def test_prepare_writes_supported_isolation_root(tmp_path: Path):
    receipt = tmp_path / "r"
    profile = receipt / "p"
    receipt.mkdir()
    binding = common.validate_isolation(
        isolated_profile=profile,
        isolated_port=18085,
        receipt_root=receipt,
        installed_app=ROOT,
        installed_interpreter=Path(sys.executable),
        package_manifest=_manifest(tmp_path / "m.json"),
        instrument_only=True,
        original_local=_original_local(),
    )
    prepare.prepare(binding)
    assert (profile / "index.db").is_file()
    assert (profile / "settings.json").is_file()
    assert (profile / "token.txt").is_file()
    settings = json.loads((profile / "settings.json").read_text(encoding="utf-8"))
    assert settings["librarian_apply_enabled"] is False
    env = json.loads((profile / "mcp.json").read_text(encoding="utf-8"))
    child_env = env["mcpServers"]["uoink"]["env"]
    assert child_env["UOINK_INDEX_PATH"] == str(profile / "index.db")


def test_original_route_does_not_use_fake_child(tmp_path: Path):
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
        "import sys\nprint('no isolation', file=sys.stderr)\nraise SystemExit(3)\n",
        encoding="utf-8",
    )
    binding = common.validate_isolation(
        isolated_profile=profile,
        isolated_port=18086,
        receipt_root=receipt,
        installed_app=app,
        installed_interpreter=Path(sys.executable),
        package_manifest=_manifest(tmp_path / "m.json"),
        instrument_only=True,
        original_local=_original_local(),
    )
    env = common.isolation_env(binding, extra={"route_label": "original-installed"})
    result = stdio_check.run_installed(binding, profile, env, "original-installed")
    assert result["fake_child_used"] is False
    assert result["hidden_by_special_route"] is False
    assert result["installed_credit"] is False
    assert result["product_findings"]
    assert any(f["route"] == "original-installed" for f in result["product_findings"])
    joined = " ".join(str(x) for x in (result.get("command") or []))
    assert "uoink_mcp.py" in joined
    assert "fake_mcp_child.py" not in joined


def test_source_runtime_original_route_against_isolation_scratch(tmp_path: Path):
    """Complete original-route checks against a disposable isolation overlay.

    Not installed credit. Stop CLI is not run.
    """
    receipt = tmp_path / "r"
    profile = receipt / "p"
    scratch = tmp_path / "iso-app"
    receipt.mkdir()
    overlay = provision.provision_isolation_scratch(product_src=ROOT, scratch_app=scratch)
    assert overlay["stop_cli_invoked"] is False
    assert (scratch / "uoink_install_isolation.py").is_file()
    mcp_text = (scratch / "uoink_mcp.py").read_text(encoding="utf-8")
    assert "apply_from_process" in mcp_text
    binding = common.validate_isolation(
        isolated_profile=profile,
        isolated_port=18087,
        receipt_root=receipt,
        installed_app=scratch,
        installed_interpreter=Path(sys.executable),
        package_manifest=_manifest(tmp_path / "m.json"),
        runtime_mode="source-runtime",
        original_local=_original_local(),
    )
    assert binding["installed_credit"] is False
    prepare.prepare(binding)
    assert (profile / "index.db").is_file()
    env = common.isolation_env(binding, extra={"route_label": "original-installed"})
    result = stdio_check.run_installed(binding, profile, env, "original-installed")
    dump = ROOT / "_scratch" / "p4kit-repair-source-runtime.json"
    dump.parent.mkdir(parents=True, exist_ok=True)
    dump.write_text(json.dumps({
        "observed_inventory": result.get("observed_inventory"),
        "reconnect": result.get("reconnect"),
        "unavailable_storage": result.get("unavailable_storage"),
        "transport_failure": result.get("transport_failure"),
        "installed_credit": result.get("installed_credit"),
        "product_findings": result.get("product_findings"),
        "inspection_complete": (result.get("inspection") or {}).get("packet_and_prompt_subset_complete"),
        "elapsed_ms": result.get("elapsed_ms"),
        "command": result.get("command"),
        "live_index_forbidden": binding.get("live_index_forbidden"),
    }, default=str, indent=2) + "\n", encoding="utf-8")
    assert result["fake_child_used"] is False
    assert result["route_label"] == "original-installed"
    assert result["installed_credit"] is False
    # Inventory, packets, reconnect, bounds are measured even when they fail.
    assert "tools" in (result.get("observed_inventory") or {})
    assert "reconnect" in result
    assert "unavailable_storage" in result
    assert "transport_failure" in result
    assert result["unavailable_storage"]["bound_ms"] == 2000
    assert result["transport_failure"]["bound_ms"] == 15000
    for finding in result.get("product_findings") or []:
        assert finding["hidden_by_special_route"] is False
        assert "input" in finding
