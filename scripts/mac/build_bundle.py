"""Assemble the ad-hoc-signed CI app and DMG from pinned payloads."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import plistlib
import posixpath
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.parse
import urllib.request

from qualify_deps import ROOT, sha256, standalone_pins, write_json
from wheel_lock import LOCK_NAME, verify
import ffmpeg_bundle

MAC = Path(__file__).parent
PYTHON_ROOT = Path("Contents/Resources/Python")
PYTHON_EXECUTABLE = PYTHON_ROOT / "bin/python3"


def run(command, **kwargs):
    command = [str(x) for x in command]
    if command[0] == "codesign":
        kwargs["capture_output"] = True
    try:
        return subprocess.run(command, check=True, text=True, **kwargs)
    except subprocess.CalledProcessError as exc:
        if command[0] == "codesign":
            print(f"codesign failed ({exc.returncode}): {command[-1]}", file=sys.stderr)
            print(exc.stderr or "codesign produced no stderr", file=sys.stderr)
        raise


def payload_files(root: Path = ROOT) -> list[Path]:
    manifest = json.loads((root / "scripts/mac/payload.json").read_text(encoding="utf-8"))
    if manifest["schema_version"] != 1:
        raise ValueError("Unknown payload manifest")
    paths = manifest["paths"]
    for name in paths:
        path = Path(name)
        if path.is_absolute() or ".." in path.parts or not (root / path).exists():
            raise ValueError(f"Invalid or missing payload path: {name}")
    # Tracked files only: never copy scratch, state, caches or developer secrets.
    result = run(["git", "ls-files", "-z", "--", *paths], cwd=root, capture_output=True)
    files = [Path(name) for name in result.stdout.split("\0") if name]
    # Explicit reviewed additions also work in an uncommitted worktree. No glob
    # may admit untracked state; this list names individual source files only.
    for name in manifest.get("mac_files", []):
        path = Path(name)
        if path.is_absolute() or ".." in path.parts or not (root / path).is_file():
            raise ValueError(f"Invalid Mac source: {name}")
        if path not in files:
            files.append(path)
    for path in files:
        if (path.name in {"token.txt", "server.log", "server.pid"} or
                path.suffix in {".pem", ".key", ".pyc"} or path.name.startswith(".env") or
                "__pycache__" in path.parts or (root / path).is_symlink()):
            raise ValueError(f"Forbidden source payload: {path}")
    for name in paths:
        if not any(p == Path(name) or Path(name) in p.parents for p in files):
            raise ValueError(f"Payload not tracked: {name}")
    return sorted(files)


def tree_inventory(root: Path) -> list[dict]:
    rows = []
    for path in sorted(root.rglob("*")):
        meta = path.lstat()
        row = {"path": path.relative_to(root).as_posix(), "mode": stat.S_IMODE(meta.st_mode)}
        if path.is_symlink():
            if not bundle_path(path, root) or not path.resolve(strict=True).is_relative_to(root.resolve()):
                raise ValueError(f"Symlink escapes app: {path}")
            row.update(type="symlink", target=os.readlink(path))
        elif path.is_file():
            row.update(type="file", size=meta.st_size, sha256=sha256(path))
        elif path.is_dir():
            row.update(type="directory")
        else:
            raise ValueError(f"Special file in app: {path}")
        rows.append(row)
    return rows


def relocate_python_script(content: str) -> str:
    """Replace pip's build-path shebang with a relative interpreter shim."""
    lines = content.splitlines(keepends=True)
    if not lines or not lines[0].startswith("#!"):
        return content
    if "python" in lines[0]:
        body = "".join(lines[1:])
    elif len(lines) > 2 and lines[1].startswith("'''exec'") and "python" in lines[1]:
        body = "".join(lines[3:])
    else:
        return content
    return ("#!/bin/sh\n'''exec' \"$(dirname \"$0\")/python3\" -B -s \"$0\" \"$@\"\n' '''\n" + body)


def extract_python(archive: Path, destination: Path, pin: dict) -> None:
    if archive.stat().st_size != pin["size_bytes"] or sha256(archive) != pin["sha256"]:
        raise ValueError("Standalone Python size/hash mismatch")
    with tarfile.open(archive) as bundle:
        members = bundle.getmembers()
        if not members or any(m.name.split("/")[0] != "python" for m in members):
            raise ValueError("Unexpected standalone Python archive root")
        # data_filter rejects escaping symlinks, traversal and special files.
        bundle.extractall(destination, filter="data")


def prune_python(app: Path, report: Path) -> list[dict]:
    """Remove development payload after pip installation; preserve the Tk picker."""
    root = app / PYTHON_ROOT
    targets = [root / name for name in ("include", "lib/pkgconfig", "share")]
    for pattern in ("lib/python*/config-*-darwin", "lib/python*/test",
                    "lib/python*/unittest/test", "lib/python*/ctypes/test"):
        targets.extend(root.glob(pattern))
    # Uoink invokes modules via python3 -m, never wheel console entry points.
    # Keep the canonical python3 link and its real interpreter target only.
    python = root / "bin/python3"
    keep = {python, python.resolve(strict=True)}
    if not bundle_path(python, root) or python.resolve().parent != (root / "bin").resolve():
        raise ValueError("Bundled Python interpreter must stay inside Python/bin")
    targets.extend(path for path in (root / "bin").iterdir() if path not in keep)
    removed = []
    write_json(report, removed)
    for target in sorted(set(targets)):
        if not target.exists() and not target.is_symlink():
            continue
        if not bundle_path(target, root):
            raise ValueError(f"Refusing to prune outside bundled Python: {target}")
        entries = [target] if target.is_symlink() else [target, *sorted(target.rglob("*"))]
        rows = [{"path": entry.relative_to(root).as_posix(),
                 "type": "symlink" if entry.is_symlink() else "directory" if entry.is_dir() else "file"}
                for entry in entries]
        if target.is_symlink() or target.is_file():
            target.unlink()
        else:
            shutil.rmtree(target)
        removed.extend(rows)
        write_json(report, removed)
    return removed


MACHO = {b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xce",
         b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca",
         b"\xca\xfe\xba\xbf", b"\xbf\xba\xfe\xca"}


def native_loader_paths(commands: str) -> list[tuple[str, str]]:
    """Read loader paths from otool -l, excluding LC_ID_DYLIB in every slice.

    otool -L also prints a dylib's own install ID as an indented entry. That
    ID (including delocate's /DLC/... IDs) is not a dependency to resolve.
    """
    paths = []
    load_commands = {"LC_LOAD_DYLIB", "LC_LOAD_WEAK_DYLIB", "LC_REEXPORT_DYLIB",
                     "LC_LAZY_LOAD_DYLIB", "LC_LOAD_UPWARD_DYLIB"}
    blocks = re.split(r"(?m)^\s*cmd (LC_\w+)\s*$", commands)
    for command, body in zip(blocks[1::2], blocks[2::2]):
        if command == "LC_RPATH":
            kind, field = "rpath", "path"
        elif command in load_commands:
            kind, field = "dependency", "name"
        else:
            continue
        match = re.search(rf"(?m)^\s*{field} (.+?) \(offset \d+\)\s*$", body)
        if not match:
            raise ValueError(f"Malformed {command} load command")
        paths.append((kind, match.group(1)))
    return paths


def bundle_path(path: Path, app: Path, seen: frozenset[Path] = frozenset()) -> bool:
    """Require lexical containment as well as symlink containment.

    An outside link pointing back into the app is still an outside stored path.
    Inspect link targets too, so a chain cannot leave the app and return to it.
    """
    app = Path(os.path.abspath(app))
    if not path.is_absolute():
        path = Path.cwd() / path
    if not Path(os.path.abspath(path)).is_relative_to(app):
        return False
    for entry in (path, *path.parents):
        if entry == app:
            break
        if entry.is_symlink():
            if entry in seen or not bundle_path(
                    entry.parent / os.readlink(entry), app, seen | {entry}):
                return False
    try:
        return path.resolve().is_relative_to(app.resolve())
    except (OSError, RuntimeError):
        return False


def allowed_absolute_loader_path(value: str, app: Path) -> bool:
    normalized = posixpath.normpath(value)
    if normalized in ("/usr/lib", "/System/Library") or normalized.startswith(
            ("/usr/lib/", "/System/Library/")):
        return True
    return Path(value).is_absolute() and bundle_path(Path(value), app)


def rpath_removals(commands: str, app: Path) -> list[str]:
    """Plan deletions from otool -l, once per value across universal slices."""
    return list(dict.fromkeys(value for kind, value in native_loader_paths(commands)
                             if kind == "rpath" and
                             (posixpath.isabs(value) or Path(value).is_absolute()) and
                             not allowed_absolute_loader_path(value, app)))


def macho_files(app: Path):
    for path in sorted(app.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        if not bundle_path(path, app):
            raise ValueError(f"File escapes app: {path}")
        with path.open("rb") as stream:
            magic = stream.read(4)
        if magic in MACHO:
            yield path


def rewrite_rpaths(app: Path, report: Path) -> None:
    removals = []
    # Keep successful removals available even if a later tool or inventory fails.
    write_json(report, removals)
    for path in macho_files(app):
        commands = run(["otool", "-l", path], capture_output=True).stdout
        planned = rpath_removals(commands, app)
        for rpath in planned:
            run(["install_name_tool", "-delete_rpath", rpath, path])
            removals.append({"file": path.relative_to(app).as_posix(), "rpath": rpath})
            write_json(report, removals)
        # Header edits invalidate old signatures. sign_app signs the completed
        # tree inside-out, including native files under Resources, then the app.


def binary_inventory(app: Path) -> list[dict]:
    rows = []
    for path in macho_files(app):
        arch = run(["lipo", "-archs", path], capture_output=True).stdout.strip()
        if "arm64" not in arch.split():
            raise ValueError(f"Missing arm64 architecture: {path}: {arch}")
        loads = run(["otool", "-L", path], capture_output=True).stdout
        commands = run(["otool", "-l", path], capture_output=True).stdout
        for kind, dependency in native_loader_paths(commands):
            if dependency.startswith(("@loader_path/", "@rpath/", "@executable_path/")) or dependency in (
                                          "@loader_path", "@rpath", "@executable_path"):
                continue
            if allowed_absolute_loader_path(dependency, app):
                continue
            raise ValueError(f"Nonrelocatable {kind}: {path}: {dependency}")
        rows.append({"path": path.relative_to(app).as_posix(), "architectures": arch,
                     "sha256": sha256(path), "load_commands": loads, "headers": commands})
    if not rows:
        raise ValueError("App has no Mach-O payload")
    return rows


def signing_order(app: Path) -> list[Path]:
    with (app / "Contents/Info.plist").open("rb") as stream:
        if plistlib.load(stream).get("CFBundleExecutable") != "Uoink":
            raise ValueError("CFBundleExecutable must match Contents/MacOS/Uoink")
    targets = set(macho_files(app))
    main = app / "Contents/MacOS/Uoink"
    if main not in targets:
        raise ValueError("Contents/MacOS/Uoink must be a native executable")
    # Executable scripts in code locations (the uoink CLI shim in Helpers) are
    # code to codesign; sign them like Mach-O files (signature in xattrs).
    for folder in ("Contents/Helpers", "Contents/MacOS"):
        root = app / folder
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.is_symlink() or not path.is_file() or path in targets:
                continue
            with path.open("rb") as stream:
                if stream.read(2) == b"#!":
                    targets.add(path)
    for path in app.rglob("*"):
        if path.is_symlink() or not path.is_dir() or path.suffix not in {".app", ".framework", ".bundle", ".xpc"}:
            continue
        for relative in ("Contents/Info.plist", "Resources/Info.plist", "Info.plist"):
            info = path / relative
            if info.is_file():
                with info.open("rb") as stream:
                    if plistlib.load(stream).get("CFBundleExecutable"):
                        targets.add(path)
                break
    return sorted(targets, key=lambda p: (-len(p.parts), str(p))) + [app]


def sign_app(app: Path, report: Path) -> None:
    ordered = signing_order(app)
    for path in ordered:
        run(["codesign", "--force", "--sign", "-", "--timestamp=none", path])
    run(["codesign", "--verify", "--strict", "--deep", app])
    assessment = subprocess.run(["spctl", "--assess", "--type", "execute", "--verbose=4", str(app)],
                                text=True, capture_output=True, timeout=120)
    write_json(report, {"identity": "ad-hoc", "strict_verification": "passed",
                        "signed": [p.relative_to(app).as_posix() for p in ordered],
                        "spctl": {"returncode": assessment.returncode, "stdout": assessment.stdout,
                                  "stderr": assessment.stderr, "expected": "rejection until Developer ID and notarization"}})


def create_dmg(app: Path, output: Path, version: str) -> Path:
    dmg = output / f"Uoink-{version}-macos-arm64.dmg"
    if dmg.exists():
        raise ValueError("DMG already exists")
    with tempfile.TemporaryDirectory(prefix="uoink-dmg-stage-") as temporary:
        stage = Path(temporary)
        run(["ditto", app, stage / "Uoink.app"])
        (stage / "Applications").symlink_to("/Applications", target_is_directory=True)
        command = ["hdiutil", "create", "-format", "UDZO", "-volname", f"Uoink {version}",
                   "-srcfolder", stage, dmg]
        # Hosted macOS runners intermittently report "hdiutil: create failed -
        # Resource busy"; retry a bounded number of times before failing.
        for attempt in range(1, 4):
            try:
                run(command, capture_output=True)
                break
            except subprocess.CalledProcessError as error:
                detail = (error.stderr or "").strip()
                print(f"hdiutil create attempt {attempt} failed: {detail}", file=sys.stderr, flush=True)
                if dmg.exists():
                    dmg.unlink()
                if "Resource busy" not in detail or attempt == 3:
                    raise
                time.sleep(10 * attempt)
    write_json(output / "dmg.json", {"filename": dmg.name, "size_bytes": dmg.stat().st_size,
                                     "sha256": sha256(dmg), "volume": f"Uoink {version}"})
    return dmg


def build(wheels: Path, output: Path, ffmpeg_output: Path | None = None) -> Path:
    if sys.platform != "darwin" or platform.machine() != "arm64":
        raise RuntimeError("Build requires native macOS arm64")
    if ffmpeg_output is None:
        raise ValueError("A verified FFmpeg build output is required")
    if output.exists():
        raise ValueError("Build output must be a new directory; existing artifacts are never overwritten")
    output.mkdir(parents=True)
    exclusions = json.loads((MAC / "dependency-exclusions.json").read_text())
    rows = verify(wheels, exclusions)
    pins = standalone_pins()
    pin = next(row for row in pins["assets"] if row["name"].endswith("-install_only.tar.gz"))
    app = output / "Uoink.app"
    contents = app / "Contents"
    resources = contents / "Resources"
    resources.mkdir(parents=True)
    (contents / "MacOS").mkdir()
    (contents / "Frameworks").mkdir()
    with tempfile.TemporaryDirectory(prefix="uoink-payload-") as temporary:
        scratch = Path(temporary)
        archive = scratch / pin["name"]
        url = ("https://github.com/astral-sh/python-build-standalone/releases/download/" +
               pins["release_tag"] + "/" + urllib.parse.quote(pin["name"], safe=""))
        with urllib.request.urlopen(url, timeout=120) as response, archive.open("wb") as target:
            shutil.copyfileobj(response, target)
        extract_python(archive, scratch / "unpacked", pin)
        shutil.move(str(scratch / "unpacked/python"), app / PYTHON_ROOT)
        selected = scratch / "wheels"
        selected.mkdir()
        for row in rows:
            shutil.copyfile(wheels / row["filename"], selected / row["filename"])
        python = app / PYTHON_EXECUTABLE
        env = os.environ.copy()
        for key in ("PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP"):
            env.pop(key, None)
        env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")
        version = run([python, "-B", "-c", "import platform; print(platform.python_version()); print(platform.machine())"],
                      env=env, capture_output=True).stdout.splitlines()
        expected_python = pin["name"].split("+")[0].removeprefix("cpython-")
        if version != [expected_python, "arm64"]:
            raise ValueError(f"Wrong bundled interpreter: {version}")
        run([python, "-B", "-m", "pip", "--isolated", "install", "--no-index", "--no-cache-dir",
             "--no-compile", "--only-binary=:all:", "--require-hashes", "--find-links", selected,
             "-r", wheels / LOCK_NAME], env=env)
        run([python, "-B", "-m", "pip", "check"], env=env)
        packages = run([python, "-B", "-c", "import importlib.metadata as m, json; "
                        "print(json.dumps(sorted([{'name': d.metadata['Name'], 'version': d.version, "
                        "'license': d.metadata.get('License-Expression') or d.metadata.get('License'), "
                        "'license_files': d.metadata.get_all('License-File') or []} "
                        "for d in m.distributions()], key=lambda d:d['name'])))"],
                       env=env, capture_output=True).stdout
        pruned = prune_python(app, output / "python-pruned.json")
        write_json(output / "python-bin-pruned.json", [row["path"].split("/")[1] for row in pruned
                   if row["path"].startswith("bin/") and row["path"].count("/") == 1])
    files = payload_files()
    for relative in files:
        target = resources / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    (resources / "uoink").chmod(0o755)
    launcher = contents / "MacOS/Uoink"
    run(["xcrun", "clang", "-arch", "arm64", "-mmacosx-version-min=14.0", "-Wall", "-Wextra", "-Werror",
         ROOT / "installer/mac/launcher.c", "-o", launcher])
    launcher.chmod(0o755)
    version = (ROOT / "VERSION").read_text().strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Invalid product VERSION")
    with (contents / "Info.plist").open("wb") as stream:
        plistlib.dump({"CFBundleName": "Uoink", "CFBundleDisplayName": "Uoink",
                       "CFBundleIdentifier": "com.ryanbiddy.uoink", "CFBundleExecutable": "Uoink",
                       "CFBundlePackageType": "APPL", "CFBundleShortVersionString": version,
                       "CFBundleVersion": version, "LSMinimumSystemVersion": "14.0",
                       "LSUIElement": True}, stream)
    notices = resources / "notices"
    notices.mkdir()
    shutil.copyfile(output / "python-pruned.json", notices / "python-pruned.json")
    shutil.copyfile(wheels / LOCK_NAME, notices / LOCK_NAME)
    shutil.copyfile(MAC / "standalone-python.json", notices / "standalone-python.json")
    shutil.copyfile(MAC / "FFMPEG.md", notices / "FFMPEG.md")
    shutil.copyfile(MAC / "payload.json", notices / "payload.json")
    write_json(notices / "resolved-wheels.json", {"wheels": rows})
    write_json(notices / "packages.json", json.loads(packages))
    ffmpeg = ffmpeg_bundle.install(ffmpeg_output, app, notices)
    cli = contents / "Helpers/uoink"
    shutil.copyfile(ROOT / "installer/mac/cli.sh", cli)
    cli.chmod(0o755)
    (resources / "scripts/mac/uninstall.sh").chmod(0o755)
    rewrite_rpaths(app, output / "native-rpath-removals.json")
    write_json(notices / "build.json", {"version": version, "python": pin, "python_url": url,
                                       "platform": platform.platform(), "ffmpeg": ffmpeg,
                                       "signing": "whole app ad-hoc; no Developer ID or notarization",
                                       "minimum_os": "14.0",
                                       "source_files": [p.as_posix() for p in files]})
    sign_app(app, output / "signing.json")
    write_json(output / "native-inventory.json", binary_inventory(app))
    inventory = tree_inventory(app)
    write_json(output / "file-inventory.json", inventory)
    write_json(output / "size.json", {"file_bytes": sum(row.get("size", 0) for row in inventory),
                                      "entries": len(inventory)})
    # tar preserves executable modes and relative symlinks, unlike artifact upload.
    with tarfile.open(output / f"uoink-{version}-macos-arm64.tar.gz", "w:gz") as archive:
        archive.add(app, arcname=app.name)
    archive_path = output / f"uoink-{version}-macos-arm64.tar.gz"
    write_json(output / "archive.json", {"filename": archive_path.name,
                                         "size_bytes": archive_path.stat().st_size,
                                         "sha256": sha256(archive_path)})
    create_dmg(app, output, version)
    return app


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheels", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--ffmpeg-output", required=True, type=Path)
    args = parser.parse_args()
    print(build(args.wheels.resolve(), args.output.resolve(), args.ffmpeg_output.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
