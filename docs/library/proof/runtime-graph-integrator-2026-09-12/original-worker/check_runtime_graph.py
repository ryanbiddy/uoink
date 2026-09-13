"""Check runtime dependency graph and wheel compatibility for Windows x64 CPython 3.13.

Inspects saved PyPI JSON and wheel METADATA offline without importing packages
or executing setup/build hooks. Evaluates PEP 508 markers, extras, wheel tags,
and constraint closures.
"""

from __future__ import annotations

import argparse
import email
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.tags import Tag, compatible_tags, cpython_tags
from packaging.utils import parse_wheel_filename
from packaging.version import Version


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCK = ROOT / "requirements-installer-lock.txt"
DEFAULT_PROOF_DIR = ROOT / "docs" / "library" / "proof" / "runtime-graph-01-2026-09-12"

PIN_REGEX = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s;]+)$")

# Canonical environment for Windows x86-64 CPython 3.13
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


def canonical_name(value: str) -> str:
    """Normalize package names per PEP 503."""
    return re.sub(r"[-_.]+", "-", value).lower()


def get_supported_wheel_tags(
    python_version: tuple[int, int] = (3, 13), platform: str = "win_amd64"
) -> set[Tag]:
    """Generate all supported wheel tags for Windows x86-64 CPython 3.13."""
    tags: set[Tag] = set()
    tags.update(cpython_tags(python_version=python_version, platforms=[platform]))
    tags.update(compatible_tags(python_version=python_version, platforms=[platform]))
    tags.update(compatible_tags(python_version=python_version))
    for minor in range(2, python_version[1] + 1):
        tags.update(
            cpython_tags(
                python_version=(python_version[0], minor),
                abis=["abi3"],
                platforms=[platform],
            )
        )
    return tags


def parse_lock(path: Path) -> dict[str, str]:
    """Parse name==version pins from a requirements lockfile."""
    locked: dict[str, str] = {}
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = PIN_REGEX.fullmatch(line)
        if not match:
            raise ValueError(f"{path}:{line_no}: expected exact name==version pin")
        name, ver = match.groups()
        cname = canonical_name(name)
        if cname in locked:
            raise ValueError(f"{path}:{line_no}: duplicate package {name}")
        locked[cname] = ver
    return locked


def parse_selection(path: Path) -> dict[str, str]:
    """Parse selection from JSON or lockfile."""
    text = path.read_text(encoding="utf-8").strip()
    if path.suffix == ".json" or text.startswith("{"):
        data = json.loads(text)
        if isinstance(data, dict):
            raw_dict = (
                data.get("selected")
                or data.get("packages")
                or data.get("pins")
                or data
            )
            if isinstance(raw_dict, dict):
                return {canonical_name(k): str(v) for k, v in raw_dict.items() if not k.startswith("_")}
        elif isinstance(data, list):
            locked: dict[str, str] = {}
            for item in data:
                if isinstance(item, str) and "==" in item:
                    name, ver = item.split("==", 1)
                    locked[canonical_name(name.strip())] = ver.strip()
            return locked
        raise ValueError(f"Unrecognized selection JSON format in {path}")
    return parse_lock(path)


def parse_metadata_text(content: str) -> dict[str, Any]:
    """Parse wheel METADATA headers."""
    msg = email.message_from_string(content)
    requires_dist = msg.get_all("Requires-Dist") or []
    requires_python = msg.get("Requires-Python")
    name = msg.get("Name")
    version = msg.get("Version")
    return {
        "name": name,
        "version": version,
        "requires_dist": requires_dist,
        "requires_python": requires_python,
    }


def find_pypi_json_for_package(
    proof_dir: Path, cname: str, version: str | None = None
) -> tuple[Path | None, dict[str, Any] | None]:
    """Find and load saved PyPI JSON from proof directory."""
    pypi_dir = proof_dir / "pypi"
    if not pypi_dir.is_dir():
        return None, None

    candidates: list[Path] = []
    if version:
        candidates.extend([
            pypi_dir / f"{cname}-{version}.json",
            pypi_dir / f"{cname}@{version}.json",
        ])
    candidates.extend([
        pypi_dir / f"{cname}.json",
        pypi_dir / f"{cname.replace('-', '_')}.json",
    ])

    for candidate in candidates:
        if candidate.is_file():
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
                return candidate, data
            except Exception:
                continue
    return None, None


def find_wheel_metadata_file(
    proof_dir: Path, cname: str, version: str, wheel_filename: str | None = None
) -> tuple[Path | None, dict[str, Any] | None]:
    """Find and parse saved wheel METADATA file."""
    meta_dir = proof_dir / "metadata"
    if not meta_dir.is_dir():
        return None, None

    candidates: list[Path] = []
    if wheel_filename:
        candidates.append(meta_dir / f"{wheel_filename}.metadata")
        candidates.append(meta_dir / wheel_filename)

    candidates.extend([
        meta_dir / f"{cname}-{version}.metadata",
        meta_dir / f"{cname.replace('-', '_')}-{version}.metadata",
        meta_dir / f"{cname}-{version}.dist-info" / "METADATA",
    ])

    # Also glob for any wheel metadata matching this package and version
    for path in meta_dir.glob(f"{cname}*-{version}*.metadata"):
        if path not in candidates:
            candidates.append(path)
    for path in meta_dir.glob(f"{cname.replace('-', '_')}*-{version}*.metadata"):
        if path not in candidates:
            candidates.append(path)

    for candidate in candidates:
        if candidate.is_file():
            try:
                parsed = parse_metadata_text(candidate.read_text(encoding="utf-8"))
                return candidate, parsed
            except Exception:
                continue
    return None, None


def check_wheel_for_release(
    cname: str,
    version: str,
    release_files: list[dict[str, Any]],
    supported_tags: set[Tag],
    target_env: dict[str, str],
) -> dict[str, Any]:
    """Find a compatible Windows x64 CPython 3.13 wheel and check yanked status."""
    compatible_wheels: list[dict[str, Any]] = []
    incompatible_wheels: list[dict[str, Any]] = []
    yanked_wheels: list[dict[str, Any]] = []

    for file_info in release_files:
        filename = file_info.get("filename", "")
        if not filename.endswith(".whl") or file_info.get("packagetype") != "bdist_wheel":
            continue

        is_yanked = bool(file_info.get("yanked"))
        yanked_reason = file_info.get("yanked_reason")

        try:
            _, _, _, wheel_tags = parse_wheel_filename(filename)
        except Exception:
            continue

        tag_match = bool(wheel_tags & supported_tags)

        req_py = file_info.get("requires_python")
        py_match = True
        if req_py:
            try:
                py_spec = SpecifierSet(req_py)
                py_match = py_spec.contains(target_env["python_full_version"])
            except Exception:
                py_match = True

        wheel_record = {
            "filename": filename,
            "size": file_info.get("size"),
            "sha256": (file_info.get("digests") or {}).get("sha256"),
            "url": file_info.get("url"),
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
        # Prefer more specific tags (e.g. cp313-cp313-win_amd64 over py3-none-any)
        def sort_key(w: dict[str, Any]) -> int:
            fn = w["filename"]
            if "cp313-cp313" in fn:
                return 3
            if "abi3" in fn:
                return 2
            if "py3-none-any" in fn or "py2.py3" in fn:
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
        }

    if yanked_wheels and not incompatible_wheels:
        return {
            "status": "YANKED",
            "error": f"All available matching wheels for {cname}=={version} are yanked: {yanked_wheels[0].get('yanked_reason')}",
            "yanked_wheels": yanked_wheels,
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
        }

    return {
        "status": "NO_WHEELS",
        "error": f"No wheel distributions found for {cname}=={version} in release files",
        "release_files_count": len(release_files),
    }


def verify_evidence_integrity(proof_dir: Path) -> tuple[bool, list[str]]:
    """Check SHA256 integrity manifest if present."""
    manifest_paths = [
        proof_dir / "SHA256.json",
        proof_dir / "manifest.json",
        proof_dir / "evidence_manifest.json",
    ]
    manifest_path = next((p for p in manifest_paths if p.is_file()), None)
    if not manifest_path:
        return True, []

    errors: list[str] = []
    try:
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, [f"Corrupt manifest {manifest_path.name}: {exc}"]

    # Manifest can be {relative_path: sha256} or {"files": {relative_path: {"sha256": ...}}}
    files_map: dict[str, str] = {}
    if isinstance(manifest_data, dict):
        if "files" in manifest_data and isinstance(manifest_data["files"], dict):
            for k, v in manifest_data["files"].items():
                if isinstance(v, dict) and "sha256" in v:
                    files_map[k] = v["sha256"]
                elif isinstance(v, str):
                    files_map[k] = v
        else:
            for k, v in manifest_data.items():
                if isinstance(v, str):
                    files_map[k] = v
                elif isinstance(v, dict) and "sha256" in v:
                    files_map[k] = v["sha256"]

    for rel_str, expected_hash in files_map.items():
        target_file = proof_dir / rel_str
        if not target_file.is_file():
            errors.append(f"Missing evidence file referenced in manifest: {rel_str}")
            continue
        actual_hash = hashlib.sha256(target_file.read_bytes()).hexdigest()
        if actual_hash.lower() != expected_hash.lower():
            errors.append(
                f"Tampered/mismatched evidence: {rel_str} expected {expected_hash} but got {actual_hash}"
            )

    return len(errors) == 0, errors


def check_runtime_graph(
    selection: dict[str, str],
    proof_dir: Path,
    target_env: dict[str, str] | None = None,
    verify_manifest: bool = True,
) -> dict[str, Any]:
    """Execute complete runtime graph verification against captured proof metadata."""
    if target_env is None:
        target_env = dict(TARGET_ENV)

    supported_tags = get_supported_wheel_tags(python_version=(3, 13), platform="win_amd64")

    # Step 0: Evidence manifest integrity
    manifest_ok, manifest_errors = True, []
    if verify_manifest:
        manifest_ok, manifest_errors = verify_evidence_integrity(proof_dir)

    selected_versions: dict[str, str] = dict(selection)
    active_edges: list[dict[str, Any]] = []
    missing_packages: list[dict[str, Any]] = []
    conflicting_constraints: list[dict[str, Any]] = []
    wheel_details: dict[str, Any] = {}
    incomplete_evidence: list[dict[str, Any]] = []
    wheel_failures: list[dict[str, Any]] = []

    # Step 1: For every selected package, inspect wheel & metadata
    package_metadata_map: dict[str, dict[str, Any]] = {}

    for cname, version in sorted(selected_versions.items()):
        pypi_path, pypi_json = find_pypi_json_for_package(proof_dir, cname, version)
        if not pypi_json:
            incomplete_evidence.append({
                "package": cname,
                "version": version,
                "error": f"Missing captured PyPI JSON for {cname}",
            })
            continue

        # Look up release files
        releases = pypi_json.get("releases", {})
        release_files = releases.get(version)
        if release_files is None:
            # Check if this PyPI JSON is version-specific (e.g. has "urls" at root)
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
            })
            continue

        wheel_info = wheel_res["wheel"]
        wheel_details[cname] = wheel_info

        # Extract requirements from wheel METADATA or PyPI JSON
        meta_path, meta_dict = find_wheel_metadata_file(
            proof_dir, cname, version, wheel_info.get("filename")
        )

        requires_dist: list[str] = []
        requires_python = wheel_info.get("requires_python")

        if meta_dict:
            requires_dist = meta_dict.get("requires_dist", [])
            if meta_dict.get("requires_python"):
                requires_python = meta_dict.get("requires_python")
        else:
            # Fallback to PyPI JSON requires_dist if version matches
            info = pypi_json.get("info", {})
            if info.get("version") == version and "requires_dist" in info:
                requires_dist = info.get("requires_dist") or []
            else:
                incomplete_evidence.append({
                    "package": cname,
                    "version": version,
                    "error": f"Missing wheel METADATA for {cname}=={version}",
                })
                continue

        package_metadata_map[cname] = {
            "version": version,
            "wheel": wheel_info,
            "requires_dist": requires_dist,
            "requires_python": requires_python,
            "metadata_source": str(meta_path.name) if meta_path else "pypi_json",
        }

    # Step 2: Parse PEP 508 requirements and active edges
    for cname, pkg_data in package_metadata_map.items():
        for req_raw in pkg_data["requires_dist"]:
            try:
                req = Requirement(req_raw)
            except Exception as exc:
                incomplete_evidence.append({
                    "package": cname,
                    "error": f"Unparseable requirement {req_raw!r}: {exc}",
                })
                continue

            # Evaluate marker against target environment with extra=""
            is_active = True
            if req.marker:
                try:
                    is_active = req.marker.evaluate(target_env)
                except Exception:
                    is_active = False

            if not is_active:
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

            # Check constraint conflict
            target_version_str = selected_versions[target_cname]
            if req.specifier:
                try:
                    is_satisfied = req.specifier.contains(target_version_str, prereleases=True)
                except Exception:
                    is_satisfied = False

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
        and len(incomplete_evidence) == 0
        and len(wheel_failures) == 0
        and len(missing_packages) == 0
        and len(conflicting_constraints) == 0
    )

    return {
        "status": "PASS" if passed else "FAIL",
        "passed": passed,
        "environment": target_env,
        "selection_count": len(selected_versions),
        "active_edges_count": len(active_edges),
        "selected_versions": selected_versions,
        "active_edges": active_edges,
        "missing_packages": missing_packages,
        "conflicting_constraints": conflicting_constraints,
        "wheel_details": wheel_details,
        "wheel_failures": wheel_failures,
        "incomplete_evidence": incomplete_evidence,
        "manifest_errors": manifest_errors,
        "scope_notice": (
            "Graph compatibility verifies PEP 508 constraints and wheel metadata only. "
            "Advisory disposition, binary import compatibility, model safety, and inference "
            "quality are separate gates and are not qualified by this check."
        ),
    }


def print_report(result: dict[str, Any], verbose: bool = False) -> None:
    """Print readable text summary of the graph check."""
    status = result["status"]
    print(f"=== RUNTIME GRAPH COMPATIBILITY REPORT: {status} ===")
    print(f"Target Environment: Windows x86-64 CPython {result['environment']['python_version']} ({result['environment']['platform_machine']})")
    print(f"Selected Packages: {result['selection_count']}")
    print(f"Active Edges Evaluated: {result['active_edges_count']}")

    if result["manifest_errors"]:
        print(f"\n[!] EVIDENCE INTEGRITY FAILURES ({len(result['manifest_errors'])}):")
        for err in result["manifest_errors"]:
            print(f"  - {err}")

    if result["incomplete_evidence"]:
        print(f"\n[!] INCOMPLETE EVIDENCE ({len(result['incomplete_evidence'])}):")
        for inc in result["incomplete_evidence"]:
            pkg = inc.get("package", "unknown")
            ver = inc.get("version", "")
            err = inc.get("error", "")
            print(f"  - {pkg}{'==' + ver if ver else ''}: {err}")

    if result["wheel_failures"]:
        print(f"\n[!] WHEEL REJECTIONS ({len(result['wheel_failures'])}):")
        for wf in result["wheel_failures"]:
            print(f"  - {wf['package']}=={wf['version']} [{wf['status']}]: {wf['error']}")

    if result["missing_packages"]:
        print(f"\n[!] MISSING ACTIVE PACKAGES ({len(result['missing_packages'])}):")
        for mp in result["missing_packages"]:
            print(f"  - {mp['source']} requires {mp['target']} ({mp['specifier']}) but {mp['target']} is not in selection")

    if result["conflicting_constraints"]:
        print(f"\n[!] CONFLICTING CONSTRAINTS ({len(result['conflicting_constraints'])}):")
        for cc in result["conflicting_constraints"]:
            print(
                f"  - {cc['source']} requires '{cc['target']}{cc['required_specifier']}', "
                f"but selected version is {cc['selected_version']}"
            )

    if verbose and result["wheel_details"]:
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
        help="Skip checking SHA256 evidence manifest",
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

    if not args.evidence_dir.is_dir():
        print(f"Error: evidence directory not found: {args.evidence_dir}", file=sys.stderr)
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
