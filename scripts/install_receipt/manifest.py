"""Operator manifest. Astra seals hashes later; this kit never invents them."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import KIT_DATE, KIT_SCHEMA
from .constants import (
    CANDIDATE_PACKAGE_02_DIR,
    INNO_NOCLOSE_FLAG,
    INNO_NORESTARTAPPS_FLAG,
    ISOLATED_PORT_FLAG,
    ISOLATED_PROFILE_FLAG,
    LEGACY_FIXTURE_VERSION,
    SCENARIO_IDS,
)
from .hashes import sha256_file
from .validation import (
    C22ValidationError,
    validate_git_commit,
    validate_port,
    validate_sha256,
)

SEALED_HASH_FIELDS = (
    "expected_package_sha256",
    "candidate_sha",
    "installer_source_sha",
)


def example_manifest() -> dict[str, Any]:
    return {
        "schema": KIT_SCHEMA,
        "kit_date": KIT_DATE,
        "sealed_by": None,
        "seal_note": (
            "Astra fills expected_package_sha256, candidate_sha and "
            "installer_source_sha when sealing. This kit refuses to invent them."
        ),
        "expected_package_sha256": None,
        "candidate_sha": None,
        "installer_source_sha": None,
        "isolation_flags": {
            "profile": ISOLATED_PROFILE_FLAG,
            "port": ISOLATED_PORT_FLAG,
            "from_install_dir": "--isolated-from-install-dir",
            "token": "<profile>/token.txt",
            "marker": "isolated-install.json",
            "implemented_by": "isolation worker; this kit only consumes them",
        },
        "inno_isolated_args_template": [
            "/VERYSILENT",
            "/NORESTART",
            "/SUPPRESSMSGBOXES",
            '/DIR="{installed_app_path}"',
            "/ISOLATED=1",
            "/PROFILE={isolated_profile}",
            "/PORT={isolated_port}",
            INNO_NOCLOSE_FLAG,
            INNO_NORESTARTAPPS_FLAG,
        ],
        "inno_isolated_args_note": (
            "Agreed Inno surface is /ISOLATED=1 /PROFILE=<root> /PORT=<non5179> "
            "/DIR=<app> /NOCLOSEAPPLICATIONS /NORESTARTAPPLICATIONS. "
            "Positive /CLOSEAPPLICATIONS /FORCECLOSEAPPLICATIONS "
            "/RESTARTAPPLICATIONS overrides are refused. This kit records "
            "the command and does not execute Inno."
        ),
        "upgrade": {
            "same_version_reinstall_label": "same_version_reinstall",
            "cross_version_upgrade_label": "cross_version_upgrade",
            "do_not_mislabel": True,
        },
        "legacy_fixture_version": LEGACY_FIXTURE_VERSION,
        "scenarios": list(SCENARIO_IDS),
        "phase4_client_scope": "astra_separate_not_this_kit",
    }


def load_manifest(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return example_manifest()
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise C22ValidationError("manifest must be a JSON object")
    if data.get("schema") != KIT_SCHEMA:
        raise C22ValidationError(
            f"manifest schema must be {KIT_SCHEMA}, got {data.get('schema')}")
    return merge_manifest(data)


def merge_manifest(data: dict[str, Any]) -> dict[str, Any]:
    base = example_manifest()
    base.update(data)
    base["schema"] = KIT_SCHEMA
    if "scenarios" not in data:
        base["scenarios"] = list(SCENARIO_IDS)
    return base


def require_sealed_package_hash(manifest: dict[str, Any]) -> str:
    value = manifest.get("expected_package_sha256")
    if value in (None, "", "TBD", "todo", "seal-later"):
        raise C22ValidationError(
            "expected_package_sha256 is unsealed. Astra must seal the "
            "package digest; this kit will not invent one.")
    return validate_sha256(value, label="expected_package_sha256")


def upgrade_kind(manifest: dict[str, Any], *,
                 installed_version: str | None,
                 package_version: str | None) -> str:
    labels = manifest.get("upgrade") or example_manifest()["upgrade"]
    if not installed_version or not package_version:
        return "unspecified_pending_inventory"
    if installed_version == package_version:
        return labels["same_version_reinstall_label"]
    return labels["cross_version_upgrade_label"]


def write_example(path: Path) -> Path:
    path.write_text(json.dumps(example_manifest(), indent=2) + "\n",
                    encoding="utf-8")
    return path


def load_candidate_package_02() -> dict[str, Any]:
    """Consume Astra's active committed seal; the function name is a compatibility API."""
    root = CANDIDATE_PACKAGE_02_DIR
    bindings_path = root / "source-bindings.json"
    manifest_path = root / "package-manifest.json"
    if not bindings_path.is_file() or not manifest_path.is_file():
        raise C22ValidationError(
            f"candidate package seal missing under {root}")
    bindings = json.loads(bindings_path.read_text(encoding="utf-8"))
    package = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(bindings, dict) or not isinstance(package, dict):
        raise C22ValidationError("candidate package seal is not a JSON object")
    source = validate_git_commit(
        package.get("installer_source_sha") or bindings.get("build_source"),
        label="candidate package installer_source_sha")
    build = validate_git_commit(
        package.get("build_source") or bindings.get("build_source"),
        label="candidate package build_source")
    digest = validate_sha256(
        package.get("package_sha256"), label="candidate package package_sha256")
    files = package.get("files") or bindings.get("files") or []
    if not isinstance(files, list) or not files:
        raise C22ValidationError("candidate package files list is empty")
    by_path: dict[str, dict[str, Any]] = {}
    for row in files:
        if not isinstance(row, dict):
            continue
        staged = str(row.get("staged_path") or "")
        blob = row.get("source_git_blob")
        content = row.get("checkout_and_staged_sha256")
        if blob:
            validate_git_commit(blob, label=f"{staged} source_git_blob")
        if content:
            validate_sha256(content, label=f"{staged} checkout_and_staged_sha256")
        if staged:
            by_path[staged.replace("\\", "/")] = row
    bytes_count = package.get("package_bytes")
    if type(bytes_count) is not int or bytes_count <= 0:
        raise C22ValidationError("candidate package package_bytes is missing")
    return {
        "schema": "candidate-package-02",  # Receipt format, not the active package number.
        "active_package_directory": root.name,
        "dir": str(root),
        "source_bindings_path": str(bindings_path),
        "package_manifest_path": str(manifest_path),
        "source_bindings_sha256": sha256_file(bindings_path),
        "package_manifest_sha256": sha256_file(manifest_path),
        "installer_source_sha": source,
        "build_source": build,
        "package_sha256": digest,
        "package_bytes": bytes_count,
        "package_name": package.get("package_name"),
        "files_by_path": by_path,
        "invented": False,
        "installed_credit": False,
    }
