#!/usr/bin/env python3
"""Deterministic preparation utility for NLTK pathsec backport (GHSA-8mgp-746c-j5xp).

Applies the exact reviewed unified patch to a clean copy of NLTK 3.10.3 in an
explicitly new destination after validating boundary invariants and source hashes.

Constraints & Integrity Rules:
- Never imports nltk (and never exits merely because the caller imported it).
- Never writes to staging; staging is strictly read-only.
- Never fetches remote resources or accesses the network.
- Never accepts path traversal ('..').
- Never overwrites an existing destination.
- Refuses source/destination symlinks and Windows reparse points, including all ancestors.
- Refuses destination inside source, source inside destination, or any overlap.
- Copies without following symlinks.
- Validates original input hashes in source and validates copied files before patching.
- Applies the exact reviewed unified patch directly rather than duplicated replacements.
- Verifies patch integrity against expected hash.
- Writes preparation receipt strictly inside the destination using exclusive creation ('x').
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath

EXPECTED_VERSION = "3.10.3"

# Exact SHA-256 hashes for NLTK 3.10.3 inputs
EXPECTED_ORIGINAL_HASHES: dict[str, str] = {
    os.path.normpath("classify/maxent.py"): "11f704cf6cd2a43b51cb13634e9cdbc46b0e8394e1e291e9b66036d6a59c2583",
    os.path.normpath("parse/transitionparser.py"): "ed55985d08ed38333d007c5e5c19170a4dc19009e871ab616d198a3da92eea70",
    os.path.normpath("tag/perceptron.py"): "9d619a5ce7533c7eb388a70fedca8dcf0fb78279e1744e2abfdfcca9abd459ea",
}

# Expected hash for the reviewed backport patch
EXPECTED_PATCH_SHA256 = "56d70eece6711a52d0082b066f79ff1388c1cbe6db19d3eb09bf98b5ae11f71b"

# Expected hashes for patched outputs
EXPECTED_PATCHED_HASHES: dict[str, str] = {
    os.path.normpath("classify/maxent.py"): "60645d1be785066c083f2458153f7e83931ebd8db20d976a8d34dea100f83f3c",
    os.path.normpath("parse/transitionparser.py"): "8dcc54a30557450084858b3ed7f559697f945593f50a2fdc9f4a08e3bbbbdd60",
    os.path.normpath("tag/perceptron.py"): "31d1577b9b04b22aace4fdead2b3f7bcb48864af45bfa5210f1e1d32a3cb81b9",
}

COVERED_APIS = [
    "TransitionParser.train",
    "TransitionParser.parse",
    "AveragedPerceptron.save",
    "AveragedPerceptron.load",
    "PerceptronTagger.save_to_json",
    "save_maxent_params",
]


def sha256_file(path: str | Path) -> str:
    """Compute sha256 digest of a file."""
    verify_no_links_or_reparse(Path(path).absolute(), 'Hash input')
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def is_symlink_or_reparse(p: Path) -> bool:
    """Check whether a path is a symlink or Windows reparse point without following it."""
    try:
        st = os.lstat(p)
        if stat.S_ISLNK(st.st_mode):
            return True
        # Windows reparse tag check
        if getattr(st, "st_reparse_tag", 0) != 0:
            return True
        # Windows FILE_ATTRIBUTE_REPARSE_POINT (0x0400)
        file_attrs = getattr(st, "st_file_attributes", 0)
        if bool(file_attrs & 0x0400):
            return True
    except FileNotFoundError:
        pass
    return False


def verify_no_links_or_reparse(target: Path, label: str) -> None:
    """Verify that neither target nor any of its ancestors is a symlink or reparse point."""
    # Inspect from the root toward the leaf before any following probe.
    for ancestor in [*reversed(target.absolute().parents), target.absolute()]:
        if is_symlink_or_reparse(ancestor):
            raise PermissionError(
                f"Ancestor {ancestor} of {label} path is a symlink or Windows reparse point."
            )


def safe_local_path(value: str | Path) -> Path:
    text = str(value)
    win = PureWindowsPath(text)
    if not text.strip() or '\x00' in text or text.startswith(('\\\\', '//')):
        raise ValueError('Local non-device path required')
    if win.drive and not win.is_absolute():
        raise ValueError('Drive-relative path refused')
    if '..' in win.parts or '..' in Path(text).parts:
        raise ValueError('Path traversal refused')
    for part in win.parts:
        if part == win.anchor:
            continue
        if ':' in part or part.rstrip(' .') != part or re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])(?:\..*)?', part):
            raise ValueError('Device, stream or ambiguous Windows path refused')
    result = Path(os.path.abspath(text))
    verify_no_links_or_reparse(result, 'Input')
    return result


def tree_hashes(directory: Path) -> dict[str, str]:
    result = {}
    for current, dirs, files in os.walk(directory, followlinks=False):
        for name in dirs + files:
            verify_no_links_or_reparse(Path(current) / name, 'Tree entry')
        for name in files:
            path = Path(current) / name
            if not stat.S_ISREG(path.lstat().st_mode):
                raise PermissionError('Non-regular source entry')
            result[path.relative_to(directory).as_posix()] = sha256_file(path)
    return result


def validate_destination_boundary(dst_path: str | Path, src_dir: Path) -> Path:
    """Validate that destination path is non-existent, safe, unlinked, and does not overlap source."""
    dst_str = str(dst_path)
    if not dst_str or not dst_str.strip():
        raise ValueError("Destination path must not be empty.")

    raw_dst = safe_local_path(dst_str)
    if ".." in raw_dst.parts:
        raise ValueError(f"Path traversal ('..') detected in destination path: {dst_str}")

    # Inspect without resolving away evidence
    verify_no_links_or_reparse(raw_dst, "Destination")

    # Check containment and overlap before checking exists
    if raw_dst == src_dir or raw_dst.is_relative_to(src_dir):
        raise ValueError(f"Destination {raw_dst} cannot be inside or equal to source {src_dir}.")

    if src_dir == raw_dst or src_dir.is_relative_to(raw_dst):
        raise ValueError(f"Source {src_dir} cannot be inside destination {raw_dst}.")

    resolved_dst = raw_dst.resolve()
    resolved_src = src_dir.resolve()

    if resolved_dst == resolved_src or resolved_dst.is_relative_to(resolved_src):
        raise ValueError(f"Resolved destination {resolved_dst} overlaps source {resolved_src}.")

    if resolved_src == resolved_dst or resolved_src.is_relative_to(resolved_dst):
        raise ValueError(f"Resolved source {resolved_src} overlaps destination {resolved_dst}.")

    if raw_dst.exists():
        raise FileExistsError(f"Destination already exists: {raw_dst}. Refusing to overwrite.")

    if resolved_dst.exists():
        raise FileExistsError(f"Resolved destination already exists: {resolved_dst}. Refusing to overwrite.")

    return raw_dst


def validate_source_tree(src_path: str | Path) -> Path:
    """Validate source tree exists, has no symlinks/reparse points, matches version and hashes."""
    src_p = safe_local_path(src_path)
    if not src_p.is_dir():
        raise FileNotFoundError(f"Source directory not found: {src_p}")

    verify_no_links_or_reparse(src_p, "Source")

    # Check for symlinks/reparse points inside source tree
    for root, dirs, files in os.walk(src_p, followlinks=False):
        for d in dirs:
            dp = Path(root) / d
            if is_symlink_or_reparse(dp):
                raise PermissionError(f"Source directory contains symlink or reparse point: {dp}")
        for f in files:
            fp = Path(root) / f
            if is_symlink_or_reparse(fp):
                raise PermissionError(f"Source file contains symlink or reparse point: {fp}")

    # Check VERSION
    version_file = src_p / "VERSION"
    if not version_file.is_file():
        raise FileNotFoundError(f"VERSION file not found in source: {version_file}")

    with open(version_file, "r", encoding="utf-8") as vf:
        version = vf.read().strip()

    if version != EXPECTED_VERSION:
        raise ValueError(
            f"Unsupported source version '{version}'. Expected exactly '{EXPECTED_VERSION}'."
        )

    # Check original hashes in source
    for rel_path, expected_hash in EXPECTED_ORIGINAL_HASHES.items():
        full_path = src_p / rel_path
        if not full_path.is_file():
            raise FileNotFoundError(f"Required source file missing: {full_path}")
        observed = sha256_file(full_path)
        if observed != expected_hash:
            raise ValueError(
                f"Source hash mismatch for {rel_path}!\n"
                f"  Expected: {expected_hash}\n"
                f"  Observed: {observed}"
            )

    return src_p


def validate_receipt_path(receipt_arg: str | Path | None, dst_dir: Path) -> Path:
    """Ensure receipt path lives strictly inside the newly created destination."""
    if receipt_arg is None:
        receipt_path = dst_dir / "nltk-pathsec-receipt.json"
    else:
        raw_r = Path(receipt_arg)
        safe_local_path(raw_r)
        if ".." in raw_r.parts:
            raise ValueError(f"Path traversal ('..') detected in receipt path: {receipt_arg}")
        if raw_r.is_absolute():
            # Must be strictly within dst_dir
            try:
                raw_r.relative_to(dst_dir)
            except ValueError:
                raise ValueError(
                    f"Receipt path {raw_r} must live inside destination directory {dst_dir}."
                )
            receipt_path = raw_r
        else:
            receipt_path = dst_dir / raw_r

    receipt_path = safe_local_path(receipt_path)
    if receipt_path == dst_dir or not receipt_path.is_relative_to(dst_dir) or receipt_path.suffix != '.json':
        raise ValueError('Receipt path must live inside destination and name a JSON file')
    return receipt_path


def copy_source_tree(src_dir: Path, dst_dir: Path) -> None:
    """Copy source tree to destination without following symlinks."""
    def _copy_file_no_follow(src_file, dst_file):
        sp = Path(src_file)
        verify_no_links_or_reparse(sp, 'Copy source')
        verify_no_links_or_reparse(Path(dst_file), 'Copy destination')
        if is_symlink_or_reparse(sp):
            raise PermissionError(f"Refusing to copy symlink/reparse point: {sp}")
        shutil.copyfile(src_file, dst_file, follow_symlinks=False)
        shutil.copymode(src_file, dst_file, follow_symlinks=False)

    shutil.copytree(
        src_dir,
        dst_dir,
        symlinks=False,
        copy_function=_copy_file_no_follow,
    )


def validate_copied_source(dst_dir: Path) -> None:
    """Validate that copied files in destination match expected original hashes before patching."""
    for rel_path, expected_hash in EXPECTED_ORIGINAL_HASHES.items():
        target = dst_dir / rel_path
        if not target.is_file():
            raise FileNotFoundError(f"Copied source file missing before patch: {target}")
        actual_hash = sha256_file(target)
        if actual_hash != expected_hash:
            raise ValueError(
                f"Copied source file altered or corrupted before patch for {rel_path}!\n"
                f"  Expected: {expected_hash}\n"
                f"  Observed: {actual_hash}"
            )


def apply_reviewed_patch(patch_path: Path, dst_dir: Path) -> dict[str, str]:
    """Apply unified diff patch directly to dst_dir and return dict of patched hashes."""
    if not patch_path.is_file():
        raise FileNotFoundError(f"Patch file not found: {patch_path}")

    actual_patch_hash = sha256_file(patch_path)
    required_hash = EXPECTED_PATCH_SHA256
    if actual_patch_hash != required_hash:
        raise ValueError(
            f"Patch hash mismatch (patch tampered or unexpected)!\n"
            f"  Expected: {required_hash}\n"
            f"  Observed: {actual_patch_hash}"
        )

    patch_text = patch_path.read_text(encoding="utf-8")
    lines = patch_text.splitlines()

    # Split into file patches
    file_patches: list[tuple[str, list[str]]] = []
    current_file: str | None = None
    current_lines: list[str] = []

    for line in lines:
        if line.startswith("diff --git "):
            if current_file and current_lines:
                file_patches.append((current_file, current_lines))
            parts = line.split()
            # extract path from b/nltk/...
            current_file = parts[-1]
            if current_file.startswith("b/"):
                current_file = current_file[2:]
            current_lines = [line]
        else:
            if current_lines is not None:
                current_lines.append(line)

    if current_file and current_lines:
        file_patches.append((current_file, current_lines))

    hunk_header_re = re.compile(r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@")
    patched_hashes: dict[str, str] = {}

    for rel_file, flines in file_patches:
        if not rel_file.startswith('nltk/') or os.path.normpath(rel_file[5:]) not in EXPECTED_ORIGINAL_HASHES:
            raise ValueError('Unexpected patch target')
        norm_name = os.path.normpath(rel_file[5:])
        if norm_name in patched_hashes:
            raise ValueError('Duplicate patch target')
        target_file = dst_dir / rel_file[5:]
        verify_no_links_or_reparse(target_file, 'Patch target')

        if not target_file.is_file():
            raise FileNotFoundError(f"Patch target file not found in destination: {rel_file}")

        orig_content = target_file.read_text(encoding="utf-8")
        file_lines = orig_content.splitlines()

        hunks = []
        i = 0
        while i < len(flines):
            line = flines[i]
            m = hunk_header_re.match(line)
            if m:
                old_start = int(m.group(1))
                old_len = int(m.group(2)) if m.group(2) else 1
                new_start = int(m.group(3))
                new_len = int(m.group(4)) if m.group(4) else 1

                hunk_lines = []
                i += 1
                while i < len(flines) and not flines[i].startswith("diff --git ") and not flines[i].startswith("@@"):
                    hunk_lines.append(flines[i])
                    i += 1
                hunks.append((old_start, old_len, new_start, new_len, hunk_lines))
            else:
                i += 1

        line_offset = 0
        for old_start, old_len, new_start, new_len, hlines in hunks:
            expected_old = []
            replacement = []
            for hline in hlines:
                if not hline:
                    expected_old.append("")
                    replacement.append("")
                elif hline.startswith(" "):
                    expected_old.append(hline[1:])
                    replacement.append(hline[1:])
                elif hline.startswith("-"):
                    expected_old.append(hline[1:])
                elif hline.startswith("+"):
                    replacement.append(hline[1:])
                elif hline.startswith("\\ No newline at end of file"):
                    pass
                else:
                    expected_old.append(hline)
                    replacement.append(hline)

            target_idx = old_start - 1 + line_offset
            matched_idx = None
            if len(expected_old) != old_len or len(replacement) != new_len or target_idx != new_start - 1:
                raise ValueError('Patch hunk count/location mismatch')
            for delta in [0]:
                candidate = target_idx + delta
                if 0 <= candidate and candidate + len(expected_old) <= len(file_lines):
                    if file_lines[candidate:candidate + len(expected_old)] == expected_old:
                        matched_idx = candidate
                        break

            if matched_idx is None:
                raise ValueError(
                    f"Hunk at {rel_file}:{old_start} failed to match destination file content."
                )

            file_lines[matched_idx:matched_idx + len(expected_old)] = replacement
            line_offset += len(replacement) - len(expected_old)

        new_content = "\n".join(file_lines)
        if orig_content.endswith("\n"):
            new_content += "\n"

        target_file.write_text(new_content, encoding="utf-8", newline="\n")

        norm_rel = os.path.normpath(str(Path(rel_file).as_posix()))
        if norm_rel.startswith("nltk" + os.sep) or norm_rel.startswith("nltk/"):
            norm_rel = norm_rel[5:]
        patched_hashes[norm_rel] = sha256_file(target_file)

    if set(patched_hashes) != set(EXPECTED_PATCHED_HASHES):
        raise ValueError('Incomplete patch output')
    # Verify patched hashes against expected
    for rel_p, exp_h in EXPECTED_PATCHED_HASHES.items():
        norm_key = os.path.normpath(rel_p)
        if norm_key in patched_hashes and patched_hashes[norm_key] != exp_h:
            raise ValueError(
                f"Patched output hash mismatch for {rel_p}!\n"
                f"  Expected: {exp_h}\n"
                f"  Observed: {patched_hashes[norm_key]}"
            )

    return patched_hashes


def prepare_backport(
    src: str | Path,
    dst: str | Path,
    patch_file: str | Path | None = None,
    receipt_path: str | Path | None = None,
) -> dict:
    """Execute the full backport preparation pipeline deterministically."""
    # 1. Validate inputs and boundaries BEFORE any write
    src_dir = validate_source_tree(src)
    dst_dir = validate_destination_boundary(dst, src_dir)
    final_receipt_path = validate_receipt_path(receipt_path, dst_dir)

    default_patch = (
        Path(__file__).resolve().parent.parent
        / "vendor"
        / "nltk-pathsec"
        / "nltk-3.10.3-pathsec.patch"
    )
    patch_path = safe_local_path(patch_file if patch_file else default_patch)
    if not patch_path.is_file():
        raise FileNotFoundError(f"Patch file not found: {patch_path}")
    patch_sha256 = sha256_file(patch_path)
    if patch_sha256 != EXPECTED_PATCH_SHA256:
        raise ValueError('Patch hash mismatch')
    complete_original = tree_hashes(src_dir)
    receipt_relative = final_receipt_path.relative_to(dst_dir).as_posix().casefold()
    if any(receipt_relative == name.casefold() or receipt_relative.startswith(name.casefold() + '/') for name in complete_original):
        raise ValueError('Receipt would replace a source entry')

    # 2. Copy source tree to new destination without following symlinks
    copy_source_tree(src_dir, dst_dir)

    # 3. Validate copied original files in destination before patching
    validate_copied_source(dst_dir)
    if tree_hashes(dst_dir) != complete_original:
        raise ValueError('Copied tree hash mismatch')

    # 4. Apply exact reviewed patch
    patched_hashes = apply_reviewed_patch(patch_path, dst_dir)
    expected_tree = dict(complete_original)
    expected_tree.update({Path(k).as_posix(): v for k, v in EXPECTED_PATCHED_HASHES.items()})
    if tree_hashes(dst_dir) != expected_tree or tree_hashes(src_dir) != complete_original:
        raise ValueError('Source or prepared tree changed unexpectedly')

    # 5. Construct truthful preparation receipt
    actual_orig_hashes = {
        rel: sha256_file(src_dir / rel) for rel in EXPECTED_ORIGINAL_HASHES
    }

    receipt = {
        "status": "SUCCESS",
        "advisory": "GHSA-8mgp-746c-j5xp",
        "target_version": EXPECTED_VERSION,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "source_directory": str(src_dir),
        "destination_directory": str(dst_dir),
        "patch_file": str(patch_path),
        "patch_sha256": patch_sha256,
        "original_hashes": actual_orig_hashes,
        "patched_hashes": patched_hashes,
        "covered_apis": COVERED_APIS,
        "source_tree_hashes": complete_original,
        "prepared_tree_hashes": expected_tree,
        "release_ready": False,
    }

    # 6. Write receipt exclusively inside the destination
    verify_no_links_or_reparse(final_receipt_path, 'Final receipt')
    final_receipt_path.parent.mkdir(parents=True, exist_ok=True)
    with open(final_receipt_path, "x", encoding="utf-8") as rf:
        json.dump(receipt, rf, indent=2)
        rf.write("\n")

    return receipt


def main():
    parser = argparse.ArgumentParser(
        description="Deterministic preparation utility for NLTK pathsec backport (GHSA-8mgp-746c-j5xp)."
    )
    default_staging = Path(
        "E:/AI/projects/uoink/checkouts/Yoink-library/installer/staging/python/Lib/site-packages/nltk"
    )
    parser.add_argument(
        "--src",
        default=str(default_staging) if default_staging.is_dir() else None,
        required=not default_staging.is_dir(),
        help="Path to clean, unpatched NLTK 3.10.3 source directory.",
    )
    parser.add_argument(
        "--dst",
        required=True,
        help="Path to explicitly new destination directory.",
    )
    parser.add_argument(
        "--patch-file",
        default=None,
        help="Optional path to unified diff patch file.",
    )
    parser.add_argument(
        "--receipt",
        default=None,
        help="Optional path to write receipt JSON file (must be inside destination).",
    )

    args = parser.parse_args()

    try:
        receipt = prepare_backport(
            src=args.src,
            dst=args.dst,
            patch_file=args.patch_file,
            receipt_path=args.receipt,
        )
        print("NLTK Pathsec Backport Preparation Successful!")
        print(f"  Source:      {receipt['source_directory']}")
        print(f"  Destination: {receipt['destination_directory']}")
        print(f"  Patch Hash:  {receipt['patch_sha256']}")
        print("  Patched file hashes:")
        for k, v in receipt["patched_hashes"].items():
            print(f"    {k}: {v}")
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
