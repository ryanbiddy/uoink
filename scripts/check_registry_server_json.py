"""Check server.json (the MCP registry listing) against a release tag.

Usage: check_registry_server_json.py <server.json> <tag> [SHA256SUMS.txt]

Fails closed when the listing's version, .mcpb URL or checksum does not match
the tag, VERSION, or the release's SHA256SUMS.txt. Stdlib only.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_URL = "https://github.com/ryanbiddy/uoink"
NAME = "io.github.ryanbiddy/uoink"


def check(server_path: Path, tag: str, sums_path: Path | None) -> list[str]:
    errors: list[str] = []
    data = json.loads(server_path.read_text(encoding="utf-8"))
    version = tag[1:] if tag.startswith("v") else tag
    repo_version = (server_path.parent / "VERSION").read_text(encoding="utf-8").strip()
    if data.get("name") != NAME:
        errors.append(f"name is {data.get('name')!r}, expected {NAME!r}")
    if data.get("version") != version:
        errors.append(f"version is {data.get('version')!r}, tag says {version!r}")
    if repo_version != version:
        errors.append(f"VERSION is {repo_version!r}, tag says {version!r}")
    description = data.get("description", "")
    if not 1 <= len(description) <= 100:
        errors.append(f"description must be 1-100 characters, got {len(description)}")
    packages = data.get("packages") or []
    if len(packages) != 1 or packages[0].get("registryType") != "mcpb":
        errors.append("expected exactly one mcpb package")
        return errors
    package = packages[0]
    asset = f"uoink-{version}.mcpb"
    expected_url = f"{REPO_URL}/releases/download/v{version}/{asset}"
    if package.get("identifier") != expected_url:
        errors.append(f"identifier is {package.get('identifier')!r}, expected {expected_url!r}")
    digest = package.get("fileSha256", "")
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        errors.append(f"fileSha256 is not a lowercase sha256: {digest!r}")
    if package.get("transport") != {"type": "stdio"}:
        errors.append("transport must be stdio")
    if sums_path is not None:
        sums = {}
        for line in sums_path.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) == 2:
                sums[parts[1].lstrip("*")] = parts[0].lower()
        if sums.get(asset) != digest:
            errors.append(f"fileSha256 does not match SHA256SUMS.txt for {asset}: {sums.get(asset)!r}")
    return errors


def main(argv: list[str]) -> int:
    if len(argv) not in (3, 4):
        print(__doc__.strip(), file=sys.stderr)
        return 2
    sums = Path(argv[3]) if len(argv) == 4 else None
    errors = check(Path(argv[1]), argv[2], sums)
    for error in errors:
        print(f"server.json: {error}", file=sys.stderr)
    if errors:
        return 1
    print(f"server.json matches {argv[2]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
