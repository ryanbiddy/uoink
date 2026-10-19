"""Generate the two publishable skill copies from skills/uoink; no network."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "skills" / "uoink"
DESTINATIONS = (ROOT / "agent-kit" / "skills" / "uoink",
                ROOT / "agent-kit" / "plugins" / "uoink" / "skills" / "uoink")


def files(root):
    return {path.relative_to(root): path.read_bytes() for path in sorted(root.rglob("*"))
            if path.is_file() and "__pycache__" not in path.parts}


def build(check=False):
    if not (SOURCE / "SKILL.md").is_file():
        raise ValueError("canonical skills/uoink/SKILL.md is missing")
    expected = files(SOURCE)
    problems = []
    for destination in DESTINATIONS:
        if destination.is_symlink() or ROOT.resolve() not in destination.resolve().parents:
            raise ValueError(f"unsafe generated directory: {destination}")
        actual = files(destination)
        for relative in sorted(expected.keys() | actual.keys()):
            if expected.get(relative) == actual.get(relative):
                continue
            target = destination / relative
            if check:
                problems.append(str(target.relative_to(ROOT)))
                continue
            resolved = target.resolve()
            if destination.resolve() not in resolved.parents or target.is_symlink():
                raise ValueError(f"unsafe generated path: {target}")
            if relative not in expected:
                target.unlink()
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(expected[relative])
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    problems = build(args.check)
    if problems:
        print("Agent kit skill copies differ:\n" + "\n".join(problems), file=sys.stderr)
        return 1
    print("Agent kit skills match skills/uoink" if args.check else "Agent kit skills generated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
