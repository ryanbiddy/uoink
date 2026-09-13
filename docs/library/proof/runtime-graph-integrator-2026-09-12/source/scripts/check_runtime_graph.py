"""Check runtime dependency graph and wheel compatibility for Windows x64 CPython 3.13.

Inspects saved PyPI JSON and wheel METADATA offline without importing packages
or executing setup/build hooks. Evaluates PEP 508 markers, extras propagation to
fixed point, wheel tags, and constraint closures.
"""

from __future__ import annotations

import argparse
import email
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import os
import stat
from urllib.parse import urlsplit
import re
import sys
from typing import Any

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.tags import Tag, compatible_tags, cpython_tags
from packaging.utils import parse_wheel_filename
from packaging.version import InvalidVersion, Version


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCK = ROOT / "requirements-installer-lock.txt"
DEFAULT_PROOF_DIR = ROOT / "docs" / "library" / "proof" / "runtime-graph-01-2026-09-12"

PACKAGE_NAME_REGEX = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?$")
EXTRA_NAME_REGEX = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?$")
SHA256_HEX_REGEX = re.compile(r"^[0-9a-fA-F]{64}$")

PIN_REGEX = re.compile(
    r"^([A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)(?:\[([A-Za-z0-9_.,\s-]+)\])?==([^\s;]+)$"
)

# Canonical environment for Windows x86-64 CPython 3.13 (non-free-threaded)
TARGET_ENV: dict[str, str] = {
    "implementation_name": "cpython",
    "implementation_version": "3.13.15",
    "os_name": "nt",
    "platform_machine": "AMD64",
    "platform_python_implementation": "CPython",
    "platform_release": "10",
    "platform_system": "Windows",
    "platform_version": "10.0.26100",
    "python_full_version": "3.13.15",
    "python_version": "3.13",
    "sys_platform": "win32",
    "extra": "",
}



def _unique_json(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON key: ' + key)
            result[key] = value
        return result
    try:
        return json.loads(text, object_pairs_hook=unique)
    except RecursionError as exc:
        raise ValueError('JSON nesting exceeds parser limit') from exc


def _no_links(path):
    for parent in [*reversed(path.absolute().parents), path.absolute()]:
        try:
            info = parent.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Symlink/reparse evidence path: ' + str(parent))


def _bounded_path(root, relative):
    raw_root = os.fspath(root)
    win_root = PureWindowsPath(raw_root)
    if (not raw_root or '\x00' in raw_root or raw_root.startswith(('\\\\', '//')) or
            (win_root.drive and not win_root.root)):
        raise ValueError('Unsafe evidence root')
    for part in win_root.parts[1:] if win_root.anchor else win_root.parts:
        if (part == '..' or ':' in part or part.rstrip(' .') != part or
                re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])(?:\..*)?', part)):
            raise ValueError('Unsafe evidence root')
    root = Path(root).absolute()
    if '..' in root.parts or str(root).startswith(('\\\\', '//')):
        raise ValueError('Unsafe evidence root')
    _no_links(root)
    if not isinstance(relative, str) or not relative or '\x00' in relative:
        raise ValueError('Invalid evidence path')
    relative = relative.replace('\\', '/')
    win = PureWindowsPath(relative)
    if win.drive or win.root or relative.startswith('/'):
        raise ValueError('Absolute path in evidence')
    parts = PurePosixPath(relative).parts
    if '..' in parts:
        raise ValueError('Path traversal in evidence')
    for part in parts:
        if ':' in part or part.rstrip(' .') != part or re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])(?:\..*)?', part):
            raise ValueError('Device/stream evidence path refused')
    result = root.joinpath(*parts)
    if result == root:
        raise ValueError('Evidence must name a file')
    _no_links(result)
    return result


def _covered_bytes(root, relative, verified):
    path = _bounded_path(root, relative)
    key = path.relative_to(Path(root).absolute()).as_posix()
    if not isinstance(verified, dict) or key not in verified:
        raise ValueError('Manifest coverage failure: ' + key)
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != verified[key]:
        raise ValueError('Evidence changed after manifest verification: ' + key)
    return path, data


def _artifact_url(url):
    if not isinstance(url, str) or re.search(r'[\x00-\x20\\]', url):
        return False
    try:
        parsed = urlsplit(url)
        return (parsed.scheme == 'https' and bool(parsed.hostname) and
                parsed.username is None and parsed.password is None and
                not parsed.fragment and parsed.port in (None, 443))
    except ValueError:
        return False


def canonical_name(value: str) -> str:
    """Normalize package names per PEP 503."""
    return re.sub(r"[-_.]+", "-", value).lower()


def validate_package_name(name: str) -> bool:
    """Validate package name per PEP 508."""
    return bool(PACKAGE_NAME_REGEX.fullmatch(name))


def validate_extra_name(extra: str) -> bool:
    """Validate extra name per PEP 508."""
    return bool(EXTRA_NAME_REGEX.fullmatch(extra))


def get_supported_wheel_tags(
    python_version: tuple[int, int] = (3, 13), platform: str = "win_amd64"
) -> set[Tag]:
    """Generate all supported wheel tags for Windows x86-64 CPython 3.13 non-free-threaded.

    Explicitly specifies cp313 ABI (excluding cp313t free-threaded) and cp313 interpreter,
    strictly targeting the designated platform without host platform leakage or older
    interpreter none tags.
    """
    tags: set[Tag] = set()
    # Explicitly CPython 3.13 non-free-threaded (cp313 ABI)
    tags.update(
        cpython_tags(
            python_version=python_version,
            abis=["cp313"],
            platforms=[platform],
        )
    )
    # ABI3 forward compatibility for CPython 3.2 through 3.13 on target platform (abi3 ABI only)
    for minor in range(2, python_version[1] + 1):
        tags.add(Tag(f"cp3{minor}", "abi3", platform))

    # Compatible pure-python and interpreter tags with explicit cp313 interpreter and platform
    tags.update(
        compatible_tags(
            python_version=python_version,
            interpreter="cp313",
            platforms=[platform],
        )
    )
    # Explicitly remove any older interpreter none tags (e.g. cp312-none, cp311-none)
    return {
        t
        for t in tags
        if not (t.abi == "none" and t.interpreter != "cp313" and not t.interpreter.startswith("py"))
    }


def parse_lock(path: Path) -> dict[str, str]:
    """Parse name==version pins from a requirements lockfile."""
    text = path.read_text(encoding="utf-8")
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    if not lines:
        raise ValueError(f"{path}: selection is empty")

    locked: dict[str, str] = {}
    for line_no, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = PIN_REGEX.fullmatch(line)
        if not match:
            raise ValueError(f"{path}:{line_no}: expected exact name==version pin")
        name, extras, ver = match.groups()
        if not validate_package_name(name):
            raise ValueError(f"{path}:{line_no}: invalid package name '{name}'")
        try:
            Version(ver)
        except InvalidVersion as exc:
            raise ValueError(f"{path}:{line_no}: invalid version '{ver}' for '{name}': {exc}")

        cname = canonical_name(name)
        if cname in [key.split("[")[0] for key in locked]:
            raise ValueError(f"{path}:{line_no}: duplicate package {name}")
        locked[f"{cname}[{extras}]" if extras else cname] = ver
    return locked


def parse_selection(path: Path) -> dict[str, str]:
    """Parse selection from JSON or lockfile, validating names, versions, and duplicates."""
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"Selection file is empty: {path}")

    if path.suffix == ".json" or text.startswith("{") or text.startswith("["):
        try:
            data = _unique_json(text)
        except Exception as exc:
            raise ValueError(f"Malformed JSON in selection {path}: {exc}")

        if isinstance(data, dict):
            raw_dict = (
                data.get("selected")
                or data.get("packages")
                or data.get("pins")
                or data
            )
            if not isinstance(raw_dict, dict) or not raw_dict:
                raise ValueError(f"Selection JSON in {path} contains no package mappings")

            locked: dict[str, str] = {}
            for k, v in raw_dict.items():
                if k.startswith("_"):
                    raise ValueError("Invalid package name in selection: " + k)
                # Support root extras in key e.g. "uvicorn[standard]"
                match = PIN_REGEX.fullmatch(f"{k}=={v}")
                if match:
                    pkg_name, extras_str, ver_str = match.groups()
                else:
                    pkg_name, extras_str, ver_str = k, None, str(v)

                if not validate_package_name(pkg_name):
                    raise ValueError(f"Invalid package name in selection: '{pkg_name}'")
                try:
                    Version(ver_str)
                except InvalidVersion as exc:
                    raise ValueError(f"Invalid version '{ver_str}' for '{pkg_name}': {exc}")

                cname = canonical_name(pkg_name)
                # Form composite key if extras specified
                store_key = f"{cname}[{extras_str}]" if extras_str else cname
                if cname in [k.split("[")[0] for k in locked]:
                    raise ValueError(f"Duplicate package '{pkg_name}' in selection {path}")
                locked[store_key] = str(ver_str)
            if not locked:
                raise ValueError(f"Selection JSON in {path} contains no valid package entries")
            return locked

        elif isinstance(data, list):
            if not data:
                raise ValueError(f"Selection JSON array in {path} is empty")
            locked: dict[str, str] = {}
            for item in data:
                if not isinstance(item, str):
                    raise ValueError(f"Expected string pin in selection list: {item}")
                match = PIN_REGEX.fullmatch(item.strip())
                if not match:
                    raise ValueError(f"Expected exact name==version pin in list: '{item}'")
                name, extras_str, ver = match.groups()
                if not validate_package_name(name):
                    raise ValueError(f"Invalid package name: '{name}'")
                try:
                    Version(ver)
                except InvalidVersion as exc:
                    raise ValueError(f"Invalid version '{ver}' for '{name}': {exc}")
                cname = canonical_name(name)
                store_key = f"{cname}[{extras_str}]" if extras_str else cname
                if cname in [k.split("[")[0] for k in locked]:
                    raise ValueError(f"Duplicate package '{name}' in selection {path}")
                locked[store_key] = ver
            return locked

        raise ValueError(f"Unrecognized selection JSON structure in {path}")

    return parse_lock(path)


def parse_metadata_text(content: str) -> dict[str, Any]:
    """Parse wheel METADATA headers."""
    msg = email.message_from_string(content)
    for singleton in ('Name', 'Version', 'Requires-Python'):
        if len(msg.get_all(singleton) or []) > 1:
            raise ValueError('Duplicate METADATA singleton: ' + singleton)
    requires_dist = msg.get_all("Requires-Dist") or []
    requires_python = msg.get("Requires-Python")
    name = msg.get("Name")
    version = msg.get("Version")
    provides_extra = msg.get_all("Provides-Extra") or []
    return {
        "name": name,
        "version": version,
        "requires_dist": requires_dist,
        "requires_python": requires_python,
        "provides_extra": provides_extra,
    }


def verify_evidence_integrity(proof_dir):
    """Verify retained byte hashes before any dependent evidence is consumed."""
    verified, seen, errors = {}, set(), []
    try:
        manifest_path = None
        for name in ('SHA256.json', 'manifest.json', 'evidence_manifest.json'):
            candidate = _bounded_path(proof_dir, name)
            if candidate.is_file():
                manifest_path = candidate
                break
        if manifest_path is None:
            return False, ['Missing evidence manifest'], {}
        raw = manifest_path.read_text(encoding='utf8')
        if not raw:
            return False, ['Empty manifest'], {}
        try:
            parsed = _unique_json(raw)
        except ValueError as exc:
            return False, ['Malformed manifest JSON: ' + str(exc)], {}
        files = parsed.get('files', parsed) if isinstance(parsed, dict) else None
        if not isinstance(files, dict) or not files:
            return False, ['Manifest contains no entries'], {}
        for name, value in files.items():
            try:
                digest = value.get('sha256') if isinstance(value, dict) else value
                if not isinstance(digest, str) or not SHA256_HEX_REGEX.fullmatch(digest):
                    raise ValueError('Invalid SHA256 value for ' + str(name))
                target = _bounded_path(proof_dir, name)
                key = target.relative_to(Path(proof_dir).absolute()).as_posix()
                if key.casefold() in seen:
                    raise ValueError('Duplicate normalized manifest entry: ' + name)
                seen.add(key.casefold())
                actual = hashlib.sha256(target.read_bytes()).hexdigest()
                if actual != digest.lower():
                    raise ValueError('Tampered/mismatched evidence: ' + name)
                verified[key] = actual
            except (OSError, ValueError) as exc:
                errors.append(str(exc))
    except (OSError, ValueError) as exc:
        errors.append(str(exc))
    return not errors, errors, verified


def find_pypi_json_for_package(proof_dir, cname, version=None, verified_files=None):
    """Read only an enumerated package record, bound to its manifest bytes."""
    names = ([f'{cname}-{version}.json', f'{cname}@{version}.json'] if version else [])
    names += [f'{cname}.json', f"{cname.replace('-', '_')}.json", f"{cname.replace('-', '.')}.json"]
    try:
        for name in dict.fromkeys(names):
            relative = 'pypi/' + name
            candidate = _bounded_path(proof_dir, relative)
            if candidate.is_file():
                path, data = _covered_bytes(proof_dir, relative, verified_files)
                parsed = _unique_json(data.decode('utf8'))
                if not isinstance(parsed, dict) or not isinstance(parsed.get('info', {}), dict):
                    raise ValueError('Malformed PyPI record structure')
                if not isinstance(parsed.get('releases', {}), dict) or not isinstance(parsed.get('urls', []), list):
                    raise ValueError('Malformed PyPI release structure')
                info_name = parsed.get('info', {}).get('name')
                if info_name is not None and canonical_name(info_name) != cname:
                    raise ValueError('PyPI package Name mismatch')
                return path, parsed, []
    except (OSError, ValueError, TypeError, UnicodeError) as exc:
        return None, None, [str(exc)]
    return None, None, [f"PyPI JSON not found for package '{cname}'"]


def check_wheel_for_release(
    cname: str,
    version: str,
    release_files: list[dict[str, Any]],
    supported_tags: set[Tag],
    target_env: dict[str, str],
) -> dict[str, Any]:
    """Find compatible Windows x64 CPython 3.13 wheel, validating hashes, URLs, tags, and Requires-Python."""
    compatible_wheels: list[dict[str, Any]] = []
    incompatible_wheels: list[dict[str, Any]] = []
    yanked_wheels: list[dict[str, Any]] = []
    rejected_invalid: list[str] = []

    if not isinstance(release_files, list):
        return {'status': 'NO_WHEELS', 'error': 'Malformed release files list'}
    for file_info in release_files:
        if not isinstance(file_info, dict) or not isinstance(file_info.get('filename'), str):
            rejected_invalid.append('Malformed wheel record')
            continue
        filename = file_info.get("filename", "")
        if not filename.endswith(".whl") or file_info.get("packagetype") != "bdist_wheel":
            continue

        # Match package name and version in wheel filename
        try:
            w_name, w_ver, _, wheel_tags = parse_wheel_filename(filename)
        except Exception as exc:
            rejected_invalid.append(f"{filename}: invalid wheel filename ({exc})")
            continue

        if canonical_name(w_name) != cname:
            rejected_invalid.append(
                f"{filename}: package name '{w_name}' does not match selected '{cname}'"
            )
            continue

        try:
            if Version(str(w_ver)) != Version(version):
                rejected_invalid.append(
                    f"{filename}: version '{w_ver}' does not match selected '{version}'"
                )
                continue
        except Exception:
            if str(w_ver) != version:
                continue

        # Reject missing or invalid wheel URL
        url = file_info.get("url")
        if not _artifact_url(url):
            rejected_invalid.append(f"{filename}: missing or invalid URL '{url}'")
            continue

        # Reject missing or invalid SHA256 digest
        digests = file_info.get("digests") or {}
        if not isinstance(digests, dict):
            rejected_invalid.append('Malformed wheel digests')
            continue
        sha256 = digests.get("sha256")
        if not sha256 or not isinstance(sha256, str) or not SHA256_HEX_REGEX.fullmatch(sha256.strip()):
            rejected_invalid.append(f"{filename}: missing or invalid SHA256 digest '{sha256}'")
            continue

        is_yanked = bool(file_info.get("yanked"))
        yanked_reason = file_info.get("yanked_reason")

        tag_match = bool(wheel_tags & supported_tags)

        req_py = file_info.get("requires_python")
        py_match = True
        if req_py:
            try:
                py_spec = SpecifierSet(req_py)
                py_match = py_spec.contains(target_env["python_full_version"])
            except Exception:
                # Reject malformed constraint instead of accepting it!
                rejected_invalid.append(f"{filename}: malformed Requires-Python '{req_py}'")
                py_match = False

        wheel_record = {
            "filename": filename,
            "size": file_info.get("size"),
            "sha256": sha256.strip().lower(),
            "url": url,
            "core_metadata": file_info.get("core-metadata") or file_info.get("core_metadata"),
            "requires_python": req_py,
            "is_yanked": is_yanked,
            "yanked_reason": yanked_reason,
            "tag_match": tag_match,
            "py_match": py_match,
        }

        if is_yanked:
            yanked_wheels.append(wheel_record)
            continue

        if tag_match and py_match:
            compatible_wheels.append(wheel_record)
        else:
            incompatible_wheels.append(wheel_record)

    if compatible_wheels:
        # Prefer specific Windows CPython 3.13 native wheels over ABI3 over pure Python
        def sort_key(w: dict[str, Any]) -> int:
            fn = w["filename"]
            if "cp313-cp313-win_amd64" in fn:
                return 3
            if "abi3-win_amd64" in fn:
                return 2
            if "py3-none-any" in fn or "py2.py3-none-any" in fn:
                return 1
            return 0

        compatible_wheels.sort(key=sort_key, reverse=True)
        selected_wheel = compatible_wheels[0]
        return {
            "status": "OK",
            "wheel": selected_wheel,
            "compatible_count": len(compatible_wheels),
            "incompatible_count": len(incompatible_wheels),
            "yanked_count": len(yanked_wheels),
            "rejected_invalid": rejected_invalid,
        }

    if yanked_wheels and not incompatible_wheels:
        return {
            "status": "YANKED",
            "error": f"All available matching wheels for {cname}=={version} are yanked: {yanked_wheels[0].get('yanked_reason')}",
            "yanked_wheels": yanked_wheels,
            "rejected_invalid": rejected_invalid,
        }

    if incompatible_wheels:
        reasons: list[str] = []
        for w in incompatible_wheels:
            fn = w["filename"]
            if not w["tag_match"]:
                reasons.append(f"{fn} (incompatible tags)")
            elif not w["py_match"]:
                reasons.append(f"{fn} (Requires-Python {w['requires_python']} excludes 3.13)")
        return {
            "status": "INCOMPATIBLE_TAGS",
            "error": f"No compatible Windows x64 CPython 3.13 wheel found for {cname}=={version}. Available wheels: {', '.join(reasons[:5])}",
            "incompatible_wheels": incompatible_wheels,
            "yanked_count": len(yanked_wheels),
            "rejected_invalid": rejected_invalid,
        }

    return {
        "status": "NO_WHEELS",
        "error": f"No wheel distributions found for {cname}=={version} in release files",
        "release_files_count": len(release_files),
        "rejected_invalid": rejected_invalid,
    }


def find_exact_wheel_metadata_file(
    proof_dir: Path,
    cname: str,
    version: str,
    wheel_filename: str,
    verified_files: dict[str, str] | None = None,
    target_env: dict[str, str] | None = None,
) -> tuple[Path | None, dict[str, Any] | None, list[str]]:
    """Find exact wheel METADATA file without wildcards, globs, or fallback to other releases."""
    relative = 'metadata/' + wheel_filename + '.metadata'
    errors = []
    try:
        target_file, data = _covered_bytes(proof_dir, relative, verified_files)
        parsed = parse_metadata_text(data.decode('utf8'))
    except (OSError, ValueError, UnicodeError) as exc:
        return None, None, ['Missing or invalid exact wheel METADATA: ' + str(exc)]

    # Validate Name and Version match selected package
    meta_name = parsed.get("name")
    meta_ver = parsed.get("version")
    if not meta_name or canonical_name(meta_name) != cname:
        errors.append(
            f"METADATA Name mismatch in {target_file.name}: expected '{cname}', got '{meta_name}'"
        )
    if not meta_ver:
        errors.append(f"METADATA missing Version in {target_file.name}")
    else:
        try:
            if Version(meta_ver) != Version(version):
                errors.append(
                    f"METADATA Version mismatch in {target_file.name}: expected '{version}', got '{meta_ver}'"
                )
        except Exception:
            if str(meta_ver) != version:
                errors.append(
                    f"METADATA Version mismatch in {target_file.name}: expected '{version}', got '{meta_ver}'"
                )

    # Check METADATA Requires-Python
    meta_req_py = parsed.get("requires_python")
    if meta_req_py and target_env:
        try:
            meta_py_spec = SpecifierSet(meta_req_py)
            if not meta_py_spec.contains(target_env["python_full_version"]):
                errors.append(
                    f"METADATA Requires-Python '{meta_req_py}' excludes target {target_env['python_full_version']}"
                )
        except Exception as exc:
            errors.append(f"Malformed METADATA Requires-Python '{meta_req_py}': {exc}")

    if errors:
        return None, None, errors

    return target_file, parsed, []


def check_runtime_graph(
    selection: dict[str, str],
    proof_dir: Path,
    target_env: dict[str, str] | None = None,
    verify_manifest: bool = True,
    root_extras: dict[str, set[str]] | None = None,
) -> dict[str, Any]:
    """Execute complete runtime graph verification against captured proof metadata.

    Enforces manifest boundedness, SHA256 integrity, exact wheel matching,
    CPython 3.13 tag compatibility, and fixed-point extras propagation.
    """
    if target_env is None:
        target_env = dict(TARGET_ENV)

    supported_tags = get_supported_wheel_tags(python_version=(3, 13), platform="win_amd64")

    # Step 0: Evidence manifest integrity and boundedness
    manifest_ok = True
    manifest_errors: list[str] = []
    verified_files: dict[str, str] = {}

    if not verify_manifest:
        # Per brief rule: No integrity-bypass option may produce PASS
        manifest_ok = False
        manifest_errors.append("Integrity check bypassed: integrity-bypass cannot produce PASS")
    else:
        manifest_ok, manifest_errors, verified_files = verify_evidence_integrity(proof_dir)

    # Empty selections cannot pass
    selection_errors: list[str] = []
    if any(target_env.get(key) != value for key, value in TARGET_ENV.items()):
        selection_errors.append('Target environment differs from fixed Windows CPython 3.13 target')
    if not selection:
        selection_errors.append("Empty selection cannot pass")

    # Process input selection and extract root extras
    selected_versions: dict[str, str] = {}
    pkg_active_extras: dict[str, set[str]] = {}

    for raw_k, ver_str in selection.items():
        if not isinstance(raw_k, str) or not isinstance(ver_str, str):
            selection_errors.append('Package and version must be strings')
            continue
        if "[" in raw_k and raw_k.endswith("]"):
            base_name, extras_part = raw_k[:-1].split("[", 1)
            if not extras_part.strip():
                selection_errors.append(f"Refused malformed empty root extra: '{raw_k}'")
                continue
            cname = canonical_name(base_name)
            parsed_extras = set()
            for e in extras_part.split(","):
                clean_e = e.strip()
                if not validate_extra_name(clean_e):
                    selection_errors.append(f"Refused invalid root extra name: '{clean_e}' in '{raw_k}'")
                    continue
                parsed_extras.add(canonical_name(clean_e))
            pkg_active_extras.setdefault(cname, set()).update(parsed_extras)
        else:
            cname = canonical_name(raw_k)

        if not validate_package_name(cname):
            selection_errors.append(f"Invalid package name in selection: '{raw_k}'")
            continue

        try:
            Version(ver_str)
        except InvalidVersion as exc:
            selection_errors.append(f"Invalid version '{ver_str}' for '{cname}': {exc}")
            continue

        if cname in selected_versions:
            selection_errors.append(f"Duplicate package in selection: '{cname}'")
            continue

        selected_versions[cname] = str(ver_str)
        if cname not in pkg_active_extras:
            pkg_active_extras[cname] = set()

    if root_extras:
        for r_pkg, r_exts in root_extras.items():
            cname = canonical_name(r_pkg)
            if cname in selected_versions:
                for re_item in r_exts:
                    if not validate_extra_name(re_item):
                        selection_errors.append(f"Refused invalid root extra '{re_item}' for '{cname}'")
                    else:
                        pkg_active_extras[cname].add(canonical_name(re_item))

    active_edges: list[dict[str, Any]] = []
    missing_packages: list[dict[str, Any]] = []
    conflicting_constraints: list[dict[str, Any]] = []
    wheel_details: dict[str, Any] = {}
    incomplete_evidence: list[dict[str, Any]] = []
    wheel_failures: list[dict[str, Any]] = []
    marker_errors: list[dict[str, Any]] = []
    direct_url_errors: list[dict[str, Any]] = []

    # Step 1: Inspect wheel and METADATA for every selected package
    package_metadata_map: dict[str, dict[str, Any]] = {}

    for cname, version in (sorted(selected_versions.items()) if manifest_ok else []):
        pypi_path, pypi_json, pypi_errs = find_pypi_json_for_package(
            proof_dir, cname, version, verified_files=verified_files if verify_manifest else None
        )
        if pypi_errs or not pypi_json:
            incomplete_evidence.append({
                "package": cname,
                "version": version,
                "error": pypi_errs[0] if pypi_errs else f"Missing captured PyPI JSON for {cname}",
            })
            continue

        # Look up release files for the exact version
        releases = pypi_json.get("releases", {})
        release_files = releases.get(version)
        if release_files is None:
            if pypi_json.get("info", {}).get("version") == version and "urls" in pypi_json:
                release_files = pypi_json.get("urls", [])
            else:
                incomplete_evidence.append({
                    "package": cname,
                    "version": version,
                    "error": f"PyPI JSON does not contain release files for version {version}",
                })
                continue

        wheel_res = check_wheel_for_release(
            cname, version, release_files, supported_tags, target_env
        )
        if wheel_res["status"] != "OK":
            wheel_failures.append({
                "package": cname,
                "version": version,
                "status": wheel_res["status"],
                "error": wheel_res.get("error", "Wheel check failed"),
                "rejected_invalid": wheel_res.get("rejected_invalid", []),
            })
            continue

        wheel_info = wheel_res["wheel"]
        wheel_details[cname] = wheel_info

        # Extract requirements exclusively from exact wheel METADATA (no wildcards or fallbacks)
        meta_path, meta_dict, meta_errs = find_exact_wheel_metadata_file(
            proof_dir,
            cname,
            version,
            wheel_info["filename"],
            verified_files=verified_files if verify_manifest else None,
            target_env=target_env,
        )

        if meta_errs or not meta_dict:
            incomplete_evidence.append({
                "package": cname,
                "version": version,
                "error": meta_errs[0] if meta_errs else f"Missing exact wheel METADATA for {cname}=={version}",
            })
            continue

        requires_dist = meta_dict.get("requires_dist", [])
        requires_python = meta_dict.get("requires_python") or wheel_info.get("requires_python")

        # Ensure JSON and METADATA Requires-Python do not contradict
        json_req_py = wheel_info.get("requires_python")
        meta_req_py = meta_dict.get("requires_python")
        if json_req_py and meta_req_py:
            try:
                js_spec = SpecifierSet(json_req_py)
                me_spec = SpecifierSet(meta_req_py)
                if not js_spec.contains(target_env["python_full_version"]) or not me_spec.contains(
                    target_env["python_full_version"]
                ):
                    wheel_failures.append({
                        "package": cname,
                        "version": version,
                        "status": "CONTRADICTORY_REQUIRES_PYTHON",
                        "error": f"Requires-Python mismatch: JSON={json_req_py} vs METADATA={meta_req_py}",
                    })
                    continue
            except Exception as exc:
                wheel_failures.append({
                    "package": cname,
                    "version": version,
                    "status": "MALFORMED_REQUIRES_PYTHON",
                    "error": f"Malformed Requires-Python constraint: {exc}",
                })
                continue

        package_metadata_map[cname] = {
            "version": version,
            "wheel": wheel_info,
            "requires_dist": requires_dist,
            "requires_python": requires_python,
            "provides_extra": meta_dict.get("provides_extra", []),
            "metadata_source": str(meta_path.name) if meta_path else "missing",
        }

    # Step 2: Extras fixed-point propagation (including cycles)
    # Propagates requested extras until no new extras are added
    changed = True
    iteration = 0
    max_iterations = 1000

    while changed and iteration < max_iterations:
        changed = False
        iteration += 1

        for cname, pkg_data in package_metadata_map.items():
            extras_for_pkg = pkg_active_extras.get(cname, set())

            for req_raw in pkg_data["requires_dist"]:
                try:
                    req = Requirement(req_raw)
                except Exception:
                    continue

                # Determine if requirement is active under base or any activated extra
                is_active = False
                candidate_extras = [""] + sorted(extras_for_pkg)

                if req.marker is None:
                    is_active = True
                else:
                    for extra_cand in candidate_extras:
                        test_env = dict(target_env, extra=extra_cand)
                        try:
                            if req.marker.evaluate(test_env):
                                is_active = True
                                break
                        except Exception:
                            # Handled during edge construction pass
                            pass

                if is_active and req.extras:
                    target_cname = canonical_name(req.name)
                    if target_cname in pkg_active_extras:
                        for req_extra in req.extras:
                            norm_e = canonical_name(req_extra)
                            if norm_e not in pkg_active_extras[target_cname]:
                                pkg_active_extras[target_cname].add(norm_e)
                                changed = True

    if changed:
        selection_errors.append('Extras propagation did not converge')

    # Step 3: Evaluate PEP 508 active edges, markers, and constraints
    for cname, pkg_data in package_metadata_map.items():
        extras_for_pkg = pkg_active_extras.get(cname, set())

        for req_raw in pkg_data["requires_dist"]:
            try:
                req = Requirement(req_raw)
            except Exception as exc:
                if ";" in req_raw:
                    marker_errors.append({
                        "source": cname,
                        "requirement": req_raw,
                        "error": f"Marker syntax error: {exc}",
                    })
                else:
                    incomplete_evidence.append({
                        "package": cname,
                        "error": f"Unparseable requirement {req_raw!r}: {exc}",
                    })
                continue

            is_active = False
            candidate_extras = [""] + sorted(extras_for_pkg)
            marker_error_occurred = False

            if req.marker is None:
                is_active = True
            else:
                for extra_cand in candidate_extras:
                    test_env = dict(target_env, extra=extra_cand)
                    try:
                        if req.marker.evaluate(test_env):
                            is_active = True
                            break
                    except Exception as exc:
                        # Marker errors must be errors, not inactive edges!
                        marker_error_occurred = True
                        marker_errors.append({
                            "source": cname,
                            "requirement": req_raw,
                            "error": f"Marker evaluation failed: {exc}",
                        })
                        break

            if marker_error_occurred or not is_active:
                continue

            # Reject unsupported active direct-URL requirements
            if req.url:
                direct_url_errors.append({
                    "source": cname,
                    "requirement": req_raw,
                    "url": req.url,
                    "error": f"Unsupported active direct-URL requirement: {req_raw}",
                })
                continue

            target_cname = canonical_name(req.name)
            edge = {
                "source": cname,
                "target": target_cname,
                "specifier": str(req.specifier),
                "requirement_raw": req_raw,
                "extras": list(req.extras),
            }
            active_edges.append(edge)

            # Check if target is in selected set
            if target_cname not in selected_versions:
                missing_packages.append({
                    "source": cname,
                    "target": target_cname,
                    "specifier": str(req.specifier),
                    "requirement_raw": req_raw,
                })
                continue

            # Check constraint satisfaction
            target_version_str = selected_versions[target_cname]
            if req.specifier:
                try:
                    is_satisfied = req.specifier.contains(target_version_str, prereleases=True)
                except Exception as exc:
                    conflicting_constraints.append({
                        "source": cname,
                        "target": target_cname,
                        "selected_version": target_version_str,
                        "required_specifier": str(req.specifier),
                        "requirement_raw": req_raw,
                        "error": f"Specifier evaluation error: {exc}",
                    })
                    continue

                if not is_satisfied:
                    conflicting_constraints.append({
                        "source": cname,
                        "target": target_cname,
                        "selected_version": target_version_str,
                        "required_specifier": str(req.specifier),
                        "requirement_raw": req_raw,
                    })

    # Overall compatibility evaluation
    passed = (
        manifest_ok
        and len(manifest_errors) == 0
        and len(selection_errors) == 0
        and len(incomplete_evidence) == 0
        and len(wheel_failures) == 0
        and len(missing_packages) == 0
        and len(conflicting_constraints) == 0
        and len(marker_errors) == 0
        and len(direct_url_errors) == 0
        and len(selected_versions) > 0
    )

    return {
        "status": "PASS" if passed else "FAIL",
        "passed": passed,
        "environment": target_env,
        "selection_count": len(selected_versions),
        "active_edges_count": len(active_edges),
        "selected_versions": selected_versions,
        "active_extras": {k: sorted(v) for k, v in pkg_active_extras.items() if v},
        "active_edges": active_edges,
        "missing_packages": missing_packages,
        "conflicting_constraints": conflicting_constraints,
        "wheel_details": wheel_details,
        "wheel_failures": wheel_failures,
        "incomplete_evidence": incomplete_evidence,
        "manifest_errors": manifest_errors,
        "marker_errors": marker_errors,
        "direct_url_errors": direct_url_errors,
        "selection_errors": selection_errors,
        "scope_notice": (
            "Graph compatibility verifies PEP 508 constraints and wheel metadata only. "
            "A local SHA256 manifest proves retained-byte integrity, not authenticity on its own. "
            "Advisory disposition, binary import compatibility, model safety, and inference "
            "quality are separate gates and are not qualified by this check."
        ),
    }


def print_report(result: dict[str, Any], verbose: bool = False) -> None:
    """Print readable text summary of the graph check."""
    status = result["status"]
    print(f"=== RUNTIME GRAPH COMPATIBILITY REPORT: {status} ===")
    print(
        f"Target Environment: Windows x86-64 CPython {result['environment']['python_version']} ({result['environment']['platform_machine']})"
    )
    print(f"Selected Packages: {result['selection_count']}")
    print(f"Active Edges Evaluated: {result['active_edges_count']}")

    if result.get("selection_errors"):
        print(f"\n[!] SELECTION ERRORS ({len(result['selection_errors'])}):")
        for err in result["selection_errors"]:
            print(f"  - {err}")

    if result.get("manifest_errors"):
        print(f"\n[!] EVIDENCE INTEGRITY FAILURES ({len(result['manifest_errors'])}):")
        for err in result["manifest_errors"]:
            print(f"  - {err}")

    if result.get("incomplete_evidence"):
        print(f"\n[!] INCOMPLETE EVIDENCE ({len(result['incomplete_evidence'])}):")
        for inc in result["incomplete_evidence"]:
            pkg = inc.get("package", "unknown")
            ver = inc.get("version", "")
            err = inc.get("error", "")
            print(f"  - {pkg}{'==' + ver if ver else ''}: {err}")

    if result.get("wheel_failures"):
        print(f"\n[!] WHEEL REJECTIONS ({len(result['wheel_failures'])}):")
        for wf in result["wheel_failures"]:
            print(f"  - {wf['package']}=={wf['version']} [{wf['status']}]: {wf['error']}")

    if result.get("marker_errors"):
        print(f"\n[!] MARKER ERRORS ({len(result['marker_errors'])}):")
        for me in result["marker_errors"]:
            print(f"  - {me['source']} in '{me['requirement']}': {me['error']}")

    if result.get("direct_url_errors"):
        print(f"\n[!] DIRECT-URL REQUIREMENT REJECTIONS ({len(result['direct_url_errors'])}):")
        for du in result["direct_url_errors"]:
            print(f"  - {du['source']} requires direct URL '{du['url']}'")

    if result.get("missing_packages"):
        print(f"\n[!] MISSING ACTIVE PACKAGES ({len(result['missing_packages'])}):")
        for mp in result["missing_packages"]:
            print(
                f"  - {mp['source']} requires {mp['target']} ({mp['specifier']}) but {mp['target']} is not in selection"
            )

    if result.get("conflicting_constraints"):
        print(f"\n[!] CONFLICTING CONSTRAINTS ({len(result['conflicting_constraints'])}):")
        for cc in result["conflicting_constraints"]:
            print(
                f"  - {cc['source']} requires '{cc['target']}{cc['required_specifier']}', "
                f"but selected version is {cc['selected_version']}"
            )

    if verbose and result.get("wheel_details"):
        print(f"\n--- Compatible Wheels Validated ({len(result['wheel_details'])}):")
        for pkg, w in sorted(result["wheel_details"].items()):
            print(f"  {pkg}: {w['filename']} ({w['size']} bytes, sha256={w['sha256'][:16]}...)")

    print(f"\nScope: {result['scope_notice']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify runtime dependency graph and wheel tags for Windows CPython 3.13"
    )
    parser.add_argument(
        "--selection",
        type=Path,
        default=DEFAULT_LOCK,
        help="Path to selection lockfile (.txt) or proposal (.json)",
    )
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        default=DEFAULT_PROOF_DIR,
        help="Path to proof directory containing pypi/ and metadata/ subdirs",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional path to write full JSON report",
    )
    parser.add_argument(
        "--no-manifest-check",
        action="store_true",
        help="Skip checking SHA256 evidence manifest (Note: integrity bypass cannot produce PASS)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print detailed wheel and edge listing",
    )

    args = parser.parse_args(argv)

    if not args.selection.is_file():
        print(f"Error: selection file not found: {args.selection}", file=sys.stderr)
        return 1

    try:
        _bounded_path(args.evidence_dir, 'SHA256.json')
    except (OSError, ValueError) as exc:
        print(f"Error: invalid evidence directory: {exc}", file=sys.stderr)
        return 1

    try:
        selection = parse_selection(args.selection)
    except Exception as exc:
        print(f"Error parsing selection: {exc}", file=sys.stderr)
        return 1

    result = check_runtime_graph(
        selection=selection,
        proof_dir=args.evidence_dir,
        verify_manifest=not args.no_manifest_check,
    )

    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print_report(result, verbose=args.verbose)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
