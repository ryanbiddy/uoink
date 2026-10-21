"""Mount the DMG read-only, install a copy, and smoke only that copy."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from pathlib import Path
import os
import subprocess
import tempfile

from build_bundle import run, sha256
from build_mcpb import check
from bundle_smoke import smoke
from qualify_deps import write_json


@contextmanager
def installed_dmg(dmg: Path, scratch: Path, report: dict):
    """Share the read-only mount/copy/detach path with the install receipt."""
    mount = scratch / "mounted"
    mount.mkdir()
    installed = scratch / "Applications With Spaces/Uoink.app"
    report.update(mount=str(mount), read_only=True, app=str(installed), detached=False)
    attached = False
    try:
        run(["hdiutil", "attach", "-readonly", "-nobrowse", "-mountpoint", mount, dmg], timeout=120)
        attached = True
        if not (mount / "Applications").is_symlink() or os.readlink(mount / "Applications") != "/Applications":
            raise ValueError("DMG is missing its /Applications link")
        installed.parent.mkdir()
        run(["ditto", mount / "Uoink.app", installed], timeout=300)
        run(["codesign", "--verify", "--strict", "--deep", installed], timeout=120)
        yield mount / "Uoink.app", installed
    finally:
        # Also detach a partially successful attach when hdiutil raised.
        if attached or os.path.ismount(mount):
            subprocess.run(["hdiutil", "detach", str(mount)], check=True, timeout=120)
            report["detached"] = True


def smoke_dmg(dmg: Path, mcpb: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=False)
    report = {"ok": False, "sha256": sha256(dmg), "detached": False}
    with tempfile.TemporaryDirectory(prefix="uoink-dmg-install-") as temporary:
        scratch = Path(temporary)
        try:
            with installed_dmg(dmg, scratch, report) as (_, installed):
                report["mcpb"] = {"version": check(mcpb)["version"], "platform": "darwin", "ok": True}
                smoke(installed, output / "installed-copy")
                run(["codesign", "--verify", "--strict", "--deep", installed], capture_output=True)
                report["ok"] = True
        finally:
            report["ok"] = report["ok"] and report["detached"]
            write_json(output / "dmg-smoke.json", report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dmg", type=Path, required=True)
    parser.add_argument("--mcpb", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    smoke_dmg(args.dmg.resolve(), args.mcpb.resolve(), args.output.resolve())
