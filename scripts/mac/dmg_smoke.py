"""Mount the DMG read-only, install a copy, and smoke only that copy."""
from __future__ import annotations

import argparse
from pathlib import Path
import os
import subprocess
import tempfile

from build_bundle import run, sha256
from build_mcpb import check
from bundle_smoke import smoke
from qualify_deps import write_json


def smoke_dmg(dmg: Path, mcpb: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=False)
    report = {"ok": False, "sha256": sha256(dmg), "detached": False}
    with tempfile.TemporaryDirectory(prefix="uoink-dmg-install-") as temporary:
        scratch = Path(temporary)
        mount = scratch / "mounted"
        mount.mkdir()
        attached = False
        try:
            run(["hdiutil", "attach", "-readonly", "-nobrowse", "-mountpoint", mount, dmg])
            attached = True
            if not (mount / "Applications").is_symlink() or os.readlink(mount / "Applications") != "/Applications":
                raise ValueError("DMG is missing its /Applications link")
            installed = scratch / "Applications With Spaces/Uoink.app"
            installed.parent.mkdir()
            run(["ditto", mount / "Uoink.app", installed])
            run(["codesign", "--verify", "--strict", installed], capture_output=True)
            report["mcpb"] = {"version": check(mcpb)["version"], "platform": "darwin", "ok": True}
            smoke(installed, output / "installed-copy")
            # The existing smoke relocates and restores its input. Verify again
            # at the temporary Applications destination after that exercise.
            run(["codesign", "--verify", "--strict", installed], capture_output=True)
            report["ok"] = True
        finally:
            try:
                if attached:
                    subprocess.run(["hdiutil", "detach", str(mount)], check=True, timeout=120)
                    report["detached"] = True
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
