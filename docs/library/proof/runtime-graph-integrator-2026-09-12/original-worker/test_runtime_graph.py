from __future__ import annotations

import email
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest
from packaging.requirements import Requirement
from packaging.tags import Tag
from packaging.utils import parse_wheel_filename

ROOT = Path(__file__).resolve().parents[1]
CHECK_SCRIPT = ROOT / "scripts" / "check_runtime_graph.py"
LOCK = ROOT / "requirements-installer-lock.txt"
PROOF_DIR = ROOT / "docs" / "library" / "proof" / "runtime-graph-01-2026-09-12"

spec = importlib.util.spec_from_file_location("check_runtime_graph", CHECK_SCRIPT)
assert spec is not None and spec.loader is not None
crg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(crg)


def test_target_env_and_pep508_marker_closure() -> None:
    env = dict(crg.TARGET_ENV)
    assert env["sys_platform"] == "win32"
    assert env["platform_machine"] == "AMD64"
    assert env["python_version"] == "3.13"
    assert env["extra"] == ""

    # Windows marker matches
    r_win = Requirement(
        'torchcodec<0.8.0,>=0.6.0; (sys_platform == "linux" and platform_machine == "x86_64") or sys_platform == "darwin" or sys_platform == "win32"'
    )
    assert r_win.marker.evaluate(env) is True

    # Linux-only marker does not match
    r_linux = Requirement(
        'triton>=3.3.0; sys_platform == "linux" and platform_machine == "x86_64"'
    )
    assert r_linux.marker.evaluate(env) is False

    # Older python marker does not match
    r_old_py = Requirement("tomli>=1.1.0; python_version < '3.11'")
    assert r_old_py.marker.evaluate(env) is False

    # Extras requirement does not match default installer runtime
    r_dev = Requirement('pytest>=8.0; extra == "dev"')
    assert r_dev.marker.evaluate(env) is False


def test_wheel_tag_and_python_compatibility_rules() -> None:
    tags = crg.get_supported_wheel_tags(python_version=(3, 13), platform="win_amd64")

    # Pure Python wheels are compatible
    assert bool(parse_wheel_filename("whisperx-3.8.6-py3-none-any.whl")[3] & tags)
    assert bool(parse_wheel_filename("six-1.17.0-py2.py3-none-any.whl")[3] & tags)

    # Windows CPython 3.13 native wheels are compatible
    assert bool(parse_wheel_filename("torch-2.8.0-cp313-cp313-win_amd64.whl")[3] & tags)

    # ABI3 wheels built for earlier Python versions are forward-compatible with 3.13
    assert bool(parse_wheel_filename("tokenizers-0.22.2-cp39-abi3-win_amd64.whl")[3] & tags)
    assert bool(parse_wheel_filename("safetensors-0.8.0-cp310-abi3-win_amd64.whl")[3] & tags)

    # Incompatible platform wheels are rejected
    assert not bool(parse_wheel_filename("torch-2.8.0-cp313-cp313-manylinux1_x86_64.whl")[3] & tags)
    assert not bool(parse_wheel_filename("torch-2.8.0-cp313-cp313-macosx_11_0_arm64.whl")[3] & tags)

    # Incompatible CPython version non-abi3 wheels are rejected
    assert not bool(parse_wheel_filename("torch-2.8.0-cp312-cp312-win_amd64.whl")[3] & tags)


def test_check_wheel_for_release_rejects_yanked_and_incompatible() -> None:
    supported = crg.get_supported_wheel_tags()
    env = dict(crg.TARGET_ENV)

    # Case 1: Yanked wheel
    files_yanked = [
        {
            "filename": "demo-1.0.0-py3-none-any.whl",
            "packagetype": "bdist_wheel",
            "yanked": True,
            "yanked_reason": "critical security bug",
            "digests": {"sha256": "abc"},
            "size": 1234,
            "url": "https://example.com/demo.whl",
        }
    ]
    res_yanked = crg.check_wheel_for_release("demo", "1.0.0", files_yanked, supported, env)
    assert res_yanked["status"] == "YANKED"
    assert "critical security bug" in res_yanked["error"]

    # Case 2: Incompatible tags (only linux)
    files_linux = [
        {
            "filename": "demo-1.0.0-cp313-cp313-manylinux_2_17_x86_64.whl",
            "packagetype": "bdist_wheel",
            "yanked": False,
            "digests": {"sha256": "def"},
            "size": 5678,
            "url": "https://example.com/demo-linux.whl",
        }
    ]
    res_incompat = crg.check_wheel_for_release("demo", "1.0.0", files_linux, supported, env)
    assert res_incompat["status"] == "INCOMPATIBLE_TAGS"

    # Case 3: Incompatible Requires-Python
    files_old_py = [
        {
            "filename": "demo-1.0.0-py3-none-any.whl",
            "packagetype": "bdist_wheel",
            "requires_python": "<3.13,>=3.9",
            "yanked": False,
            "digests": {"sha256": "ghi"},
            "size": 9012,
            "url": "https://example.com/demo-old.whl",
        }
    ]
    res_py = crg.check_wheel_for_release("demo", "1.0.0", files_old_py, supported, env)
    assert res_py["status"] == "INCOMPATIBLE_TAGS"
    assert "Requires-Python" in res_py["error"]


def test_detects_conflicting_constraints_and_missing_packages(tmp_path: Path) -> None:
    pypi_dir = tmp_path / "pypi"
    meta_dir = tmp_path / "metadata"
    pypi_dir.mkdir()
    meta_dir.mkdir()

    # Package A requires B~=1.0 and C>=2.0
    a_json = {
        "info": {"version": "1.0.0"},
        "releases": {
            "1.0.0": [
                {
                    "filename": "pkg_a-1.0.0-py3-none-any.whl",
                    "packagetype": "bdist_wheel",
                    "yanked": False,
                    "digests": {"sha256": "1111"},
                    "size": 100,
                    "url": "https://example.com/a.whl",
                }
            ]
        },
    }
    (pypi_dir / "pkg-a.json").write_text(json.dumps(a_json), encoding="utf-8")
    (meta_dir / "pkg_a-1.0.0-py3-none-any.whl.metadata").write_text(
        "Metadata-Version: 2.1\nName: pkg-a\nVersion: 1.0.0\nRequires-Dist: pkg-b~=1.0.0\nRequires-Dist: pkg-c>=2.0.0\n",
        encoding="utf-8",
    )

    # Package B at version 1.2.0 (conflicts with ~=1.0.0)
    b_json = {
        "info": {"version": "1.2.0"},
        "releases": {
            "1.2.0": [
                {
                    "filename": "pkg_b-1.2.0-py3-none-any.whl",
                    "packagetype": "bdist_wheel",
                    "yanked": False,
                    "digests": {"sha256": "2222"},
                    "size": 200,
                    "url": "https://example.com/b.whl",
                }
            ]
        },
    }
    (pypi_dir / "pkg-b.json").write_text(json.dumps(b_json), encoding="utf-8")
    (meta_dir / "pkg_b-1.2.0-py3-none-any.whl.metadata").write_text(
        "Metadata-Version: 2.1\nName: pkg-b\nVersion: 1.2.0\n", encoding="utf-8"
    )

    # Package C is missing from selection
    selection = {"pkg-a": "1.0.0", "pkg-b": "1.2.0"}

    res = crg.check_runtime_graph(selection, tmp_path, verify_manifest=False)

    assert res["status"] == "FAIL"
    assert res["passed"] is False

    # Check conflict
    assert len(res["conflicting_constraints"]) == 1
    conflict = res["conflicting_constraints"][0]
    assert conflict["source"] == "pkg-a"
    assert conflict["target"] == "pkg-b"
    assert conflict["selected_version"] == "1.2.0"
    assert conflict["required_specifier"] == "~=1.0.0"

    # Check missing package
    assert len(res["missing_packages"]) == 1
    missing = res["missing_packages"][0]
    assert missing["source"] == "pkg-a"
    assert missing["target"] == "pkg-c"


def test_tampered_evidence_manifest_rejection(tmp_path: Path) -> None:
    pypi_dir = tmp_path / "pypi"
    pypi_dir.mkdir()
    f1 = pypi_dir / "sample.json"
    f1.write_text('{"info": {}}', encoding="utf-8")

    manifest = {"pypi/sample.json": hashlib.sha256(b"authentic bytes").hexdigest()}
    (tmp_path / "SHA256.json").write_text(json.dumps(manifest), encoding="utf-8")

    ok, errors = crg.verify_evidence_integrity(tmp_path)
    assert ok is False
    assert len(errors) == 1
    assert "Tampered/mismatched evidence" in errors[0]


def test_successful_synthetic_graph_closure(tmp_path: Path) -> None:
    pypi_dir = tmp_path / "pypi"
    meta_dir = tmp_path / "metadata"
    pypi_dir.mkdir()
    meta_dir.mkdir()

    # Create root package and child package with mutually compatible pins
    root_json = {
        "info": {"version": "2.0.0"},
        "releases": {
            "2.0.0": [
                {
                    "filename": "demo_root-2.0.0-py3-none-any.whl",
                    "packagetype": "bdist_wheel",
                    "yanked": False,
                    "digests": {"sha256": "1111"},
                    "size": 100,
                    "url": "https://example.com/root.whl",
                }
            ]
        },
    }
    child_json = {
        "info": {"version": "1.5.0"},
        "releases": {
            "1.5.0": [
                {
                    "filename": "demo_child-1.5.0-cp313-cp313-win_amd64.whl",
                    "packagetype": "bdist_wheel",
                    "yanked": False,
                    "digests": {"sha256": "2222"},
                    "size": 200,
                    "url": "https://example.com/child.whl",
                }
            ]
        },
    }

    (pypi_dir / "demo-root.json").write_text(json.dumps(root_json), encoding="utf-8")
    (pypi_dir / "demo-child.json").write_text(json.dumps(child_json), encoding="utf-8")

    (meta_dir / "demo_root-2.0.0-py3-none-any.whl.metadata").write_text(
        "Metadata-Version: 2.1\nName: demo-root\nVersion: 2.0.0\nRequires-Dist: demo-child>=1.0.0,<2.0.0\n",
        encoding="utf-8",
    )
    (meta_dir / "demo_child-1.5.0-cp313-cp313-win_amd64.whl.metadata").write_text(
        "Metadata-Version: 2.1\nName: demo-child\nVersion: 1.5.0\n", encoding="utf-8"
    )

    # Manifest with exact matching hashes
    manifest: dict[str, str] = {}
    for p in tmp_path.rglob("*"):
        if p.is_file():
            manifest[str(p.relative_to(tmp_path)).replace("\\", "/")] = hashlib.sha256(
                p.read_bytes()
            ).hexdigest()
    (tmp_path / "SHA256.json").write_text(json.dumps(manifest), encoding="utf-8")

    selection = {"demo-root": "2.0.0", "demo-child": "1.5.0"}
    res = crg.check_runtime_graph(selection, tmp_path, verify_manifest=True)

    assert res["status"] == "PASS"
    assert res["passed"] is True
    assert len(res["active_edges"]) == 1
    assert len(res["missing_packages"]) == 0
    assert len(res["conflicting_constraints"]) == 0
    assert len(res["wheel_details"]) == 2


def test_proof_directory_has_complete_evidence_for_all_140_packages() -> None:
    assert PROOF_DIR.is_dir(), f"Proof directory missing: {PROOF_DIR}"
    locked = crg.parse_lock(LOCK)
    assert len(locked) == 140

    # Ensure every locked package has PyPI JSON and metadata captured
    pypi_dir = PROOF_DIR / "pypi"
    for cname in locked:
        assert (pypi_dir / f"{cname}.json").is_file(), f"Missing PyPI JSON for {cname}"

    # Verify SHA256 integrity of the proof directory
    ok, errors = crg.verify_evidence_integrity(PROOF_DIR)
    assert ok is True, f"Evidence integrity failed: {errors}"


def test_runtime_graph_on_installer_lock_truthfully_reports_status() -> None:
    locked = crg.parse_lock(LOCK)
    res = crg.check_runtime_graph(locked, PROOF_DIR)

    # Truthful reporting:
    assert res["selection_count"] == 140
    assert res["active_edges_count"] >= 280

    # There are 0 missing packages and 0 conflicting constraints in the locked set
    assert len(res["missing_packages"]) == 0
    assert len(res["conflicting_constraints"]) == 0

    # 138 packages have Windows cp313 wheels; exactly 2 are missing wheels on PyPI
    assert len(res["wheel_details"]) == 138
    assert len(res["wheel_failures"]) == 2

    failed_pkgs = {f["package"] for f in res["wheel_failures"]}
    assert failed_pkgs == {"antlr4-python3-runtime", "proxy-tools"}
    for wf in res["wheel_failures"]:
        assert wf["status"] == "NO_WHEELS"

    # Status must be truthfully FAIL because of the 2 missing wheels
    assert res["status"] == "FAIL"
    assert res["passed"] is False


def test_proposed_upgrades_conflict_with_whisperx_constraints() -> None:
    locked = crg.parse_lock(LOCK)

    # Proposed stack with Torch 2.10.0 and Transformers 5.10.0
    proposal = dict(locked)
    proposal["torch"] = "2.10.0"
    proposal["torchaudio"] = "2.10.0"
    proposal["torchvision"] = "0.25.0"
    proposal["torchcodec"] = "0.9.0"
    proposal["transformers"] = "5.10.0"
    proposal["huggingface-hub"] = "1.5.0"

    res = crg.check_runtime_graph(proposal, PROOF_DIR)
    assert res["status"] == "FAIL"

    conflicts = {
        (c["source"], c["target"]): (c["selected_version"], c["required_specifier"])
        for c in res["conflicting_constraints"]
    }

    # WhisperX strictly requires ~=2.8.0 for torch, torchaudio, torchvision, torchcodec
    assert ("whisperx", "torch") in conflicts
    assert conflicts[("whisperx", "torch")] == ("2.10.0", "~=2.8.0")

    assert ("whisperx", "torchaudio") in conflicts
    assert conflicts[("whisperx", "torchaudio")] == ("2.10.0", "~=2.8.0")

    assert ("whisperx", "torchvision") in conflicts
    assert conflicts[("whisperx", "torchvision")] == ("0.25.0", "~=0.23.0")

    assert ("whisperx", "torchcodec") in conflicts
    assert conflicts[("whisperx", "torchcodec")][0] == "0.9.0"

    # WhisperX strictly requires huggingface-hub<1.0.0
    assert ("whisperx", "huggingface-hub") in conflicts
    assert conflicts[("whisperx", "huggingface-hub")] == ("1.5.0", "<1.0.0")
