"""Freeze the successful native qualification graph; never resolve during build."""
from __future__ import annotations

import json
from pathlib import Path
import re

from qualify_deps import canonical, sha256, wheel_details, write_json

LOCK_NAME = "requirements-macos-arm64-lock.txt"


def resolved_lock(report: dict, directory: Path, exclusions: dict) -> list[dict]:
    graphs = [g for g in report["graph_attempts"]
              if g["platform"] == "macosx_15_0_arm64" and g["resolved"] and not g["errors"]]
    if len(graphs) != 1:
        raise ValueError("A successful macOS 15 arm64 resolved graph is required")
    rows = graphs[0]["wheels"]
    if not rows:
        raise ValueError("Resolved graph is empty")
    names = set()
    for row in rows:
        info = wheel_details(row["filename"])
        name = info["package"]
        if name in names or name in exclusions:
            raise ValueError(f"Duplicate or excluded distribution: {name}")
        names.add(name)
        if Path(row["filename"]).name != row["filename"]:
            raise ValueError("Wheel path must be a basename")
        if not re.fullmatch(r"[0-9a-f]{64}", row["sha256"]) or sha256(directory / row["filename"]) != row["sha256"]:
            raise ValueError(f"Wheel hash mismatch: {row['filename']}")
    # Qualification must include every shipping pin, not only a partial solve.
    from packaging.version import Version
    versions = {wheel_details(r["filename"])["package"]: wheel_details(r["filename"])["version"] for r in rows}
    for pin in report["packages"]:
        if canonical(pin["package"]) not in versions or Version(versions[canonical(pin["package"])]) != Version(pin["version"]):
            raise ValueError(f"Missing qualified pin: {pin['package']}")
    return sorted(rows, key=lambda row: row["filename"])


def lock_text(rows: list[dict]) -> str:
    lines = ["# Generated from the successful macOS 15 arm64 qualification graph.",
             "# Install only with the matching verified wheel artifact; no index."]
    for row in rows:
        info = wheel_details(row["filename"])
        lines.append(f"{info['package']}=={info['version']} --hash=sha256:{row['sha256']}")
    return "\n".join(lines) + "\n"


def generate(report: dict, directory: Path, exclusions: dict) -> None:
    rows = resolved_lock(report, directory, exclusions)
    (directory / LOCK_NAME).write_text(lock_text(rows), encoding="utf-8", newline="\n")
    write_json(directory / "resolved-wheels.json", {"schema_version": 1, "wheels": rows})


def verify(directory: Path, exclusions: dict) -> list[dict]:
    manifest = json.loads((directory / "resolved-wheels.json").read_text(encoding="utf-8"))
    inventory = json.loads((directory / "wheel-manifest.json").read_text(encoding="utf-8"))
    if inventory["errors"] or manifest["schema_version"] != 1:
        raise ValueError("Invalid qualification inventory")
    rows = resolved_lock({"graph_attempts": [{"platform": "macosx_15_0_arm64", "resolved": True,
                                             "errors": [], "wheels": manifest["wheels"]}],
                          "packages": inventory["pins"]}, directory, exclusions)
    recorded = {row["filename"]: row["sha256"] for row in inventory["wheels"]}
    if any(recorded.get(row["filename"]) != row["sha256"] for row in rows):
        raise ValueError("Resolved wheel differs from qualification inventory")
    if (directory / LOCK_NAME).read_text(encoding="utf-8") != lock_text(rows):
        raise ValueError("Hash lock differs from the qualified graph")
    return rows
