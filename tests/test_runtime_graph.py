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
LOCK = ROOT / "docs/library/proof/runtime-graph-astra-review-2026-09-12/input-lock-02e06db.txt"
PROOF_DIR = ROOT / "docs" / "library" / "proof" / "runtime-graph-01-2026-09-12"
_needs_proof_dir = pytest.mark.skipif(
    not PROOF_DIR.is_dir(), reason="proof archive removed from public tree (e576ec9)")

spec = importlib.util.spec_from_file_location("check_runtime_graph", CHECK_SCRIPT)
assert spec is not None and spec.loader is not None
crg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(crg)


def make_sha256(content: bytes) -> str:
    """Generate authentic 64-char SHA256 hex digest for testing."""
    return hashlib.sha256(content).hexdigest()


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

    # Extras requirement does not match default base installer runtime
    r_dev = Requirement('pytest>=8.0; extra == "dev"')
    assert r_dev.marker.evaluate(env) is False

    # Extras requirement matches when extra is explicitly activated
    env_dev = dict(env, extra="dev")
    assert r_dev.marker.evaluate(env_dev) is True


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

    # Regression case: no host-platform leakage; tags only contain target platform or 'any'
    for tag in tags:
        assert tag.platform in {"win_amd64", "any"}, f"Host platform leakage in tag: {tag}"

    # Regression case: cp312-none tags are rejected
    assert not bool(parse_wheel_filename("demo-1.0.0-cp312-none-any.whl")[3] & tags)
    assert not bool(parse_wheel_filename("demo-1.0.0-cp312-none-win_amd64.whl")[3] & tags)

    # Regression case: free-threaded cp313t wheels are rejected for non-free-threaded runtime
    assert not bool(parse_wheel_filename("demo-1.0.0-cp313t-cp313t-win_amd64.whl")[3] & tags)


def test_check_wheel_for_release_rejects_yanked_and_incompatible_and_invalid() -> None:
    supported = crg.get_supported_wheel_tags()
    env = dict(crg.TARGET_ENV)

    valid_sha = make_sha256(b"dummy payload")

    # Case 1: Yanked wheel
    files_yanked = [
        {
            "filename": "demo-1.0.0-py3-none-any.whl",
            "packagetype": "bdist_wheel",
            "yanked": True,
            "yanked_reason": "critical security bug",
            "digests": {"sha256": valid_sha},
            "size": 1234,
            "url": "https://example.com/demo.whl",
        }
    ]
    res_yanked = crg.check_wheel_for_release("demo", "1.0.0", files_yanked, supported, env)
    assert res_yanked["status"] == "YANKED"
    assert "critical security bug" in res_yanked["error"]

    # Case 2: Incompatible platform tags (linux only)
    files_linux = [
        {
            "filename": "demo-1.0.0-cp313-cp313-manylinux_2_17_x86_64.whl",
            "packagetype": "bdist_wheel",
            "yanked": False,
            "digests": {"sha256": valid_sha},
            "size": 5678,
            "url": "https://example.com/demo-linux.whl",
        }
    ]
    res_incompat = crg.check_wheel_for_release("demo", "1.0.0", files_linux, supported, env)
    assert res_incompat["status"] == "INCOMPATIBLE_TAGS"

    # Case 3: Incompatible Requires-Python range excluding 3.13
    files_old_py = [
        {
            "filename": "demo-1.0.0-py3-none-any.whl",
            "packagetype": "bdist_wheel",
            "requires_python": "<3.13,>=3.9",
            "yanked": False,
            "digests": {"sha256": valid_sha},
            "size": 9012,
            "url": "https://example.com/demo-old.whl",
        }
    ]
    res_py = crg.check_wheel_for_release("demo", "1.0.0", files_old_py, supported, env)
    assert res_py["status"] == "INCOMPATIBLE_TAGS"

    # Case 4: Malformed Requires-Python constraint is rejected
    files_malformed_py = [
        {
            "filename": "demo-1.0.0-py3-none-any.whl",
            "packagetype": "bdist_wheel",
            "requires_python": "invalid>>syntax",
            "yanked": False,
            "digests": {"sha256": valid_sha},
            "size": 9012,
            "url": "https://example.com/demo-bad.whl",
        }
    ]
    res_malformed_py = crg.check_wheel_for_release("demo", "1.0.0", files_malformed_py, supported, env)
    assert res_malformed_py["status"] == "INCOMPATIBLE_TAGS" or len(res_malformed_py.get("rejected_invalid", [])) > 0

    # Case 5: Missing or invalid SHA256 digest is rejected
    files_bad_hash = [
        {
            "filename": "demo-1.0.0-py3-none-any.whl",
            "packagetype": "bdist_wheel",
            "yanked": False,
            "digests": {"sha256": "short_invalid_hash"},
            "size": 9012,
            "url": "https://example.com/demo.whl",
        }
    ]
    res_bad_hash = crg.check_wheel_for_release("demo", "1.0.0", files_bad_hash, supported, env)
    assert res_bad_hash["status"] == "NO_WHEELS"

    # Case 6: Missing or invalid URL is rejected
    files_bad_url = [
        {
            "filename": "demo-1.0.0-py3-none-any.whl",
            "packagetype": "bdist_wheel",
            "yanked": False,
            "digests": {"sha256": valid_sha},
            "size": 9012,
            "url": "file:///not-a-valid-http-url",
        }
    ]
    res_bad_url = crg.check_wheel_for_release("demo", "1.0.0", files_bad_url, supported, env)
    assert res_bad_url["status"] == "NO_WHEELS"


def test_manifest_adversarial_boundedness_and_integrity_checks(tmp_path: Path) -> None:
    pypi_dir = tmp_path / "pypi"
    pypi_dir.mkdir()
    sample = pypi_dir / "sample.json"
    sample.write_text('{"info": {}}', encoding="utf-8")
    sample_sha = make_sha256(sample.read_bytes())

    # 1. Missing manifest file cannot pass
    ok, errors, _ = crg.verify_evidence_integrity(tmp_path)
    assert ok is False
    assert any("Missing evidence manifest" in e for e in errors)

    # 2. Empty manifest file cannot pass
    manifest_file = tmp_path / "SHA256.json"
    manifest_file.write_text("", encoding="utf-8")
    ok, errors, _ = crg.verify_evidence_integrity(tmp_path)
    assert ok is False
    assert any("Empty manifest" in e for e in errors)

    # 3. Malformed JSON manifest cannot pass
    manifest_file.write_text("{not valid json", encoding="utf-8")
    ok, errors, _ = crg.verify_evidence_integrity(tmp_path)
    assert ok is False
    assert any("Malformed manifest JSON" in e for e in errors)

    # 4. Non-64-character SHA256 digest is rejected
    manifest_file.write_text(json.dumps({"pypi/sample.json": "abcd123"}), encoding="utf-8")
    ok, errors, _ = crg.verify_evidence_integrity(tmp_path)
    assert ok is False
    assert any("Invalid SHA256 value" in e for e in errors)

    # 5. Tampered evidence content is rejected
    manifest_file.write_text(json.dumps({"pypi/sample.json": make_sha256(b"wrong data")}), encoding="utf-8")
    ok, errors, _ = crg.verify_evidence_integrity(tmp_path)
    assert ok is False
    assert any("Tampered/mismatched evidence" in e for e in errors)

    # 6. Path traversal in manifest is rejected
    manifest_file.write_text(
        json.dumps({"../outside.json": sample_sha, "pypi/../../escaped.json": sample_sha}),
        encoding="utf-8",
    )
    ok, errors, _ = crg.verify_evidence_integrity(tmp_path)
    assert ok is False
    assert any("Path traversal" in e for e in errors)

    # 7. Absolute path in manifest is rejected
    manifest_file.write_text(
        json.dumps({"/etc/passwd": sample_sha, "C:/Windows/system.ini": sample_sha}),
        encoding="utf-8",
    )
    ok, errors, _ = crg.verify_evidence_integrity(tmp_path)
    assert ok is False
    assert any("Absolute path" in e for e in errors)

    # 8. Duplicate normalized manifest entries are rejected
    manifest_file.write_text(
        '{"pypi/sample.json": "' + sample_sha + '", "./pypi/sample.json": "' + sample_sha + '"}',
        encoding="utf-8",
    )
    ok, errors, _ = crg.verify_evidence_integrity(tmp_path)
    assert ok is False
    assert any("Duplicate normalized manifest entry" in e for e in errors)

    # 9. Integrity bypass option can NEVER produce PASS
    res = crg.check_runtime_graph({"pkg": "1.0.0"}, tmp_path, verify_manifest=False)
    assert res["status"] == "FAIL"
    assert res["passed"] is False
    assert any("integrity-bypass cannot produce PASS" in e for e in res["manifest_errors"])


def test_selection_validation_and_adversarial_rejections(tmp_path: Path) -> None:
    # 1. Empty selection file raises ValueError
    empty_file = tmp_path / "empty.txt"
    empty_file.write_text("# only comments\n\n", encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        crg.parse_selection(empty_file)

    # 2. Duplicate pins in lockfile raise ValueError
    dup_file = tmp_path / "dup.txt"
    dup_file.write_text("package-a==1.0.0\npackage_a==1.0.0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate package"):
        crg.parse_selection(dup_file)

    # 3. Duplicate pins in JSON raise ValueError
    dup_json = tmp_path / "dup.json"
    dup_json.write_text('{"selected": {"Package-A": "1.0.0", "package_a": "2.0.0"}}', encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate package"):
        crg.parse_selection(dup_json)

    # 4. Invalid package names raise ValueError
    bad_name = tmp_path / "bad_name.txt"
    bad_name.write_text("invalid name! == 1.0.0\n", encoding="utf-8")
    with pytest.raises(ValueError):
        crg.parse_selection(bad_name)

    # 5. Invalid version raises ValueError
    bad_ver = tmp_path / "bad_ver.txt"
    bad_ver.write_text("valid-name==not-a-valid-version\n", encoding="utf-8")
    with pytest.raises(ValueError):
        crg.parse_selection(bad_ver)

    # 6. Empty selection passed to check_runtime_graph produces FAIL
    res = crg.check_runtime_graph({}, tmp_path, verify_manifest=False)
    assert res["status"] == "FAIL"
    assert res["passed"] is False
    assert any("Empty selection" in e for e in res["selection_errors"])


def test_exact_wheel_metadata_matching_and_requires_python_mismatch(tmp_path: Path) -> None:
    pypi_dir = tmp_path / "pypi"
    meta_dir = tmp_path / "metadata"
    pypi_dir.mkdir()
    meta_dir.mkdir()

    sha = make_sha256(b"content")

    # Package demo has wheel demo-1.0.0-py3-none-any.whl
    pypi_json = {
        "info": {"version": "1.0.0"},
        "releases": {
            "1.0.0": [
                {
                    "filename": "demo-1.0.0-py3-none-any.whl",
                    "packagetype": "bdist_wheel",
                    "yanked": False,
                    "digests": {"sha256": sha},
                    "size": 100,
                    "url": "https://example.com/demo.whl",
                    "requires_python": ">=3.12",
                }
            ]
        },
    }
    p_file = pypi_dir / "demo.json"
    p_file.write_text(json.dumps(pypi_json), encoding="utf-8")

    # METADATA with Name mismatch: Name says 'other' instead of 'demo'
    m_file = meta_dir / "demo-1.0.0-py3-none-any.whl.metadata"
    m_file.write_text(
        "Metadata-Version: 2.1\nName: other\nVersion: 1.0.0\nRequires-Python: >=3.12\n",
        encoding="utf-8",
    )

    manifest = {
        "pypi/demo.json": make_sha256(p_file.read_bytes()),
        "metadata/demo-1.0.0-py3-none-any.whl.metadata": make_sha256(m_file.read_bytes()),
    }
    (tmp_path / "SHA256.json").write_text(json.dumps(manifest), encoding="utf-8")

    res = crg.check_runtime_graph({"demo": "1.0.0"}, tmp_path, verify_manifest=True)
    assert res["status"] == "FAIL"
    assert any("Name mismatch" in inc["error"] for inc in res["incomplete_evidence"])

    # Now fix Name, but make METADATA Requires-Python contradict target Python 3.13
    m_file.write_text(
        "Metadata-Version: 2.1\nName: demo\nVersion: 1.0.0\nRequires-Python: <3.12\n",
        encoding="utf-8",
    )
    manifest["metadata/demo-1.0.0-py3-none-any.whl.metadata"] = make_sha256(m_file.read_bytes())
    (tmp_path / "SHA256.json").write_text(json.dumps(manifest), encoding="utf-8")

    res2 = crg.check_runtime_graph({"demo": "1.0.0"}, tmp_path, verify_manifest=True)
    assert res2["status"] == "FAIL"
    assert any("Requires-Python" in inc["error"] for inc in res2["incomplete_evidence"])


def test_extras_propagation_to_fixed_point_including_cycles(tmp_path: Path) -> None:
    pypi_dir = tmp_path / "pypi"
    meta_dir = tmp_path / "metadata"
    pypi_dir.mkdir()
    meta_dir.mkdir()

    sha = make_sha256(b"dummy")

    # Package A requires B[extra_b] unconditionally
    # Package B under extra == 'extra_b' requires A[extra_a] (cycle!) and C>=1.0
    # Package A under extra == 'extra_a' requires D>=2.0
    # Package C and D have no further dependencies

    pypi_a = {
        "info": {"version": "1.0.0"},
        "releases": {
            "1.0.0": [{
                "filename": "pkg_a-1.0.0-py3-none-any.whl",
                "packagetype": "bdist_wheel",
                "yanked": False,
                "digests": {"sha256": sha},
                "size": 100,
                "url": "https://example.com/a.whl",
            }]
        },
    }
    pypi_b = {
        "info": {"version": "1.0.0"},
        "releases": {
            "1.0.0": [{
                "filename": "pkg_b-1.0.0-py3-none-any.whl",
                "packagetype": "bdist_wheel",
                "yanked": False,
                "digests": {"sha256": sha},
                "size": 100,
                "url": "https://example.com/b.whl",
            }]
        },
    }
    pypi_c = {
        "info": {"version": "1.0.0"},
        "releases": {
            "1.0.0": [{
                "filename": "pkg_c-1.0.0-py3-none-any.whl",
                "packagetype": "bdist_wheel",
                "yanked": False,
                "digests": {"sha256": sha},
                "size": 100,
                "url": "https://example.com/c.whl",
            }]
        },
    }
    pypi_d = {
        "info": {"version": "2.0.0"},
        "releases": {
            "2.0.0": [{
                "filename": "pkg_d-2.0.0-py3-none-any.whl",
                "packagetype": "bdist_wheel",
                "yanked": False,
                "digests": {"sha256": sha},
                "size": 100,
                "url": "https://example.com/d.whl",
            }]
        },
    }

    (pypi_dir / "pkg-a.json").write_text(json.dumps(pypi_a), encoding="utf-8")
    (pypi_dir / "pkg-b.json").write_text(json.dumps(pypi_b), encoding="utf-8")
    (pypi_dir / "pkg-c.json").write_text(json.dumps(pypi_c), encoding="utf-8")
    (pypi_dir / "pkg-d.json").write_text(json.dumps(pypi_d), encoding="utf-8")

    meta_a = (
        "Metadata-Version: 2.1\nName: pkg-a\nVersion: 1.0.0\n"
        "Requires-Dist: pkg-b[extra_b]>=1.0.0\n"
        'Requires-Dist: pkg-d>=2.0.0; extra == "extra_a"\n'
    )
    meta_b = (
        "Metadata-Version: 2.1\nName: pkg-b\nVersion: 1.0.0\n"
        'Requires-Dist: pkg-a[extra_a]>=1.0.0; extra == "extra_b"\n'
        'Requires-Dist: pkg-c>=1.0.0; extra == "extra_b"\n'
    )
    meta_c = "Metadata-Version: 2.1\nName: pkg-c\nVersion: 1.0.0\n"
    meta_d = "Metadata-Version: 2.1\nName: pkg-d\nVersion: 2.0.0\n"

    (meta_dir / "pkg_a-1.0.0-py3-none-any.whl.metadata").write_text(meta_a, encoding="utf-8")
    (meta_dir / "pkg_b-1.0.0-py3-none-any.whl.metadata").write_text(meta_b, encoding="utf-8")
    (meta_dir / "pkg_c-1.0.0-py3-none-any.whl.metadata").write_text(meta_c, encoding="utf-8")
    (meta_dir / "pkg_d-2.0.0-py3-none-any.whl.metadata").write_text(meta_d, encoding="utf-8")

    # Generate manifest
    manifest: dict[str, str] = {}
    for p in tmp_path.rglob("*"):
        if p.is_file():
            manifest[str(p.relative_to(tmp_path)).replace("\\", "/")] = make_sha256(p.read_bytes())
    (tmp_path / "SHA256.json").write_text(json.dumps(manifest), encoding="utf-8")

    selection = {
        "pkg-a": "1.0.0",
        "pkg-b": "1.0.0",
        "pkg-c": "1.0.0",
        "pkg-d": "2.0.0",
    }

    res = crg.check_runtime_graph(selection, tmp_path, verify_manifest=True)
    assert res["status"] == "PASS"
    assert res["passed"] is True

    # Both pkg-a and pkg-b had their extras activated despite cycle
    assert crg.canonical_name("extra_a") in res["active_extras"]["pkg-a"]
    assert crg.canonical_name("extra_b") in res["active_extras"]["pkg-b"]

    # Active edges include the optional dependencies activated by extras
    targets = {e["target"] for e in res["active_edges"]}
    assert "pkg-c" in targets
    assert "pkg-d" in targets


def test_marker_evaluation_errors_and_direct_url_rejections(tmp_path: Path) -> None:
    pypi_dir = tmp_path / "pypi"
    meta_dir = tmp_path / "metadata"
    pypi_dir.mkdir()
    meta_dir.mkdir()

    sha = make_sha256(b"dummy")

    pypi_pkg = {
        "info": {"version": "1.0.0"},
        "releases": {
            "1.0.0": [{
                "filename": "pkg-1.0.0-py3-none-any.whl",
                "packagetype": "bdist_wheel",
                "yanked": False,
                "digests": {"sha256": sha},
                "size": 100,
                "url": "https://example.com/pkg.whl",
            }]
        },
    }
    (pypi_dir / "pkg.json").write_text(json.dumps(pypi_pkg), encoding="utf-8")

    # Marker error in requires_dist AND direct-URL requirement
    meta_pkg = (
        "Metadata-Version: 2.1\nName: pkg\nVersion: 1.0.0\n"
        'Requires-Dist: bad-marker; invalid_marker_variable == "test"\n'
        "Requires-Dist: direct-pkg @ https://example.com/direct.whl\n"
    )
    (meta_dir / "pkg-1.0.0-py3-none-any.whl.metadata").write_text(meta_pkg, encoding="utf-8")

    manifest: dict[str, str] = {}
    for p in tmp_path.rglob("*"):
        if p.is_file():
            manifest[str(p.relative_to(tmp_path)).replace("\\", "/")] = make_sha256(p.read_bytes())
    (tmp_path / "SHA256.json").write_text(json.dumps(manifest), encoding="utf-8")

    res = crg.check_runtime_graph({"pkg": "1.0.0"}, tmp_path, verify_manifest=True)
    assert res["status"] == "FAIL"
    assert res["passed"] is False

    # Marker errors must be errors, not inactive edges
    assert len(res["marker_errors"]) > 0
    assert any("Marker" in m["error"] for m in res["marker_errors"])

    # Direct-URL requirements must be rejected
    assert len(res["direct_url_errors"]) > 0
    assert any("direct-pkg" in d["requirement"] for d in res["direct_url_errors"])


def test_detects_conflicting_constraints_and_missing_packages(tmp_path: Path) -> None:
    pypi_dir = tmp_path / "pypi"
    meta_dir = tmp_path / "metadata"
    pypi_dir.mkdir()
    meta_dir.mkdir()

    sha_a = make_sha256(b"wheel a")
    sha_b = make_sha256(b"wheel b")

    # Package A requires B~=1.0 and C>=2.0
    a_json = {
        "info": {"version": "1.0.0"},
        "releases": {
            "1.0.0": [
                {
                    "filename": "pkg_a-1.0.0-py3-none-any.whl",
                    "packagetype": "bdist_wheel",
                    "yanked": False,
                    "digests": {"sha256": sha_a},
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
                    "digests": {"sha256": sha_b},
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

    manifest: dict[str, str] = {}
    for p in tmp_path.rglob("*"):
        if p.is_file():
            manifest[str(p.relative_to(tmp_path)).replace("\\", "/")] = make_sha256(p.read_bytes())
    (tmp_path / "SHA256.json").write_text(json.dumps(manifest), encoding="utf-8")

    # Package C is missing from selection
    selection = {"pkg-a": "1.0.0", "pkg-b": "1.2.0"}

    res = crg.check_runtime_graph(selection, tmp_path, verify_manifest=True)

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


def test_successful_synthetic_graph_closure(tmp_path: Path) -> None:
    pypi_dir = tmp_path / "pypi"
    meta_dir = tmp_path / "metadata"
    pypi_dir.mkdir()
    meta_dir.mkdir()

    sha_root = make_sha256(b"root wheel")
    sha_child = make_sha256(b"child wheel")

    root_json = {
        "info": {"version": "2.0.0"},
        "releases": {
            "2.0.0": [
                {
                    "filename": "demo_root-2.0.0-py3-none-any.whl",
                    "packagetype": "bdist_wheel",
                    "yanked": False,
                    "digests": {"sha256": sha_root},
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
                    "digests": {"sha256": sha_child},
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

    manifest: dict[str, str] = {}
    for p in tmp_path.rglob("*"):
        if p.is_file():
            manifest[str(p.relative_to(tmp_path)).replace("\\", "/")] = make_sha256(p.read_bytes())
    (tmp_path / "SHA256.json").write_text(json.dumps(manifest), encoding="utf-8")

    selection = {"demo-root": "2.0.0", "demo-child": "1.5.0"}
    res = crg.check_runtime_graph(selection, tmp_path, verify_manifest=True)

    assert res["status"] == "PASS"
    assert res["passed"] is True
    assert len(res["active_edges"]) == 1
    assert len(res["missing_packages"]) == 0
    assert len(res["conflicting_constraints"]) == 0
    assert len(res["wheel_details"]) == 2


@_needs_proof_dir
def test_proof_directory_has_complete_evidence_for_all_140_packages() -> None:
    assert PROOF_DIR.is_dir(), f"Proof directory missing: {PROOF_DIR}"
    locked = crg.parse_lock(LOCK)
    assert len(locked) == 140

    # Ensure every locked package has PyPI JSON and manifest coverage
    ok, errors, verified_files = crg.verify_evidence_integrity(PROOF_DIR)
    assert ok is True, f"Evidence integrity failed: {errors}"

    pypi_dir = PROOF_DIR / "pypi"
    for cname in locked:
        cand1 = pypi_dir / f"{cname}.json"
        cand2 = pypi_dir / f"{cname.replace('-', '_')}.json"
        cand3 = pypi_dir / f"{cname.replace('-', '.')}.json"
        assert cand1.is_file() or cand2.is_file() or cand3.is_file(), f"Missing PyPI JSON for {cname}"


@_needs_proof_dir
def test_runtime_graph_on_installer_lock_truthfully_reports_status() -> None:
    locked = crg.parse_lock(LOCK)
    res = crg.check_runtime_graph(locked, PROOF_DIR)

    # Truthful reporting on installer lock:
    assert res["selection_count"] == 140
    # Active edges include propagated extras (e.g. fsspec[http], pyjwt[crypto])
    assert res["active_edges_count"] == 283

    # Zero missing packages and zero conflicting constraints
    assert len(res["missing_packages"]) == 0
    assert len(res["conflicting_constraints"]) == 0
    assert len(res["marker_errors"]) == 0
    assert len(res["direct_url_errors"]) == 0

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


@_needs_proof_dir
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
