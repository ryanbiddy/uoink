"""Build the two pinned LGPL FFmpeg payloads on native macOS arm64 only.

Only this CLI downloads sources. Imports, validation and fixture tests are offline.
The installed output is cacheable; build directories are not.
"""
from __future__ import annotations

import argparse
from collections import deque
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

MAC = Path(__file__).resolve().parent
FINGERPRINT = "FCF986EA15E6E293A5644F10B4322F04D67658D8"
LIBRARIES = {"avcodec": 61, "avformat": 61, "avutil": 59, "swresample": 5,
             "swscale": 8, "avfilter": 10, "avdevice": 61}
BASE_FLAGS = {"--disable-gpl", "--disable-nonfree",
              "--disable-autodetect", "--disable-doc", "--disable-debug",
              "--disable-everything", "--disable-programs", "--enable-zlib"}
ROLE_FLAGS = {
    "cli": {"--enable-static", "--disable-shared", "--enable-ffmpeg", "--enable-ffprobe",
            "--enable-network", "--enable-securetransport"},
    "shared": {"--enable-shared", "--disable-static", "--enable-pic", "--disable-network",
               "--install-name-dir=@rpath"},
}


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_config(path: Path = MAC / "payload.json") -> dict:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise ValueError("Unknown FFmpeg payload schema")
    config = manifest["ffmpeg"]
    if config["minimum_macos"] != "15.0" or set(config["common_flags"]) != BASE_FLAGS:
        raise ValueError("Unreviewed FFmpeg floor or common configure flags")
    for role, version in (("cli", "8.1.2"), ("shared", "7.1.5")):
        pin = config[role]
        if (pin["version"] != version or pin["url"] != f"https://ffmpeg.org/releases/ffmpeg-{version}.tar.xz"
                or type(pin["size_bytes"]) is not int or pin["size_bytes"] <= 0
                or not re.fullmatch(r"[0-9a-f]{64}", pin["sha256"])
                or pin["signing_key_fingerprint"] != FINGERPRINT
                or set(pin["flags"]) != ROLE_FLAGS[role]):
            raise ValueError(f"Invalid or unreviewed FFmpeg {role} pin/flags")
        for kind, names in components(config, role).items():
            if (kind not in {"demuxer", "muxer", "decoder", "encoder", "parser", "filter", "bsf", "protocol"}
                    or not names or any(not re.fullmatch(r"[a-z0-9_]+", n) or n.startswith("lib") for n in names)):
                raise ValueError(f"Invalid FFmpeg component list: {kind}")
    return config


def components(config: dict, role: str) -> dict[str, list[str]]:
    result = {k: list(v) for k, v in config["components"].items()}
    for kind, names in config[role]["components"].items():
        result.setdefault(kind, []).extend(names)
    return {k: sorted(set(v)) for k, v in result.items()}


def configure_flags(config: dict, role: str) -> list[str]:
    return [*config["common_flags"], *config[role]["flags"],
            *(f"--enable-{kind}={','.join(names)}" for kind, names in sorted(components(config, role).items()))]


def validate_configuration(config: dict, role: str, headers: str) -> None:
    """Do not mistake configure's successful exit for enabled dependencies."""
    enabled = set(re.findall(r"^#define (CONFIG_\w+) 1$", headers, re.M))
    required = {f"CONFIG_{name.upper()}_{kind.upper()}"
                for kind, names in components(config, role).items() for name in names}
    required.update(f"CONFIG_{name.upper()}" for name in LIBRARIES)
    required.add("CONFIG_ZLIB")
    required.add("CONFIG_STATIC" if role == "cli" else "CONFIG_SHARED")
    forbidden = {"CONFIG_GPL", "CONFIG_NONFREE", "CONFIG_VERSION3"}
    forbidden.add("CONFIG_SHARED" if role == "cli" else "CONFIG_STATIC")
    if role == "cli":
        required.update({"CONFIG_FFMPEG", "CONFIG_FFPROBE", "CONFIG_NETWORK", "CONFIG_SECURETRANSPORT"})
    else:
        forbidden.add("CONFIG_NETWORK")
    if required - enabled or forbidden & enabled:
        raise ValueError(f"FFmpeg configure mismatch: missing={sorted(required - enabled)}, "
                         f"forbidden={sorted(forbidden & enabled)}")


def validate_source_components(config: dict, role: str, source: Path, env: dict) -> dict:
    """Check every requested name against this hash-verified release's configure."""
    inventory = {}
    for kind, names in sorted(components(config, role).items()):
        result = run(["/bin/bash", source / "configure", f"--list-{kind}s"],
                     cwd=source, env=env, capture_output=True)
        available = set(result.stdout.split())
        missing = set(names) - available
        if missing:
            raise ValueError(f"FFmpeg {config[role]['version']} unknown {kind}s: {sorted(missing)}")
        inventory[kind] = sorted(available)
    return inventory


def print_failure_logs(source: Path, evidence: Path) -> None:
    """Expose useful diagnostics before TemporaryDirectory removes the build."""
    for path in (source / "ffbuild/config.log", evidence / "build.log"):
        print(f"\n--- Last 150 lines: {path} ---", file=sys.stderr, flush=True)
        try:
            with path.open(encoding="utf-8", errors="replace") as stream:
                print("".join(deque(stream, maxlen=150)), end="", file=sys.stderr, flush=True)
        except OSError as error:
            print(f"Log unavailable: {error}", file=sys.stderr, flush=True)


def configure_and_build(config: dict, role: str, source: Path, evidence: Path,
                        command: list, env: dict) -> None:
    with (evidence / "build.log").open("w", encoding="utf-8") as log:
        try:
            write_json(evidence / "source-components.json",
                       validate_source_components(config, role, source, env))
            run(command, cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT)
            log.flush()
            # pkg-config is absent on purpose (no system-library autodetection), so
            # its warning is expected; any other configure warning still fails, and
            # validate_configuration below checks every requested component.
            warnings = [line for line in (evidence / "build.log").read_text(encoding="utf-8").splitlines()
                        if re.search(r"WARNING:.*(?:did not match|not found|disabled)", line, re.I)
                        and not re.search(r"WARNING: pkg-config not found", line, re.I)]
            if warnings:
                raise ValueError("FFmpeg configure could not enable a requested component: " + "; ".join(warnings))
            validate_configuration(config, role, (source / "config.h").read_text() + "\n" +
                                   (source / "config_components.h").read_text())
            run(["/usr/bin/make", f"-j{os.cpu_count() or 2}"], cwd=source, env=env,
                stdout=log, stderr=subprocess.STDOUT)
            run(["/usr/bin/make", "install"], cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT)
        except (OSError, ValueError, subprocess.SubprocessError):
            log.flush()
            print_failure_logs(source, evidence)
            raise
        finally:
            for name in ("config.h", "config_components.h", "ffbuild/config.mak", "ffbuild/config.log"):
                if (source / name).is_file():
                    shutil.copyfile(source / name, evidence / Path(name).name)


def cache_key(config: dict) -> str:
    # Includes source hashes, flags/components, this recipe and the consumer.
    value = json.dumps(config, sort_keys=True).encode()
    for name in ("build_ffmpeg.py", "ffmpeg_bundle.py"):
        value += (MAC / name).read_bytes()
    return hashlib.sha256(value).hexdigest()


def extract_source(archive: Path, destination: Path, pin: dict) -> Path:
    # Both checks precede even opening the archive, including on a cache hit.
    if archive.stat().st_size != pin["size_bytes"] or digest(archive) != pin["sha256"]:
        raise ValueError("FFmpeg source size/hash mismatch")
    root = f"ffmpeg-{pin['version']}"
    with tarfile.open(archive, "r:xz") as source:
        members = source.getmembers()
        if not members or any(m.name.split("/")[0] != root for m in members):
            raise ValueError("Unexpected FFmpeg source root")
        source.extractall(destination, filter="data")
    return destination / root


def clean_environment() -> dict:
    env = {k: v for k, v in os.environ.items() if k not in {
        "CC", "CXX", "CPP", "CFLAGS", "CXXFLAGS", "CPPFLAGS", "LDFLAGS", "LIBRARY_PATH",
        "CPATH", "C_INCLUDE_PATH", "CPLUS_INCLUDE_PATH", "PKG_CONFIG", "PKG_CONFIG_PATH",
        "PKG_CONFIG_LIBDIR", "PKG_CONFIG_SYSROOT_DIR",
        "AS", "ASFLAGS", "LD", "AR", "RANLIB", "STRIP", "NM", "LDSOFLAGS",
        "SDKROOT", "MACOSX_DEPLOYMENT_TARGET", "BASH_ENV", "ENV"} and not k.startswith("DYLD_")}
    env.update(PATH="/usr/bin:/bin:/usr/sbin:/sbin", LC_ALL="C", MACOSX_DEPLOYMENT_TARGET="15.0")
    return env


def run(command, **kwargs):
    return subprocess.run([str(x) for x in command], check=True, text=True, **kwargs)


def output_inventory(root: Path) -> list[dict]:
    rows = []
    for path in sorted(root.rglob("*")):
        if path.name == "cache.json":
            continue
        if path.is_symlink():
            if not path.resolve(strict=True).is_relative_to(root.resolve()):
                raise ValueError(f"Escaping FFmpeg output link: {path}")
            rows.append({"path": path.relative_to(root).as_posix(), "link": os.readlink(path)})
        elif path.is_file():
            rows.append({"path": path.relative_to(root).as_posix(), "sha256": digest(path),
                         "mode": path.stat().st_mode & 0o777})
    return rows


def verify_output(output: Path, config: dict) -> dict:
    receipt = json.loads((output / "cache.json").read_text())
    if receipt["key"] != cache_key(config) or receipt["files"] != output_inventory(output):
        raise ValueError("FFmpeg cached output recipe/hash mismatch")
    return receipt


def build(output: Path) -> None:
    if sys.platform != "darwin" or platform.machine() != "arm64":
        raise RuntimeError("FFmpeg build requires native macOS arm64")
    config = load_config()
    if output.exists():
        verify_output(output, config)
        return
    output.mkdir(parents=True)
    env = clean_environment()
    sdk = run(["/usr/bin/xcrun", "--sdk", "macosx", "--show-sdk-path"], env=env, capture_output=True).stdout.strip()
    cc = run(["/usr/bin/xcrun", "--sdk", "macosx", "--find", "clang"], env=env, capture_output=True).stdout.strip()
    compiler = run([cc, "--version"], env=env, capture_output=True).stdout
    sdk_version = run(["/usr/bin/xcrun", "--sdk", "macosx", "--show-sdk-version"], env=env, capture_output=True).stdout.strip()
    env["SDKROOT"] = sdk
    # Separate per-role trees prevent cross-version object/library contamination.
    with tempfile.TemporaryDirectory(prefix="uoink-ffmpeg-") as temporary:
        scratch = Path(temporary)
        for role in ("cli", "shared"):
            pin = config[role]
            archive = scratch / f"ffmpeg-{pin['version']}.tar.xz"
            with urllib.request.urlopen(pin["url"], timeout=120) as response, archive.open("wb") as target:
                shutil.copyfileobj(response, target)
            source = extract_source(archive, scratch / role, pin)
            prefix = output / role
            evidence = output / "notices" / role
            evidence.mkdir(parents=True)
            # Apple clang takes the SDK through -isysroot (and SDKROOT); FFmpeg's
            # --sysroot left the SDK's libc headers (ctype.h) unresolved on macOS 15.
            flags = [f"--prefix={prefix}", "--arch=aarch64", "--target-os=darwin", f"--cc={cc}",
                     f"--extra-cflags=-arch arm64 -isysroot {sdk} -mmacosx-version-min=15.0",
                     f"--extra-ldflags=-arch arm64 -isysroot {sdk} -mmacosx-version-min=15.0 -Wl,-headerpad_max_install_names",
                     *configure_flags(config, role)]
            command = ["/bin/bash", str(source / "configure"), *flags]
            write_json(evidence / "build.json", {"source": pin, "configure": command,
                       "configure_shell": shlex.join(command), "requested_components": components(config, role),
                       "compiler": compiler, "sdk": sdk, "sdk_version": sdk_version,
                       "minimum_macos": config["minimum_macos"], "source_modified": False,
                       "signature": "Verified by orchestrator before pinning; CI verifies size and SHA-256"})
            configure_and_build(config, role, source, evidence, command, env)
            shutil.copyfile(source / "COPYING.LGPLv2.1", evidence / "LGPL-2.1.txt")
            actual = (source / "config_components.h").read_text()
            write_json(evidence / "enabled-components.json", sorted(re.findall(r"^#define (CONFIG_\w+) 1$", actual, re.M)))
            # Preserve static archives/headers in the cache for review, not in the app.
            if role == "cli":
                for name in ("ffmpeg", "ffprobe"):
                    info = run([prefix / "bin" / name, "-version"], env=env, capture_output=True).stdout
                    (evidence / f"{name}-version.txt").write_text(info)
                # ffmpeg -L writes the license text through av_log, i.e. to stderr.
                shown = run([prefix / "bin/ffmpeg", "-L"], env=env, capture_output=True)
                license_info = (shown.stdout or "") + (shown.stderr or "")
                (evidence / "ffmpeg-license.txt").write_text(license_info)
                text = " ".join(license_info.split())  # the license text wraps across lines
                if ("GNU Lesser General Public License" not in text
                        or "GNU General Public License as published" in text.replace("Lesser General", "")):
                    raise ValueError("FFmpeg did not report an LGPL build")
    for name in ("build_ffmpeg.py", "ffmpeg_bundle.py", "payload.json", "FFMPEG.md"):
        shutil.copyfile(MAC / name, output / "notices" / name)
    write_json(output / "cache.json", {"key": cache_key(config), "files": output_inventory(output)})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--cache-key", action="store_true")
    args = parser.parse_args()
    if args.cache_key:
        print(cache_key(load_config()))
    elif args.output:
        build(args.output.resolve())
    else:
        parser.error("--output or --cache-key is required")
