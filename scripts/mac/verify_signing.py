"""Strict, reusable notarization gates. No signing credentials are used here."""
from __future__ import annotations

from pathlib import Path
import plistlib
import re
import subprocess

from deno_bundle import ALLOWED_ENTITLEMENTS, HELPER as DENO_HELPER


def command(argv) -> dict:
    argv = [str(a) for a in argv]
    result = subprocess.run(argv, capture_output=True, text=True, timeout=120)
    return {"argv": argv, "exit": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_ticket(path, *, execute=command, attempts=3) -> dict:
    """stapler validate contacts Apple's CDN; retry only a dropped connection."""
    for attempt in range(attempts):
        result = execute(["xcrun", "stapler", "validate", path])
        if result["exit"] == 0 or "NSURLErrorDomain" not in result["stdout"] + result["stderr"]:
            break
    return {**result, "attempts": attempt + 1}


def verify_notarized(app: Path, dmg: Path, team: str, report: dict, *, execute=command) -> None:
    require(bool(re.fullmatch(r"[A-Z0-9]{10}", team or "")), "Strict receipt requires an expected team ID")
    report.update(expected_team_id=team, ok=False)
    for label, path in (("app", app), ("dmg", dmg)):
        assessment = (["--type", "execute"] if label == "app" else
                      ["--type", "open", "--context", "context:primary-signature"])
        report[label] = {
            "verify": execute(["/usr/bin/codesign", "--verify", "--strict", "--deep", "--verbose=2", path]),
            "details": execute(["/usr/bin/codesign", "-dv", "--verbose=4", path]),
            "ticket": validate_ticket(path, execute=execute),
            "spctl": execute(["/usr/sbin/spctl", "--assess", *assessment, "-vvv", path]),
        }
    for label in ("app", "dmg"):
        item = report[label]
        require(item["verify"]["exit"] == 0, f"{label}: strict codesign verification failed")
        details = item["details"]["stdout"] + item["details"]["stderr"]
        require(item["details"]["exit"] == 0 and "Signature=adhoc" not in details,
                f"{label}: ad-hoc or unreadable signature")
        require(re.search(rf"(?m)^TeamIdentifier={re.escape(team)}\s*$", details), f"{label}: wrong team")
        require(re.search(r"(?m)^Authority=Developer ID Application: .+$", details),
                f"{label}: missing Developer ID authority")
        require(re.search(r"flags=.*\bruntime\b", details), f"{label}: hardened runtime missing")
        timestamp = re.search(r"(?m)^Timestamp=(.+)$", details)
        require(timestamp and timestamp[1].strip().lower() not in {"none", "not set", ""},
                f"{label}: secure timestamp missing")
        require(item["ticket"]["exit"] == 0, f"{label}: stapled ticket did not validate")
        assessment = item["spctl"]["stdout"] + item["spctl"]["stderr"]
        require(item["spctl"]["exit"] == 0 and re.search(r"(?m)^.*: accepted\s*$", assessment),
                f"{label}: spctl rejected")
        if label == "app":
            require(re.search(r"(?m)^source=Notarized Developer ID\s*$", assessment),
                    "app: spctl source is not Notarized Developer ID")
    report["ok"] = True


def parse_entitlements(output: str) -> dict:
    """Read the XML plist `codesign -d --entitlements - --xml` prints; no plist means none."""
    start = output.find("<?xml")
    return plistlib.loads(output[start:].encode()) if start >= 0 else {}


def verify_entitlements(app: Path, macho_paths, *, execute=command) -> dict:
    """Only Helpers/deno may hold entitlements, and exactly allow-jit. Never --deep."""
    found, seen_deno = {}, False
    for path in sorted(Path(p) for p in macho_paths):
        relative = path.relative_to(app).as_posix()
        result = execute(["/usr/bin/codesign", "-d", "--entitlements", "-", "--xml", path])
        require(result["exit"] == 0, f"{relative}: cannot read entitlements")
        entitlements = parse_entitlements(result["stdout"] + result["stderr"])
        found[relative] = entitlements
        if relative == DENO_HELPER:
            seen_deno = True
            require(entitlements == ALLOWED_ENTITLEMENTS,
                    f"{relative}: entitlements must be exactly allow-jit, got {sorted(entitlements)}")
        else:
            require(not entitlements, f"{relative}: unexpected entitlements {sorted(entitlements)}")
    require(seen_deno, "Helpers/deno was not checked")
    return found
