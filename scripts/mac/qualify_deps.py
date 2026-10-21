"""Collect arm64 wheel and standalone-Python evidence using only the stdlib.

Network operations are explicit CLI commands, intended for hosted macOS CI.
Importing this module and running its fixture tests never access the network.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
PLATFORMS = ("macosx_14_0_arm64", "macosx_15_0_arm64")
RELEASE_API = "https://api.github.com/repos/astral-sh/python-build-standalone/releases/tags/"
SOURCE_PINS = Path(__file__).with_name("source-wheels.json")
BUILD_TOOLING = Path(__file__).with_name("build-tooling.txt")
STANDALONE_PINS = Path(__file__).with_name("standalone-python.json")


def ui_pins() -> dict:
    manifest = json.loads((ROOT / "scripts/mac/payload.json").read_text(encoding="utf-8"))
    filename = manifest["ui_wheels"]
    if Path(filename).name != filename:
        raise ValueError("UI wheel pins must be beside the payload manifest")
    pins = json.loads((ROOT / "scripts/mac" / filename).read_text(encoding="utf-8"))
    for name, pin in pins.items():
        info = wheel_details(pin["filename"])
        if (canonical(name) != name or info["package"] != name or info["version"] != pin["version"]
                or not re.fullmatch(r"[0-9a-f]{64}", pin["sha256"])):
            raise ValueError("Invalid Darwin UI wheel pin: " + name)
    return pins


def verify_ui_wheels(rows: list[dict], *, complete: bool = False) -> None:
    pins = ui_pins()
    found = set()
    for row in rows:
        name = wheel_details(row["filename"])["package"]
        if name in pins:
            pin = pins[name]
            if row["filename"] != pin["filename"] or row["sha256"] != pin["sha256"]:
                raise ValueError("Darwin UI wheel differs from reviewed PyPI bytes: " + name)
            found.add(name)
    if complete and found != set(pins):
        raise ValueError("Missing Darwin UI wheels: " + ", ".join(sorted(set(pins) - found)))


def canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def read_pins(path: Path) -> list[tuple[str, str]]:
    pins = []
    seen = set()
    for number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        match = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9_.-]*)==([A-Za-z0-9][A-Za-z0-9_.+!-]*)", line)
        if not match or canonical(match[1]) in seen:
            raise ValueError(f"{path}:{number}: expected a unique exact package==version pin")
        seen.add(canonical(match[1]))
        pins.append((match[1], match[2]))
    return pins


def wheel_details(filename: str) -> dict:
    if not filename.endswith(".whl"):
        raise ValueError(f"Not a wheel: {filename}")
    distribution, version, *tail = filename[:-4].split("-")
    if len(tail) not in (3, 4):
        raise ValueError(f"Invalid wheel filename: {filename}")
    python, abi, platform = tail[-3:]
    floors = []
    for tag in platform.split("."):
        match = re.fullmatch(r"macosx_(\d+)_(\d+)_(arm64|universal2)", tag)
        if match:
            # Apple Silicon first shipped in macOS 11, including universal2
            # wheels whose filename advertises an older Intel deployment floor.
            floors.append(max((11, 0), (int(match[1]), int(match[2]))))
    floor = min(floors) if floors else None
    return {
        "filename": filename,
        "package": canonical(distribution),
        "version": version,
        "wheel_tag": f"{python}-{abi}-{platform}",
        "minimum_macos_implied": ".".join(map(str, floor)) if floor else None,
        "minimum_macos_basis": "wheel filename for arm64, not Mach-O inspection" if floor else
                               "no macOS floor in wheel filename",
    }


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def run_logged(command: list[str], log: Path, timeout: int = 240) -> int:
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w", encoding="utf-8") as stream:
        stream.write(json.dumps(command) + "\n")
        stream.flush()
        try:
            return subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT,
                                  timeout=timeout, check=False).returncode
        except (subprocess.TimeoutExpired, OSError) as exc:
            stream.write(f"\n{type(exc).__name__}: {exc}\n")
            return 124 if isinstance(exc, subprocess.TimeoutExpired) else 127


def download_command(platform: str, destination: Path) -> list[str]:
    return [sys.executable, "-m", "pip", "--isolated", "download",
            "--disable-pip-version-check", "--no-cache-dir", "--retries", "1",
            "--timeout", "30", "--index-url", "https://pypi.org/simple",
            "--only-binary=:all:", "--platform", platform, "--python-version", "3.13",
            "--implementation", "cp", "--dest", str(destination)]


def collect_wheels(source: Path, destination: Path | None, package: str | None = None) -> tuple[list, list]:
    found, errors = [], []
    for wheel in sorted(source.glob("*.whl")):
        try:
            details = wheel_details(wheel.name)
            # pip enforces the exact version, including PEP 440 normalization
            # (a pin of 1.0 can legitimately have a filename version of 1.0.0).
            if package is not None and details["package"] != package:
                raise ValueError(f"Unexpected distribution for {package}")
            details.update(size_bytes=wheel.stat().st_size, sha256=sha256(wheel))
            if destination is not None:
                target = destination / wheel.name
                if target.exists() and sha256(target) != details["sha256"]:
                    raise ValueError("Different bytes returned for the same wheel filename")
                if not target.exists():
                    shutil.move(str(wheel), target)
            found.append(details)
        except (ValueError, OSError) as exc:
            errors.append({"filename": wheel.name, "error": f"{type(exc).__name__}: {exc}"})
    return found, errors


def windows_build_pin(name: str) -> str:
    """Use the reviewed Windows build's tooling and final NLTK hash verbatim."""
    source = (ROOT / "build.ps1").read_text(encoding="utf-8-sig")
    matches = re.findall(r"^\$" + re.escape(name) + r"\s*=\s*'([^']+)'", source, re.MULTILINE)
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one Windows build pin: {name}")
    return matches[0]


def build_source_wheels(included: list[tuple[str, str]], wheels: Path, output: Path) -> dict:
    """Only the two reviewed pure-Python sdists and the existing NLTK patch.

    The sdists are pinned to the BLAKE2-256 content addresses retained in the
    September Python qualification. Verify bytes before executing build hooks;
    also record their SHA-256. There is no generic source-build fallback.
    """
    sources = json.loads(SOURCE_PINS.read_text(encoding="utf-8"))
    requested = {canonical(name): version for name, version in included}
    selected = {key: value for key, value in sources.items() if key in requested}
    if "nltk" in requested:
        selected["nltk"] = {"version": "3.10.3+uoink.pathsec1"}
    if not selected:
        return {}
    logs = output / "logs"
    logs.mkdir(exist_ok=True)
    tooling = [line for line in BUILD_TOOLING.read_text(encoding="utf-8").splitlines()
               if line and not line.startswith("#")]
    tooling_code = run_logged([sys.executable, "-m", "pip", "--isolated", "install",
                              "--disable-pip-version-check", "--no-cache-dir",
                              "--index-url", "https://pypi.org/simple", "--only-binary=:all:",
                              "--require-hashes", "-r", str(BUILD_TOOLING)],
                             logs / "source-build-tooling.txt", timeout=300)
    results = {}
    for key, pin in selected.items():
        row = {"package": key, "version": requested[key], "tooling": tooling,
               "wheel_found": False, "wheels": [], "errors": []}
        try:
            if requested[key] != pin["version"]:
                raise ValueError(f"Unreviewed source version: {key}=={requested[key]}")
            if tooling_code:
                raise ValueError("Pinned build tooling installation failed")
            with tempfile.TemporaryDirectory(prefix="uoink-source-wheel-") as temporary:
                # /var is a symlink on macOS. The NLTK builder intentionally
                # rejects linked ancestors, so pass canonical scratch paths.
                scratch = Path(temporary).resolve()
                built = scratch / "built"
                if key == "nltk":
                    spec = importlib.util.spec_from_file_location(
                        "nltk_pathsec_builder", ROOT / "scripts/build_nltk_pathsec_wheel.py")
                    builder = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(builder)
                    requirement = scratch / "upstream.txt"
                    requirement.write_text(
                        f"nltk==3.10.3 --hash=sha256:{builder.EXPECTED_WHEEL_SHA256}\n", encoding="utf-8")
                    command = [sys.executable, "-m", "pip", "--isolated", "download", "--no-deps",
                               "--only-binary=:all:", "--require-hashes", "--no-cache-dir",
                               "--index-url", "https://pypi.org/simple", "--dest", str(scratch),
                               "-r", str(requirement)]
                    if run_logged(command, logs / "nltk-upstream.txt"):
                        raise ValueError("Pinned NLTK upstream download failed")
                    provenance = builder.build_nltk_wheel(scratch / builder.EXPECTED_WHEEL_NAME, built)
                    expected = windows_build_pin("NLTK_PATHSEC_SHA256")
                    if sha256(built / builder.OUTPUT_WHEEL_NAME) != expected:
                        raise ValueError("Patched NLTK wheel differs from the Windows build hash")
                    row.update(upstream_sha256=builder.EXPECTED_WHEEL_SHA256,
                               expected_wheel_sha256=expected, provenance=provenance)
                else:
                    source = scratch / pin["url"].rsplit("/", 1)[1]
                    with request(pin["url"]) as response, source.open("wb") as stream:
                        shutil.copyfileobj(response, stream)
                    actual = hashlib.blake2b(source.read_bytes(), digest_size=32).hexdigest()
                    row.update(source_url=pin["url"], source_blake2b_256=actual, source_sha256=sha256(source))
                    if actual != pin["blake2b_256"]:
                        raise ValueError("Pinned sdist BLAKE2-256 mismatch")
                    built.mkdir()
                    command = [sys.executable, "-m", "pip", "--isolated", "wheel", "--no-deps",
                               "--no-build-isolation", "--no-index", "--no-cache-dir",
                               "--wheel-dir", str(built), str(source)]
                    if run_logged(command, logs / f"{key}-source-build.txt", timeout=300):
                        raise ValueError("Pinned sdist wheel build failed")
                found, errors = collect_wheels(built, None, key)
                if (errors or len(found) != 1 or found[0]["version"] != requested[key]
                        or found[0]["wheel_tag"] not in ("py3-none-any", "py2.py3-none-any")):
                    raise ValueError("Source build did not produce the expected pure Python wheel")
                row["wheels"], row["errors"] = collect_wheels(built, wheels, key)
                row["wheel_found"] = bool(row["wheels"]) and not row["errors"]
        except Exception as exc:
            row["errors"].append({"error": f"{type(exc).__name__}: {exc}"})
        results[key] = row
        write_json(output / "source-builds.json", results)
    return results


def qualify_wheels(lock: Path, exclusions_path: Path, output: Path) -> dict:
    pins = read_pins(lock)
    exclusions = json.loads(exclusions_path.read_text(encoding="utf-8"))
    if (not isinstance(exclusions, dict) or
            any(key != canonical(key) or not isinstance(reason, str) or not reason.strip()
                for key, reason in exclusions.items())):
        raise ValueError("Exclusions must map canonical package names to explicit reasons")
    unknown = set(exclusions) - {canonical(name) for name, _ in pins}
    if unknown:
        raise ValueError(f"Exclusions absent from lock: {sorted(unknown)}")
    output.mkdir(parents=True, exist_ok=True)
    wheels = output / "wheels"
    wheels.mkdir(exist_ok=True)
    if any(wheels.iterdir()):
        raise ValueError("Use an empty wheel directory so stale wheels cannot count as evidence")
    included = [(name, version) for name, version in pins if canonical(name) not in exclusions]
    additions = ui_pins()
    if set(additions) & {canonical(name) for name, _ in included}:
        raise ValueError("Darwin UI pins duplicate the base lock")
    included += [(name, pin["version"]) for name, pin in additions.items()]
    filtered = output / "included-pins.txt"
    filtered.write_text("".join(f"{name}=={version}\n" for name, version in included), encoding="utf-8")
    report = {"schema_version": 1, "python_version": "3.13", "lock_sha256": sha256(lock),
              "exclusions": [{"package": name, "version": version,
                              "reason": exclusions[canonical(name)]}
                             for name, version in pins if canonical(name) in exclusions],
              "darwin_additions": additions, "packages": [], "graph_attempts": []}
    source_builds = build_source_wheels(included, wheels, output)
    report["source_builds"] = source_builds
    for platform in PLATFORMS:
        for name, version in included:
            key = canonical(name)
            if key in source_builds:
                report["packages"].append({**source_builds[key], "platform": platform,
                                            "source_built": True})
                write_json(output / "wheels.json", report)
                continue
            log = output / "logs" / f"{platform}-{key}.txt"
            with tempfile.TemporaryDirectory(prefix="uoink-wheel-") as scratch:
                destination = Path(scratch)
                command = download_command(platform, destination) + ["--no-deps", f"{name}=={version}"]
                code = run_logged(command, log)
                found, errors = collect_wheels(destination, wheels, key) if code == 0 else ([], [])
                try:
                    verify_ui_wheels(found)
                except ValueError as exc:
                    errors.append({"error": str(exc)})
                row = {"package": name, "version": version, "platform": platform,
                       "wheel_found": bool(found) and not errors, "pip_exit_code": code,
                       "wheels": found, "errors": errors, "log": str(log.relative_to(output))}
                report["packages"].append(row)
                print(f"{platform} {name}=={version}: wheel_found={row['wheel_found']}", flush=True)
                write_json(output / "wheels.json", report)
        # This separate resolver attempt includes dependencies, so individual
        # wheel availability is never mistaken for a mutually consistent graph.
        log = output / "logs" / f"{platform}-combined-graph.txt"
        with tempfile.TemporaryDirectory(prefix="uoink-graph-") as scratch:
            code = run_logged(download_command(platform, Path(scratch)) +
                              ["--find-links", str(wheels), "-r", str(filtered)],
                              log, timeout=600)
            # Preserve additional Darwin dependencies only on resolver success.
            graph_wheels, errors = collect_wheels(Path(scratch), wheels if code == 0 else None)
            if code == 0:
                try:
                    verify_ui_wheels(graph_wheels, complete=True)
                except ValueError as exc:
                    errors.append({"error": str(exc)})
        report["graph_attempts"].append({"platform": platform, "resolved": code == 0 and not errors,
                                         "pip_exit_code": code, "wheels": graph_wheels, "errors": errors,
                                         "log": str(log.relative_to(output))})
        write_json(output / "wheels.json", report)
    inventory, errors = collect_wheels(wheels, None)
    write_json(wheels / "wheel-manifest.json", {
        "pins": [{"package": canonical(name), "version": version} for name, version in included],
        "wheels": inventory, "errors": errors,
    })
    if not errors and any(row["platform"] == "macosx_15_0_arm64" and row["resolved"]
                          for row in report["graph_attempts"]):
        from wheel_lock import generate
        generate(report, wheels, exclusions)
    return report


def standalone_pins() -> dict:
    pins = json.loads(STANDALONE_PINS.read_text(encoding="utf-8"))
    tag = pins.get("release_tag", "")
    if pins.get("schema_version") != 1 or not re.fullmatch(r"\d{8}", tag):
        raise ValueError("Standalone Python requires a pinned dated release tag")
    if not pins.get("assets"):
        raise ValueError("Standalone Python requires pinned asset names and SHA-256 values")
    names = set()
    for asset in pins["assets"]:
        name = asset.get("name", "")
        pattern = (r"cpython-3\.13\.\d+\+" + tag +
                   r"-aarch64-apple-darwin-install_only(?:_stripped)?\.tar\.gz")
        if (not re.fullmatch(pattern, name) or name in names or
                not re.fullmatch(r"[0-9a-f]{64}", asset.get("sha256", "")) or
                type(asset.get("size_bytes")) is not int or asset["size_bytes"] <= 0):
            raise ValueError("Invalid or duplicate standalone Python asset pin")
        names.add(name)
    return pins


def standalone_candidates(release: dict, pins: dict) -> list[dict]:
    if release.get("tag_name") != pins["release_tag"]:
        raise ValueError("Release tag differs from the standalone Python pin")
    selected = []
    for pin in pins["assets"]:
        matches = [asset for asset in release.get("assets", []) if asset.get("name") == pin["name"]]
        if len(matches) != 1:
            raise ValueError(f"Expected one matching pinned asset: {pin['name']}")
        selected.append(matches[0])
    return selected


def request(url: str):
    headers = {"User-Agent": "uoink-mac-qualification"}
    if urllib.parse.urlparse(url).netloc == "api.github.com":
        headers["Accept"] = "application/vnd.github+json"
        # Hosted Actions provides this env var. Never read credential files,
        # print headers, or send the API token to release assets or PyPI.
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = "Bearer " + token
    return urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=120)


def standalone_error(exc: Exception) -> dict:
    result = {"error": f"{type(exc).__name__}: {exc}"}
    if isinstance(exc, urllib.error.HTTPError):
        result["http_status"] = exc.code
        exc.close()
    return result


def qualify_standalone(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    report = {"schema_version": 1, "candidates": []}
    try:
        pins = standalone_pins()
        release_api = RELEASE_API + pins["release_tag"]
        report.update(release_api=release_api, release_tag=pins["release_tag"])
        with request(release_api) as response:
            release = json.load(response)
        report.update(release_url=release["html_url"])
        for pin, asset in zip(pins["assets"], standalone_candidates(release, pins)):
            url = ("https://github.com/astral-sh/python-build-standalone/releases/download/" +
                   pins["release_tag"] + "/" + urllib.parse.quote(pin["name"], safe=""))
            row = {"name": pin["name"], "url": url, "expected_sha256": pin["sha256"],
                   "expected_size_bytes": pin["size_bytes"],
                   "published_size_bytes": asset["size"], "published_digest": asset.get("digest"),
                   "downloaded": False}
            try:
                if asset["size"] != pin["size_bytes"]:
                    raise ValueError("Published size differs from pinned size")
                digest = asset.get("digest")
                if digest and digest != "sha256:" + pin["sha256"]:
                    raise ValueError("Published hash differs from pinned SHA-256")
                # Download completely, hash, then discard; never commit or upload binaries.
                with tempfile.TemporaryDirectory(prefix="uoink-python-") as scratch:
                    target = Path(scratch) / asset["name"]
                    with request(row["url"]) as response, target.open("wb") as dest:
                        shutil.copyfileobj(response, dest)
                    row.update(size_bytes=target.stat().st_size, sha256=sha256(target))
                    if row["size_bytes"] != pin["size_bytes"]:
                        raise ValueError("Downloaded size differs from pinned size")
                    if row["sha256"] != pin["sha256"]:
                        raise ValueError("Downloaded hash differs from pinned SHA-256")
                    row["downloaded"] = True
            except Exception as exc:
                row.update(standalone_error(exc))
            report["candidates"].append(row)
            print(json.dumps(row), flush=True)
            write_json(output / "python-standalone.json", report)
    except Exception as exc:
        report.update(standalone_error(exc))
        print(json.dumps({key: value for key, value in report.items() if key != "candidates"}), flush=True)
    write_json(output / "python-standalone.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("wheels", "standalone"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--lock", type=Path, default=ROOT / "requirements-installer-lock.txt")
    parser.add_argument("--exclusions", type=Path, default=Path(__file__).with_name("dependency-exclusions.json"))
    args = parser.parse_args()
    if args.command == "wheels":
        report = qualify_wheels(args.lock, args.exclusions, args.output)
        # macOS 14 is retained as diagnostic evidence, not a supported target.
        return int(any(not row["wheel_found"] for row in report["packages"]
                       if row["platform"] == "macosx_15_0_arm64") or
                   any(not row["resolved"] for row in report["graph_attempts"]
                       if row["platform"] == "macosx_15_0_arm64"))
    report = qualify_standalone(args.output)
    return int(bool(report.get("error")) or any(not row["downloaded"] for row in report["candidates"]))


if __name__ == "__main__":
    raise SystemExit(main())
