"""CI-only Developer ID signing. Never execute the downloaded app in this phase."""
from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import platform
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import tarfile

from build_bundle import create_dmg, sha256, signing_order, tree_inventory
from qualify_deps import write_json
from sign_archives import sign_archives

DEVELOPER_ID_G2 = Path(__file__).parent / "certs/DeveloperIDG2CA.cer"
# https://www.apple.com/certificateauthority/DeveloperIDG2CA.cer
DEVELOPER_ID_G2_SHA256 = "f16cd3c54c7f83cea4bf1a3e6a0819c8aaa8e4a1528fd144715f350643d2df3a"


def verified_intermediate() -> Path:
    if sha256(DEVELOPER_ID_G2) != DEVELOPER_ID_G2_SHA256:
        raise ValueError("Developer ID G2 intermediate SHA256 mismatch")
    return DEVELOPER_ID_G2


def public_output(text: str) -> str:
    for name in ("MACOS_CERT_P12_BASE64", "MACOS_CERT_PASSWORD", "NOTARY_API_KEY_P8_BASE64",
                 "NOTARY_API_KEY_ID", "NOTARY_API_ISSUER_ID"):
        value = os.environ.get(name)
        if value:
            text = text.replace(value, "[redacted]")
    return text


def tool(argv, *, timeout=120):
    # Do not log argv: security arguments include passwords. Avoid CalledProcessError
    # tracebacks too. Only public signing/notary results are written by callers.
    try:
        return subprocess.run([str(a) for a in argv], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        return subprocess.CompletedProcess([], 124, stdout, f"{Path(argv[0]).name} timed out after {timeout}s")


def checked(argv, *, timeout=120):
    result = tool(argv, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"{Path(argv[0]).name} failed (exit {result.returncode})")
    return result


def private_path() -> Path:
    return Path(os.environ["RUNNER_TEMP"]).resolve() / "uoink-signing-private"


def prepare_identity(private: Path, team: str) -> tuple[str, Path]:
    intermediate = verified_intermediate()
    private.mkdir(mode=0o700)
    os.chmod(private, 0o700)
    original = checked(["security", "list-keychains", "-d", "user"]).stdout
    write_json(private / "search-list.json", shlex.split(original))
    default = shlex.split(checked(["security", "default-keychain", "-d", "user"]).stdout)
    if len(default) != 1:
        raise ValueError("Expected one original default keychain")
    write_json(private / "default-keychain.json", default)
    for variable, name in (("MACOS_CERT_P12_BASE64", "identity.p12"),
                           ("NOTARY_API_KEY_P8_BASE64", "notary.p8")):
        encoded = "".join(os.environ[variable].split())
        (private / name).write_bytes(base64.b64decode(encoded, validate=True))
        (private / name).chmod(0o600)
    password = secrets.token_hex(32)
    print(f"::add-mask::{password}", flush=True)
    keychain = private / "signing.keychain-db"
    checked(["security", "create-keychain", "-p", password, keychain])
    checked(["security", "import", intermediate, "-k", keychain])
    checked(["security", "set-keychain-settings", "-lut", "7200", keychain])
    checked(["security", "unlock-keychain", "-p", password, keychain])
    checked(["security", "import", private / "identity.p12", "-k", keychain,
             "-P", os.environ["MACOS_CERT_PASSWORD"], "-T", "/usr/bin/codesign"])
    checked(["security", "set-key-partition-list", "-S", "apple-tool:,apple:,codesign:",
             "-s", "-k", password, keychain])
    checked(["security", "list-keychains", "-d", "user", "-s", keychain])
    checked(["security", "default-keychain", "-d", "user", "-s", keychain])
    identities = checked(["security", "find-identity", "-v", "-p", "codesigning", keychain]).stdout
    identity = identity_from_output(identities, team)
    return identity, keychain


def identity_from_output(output: str, team: str) -> str:
    names = re.findall(r'"(Developer ID Application: [^"\r\n]+)"', output)
    if len(names) != 1 or not re.fullmatch(r"[A-Z0-9]{10}", team):
        raise ValueError("Expected exactly one imported Developer ID Application identity")
    if not names[0].endswith(f"({team})"):
        raise ValueError("Imported Developer ID identity has the wrong team")
    return names[0]


def cleanup(private: Path) -> None:
    if not private.exists():
        return
    if private.is_symlink():
        raise ValueError("Private signing directory must not be a symlink")
    errors = []
    # Attempt both restorations even if one fails, before deleting the keychain.
    for filename, operation in (("search-list.json", "list-keychains"),
                                ("default-keychain.json", "default-keychain")):
        try:
            saved = private / filename
            if saved.exists():
                checked(["security", operation, "-d", "user", "-s", *json.loads(saved.read_text())])
        except Exception:
            errors.append(f"security {operation} restore failed")
    try:
        keychain = private / "signing.keychain-db"
        if keychain.exists():
            checked(["security", "delete-keychain", keychain])
    except Exception:
        errors.append("security delete-keychain failed")
    finally:
        shutil.rmtree(private)
    if errors:
        raise RuntimeError("Signing cleanup failed: " + "; ".join(errors))


def codesign_command(path: Path, identity: str, keychain: Path) -> list:
    # No exceptions established by runtime evidence yet. In particular, do not
    # inherit upstream entitlements, disable library validation, or allow debugging.
    return ["codesign", "--force", "--options", "runtime", "--timestamp",
            "--sign", identity, "--keychain", keychain, path]


def signing_diagnostics(keychain: Path, evidence: Path) -> None:
    # Public certificate metadata only. Never dump a keychain, environment or
    # commands used to import private keys. Keep collecting if a query fails.
    commands = [["security", "find-identity", "-v", "-p", "codesigning", keychain]]
    for source in (keychain, "/Library/Keychains/System.keychain",
                   "/System/Library/Keychains/SystemRootCertificates.keychain"):
        commands.append(["security", "find-certificate", "-a", "-Z", "-c",
                         "Developer ID Certification Authority", source])
    commands.extend([["security", "list-keychains", "-d", "user"],
                     ["security", "default-keychain", "-d", "user"]])
    with (evidence / "codesign-keychain-diagnostics.txt").open("a", encoding="utf-8") as log:
        for command in commands:
            try:
                result = tool(command)
                detail = f"exit {result.returncode}\n{result.stdout}{result.stderr}"
            except Exception as exc:
                # Exception strings may contain argv or private tool output.
                detail = f"query unavailable ({type(exc).__name__})"
            log.write(public_output(shlex.join([str(a) for a in command]) + "\n" + detail + "\n"))


def sign(path: Path, identity: str, keychain: Path, evidence: Path) -> None:
    try:
        result = tool(codesign_command(path, identity, keychain), timeout=300)
    except OSError:
        signing_diagnostics(keychain, evidence)
        raise RuntimeError("codesign could not start; see codesign-keychain-diagnostics.txt") from None
    with (evidence / "codesign-sign.txt").open("a", encoding="utf-8") as log:
        log.write(public_output(f"{path}\n{result.stdout}{result.stderr}\n"))
    if result.returncode:
        signing_diagnostics(keychain, evidence)
        raise RuntimeError(public_output(f"codesign failed on {path}; see codesign-sign.txt"))


def notarize(path: Path, label: str, private: Path, evidence: Path) -> None:
    auth = ["--key", private / "notary.p8", "--key-id", os.environ["NOTARY_API_KEY_ID"],
            "--issuer", os.environ["NOTARY_API_ISSUER_ID"]]
    # notarytool's own timeout returns submission JSON even if still processing.
    result = tool(["xcrun", "notarytool", "submit", path, *auth, "--wait",
                   "--timeout", "30m", "--output-format", "json"], timeout=1860)
    (evidence / f"notary-{label}.json").write_text(public_output(result.stdout), encoding="utf-8")
    (evidence / f"notary-{label}-stderr.txt").write_text(public_output(result.stderr), encoding="utf-8")
    try:
        response = json.loads(result.stdout)
    except ValueError:
        raise RuntimeError(f"Notary {label} returned no JSON; see evidence") from None
    if response.get("status") != "Accepted" or result.returncode:
        submission = response.get("id")
        if submission:
            log = tool(["xcrun", "notarytool", "log", submission, *auth], timeout=120)
            (evidence / f"notary-{label}-log.json").write_text(public_output(log.stdout), encoding="utf-8")
            (evidence / f"notary-{label}-log-stderr.txt").write_text(public_output(log.stderr), encoding="utf-8")
        raise RuntimeError(f"Notary {label} was not Accepted; see notary-{label} evidence")


def staple(path: Path, label: str, evidence: Path) -> None:
    for operation in ("staple", "validate"):
        result = tool(["xcrun", "stapler", operation, path], timeout=300)
        (evidence / f"stapler-{label}-{operation}.txt").write_text(
            public_output(result.stdout + result.stderr), encoding="utf-8")
        if result.returncode:
            raise RuntimeError(f"stapler {operation} failed on {label}")


def prepare(download: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=False)
    archives = list(download.glob("*.tar.gz"))
    connectors = list(download.glob("*.mcpb"))
    if len(archives) != 1 or len(connectors) != 1:
        raise ValueError("Expected one build app archive and one Darwin MCPB")
    with tarfile.open(archives[0]) as archive:
        if any(m.name.split("/")[0] != "Uoink.app" for m in archive.getmembers()):
            raise ValueError("Unexpected build archive root")
        archive.extractall(output, filter="data")
    tree_inventory(output / "Uoink.app")
    shutil.copyfile(connectors[0], output / connectors[0].name)


def sign_release(output: Path, evidence: Path, private: Path, team: str) -> None:
    evidence.mkdir(parents=True, exist_ok=True)
    app = output / "Uoink.app"
    version = (app / "Contents/Resources/VERSION").read_text().strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Invalid app version")
    identity, keychain = prepare_identity(private, team)
    signer = lambda path: sign(path, identity, keychain, evidence)
    sign_archives(app, evidence / "nested-archives.json", signer)
    notice = app / "Contents/Resources/notices/build.json"
    metadata = json.loads(notice.read_text())
    metadata["signing"] = "Developer ID, hardened runtime; app and DMG submitted separately for notarization"
    write_json(notice, metadata)
    ordered = signing_order(app)
    write_json(evidence / "signing.json", {"identity": identity, "team": team, "entitlements": {},
                                           "order": [p.relative_to(app).as_posix() for p in ordered]})
    for path in ordered:
        signer(path)
    submission = output / "notary-app.zip"
    checked(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", app, submission], timeout=600)
    notarize(submission, "app", private, evidence)
    staple(app, "app", evidence)
    submission.unlink()
    dmg = create_dmg(app, output, version, signed=True)
    signer(dmg)
    notarize(dmg, "dmg", private, evidence)
    staple(dmg, "dmg", evidence)
    # create_dmg's earlier hash precedes DMG signing/stapling. Replace it last.
    write_json(output / "dmg.json", {"filename": dmg.name, "size_bytes": dmg.stat().st_size,
                                     "sha256": sha256(dmg), "volume": f"Uoink {version}"})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "sign", "cleanup"))
    parser.add_argument("--download", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    if sys.platform != "darwin" or platform.machine() != "arm64":
        raise RuntimeError("Signing requires macOS arm64")
    if args.phase == "cleanup":
        cleanup(private_path())
    elif args.phase == "prepare":
        prepare(args.download, args.output)
    else:
        try:
            sign_release(args.output, args.evidence, private_path(), os.environ["MACOS_TEAM_ID"])
        finally:
            cleanup(private_path())


if __name__ == "__main__":
    main()
