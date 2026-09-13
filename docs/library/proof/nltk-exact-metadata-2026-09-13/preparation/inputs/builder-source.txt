#!/usr/bin/env python3
"""Deterministic packaging utility for NLTK pathsec backport (GHSA-8mgp-746c-j5xp).

Constructs nltk-3.10.3+uoink.pathsec1-py3-none-any.whl from an existing upstream
nltk-3.10.3-py3-none-any.whl by using the accepted preparation utility on a fresh
extracted package, updating distribution metadata, and deterministically
recomputing RECORD.

Integrity & Bounded Packaging Rules:
- Never imports NLTK and never executes setup hooks.
- No network access inside the packaging utility.
- Pins upstream wheel to exact SHA-256 ff9598a8e20518ee0d557745890cc4435b9578489e2dcbc69c4f81fa060caf7c.
- Strictly refuses any expected-hash override.
- Validates zip members and original RECORD hashes/sizes.
- Rejects duplicates, path traversal, symlinks/reparse paths, and device/UNC/ADS paths.
- Rejects destination reuse (destination directory must be fresh and non-existent).
- Uses deterministic zip timestamps, member ordering, and file modes.
- Updates package VERSION, distribution directory, and METADATA Version.
- Preserves upstream license and dependency metadata.
- Recomputes every RECORD entry and removes any upstream RECORD signature.
- Produces full build provenance JSON alongside the wheel.
"""

from __future__ import annotations

import argparse
import base64
import csv
import email
import io
import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath

# Upstream wheel pins
EXPECTED_WHEEL_NAME = "nltk-3.10.3-py3-none-any.whl"
EXPECTED_WHEEL_SHA256 = "ff9598a8e20518ee0d557745890cc4435b9578489e2dcbc69c4f81fa060caf7c"
EXPECTED_WHEEL_SIZE = 1798643

UPSTREAM_VERSION = "3.10.3"
OUTPUT_VERSION = "3.10.3+uoink.pathsec1"
OUTPUT_WHEEL_NAME = "nltk-3.10.3+uoink.pathsec1-py3-none-any.whl"

UPSTREAM_DIST_INFO = "nltk-3.10.3.dist-info"
OUTPUT_DIST_INFO = "nltk-3.10.3+uoink.pathsec1.dist-info"

DEFAULT_ZIP_TIMESTAMP = (2026, 9, 12, 0, 0, 0)
DEFAULT_FILE_MODE = 0o100644

import zipfile


def sha256_file(path: str | Path) -> str:
    """Compute sha256 digest of a local regular file."""
    p = safe_local_path(path)
    verify_no_links_or_reparse(p, "Hash input")
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def is_symlink_or_reparse(p: Path) -> bool:
    """Check whether a path is a symlink or Windows reparse point without following it."""
    try:
        st = os.lstat(p)
        if stat.S_ISLNK(st.st_mode):
            return True
        if getattr(st, "st_reparse_tag", 0) != 0:
            return True
        file_attrs = getattr(st, "st_file_attributes", 0)
        if bool(file_attrs & 0x0400):
            return True
    except FileNotFoundError:
        pass
    return False


def verify_no_links_or_reparse(target: Path, label: str) -> None:
    """Verify that neither target nor any of its ancestors is a symlink or reparse point."""
    target_abs = target.absolute()
    for ancestor in [*reversed(target_abs.parents), target_abs]:
        if is_symlink_or_reparse(ancestor):
            raise PermissionError(
                f"Ancestor {ancestor} of {label} path is a symlink or Windows reparse point."
            )


def safe_local_path(value: str | Path) -> Path:
    """Validate that value is a safe local non-device non-UNC path."""
    text = str(value)
    win = PureWindowsPath(text)
    if not text.strip() or "\x00" in text or text.startswith(("\\\\", "//")):
        raise ValueError("Local non-device path required")
    if win.drive and not win.is_absolute():
        raise ValueError("Drive-relative path refused")
    if ".." in win.parts or ".." in Path(text).parts:
        raise ValueError("Path traversal refused")
    for part in win.parts:
        if part == win.anchor:
            continue
        if ":" in part or part.rstrip(" .") != part or re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])(?:\..*)?", part):
            raise ValueError("Device, stream or ambiguous Windows path refused")
    result = Path(os.path.abspath(text))
    verify_no_links_or_reparse(result, "Input")
    return result


def format_record_hash(digest: bytes) -> str:
    """Encode binary digest into PEP 376 RECORD hash format."""
    return "sha256=" + base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def validate_destination_boundary(dst_path: str | Path, wheel_path: Path) -> Path:
    """Ensure destination path is safe, unlinked, does not overlap wheel, and does not pre-exist."""
    dst_str = str(dst_path)
    if not dst_str or not dst_str.strip():
        raise ValueError("Destination path must not be empty.")

    raw_dst = safe_local_path(dst_str)
    verify_no_links_or_reparse(raw_dst, "Destination")

    if raw_dst == wheel_path or raw_dst.is_relative_to(wheel_path):
        raise ValueError(f"Destination {raw_dst} cannot be inside or equal to wheel {wheel_path}.")

    if wheel_path == raw_dst or wheel_path.is_relative_to(raw_dst):
        raise ValueError(f"Wheel {wheel_path} cannot be inside destination {raw_dst}.")

    resolved_dst = raw_dst.resolve()
    resolved_whl = wheel_path.resolve()

    if resolved_dst == resolved_whl or resolved_dst.is_relative_to(resolved_whl):
        raise ValueError(f"Resolved destination {resolved_dst} overlaps wheel {resolved_whl}.")

    if resolved_whl == resolved_dst or resolved_whl.is_relative_to(resolved_dst):
        raise ValueError(f"Resolved wheel {resolved_whl} overlaps destination {resolved_dst}.")

    if raw_dst.exists():
        raise FileExistsError(f"Destination already exists: {raw_dst}. Refusing destination reuse.")

    if resolved_dst.exists():
        raise FileExistsError(f"Resolved destination already exists: {resolved_dst}. Refusing destination reuse.")

    return raw_dst


def validate_zip_archive_members(
    archive: zipfile.ZipFile,
) -> tuple[dict[str, tuple[str, int]], str, str]:
    """Inspect and strictly validate archive member safety and original RECORD integrity.

    Returns:
        (record_entries, metadata_text, version_text)
    """
    seen_names: set[str] = set()
    file_members: dict[str, zipfile.ZipInfo] = {}

    for info in archive.infolist():
        name = info.filename
        if not name or "\\" in name or any(p in ("", ".", "..") for p in name.rstrip("/").split("/")):
            raise ValueError(f"Path traversal in archive member: {name} (or ambiguous spelling)")
        normalized = name.rstrip("/").casefold()
        if normalized in seen_names:
            raise ValueError(f"Duplicate member in archive: {name}")
        seen_names.add(normalized)

        posix_parts = PurePosixPath(name).parts
        win_parts = PureWindowsPath(name).parts

        if ".." in posix_parts or ".." in win_parts or name.startswith(("/", "\\")):
            raise ValueError(f"Path traversal in archive member: {name}")

        if name.startswith(("//", "\\\\")):
            raise ValueError(f"UNC path in archive member: {name}")

        for part in posix_parts:
            if ":" in part:
                raise ValueError(f"Stream or ADS path in archive member: {name}")
            if re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])(?:\..*)?", part):
                raise ValueError(f"Device name in archive member: {name}")
            if part.rstrip(" .") != part:
                raise ValueError(f"Ambiguous trailing character in archive member: {name}")

        mode = (info.external_attr >> 16) & 0o170000
        if mode == 0o120000 or (hasattr(info, "is_symlink") and info.is_symlink()):
            raise PermissionError(f"Symlink member in archive: {name}")

        if not info.is_dir():
            file_members[name] = info

    record_path = f"{UPSTREAM_DIST_INFO}/RECORD"
    if record_path not in file_members:
        raise ValueError(f"Missing original RECORD in archive: {record_path}")

    record_bytes = archive.read(record_path)
    record_lines = csv.reader(io.StringIO(record_bytes.decode("utf-8")), strict=True)
    record_entries: dict[str, tuple[str, int]] = {}
    seen_records = set()

    for parts in record_lines:
        line = repr(parts)
        if len(parts) != 3:
            raise ValueError(f"Malformed RECORD line: {line}")
        entry_path, entry_hash, entry_size = parts[0], parts[1], parts[2]
        if entry_path.casefold() in seen_records:
            raise ValueError('Duplicate RECORD entry: ' + entry_path)
        seen_records.add(entry_path.casefold())
        if entry_path == record_path:
            if entry_hash or entry_size:
                raise ValueError('RECORD self entry must have empty hash and size')
            # RECORD row for RECORD itself has empty hash and size
            continue
        if entry_path.startswith(f"{UPSTREAM_DIST_INFO}/RECORD."):
            # upstream RECORD signature row
            continue
        if not entry_hash.startswith("sha256="):
            raise ValueError(f"Unsupported hash algorithm in RECORD row: {line}")
        try:
            expected_size = int(entry_size)
        except ValueError:
            raise ValueError(f"Invalid size in RECORD row: {line}")
        record_entries[entry_path] = (entry_hash, expected_size)

    if record_path.casefold() not in seen_records:
        raise ValueError('Missing RECORD self entry')

    # Verify every member in RECORD matches actual archive content
    for entry_path, (expected_hash, expected_size) in record_entries.items():
        if entry_path not in file_members:
            raise ValueError(f"RECORD entry missing from archive: {entry_path}")
        content = archive.read(entry_path)
        if len(content) != expected_size:
            raise ValueError(
                f"RECORD size mismatch for {entry_path}: expected {expected_size}, got {len(content)}"
            )
        actual_hash = format_record_hash(hashlib.sha256(content).digest())
        if actual_hash != expected_hash:
            raise ValueError(
                f"RECORD hash mismatch for {entry_path}: expected {expected_hash}, got {actual_hash}"
            )

    # Verify every file member in archive is recorded
    for name in file_members:
        if name == record_path or name.startswith(f"{UPSTREAM_DIST_INFO}/RECORD."):
            continue
        if name not in record_entries:
            raise ValueError(f"Archive member {name} missing from original RECORD")

    # Validate distribution metadata
    metadata_path = f"{UPSTREAM_DIST_INFO}/METADATA"
    if metadata_path not in file_members:
        raise ValueError(f"Missing METADATA in archive: {metadata_path}")
    metadata_text = archive.read(metadata_path).decode("utf-8")
    parsed_meta = email.message_from_string(metadata_text)
    for header in ('Metadata-Version', 'Name', 'Version', 'Requires-Python'):
        if len(parsed_meta.get_all(header) or []) > 1:
            raise ValueError('Duplicate metadata singleton: ' + header)
    if not re.search(r"^Metadata-Version:\s*\S+", metadata_text, re.MULTILINE):
        raise ValueError("Malformed metadata: missing Metadata-Version header")
    if not re.search(r"^Name:\s*nltk\s*$", metadata_text, re.MULTILINE):
        raise ValueError("Malformed metadata: missing or unexpected Name header")
    if not re.search(rf"^Version:\s*{re.escape(UPSTREAM_VERSION)}\s*$", metadata_text, re.MULTILINE):
        raise ValueError(f"Malformed metadata: expected Version {UPSTREAM_VERSION}")

    wheel_meta_path = f"{UPSTREAM_DIST_INFO}/WHEEL"
    if wheel_meta_path not in file_members:
        raise ValueError(f"Missing WHEEL in archive: {wheel_meta_path}")
    wheel_meta_text = archive.read(wheel_meta_path).decode("utf-8")
    parsed_wheel = email.message_from_string(wheel_meta_text)
    if (parsed_wheel.get_all('Wheel-Version') != ['1.0'] or
            parsed_wheel.get_all('Root-Is-Purelib') != ['true'] or
            parsed_wheel.get_all('Tag') != ['py3-none-any']):
        raise ValueError('Malformed metadata: missing Wheel-Version 1.0 in WHEEL or incompatible wheel tags')
    if not re.search(r"^Wheel-Version:\s*1\.0\s*$", wheel_meta_text, re.MULTILINE):
        raise ValueError("Malformed metadata: missing Wheel-Version 1.0 in WHEEL")

    version_path = "nltk/VERSION"
    if version_path not in file_members:
        raise ValueError(f"Missing VERSION file in archive: {version_path}")
    version_text = archive.read(version_path).decode("utf-8").strip()
    if version_text != UPSTREAM_VERSION:
        raise ValueError(f"Malformed metadata: VERSION file is '{version_text}', expected '{UPSTREAM_VERSION}'")

    return record_entries, metadata_text, version_text


def _load_preparation_utility():
    """Load the accepted preparation utility without importing NLTK or executing hooks."""
    scripts_dir = Path(__file__).resolve().parent
    prep_path = scripts_dir / "prepare_nltk_pathsec_backport.py"
    if not prep_path.is_file():
        raise FileNotFoundError(f"Preparation utility not found at {prep_path}")
    spec = importlib.util.spec_from_file_location("prepare_nltk_pathsec_backport", prep_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load specification for {prep_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_nltk_wheel(
    wheel_path: str | Path,
    output_dir: str | Path,
    patch_file: str | Path | None = None,
    **kwargs,
) -> dict:
    """Build the patched, deterministically packaged NLTK wheel.

    Strictly refuses any expected-hash override via kwargs or parameters.
    """
    if kwargs:
        raise TypeError(
            f"Override parameters refused (no expected-hash override permitted): {list(kwargs.keys())}"
        )

    # 1. Validate wheel path & boundaries
    raw_wheel = safe_local_path(wheel_path)
    verify_no_links_or_reparse(raw_wheel, "Input wheel")
    if not raw_wheel.is_file():
        raise FileNotFoundError(f"Input wheel file not found: {raw_wheel}")

    if raw_wheel.name != EXPECTED_WHEEL_NAME:
        raise ValueError(
            f"Unexpected wheel filename '{raw_wheel.name}'. Expected '{EXPECTED_WHEEL_NAME}'."
        )

    # 2. Validate destination directory boundary
    out_dir = validate_destination_boundary(output_dir, raw_wheel)

    wheel_bytes = raw_wheel.read_bytes()
    actual_size = len(wheel_bytes)
    if actual_size != EXPECTED_WHEEL_SIZE:
        raise ValueError(
            f"Input wheel size mismatch: expected {EXPECTED_WHEEL_SIZE} bytes, got {actual_size}"
        )

    actual_sha256 = hashlib.sha256(wheel_bytes).hexdigest()
    if actual_sha256 != EXPECTED_WHEEL_SHA256:
        raise ValueError(
            f"Input wheel SHA256 mismatch!\n"
            f"  Expected: {EXPECTED_WHEEL_SHA256}\n"
            f"  Observed: {actual_sha256}"
        )

    # 3. Inspect archive members and validate RECORD
    with zipfile.ZipFile(io.BytesIO(wheel_bytes), "r") as archive:
        orig_record, metadata_text, _ = validate_zip_archive_members(archive)

        # 4. Extract pristine NLTK package tree into a fresh isolated scratch space
        scratch_dir = safe_local_path(Path(__file__).absolute().parent.parent / '_scratch')
        scratch_dir.mkdir(parents=True, exist_ok=True)
        tmp_base = safe_local_path(scratch_dir / f'.tmp_whl_build_{os.getpid()}_{time.time_ns()}')
        assert tmp_base.parent == scratch_dir
        tmp_base.mkdir(exist_ok=False)
        try:
            tmp_root = tmp_base
            src_pkg = tmp_root / "pristine_src" / "nltk"
            prepared_pkg = tmp_root / "prepared_src" / "nltk"
            src_pkg.parent.mkdir(parents=True, exist_ok=True)

            for info in archive.infolist():
                if info.is_dir():
                    continue
                if info.filename.startswith("nltk/"):
                    sub_rel = info.filename[len("nltk/"):]
                    target_file = src_pkg / sub_rel
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    target_file.write_bytes(archive.read(info))

            # 5. Execute accepted preparation utility
            prep_mod = _load_preparation_utility()
            prep_receipt = prep_mod.prepare_backport(
                src=src_pkg,
                dst=prepared_pkg,
                patch_file=patch_file,
            )
            if prep_receipt.get("status") != "SUCCESS":
                raise RuntimeError(f"Preparation backport failed: {prep_receipt}")

            # 6. Update VERSION in prepared package
            version_target = prepared_pkg / "VERSION"
            version_target.write_text(f"{OUTPUT_VERSION}\n", encoding="utf-8", newline="\n")

            # 7. Collect all output members and contents
            new_members: dict[str, bytes] = {}

            # Add all files from prepared_pkg under nltk/ (excluding preparation receipt)
            for root, _, files in os.walk(prepared_pkg, followlinks=False):
                for f in files:
                    fp = Path(root) / f
                    rel_p = fp.relative_to(prepared_pkg).as_posix()
                    if rel_p == "nltk-pathsec-receipt.json":
                        continue
                    member_name = f"nltk/{rel_p}"
                    new_members[member_name] = fp.read_bytes()

            # Process dist-info members from original archive
            for info in archive.infolist():
                if info.is_dir():
                    continue
                name = info.filename
                if name.startswith(f"{UPSTREAM_DIST_INFO}/"):
                    sub = name[len(f"{UPSTREAM_DIST_INFO}/"):]
                    if sub == "RECORD" or sub.startswith("RECORD."):
                        # Skip RECORD and signatures
                        continue
                    new_name = f"{OUTPUT_DIST_INFO}/{sub}"
                    if sub == "METADATA":
                        # Update METADATA Version header
                        updated_meta = re.sub(
                            r"^Version:\s*3\.10\.3\s*$",
                            f"Version: {OUTPUT_VERSION}",
                            metadata_text,
                            flags=re.MULTILINE,
                        )
                        if updated_meta == metadata_text:
                            raise ValueError("Failed to update Version header in METADATA")
                        new_members[new_name] = updated_meta.encode("utf-8")
                    else:
                        new_members[new_name] = archive.read(info)

            # 8. Recompute RECORD
            # Members are sorted alphabetically, with RECORD as the final entry
            sorted_non_record = sorted(new_members.keys())
            record_lines = []
            for m_name in sorted_non_record:
                m_bytes = new_members[m_name]
                digest = hashlib.sha256(m_bytes).digest()
                h_str = format_record_hash(digest)
                record_lines.append(f"{m_name},{h_str},{len(m_bytes)}")

            record_name = f"{OUTPUT_DIST_INFO}/RECORD"
            record_lines.append(f"{record_name},,")
            record_bytes = ("\n".join(record_lines) + "\n").encode("utf-8")
            new_members[record_name] = record_bytes

            final_member_order = sorted_non_record + [record_name]

            # A fixed timestamp and stored entries avoid ambient epoch/zlib drift.
            zip_time = DEFAULT_ZIP_TIMESTAMP

            # 10. Write wheel deterministically into fresh output directory
            out_dir.mkdir(parents=True, exist_ok=False)
            target_wheel = out_dir / OUTPUT_WHEEL_NAME

            with zipfile.ZipFile(
                target_wheel,
                mode="w",
                compression=zipfile.ZIP_STORED,
            ) as zf:
                for m_name in final_member_order:
                    content = new_members[m_name]
                    zinfo = zipfile.ZipInfo(m_name, date_time=zip_time)
                    zinfo.create_system = 3
                    zinfo.external_attr = DEFAULT_FILE_MODE << 16
                    zinfo.compress_type = zipfile.ZIP_STORED
                    zf.writestr(zinfo, content)

            # 11. Construct build provenance record
            wheel_sha = sha256_file(target_wheel)
            wheel_sz = target_wheel.stat().st_size

            provenance = {
                "status": "SUCCESS",
                "advisory": "GHSA-8mgp-746c-j5xp",
                "upstream_wheel": {
                    "filename": raw_wheel.name,
                    "sha256": actual_sha256,
                    "size": actual_size,
                },
                "output_wheel": {
                    "filename": target_wheel.name,
                    "sha256": wheel_sha,
                    "size": wheel_sz,
                },
                "upstream_version": UPSTREAM_VERSION,
                "packaged_version": OUTPUT_VERSION,
                "patch": {
                    "file": prep_receipt.get("patch_file"),
                    "sha256": prep_receipt.get("patch_sha256"),
                },
                "original_hashes": prep_receipt.get("original_hashes"),
                "patched_hashes": prep_receipt.get("patched_hashes"),
                "covered_apis": prep_receipt.get("covered_apis"),
                "changed_members": [
                    "nltk/VERSION",
                    "nltk/classify/maxent.py",
                    "nltk/parse/transitionparser.py",
                    "nltk/tag/perceptron.py",
                    f"{OUTPUT_DIST_INFO}/METADATA",
                    f"{OUTPUT_DIST_INFO}/RECORD",
                ],
                "renamed_dist_info": {
                    "from": UPSTREAM_DIST_INFO,
                    "to": OUTPUT_DIST_INFO,
                },
                "member_count": len(final_member_order),
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "deterministic": True,
                "archive_format": "ZIP_STORED; fixed timestamp, sorted members and Unix file modes",
                "work_directory": str(tmp_base),
                "release_ready": False,
            }

            prov_file = out_dir / f"{OUTPUT_WHEEL_NAME}.provenance.json"
            prov_file.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")

            # Also write generic provenance.json in the output directory
            (out_dir / "provenance.json").write_text(
                json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
            )
        finally:
            # Preserve work on success or failure for review; no recursive cleanup.
            pass

    return provenance


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deterministic local wheel builder for NLTK pathsec backport."
    )
    parser.add_argument(
        "--wheel",
        "-w",
        default=None,
        help="Path to pinned upstream nltk-3.10.3-py3-none-any.whl.",
    )
    parser.add_argument(
        "--out-dir",
        "--out",
        "-o",
        dest="out_dir",
        default=None,
        help="Fresh, non-existent destination directory.",
    )
    parser.add_argument(
        "--patch-file",
        default=None,
        help="Optional path to reviewed unified diff patch.",
    )
    parser.add_argument(
        "positional_args",
        nargs="*",
        help="Optional positional arguments: [wheel] [out_dir]",
    )

    args = parser.parse_args()

    wheel_arg = args.wheel
    out_dir_arg = args.out_dir

    if args.positional_args:
        if wheel_arg is None and len(args.positional_args) >= 1:
            wheel_arg = args.positional_args[0]
        if out_dir_arg is None and len(args.positional_args) >= 2:
            out_dir_arg = args.positional_args[1]

    if not wheel_arg or not out_dir_arg:
        parser.error("Both --wheel and --out-dir are required.")

    try:
        provenance = build_nltk_wheel(
            wheel_path=wheel_arg,
            output_dir=out_dir_arg,
            patch_file=args.patch_file,
        )
        print("NLTK Pathsec Local Wheel Packaging Successful!")
        print(f"  Output Wheel:  {provenance['output_wheel']['filename']}")
        print(f"  SHA-256:       {provenance['output_wheel']['sha256']}")
        print(f"  Size:          {provenance['output_wheel']['size']} bytes")
        print(f"  Members:       {provenance['member_count']}")
        print(f"  Destination:   {out_dir_arg}")
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
