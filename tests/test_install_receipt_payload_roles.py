"""Independent tests for C22 verifier payload roles and compiler-only bindings."""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from install_receipt.receipt_integrity import verify_installed_bindings

VALID_BLOB = "acdf2c535be396e168929938897f6e2bee5bc174"


def make_synthetic_package(tmp_path: Path, *, installer_only: bool = True):
    """Create 142 synthetic bindings and populate tmp_path/app accordingly."""
    app_dir = tmp_path / "app"
    app_dir.mkdir(parents=True, exist_ok=True)

    files_by_path: dict[str, dict[str, object]] = {}

    for i in range(141):
        rel = f"module_{i:03d}.py"
        content = f"# module {i}\n".encode("utf-8")
        file_path = app_dir / rel
        file_path.write_bytes(content)
        sha = hashlib.sha256(content).hexdigest()
        files_by_path[rel] = {
            "staged_path": rel,
            "source_path": f"src/{rel}",
            "source_git_blob": VALID_BLOB,
            "checkout_and_staged_sha256": sha,
        }

    prep_content = b"# upgrade prep ps1 content\n"
    prep_sha = hashlib.sha256(prep_content).hexdigest()
    prep_row: dict[str, object] = {
        "staged_path": "upgrade_prep.ps1",
        "source_path": "installer/upgrade_prep.ps1",
        "source_git_blob": VALID_BLOB,
        "checkout_and_staged_sha256": prep_sha,
    }

    if installer_only:
        prep_row["install_role"] = "installer-only"
    else:
        (app_dir / "upgrade_prep.ps1").write_bytes(prep_content)

    files_by_path["upgrade_prep.ps1"] = prep_row
    assert len(files_by_path) == 142

    return app_dir, {"files_by_path": files_by_path}


def test_positive_exact_compiler_only(tmp_path):
    """Exact compiler-only row passes without requiring upgrade_prep.ps1 inside app."""
    app_dir, sealed = make_synthetic_package(tmp_path, installer_only=True)
    assert not (app_dir / "upgrade_prep.ps1").exists()

    result = verify_installed_bindings(app_dir, sealed)
    assert result["ok"] is True
    assert result["problems"] == []
    assert result["compiler_bindings"] == 142
    assert result["installed_files_checked"] == 141
    assert result["files_checked"] == 141
    assert result["compiler_only_row"] is not None
    assert result["compiler_only_row"]["staged_path"] == "upgrade_prep.ps1"
    assert result["compiler_only_row"]["install_role"] == "installer-only"


def test_positive_legacy_installed(tmp_path):
    """Legacy unlabelled rows require all 142 files inside app."""
    app_dir, sealed = make_synthetic_package(tmp_path, installer_only=False)
    assert (app_dir / "upgrade_prep.ps1").is_file()

    result = verify_installed_bindings(app_dir, sealed)
    assert result["ok"] is True
    assert result["problems"] == []
    assert result["compiler_bindings"] == 142
    assert result["installed_files_checked"] == 142
    assert result["files_checked"] == 142
    assert result["compiler_only_row"] is None


def test_legacy_upgrade_prep_missing_fails(tmp_path):
    """Unlabelled legacy upgrade_prep.ps1 missing from app causes a failure."""
    app_dir, sealed = make_synthetic_package(tmp_path, installer_only=False)
    (app_dir / "upgrade_prep.ps1").unlink()

    result = verify_installed_bindings(app_dir, sealed)
    assert result["ok"] is False
    assert any("missing installed input: upgrade_prep.ps1" in p for p in result["problems"])


def test_omitted_runtime_bytes(tmp_path):
    """Omitted application file inside app causes verifier failure."""
    app_dir, sealed = make_synthetic_package(tmp_path, installer_only=True)
    (app_dir / "module_000.py").unlink()

    result = verify_installed_bindings(app_dir, sealed)
    assert result["ok"] is False
    assert any("missing installed input: module_000.py" in p for p in result["problems"])


def test_changed_runtime_bytes(tmp_path):
    """Changed bytes in an installed file trigger a hash mismatch failure."""
    app_dir, sealed = make_synthetic_package(tmp_path, installer_only=True)
    (app_dir / "module_000.py").write_bytes(b"# corrupted content\n")

    result = verify_installed_bindings(app_dir, sealed)
    assert result["ok"] is False
    assert any("installed input hash mismatch: module_000.py" in p for p in result["problems"])


@pytest.mark.parametrize("target", ["module_000.py", "server.py"])
def test_attempts_to_exempt_another_file(tmp_path, target):
    """No caller may mark an application file as installer-only."""
    app_dir, sealed = make_synthetic_package(tmp_path, installer_only=True)
    if target not in sealed["files_by_path"]:
        content = b"# app file\n"
        (app_dir / target).write_bytes(content)
        sha = hashlib.sha256(content).hexdigest()
        # Replace module_001.py to keep 142 count
        del sealed["files_by_path"]["module_001.py"]
        (app_dir / "module_001.py").unlink()
        sealed["files_by_path"][target] = {
            "staged_path": target,
            "source_path": f"src/{target}",
            "source_git_blob": VALID_BLOB,
            "checkout_and_staged_sha256": sha,
        }

    sealed["files_by_path"][target]["install_role"] = "installer-only"
    result = verify_installed_bindings(app_dir, sealed)
    assert result["ok"] is False
    assert any("cannot mark application file as installer-only: " + target in p for p in result["problems"])


def test_traversal_and_escaping_rejected(tmp_path):
    """Paths escaping app or containing traversal are rejected."""
    app_dir, sealed = make_synthetic_package(tmp_path, installer_only=True)
    # Escaping path
    del sealed["files_by_path"]["module_000.py"]
    (app_dir / "module_000.py").unlink()
    sealed["files_by_path"]["../escape.py"] = {
        "staged_path": "../escape.py",
        "source_path": "src/escape.py",
        "source_git_blob": VALID_BLOB,
        "checkout_and_staged_sha256": "0" * 64,
    }
    result = verify_installed_bindings(app_dir, sealed)
    assert result["ok"] is False
    assert any("escapes" in p for p in result["problems"])


def test_attempt_to_exempt_escaping_path(tmp_path):
    """Escaping path marked installer-only is rejected."""
    app_dir, sealed = make_synthetic_package(tmp_path, installer_only=True)
    del sealed["files_by_path"]["module_000.py"]
    (app_dir / "module_000.py").unlink()
    sealed["files_by_path"]["../escape.py"] = {
        "staged_path": "../escape.py",
        "source_path": "installer/upgrade_prep.ps1",
        "source_git_blob": VALID_BLOB,
        "checkout_and_staged_sha256": "0" * 64,
        "install_role": "installer-only",
    }
    result = verify_installed_bindings(app_dir, sealed)
    assert result["ok"] is False
    assert any("escapes" in p for p in result["problems"])
    assert any("cannot exempt escaping path" in p for p in result["problems"])


@pytest.mark.parametrize("role", ["unknown", "exempt", "optional", "compiler-only", 123])
def test_unknown_roles_rejected(tmp_path, role):
    """Any role other than 'installed' or valid 'installer-only' is rejected."""
    app_dir, sealed = make_synthetic_package(tmp_path, installer_only=True)
    sealed["files_by_path"]["upgrade_prep.ps1"]["install_role"] = role
    result = verify_installed_bindings(app_dir, sealed)
    assert result["ok"] is False
    assert any("rejected unknown install_role" in p for p in result["problems"])


@pytest.mark.parametrize("bad_sha", ["short", "0" * 63, "g" * 64, 12345, ""])
def test_invalid_sha256_rejected(tmp_path, bad_sha):
    """Malformed checkout_and_staged_sha256 is rejected."""
    app_dir, sealed = make_synthetic_package(tmp_path, installer_only=True)
    sealed["files_by_path"]["upgrade_prep.ps1"]["checkout_and_staged_sha256"] = bad_sha
    result = verify_installed_bindings(app_dir, sealed)
    assert result["ok"] is False
    assert any("invalid checkout_and_staged_sha256" in p for p in result["problems"])


@pytest.mark.parametrize("bad_blob", ["short", "0" * 39, "g" * 40, "0" * 64, None, ""])
def test_invalid_blob_on_compiler_only_rejected(tmp_path, bad_blob):
    """Malformed or missing source_git_blob on installer-only row is rejected."""
    app_dir, sealed = make_synthetic_package(tmp_path, installer_only=True)
    sealed["files_by_path"]["upgrade_prep.ps1"]["source_git_blob"] = bad_blob
    result = verify_installed_bindings(app_dir, sealed)
    assert result["ok"] is False
    assert any("invalid source_git_blob" in p for p in result["problems"])


@pytest.mark.parametrize("bad_blob", ["short", "0" * 39, "g" * 40, "0" * 64])
def test_invalid_blob_on_installed_row_rejected(tmp_path, bad_blob):
    """Malformed source_git_blob on an installed row is rejected."""
    app_dir, sealed = make_synthetic_package(tmp_path, installer_only=True)
    sealed["files_by_path"]["module_000.py"]["source_git_blob"] = bad_blob
    result = verify_installed_bindings(app_dir, sealed)
    assert result["ok"] is False
    assert any("invalid source_git_blob" in p for p in result["problems"])


@pytest.mark.parametrize("count_offset", [-1, 1, -142])
def test_incomplete_binding_counts_rejected(tmp_path, count_offset):
    """Package seals with anything other than 142 bindings are rejected."""
    app_dir, sealed = make_synthetic_package(tmp_path, installer_only=True)
    if count_offset == -1:
        del sealed["files_by_path"]["module_000.py"]
    elif count_offset == 1:
        sealed["files_by_path"]["extra.py"] = {
            "staged_path": "extra.py",
            "source_path": "src/extra.py",
            "source_git_blob": VALID_BLOB,
            "checkout_and_staged_sha256": "0" * 64,
        }
    elif count_offset == -142:
        sealed["files_by_path"] = {}

    result = verify_installed_bindings(app_dir, sealed)
    assert result["ok"] is False
    assert any("expected 142 package source bindings" in p for p in result["problems"])


def test_installer_only_wrong_source_path_rejected(tmp_path):
    """upgrade_prep.ps1 with wrong source_path is rejected as compiler-only."""
    app_dir, sealed = make_synthetic_package(tmp_path, installer_only=True)
    sealed["files_by_path"]["upgrade_prep.ps1"]["source_path"] = "other/upgrade_prep.ps1"
    result = verify_installed_bindings(app_dir, sealed)
    assert result["ok"] is False
    assert any("invalid compiler-only source_path" in p for p in result["problems"])


def test_reporting_no_false_claim_of_142_installed_files(tmp_path):
    """Reports compiler bindings, installed files checked, and compiler-only row separately."""
    app_dir, sealed = make_synthetic_package(tmp_path, installer_only=True)
    result = verify_installed_bindings(app_dir, sealed)
    assert result["ok"] is True
    assert result["compiler_bindings"] == 142
    assert result["installed_files_checked"] == 141
    assert result["files_checked"] == 141
    assert result["files_checked"] != 142
    assert result["compiler_only_row"]["staged_path"] == "upgrade_prep.ps1"
