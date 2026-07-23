"""Verify the final interpreter inventory against the installer lock."""

from __future__ import annotations

import argparse
import importlib.metadata
import re
import sys
from pathlib import Path


PIN = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s;]+)$")


def canonical_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def read_lock(path: Path) -> dict[str, str]:
    locked: dict[str, str] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = PIN.fullmatch(line)
        if match is None:
            raise ValueError(f"{path}:{number}: expected one exact name==version pin")
        name, version = match.groups()
        key = canonical_name(name)
        if key in locked:
            raise ValueError(f"{path}:{number}: duplicate package {name}")
        locked[key] = version
    if not locked:
        raise ValueError(f"{path}: lock is empty")
    return locked


def installed_inventory() -> dict[str, str]:
    inventory: dict[str, str] = {}
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata.get("Name")
        if name:
            inventory[canonical_name(name)] = distribution.version
    return inventory


def inventory_diff(
    locked: dict[str, str], installed: dict[str, str]
) -> tuple[list[str], list[str], list[str]]:
    missing = sorted(set(locked) - set(installed))
    unexpected = sorted(set(installed) - set(locked))
    changed = sorted(
        name
        for name in set(locked) & set(installed)
        if locked[name] != installed[name]
    )
    return missing, unexpected, changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lock", type=Path)
    parser.add_argument(
        "--print-inventory",
        action="store_true",
        help="print the current interpreter inventory as exact pins",
    )
    args = parser.parse_args(argv)
    installed = installed_inventory()
    if args.print_inventory:
        for name, version in sorted(installed.items()):
            print(f"{name}=={version}")
        return 0

    locked = read_lock(args.lock)
    missing, unexpected, changed = inventory_diff(locked, installed)
    if missing or unexpected or changed:
        if missing:
            print("missing: " + ", ".join(missing), file=sys.stderr)
        if unexpected:
            print("unexpected: " + ", ".join(unexpected), file=sys.stderr)
        for name in changed:
            print(
                f"version drift: {name} locked={locked[name]} "
                f"installed={installed[name]}",
                file=sys.stderr,
            )
        return 1
    print(f"installer dependency lock verified: {len(locked)} packages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
