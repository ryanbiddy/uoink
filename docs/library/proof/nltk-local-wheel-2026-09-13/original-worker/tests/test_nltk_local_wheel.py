"""Focused test suite for NLTK local wheel packaging (GHSA-8mgp-746c-j5xp).

Architectural rules enforced:
1. Synthetic archives are used for comprehensive parser negative tests and boundary controls.
2. The exact upstream wheel artifact is an explicitly optional integration fixture:
   if not present on disk, integration test states skip rather than failing.
3. Mock no acceptance assertions and edit no existing tests.
4. Packaging boundaries fail closed: bad size, bad sha256, tampered RECORD, duplicate
   members, path traversal, device/UNC/ADS members, symlinks, malformed metadata,
   destination reuse, and expected-hash override attempts.
5. Deterministic packaging guarantees: identical bytes produced on repeated builds.
6. NLTK is never imported.
"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import io
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Load build module directly to avoid repo-root scripts.py module collision
BUILD_SCRIPT = REPO_ROOT / "scripts" / "build_nltk_pathsec_wheel.py"
spec = importlib.util.spec_from_file_location("build_nltk_pathsec_wheel", BUILD_SCRIPT)
assert spec is not None and spec.loader is not None
wheel_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wheel_mod)

build_nltk_wheel = wheel_mod.build_nltk_wheel
EXPECTED_WHEEL_NAME = wheel_mod.EXPECTED_WHEEL_NAME
EXPECTED_WHEEL_SHA256 = wheel_mod.EXPECTED_WHEEL_SHA256
EXPECTED_WHEEL_SIZE = wheel_mod.EXPECTED_WHEEL_SIZE
OUTPUT_VERSION = wheel_mod.OUTPUT_VERSION
OUTPUT_WHEEL_NAME = wheel_mod.OUTPUT_WHEEL_NAME
format_record_hash = wheel_mod.format_record_hash
sha256_file = wheel_mod.sha256_file

# Preparation module constants for verification
PREPARE_SCRIPT = REPO_ROOT / "scripts" / "prepare_nltk_pathsec_backport.py"
prep_spec = importlib.util.spec_from_file_location("prepare_nltk_pathsec_backport", PREPARE_SCRIPT)
assert prep_spec is not None and prep_spec.loader is not None
prep_mod = importlib.util.module_from_spec(prep_spec)
prep_spec.loader.exec_module(prep_mod)

EXPECTED_ORIGINAL_HASHES = prep_mod.EXPECTED_ORIGINAL_HASHES
EXPECTED_PATCHED_HASHES = prep_mod.EXPECTED_PATCHED_HASHES


# ==============================================================================
# Synthetic Archive Helpers & Fixtures
# ==============================================================================

def make_synthetic_wheel(
    target_path: Path,
    version: str = "3.10.3",
    dist_info_name: str = "nltk-3.10.3.dist-info",
    metadata_version_header: str = "3.10.3",
    metadata_name_header: str = "nltk",
    tamper_record: bool = False,
    record_hash_mismatch: bool = False,
    record_size_mismatch: bool = False,
    missing_record_file: bool = False,
    extra_unrecorded_member: bool = False,
    duplicate_member: bool = False,
    traversal_member: bool = False,
    device_member: bool = False,
    symlink_member: bool = False,
    include_record_signature: bool = False,
    omit_metadata: bool = False,
    omit_wheel: bool = False,
    omit_version_file: bool = False,
) -> Path:
    """Construct a synthetic wheel zip archive for boundary testing."""
    target_path.parent.mkdir(parents=True, exist_ok=True)

    members: dict[str, bytes] = {}

    # Required files matching the patch
    if not omit_version_file:
        members["nltk/VERSION"] = f"{version}\n".encode("utf-8")

    orig_dir = REPO_ROOT / "vendor/nltk-pathsec/original"
    for rel_path in EXPECTED_ORIGINAL_HASHES:
        posix_rel = Path(rel_path).as_posix()
        src_file = orig_dir / rel_path
        if src_file.is_file():
            members[f"nltk/{posix_rel}"] = src_file.read_bytes()
        else:
            members[f"nltk/{posix_rel}"] = b"# dummy original\n"

    # Dist-info
    if not omit_metadata:
        metadata_content = (
            f"Metadata-Version: 2.4\n"
            f"Name: {metadata_name_header}\n"
            f"Version: {metadata_version_header}\n"
            f"Summary: Natural Language Toolkit\n"
            f"License: Apache License, Version 2.0\n"
            f"Requires-Dist: defusedxml\n"
        ).encode("utf-8")
        members[f"{dist_info_name}/METADATA"] = metadata_content

    if not omit_wheel:
        wheel_content = (
            "Wheel-Version: 1.0\n"
            "Generator: setuptools\n"
            "Root-Is-Purelib: true\n"
            "Tag: py3-none-any\n"
        ).encode("utf-8")
        members[f"{dist_info_name}/WHEEL"] = wheel_content

    if extra_unrecorded_member:
        members["nltk/extra.py"] = b"# extra\n"

    # Build RECORD
    record_lines = []
    for m_name, m_data in sorted(members.items()):
        if extra_unrecorded_member and m_name == "nltk/extra.py":
            continue
        if missing_record_file and m_name == "nltk/VERSION":
            continue

        m_hash = format_record_hash(hashlib.sha256(m_data).digest())
        m_size = len(m_data)

        if record_hash_mismatch and m_name == "nltk/VERSION":
            m_hash = "sha256=tamperedhashvalue1234567890abcdef"
        if record_size_mismatch and m_name == "nltk/VERSION":
            m_size = 99999

        record_lines.append(f"{m_name},{m_hash},{m_size}")

    if not tamper_record:
        record_lines.append(f"{dist_info_name}/RECORD,,")
        members[f"{dist_info_name}/RECORD"] = ("\n".join(record_lines) + "\n").encode("utf-8")

    if include_record_signature:
        members[f"{dist_info_name}/RECORD.jws"] = b'{"payload": "dummy_sig"}\n'

    # Write zip archive
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for m_name, m_data in members.items():
            zinfo = zipfile.ZipInfo(m_name, date_time=(2026, 9, 12, 0, 0, 0))
            zinfo.external_attr = 0o100644 << 16
            zf.writestr(zinfo, m_data)

        if duplicate_member:
            dup_info = zipfile.ZipInfo("nltk/VERSION", date_time=(2026, 9, 12, 0, 0, 0))
            dup_info.external_attr = 0o100644 << 16
            zf.writestr(dup_info, b"duplicate\n")

        if traversal_member:
            trav_info = zipfile.ZipInfo("../../traversal.py", date_time=(2026, 9, 12, 0, 0, 0))
            trav_info.external_attr = 0o100644 << 16
            zf.writestr(trav_info, b"evil\n")

        if device_member:
            dev_info = zipfile.ZipInfo("nltk/CON", date_time=(2026, 9, 12, 0, 0, 0))
            dev_info.external_attr = 0o100644 << 16
            zf.writestr(dev_info, b"device\n")

        if symlink_member:
            sym_info = zipfile.ZipInfo("nltk/symlink_entry", date_time=(2026, 9, 12, 0, 0, 0))
            sym_info.external_attr = (0o120777) << 16
            zf.writestr(sym_info, b"target")

    target_path.write_bytes(buf.getvalue())
    return target_path


@pytest.fixture
def upstream_wheel_fixture() -> Path:
    """Optional fixture for the verified upstream NLTK 3.10.3 wheel."""
    candidates = [
        Path(os.environ.get("UOINK_UPSTREAM_NLTK_WHEEL", "")),
        REPO_ROOT / "_scratch/upstream/nltk-3.10.3-py3-none-any.whl",
        REPO_ROOT / "vendor/nltk-pathsec/dist/nltk-3.10.3-py3-none-any.whl",
    ]
    for c in candidates:
        if str(c) and c.is_file():
            if (
                c.stat().st_size == EXPECTED_WHEEL_SIZE
                and sha256_file(c) == EXPECTED_WHEEL_SHA256
            ):
                return c
    pytest.skip("Upstream NLTK 3.10.3 wheel fixture not found on disk or environment.")


# ==============================================================================
# Portable Parser Negatives & Boundary Controls
# ==============================================================================

def test_wheel_file_not_found(tmp_path: Path) -> None:
    non_existent = tmp_path / "nltk-3.10.3-py3-none-any.whl"
    out_dir = tmp_path / "out"
    with pytest.raises(FileNotFoundError, match="Input wheel file not found"):
        build_nltk_wheel(wheel_path=non_existent, output_dir=out_dir)
    assert not out_dir.exists()


def test_wheel_filename_unexpected(tmp_path: Path) -> None:
    wrong_name = tmp_path / "nltk-3.10.4-py3-none-any.whl"
    wrong_name.write_bytes(b"dummy")
    out_dir = tmp_path / "out"
    with pytest.raises(ValueError, match="Unexpected wheel filename"):
        build_nltk_wheel(wheel_path=wrong_name, output_dir=out_dir)
    assert not out_dir.exists()


def test_wheel_size_mismatch_refused(tmp_path: Path) -> None:
    whl = tmp_path / EXPECTED_WHEEL_NAME
    whl.write_bytes(b"short bytes")
    out_dir = tmp_path / "out"
    with pytest.raises(ValueError, match="size mismatch"):
        build_nltk_wheel(wheel_path=whl, output_dir=out_dir)
    assert not out_dir.exists()


def test_wheel_sha256_mismatch_refused(tmp_path: Path) -> None:
    whl = tmp_path / EXPECTED_WHEEL_NAME
    # Write exact expected byte count, but altered content
    whl.write_bytes(b"0" * EXPECTED_WHEEL_SIZE)
    out_dir = tmp_path / "out"
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        build_nltk_wheel(wheel_path=whl, output_dir=out_dir)
    assert not out_dir.exists()


def test_no_expected_hash_override(tmp_path: Path) -> None:
    whl = tmp_path / EXPECTED_WHEEL_NAME
    whl.write_bytes(b"dummy")
    out_dir = tmp_path / "out"
    with pytest.raises(TypeError, match="Override parameters refused"):
        build_nltk_wheel(
            wheel_path=whl,
            output_dir=out_dir,
            expected_hash="override_hash_value",
        )
    assert not out_dir.exists()


def test_destination_reuse_refused(tmp_path: Path) -> None:
    whl = tmp_path / EXPECTED_WHEEL_NAME
    whl.write_bytes(b"dummy")
    out_dir = tmp_path / "existing_out"
    out_dir.mkdir()
    with pytest.raises(FileExistsError, match="Destination already exists"):
        build_nltk_wheel(wheel_path=whl, output_dir=out_dir)


def test_destination_boundary_overlap_refused(tmp_path: Path) -> None:
    whl = tmp_path / EXPECTED_WHEEL_NAME
    whl.write_bytes(b"dummy")
    # Destination equal to wheel
    with pytest.raises(ValueError, match="Destination.*cannot be inside or equal"):
        build_nltk_wheel(wheel_path=whl, output_dir=whl)


@pytest.mark.parametrize(
    "bad_dest",
    [
        "out/../escape",
        "C:out_dir",
        "out_dir:stream",
        "CON",
        "NUL",
        "//share/out",
    ],
)
def test_unsafe_destination_refused(tmp_path: Path, bad_dest: str) -> None:
    whl = tmp_path / EXPECTED_WHEEL_NAME
    whl.write_bytes(b"dummy")
    with pytest.raises((ValueError, PermissionError)):
        build_nltk_wheel(wheel_path=whl, output_dir=bad_dest)


# Synthetic archive parser validations (exercised on validate_zip_archive_members)

def test_archive_duplicate_member_rejected(tmp_path: Path) -> None:
    archive_path = tmp_path / "test.whl"
    make_synthetic_wheel(archive_path, duplicate_member=True)
    with zipfile.ZipFile(archive_path, "r") as z:
        with pytest.raises(ValueError, match="Duplicate member in archive"):
            wheel_mod.validate_zip_archive_members(z)


def test_archive_path_traversal_member_rejected(tmp_path: Path) -> None:
    archive_path = tmp_path / "test.whl"
    make_synthetic_wheel(archive_path, traversal_member=True)
    with zipfile.ZipFile(archive_path, "r") as z:
        with pytest.raises(ValueError, match="Path traversal in archive member"):
            wheel_mod.validate_zip_archive_members(z)


def test_archive_device_member_rejected(tmp_path: Path) -> None:
    archive_path = tmp_path / "test.whl"
    make_synthetic_wheel(archive_path, device_member=True)
    with zipfile.ZipFile(archive_path, "r") as z:
        with pytest.raises(ValueError, match="Device name in archive member"):
            wheel_mod.validate_zip_archive_members(z)


def test_archive_symlink_member_rejected(tmp_path: Path) -> None:
    archive_path = tmp_path / "test.whl"
    make_synthetic_wheel(archive_path, symlink_member=True)
    with zipfile.ZipFile(archive_path, "r") as z:
        with pytest.raises(PermissionError, match="Symlink member in archive"):
            wheel_mod.validate_zip_archive_members(z)


def test_archive_missing_record_rejected(tmp_path: Path) -> None:
    archive_path = tmp_path / "test.whl"
    make_synthetic_wheel(archive_path, tamper_record=True)
    with zipfile.ZipFile(archive_path, "r") as z:
        with pytest.raises(ValueError, match="Missing original RECORD in archive"):
            wheel_mod.validate_zip_archive_members(z)


def test_archive_record_hash_mismatch_rejected(tmp_path: Path) -> None:
    archive_path = tmp_path / "test.whl"
    make_synthetic_wheel(archive_path, record_hash_mismatch=True)
    with zipfile.ZipFile(archive_path, "r") as z:
        with pytest.raises(ValueError, match="RECORD hash mismatch"):
            wheel_mod.validate_zip_archive_members(z)


def test_archive_record_size_mismatch_rejected(tmp_path: Path) -> None:
    archive_path = tmp_path / "test.whl"
    make_synthetic_wheel(archive_path, record_size_mismatch=True)
    with zipfile.ZipFile(archive_path, "r") as z:
        with pytest.raises(ValueError, match="RECORD size mismatch"):
            wheel_mod.validate_zip_archive_members(z)


def test_archive_member_missing_from_record_rejected(tmp_path: Path) -> None:
    archive_path = tmp_path / "test.whl"
    make_synthetic_wheel(archive_path, extra_unrecorded_member=True)
    with zipfile.ZipFile(archive_path, "r") as z:
        with pytest.raises(ValueError, match="missing from original RECORD"):
            wheel_mod.validate_zip_archive_members(z)


def test_archive_record_member_missing_from_archive_rejected(tmp_path: Path) -> None:
    archive_path = tmp_path / "test.whl"
    make_synthetic_wheel(archive_path, missing_record_file=True)
    # The file is omitted from archive, but RECORD line was deleted; now add RECORD entry without file
    with zipfile.ZipFile(archive_path, "r") as z:
        rec_data = z.read("nltk-3.10.3.dist-info/RECORD").decode("utf-8")
    rec_data = "nltk/ghost.py,sha256=1111111111111111111111111111111111111111111,10\n" + rec_data
    # Recreate zip with phantom record entry
    archive_phantom = tmp_path / "phantom.whl"
    with zipfile.ZipFile(archive_phantom, "w") as zf:
        zf.writestr("nltk-3.10.3.dist-info/RECORD", rec_data)
        zf.writestr("nltk-3.10.3.dist-info/METADATA", "Metadata-Version: 2.4\nName: nltk\nVersion: 3.10.3\n")
        zf.writestr("nltk-3.10.3.dist-info/WHEEL", "Wheel-Version: 1.0\n")
        zf.writestr("nltk/VERSION", "3.10.3\n")
    with zipfile.ZipFile(archive_phantom, "r") as z:
        with pytest.raises(ValueError, match="RECORD entry missing from archive"):
            wheel_mod.validate_zip_archive_members(z)


def test_archive_malformed_metadata_missing_version(tmp_path: Path) -> None:
    archive_path = tmp_path / "test.whl"
    make_synthetic_wheel(archive_path, metadata_version_header="9.9.9")
    with zipfile.ZipFile(archive_path, "r") as z:
        with pytest.raises(ValueError, match="Malformed metadata: expected Version"):
            wheel_mod.validate_zip_archive_members(z)


def test_archive_malformed_metadata_wrong_name(tmp_path: Path) -> None:
    archive_path = tmp_path / "test.whl"
    make_synthetic_wheel(archive_path, metadata_name_header="not-nltk")
    with zipfile.ZipFile(archive_path, "r") as z:
        with pytest.raises(ValueError, match="Malformed metadata: missing or unexpected Name"):
            wheel_mod.validate_zip_archive_members(z)


def test_archive_malformed_wheel_metadata(tmp_path: Path) -> None:
    archive_path = tmp_path / "test.whl"
    make_synthetic_wheel(archive_path, omit_wheel=True)
    with zipfile.ZipFile(archive_path, "r") as z:
        with pytest.raises(ValueError, match="Missing WHEEL in archive"):
            wheel_mod.validate_zip_archive_members(z)


def test_archive_malformed_version_file(tmp_path: Path) -> None:
    archive_path = tmp_path / "test.whl"
    make_synthetic_wheel(archive_path, version="wrong.version")
    with zipfile.ZipFile(archive_path, "r") as z:
        with pytest.raises(ValueError, match="Malformed metadata: VERSION file is"):
            wheel_mod.validate_zip_archive_members(z)


def test_nltk_not_imported() -> None:
    """Invariant: NLTK module must never be imported in memory."""
    assert "nltk" not in sys.modules, "NLTK module unexpectedly imported in test session"


# ==============================================================================
# Explicitly Optional Integration Fixture Tests
# ==============================================================================

def test_upstream_artifact_packaging_full_qualification(
    upstream_wheel_fixture: Path,
    tmp_path: Path,
) -> None:
    """End-to-end qualification of wheel building from pristine upstream artifact."""
    out_dir = tmp_path / "qualified_wheel_output"

    provenance = build_nltk_wheel(
        wheel_path=upstream_wheel_fixture,
        output_dir=out_dir,
    )

    assert provenance["status"] == "SUCCESS"
    assert provenance["upstream_version"] == "3.10.3"
    assert provenance["packaged_version"] == OUTPUT_VERSION
    assert provenance["deterministic"] is True
    assert provenance["member_count"] == 512

    out_wheel = out_dir / OUTPUT_WHEEL_NAME
    assert out_wheel.is_file()

    # Known bit-for-bit reproducible wheel hash
    expected_output_sha256 = "11c885646a44e22fe515b1e487d74b87f82922a580b96d7c3b2a6bc5ead1ccb0"
    actual_sha256 = sha256_file(out_wheel)
    assert actual_sha256 == expected_output_sha256, (
        f"Output wheel hash mismatch: expected {expected_output_sha256}, got {actual_sha256}"
    )

    # Inspect the packaged wheel archive
    with zipfile.ZipFile(out_wheel, "r") as zf:
        members = zf.namelist()
        assert len(members) == 512

        # 1. Distribution directory renamed
        dist_info_members = [m for m in members if ".dist-info" in m]
        assert all(m.startswith("nltk-3.10.3+uoink.pathsec1.dist-info/") for m in dist_info_members)
        assert not any("nltk-3.10.3.dist-info" in m for m in members)

        # 2. Package VERSION updated with exact LF
        version_data = zf.read("nltk/VERSION")
        assert version_data == b"3.10.3+uoink.pathsec1\n"

        # 3. METADATA Version updated
        metadata_text = zf.read("nltk-3.10.3+uoink.pathsec1.dist-info/METADATA").decode("utf-8")
        assert "Version: 3.10.3+uoink.pathsec1" in metadata_text
        assert "Name: nltk" in metadata_text
        assert "License: Apache License, Version 2.0" in metadata_text
        assert "Requires-Dist: defusedxml" in metadata_text

        # 4. No upstream RECORD signatures
        assert not any(m.endswith(".dist-info/RECORD.jws") or m.endswith(".dist-info/RECORD.p7s") for m in members)

        # 5. RECORD recomputed and matches every single member byte-for-byte
        record_text = zf.read("nltk-3.10.3+uoink.pathsec1.dist-info/RECORD").decode("utf-8")
        record_rows = record_text.splitlines()
        assert len(record_rows) == 512

        for row in record_rows:
            r_path, r_hash, r_size = row.split(",")
            if r_path.endswith("/RECORD"):
                assert r_hash == "" and r_size == ""
            else:
                raw_bytes = zf.read(r_path)
                assert len(raw_bytes) == int(r_size)
                computed_h = format_record_hash(hashlib.sha256(raw_bytes).digest())
                assert r_hash == computed_h

        # 6. Patched source file hashes match EXPECTED_PATCHED_HASHES
        for rel_path, exp_hex in EXPECTED_PATCHED_HASHES.items():
            posix_rel = Path(rel_path).as_posix()
            member_name = f"nltk/{posix_rel}"
            file_bytes = zf.read(member_name)
            assert hashlib.sha256(file_bytes).hexdigest() == exp_hex

    # Check provenance file
    prov_file = out_dir / f"{OUTPUT_WHEEL_NAME}.provenance.json"
    assert prov_file.is_file()
    loaded_prov = json.loads(prov_file.read_text(encoding="utf-8"))
    assert loaded_prov["status"] == "SUCCESS"
    assert loaded_prov["output_wheel"]["sha256"] == expected_output_sha256
    assert loaded_prov["output_wheel"]["size"] == 1799214


def test_deterministic_packaging_repeated_build(
    upstream_wheel_fixture: Path,
    tmp_path: Path,
) -> None:
    """Verify that building twice into fresh directories produces byte-for-byte identical wheels."""
    out_dir_a = tmp_path / "repeat_build_a"
    out_dir_b = tmp_path / "repeat_build_b"

    build_nltk_wheel(wheel_path=upstream_wheel_fixture, output_dir=out_dir_a)
    build_nltk_wheel(wheel_path=upstream_wheel_fixture, output_dir=out_dir_b)

    whl_a = out_dir_a / OUTPUT_WHEEL_NAME
    whl_b = out_dir_b / OUTPUT_WHEEL_NAME

    bytes_a = whl_a.read_bytes()
    bytes_b = whl_b.read_bytes()

    assert bytes_a == bytes_b, "Repeat packaging produced diverging wheel bytes!"
    assert sha256_file(whl_a) == sha256_file(whl_b)
