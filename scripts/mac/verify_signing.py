"""Strict, reusable notarization gates. No signing credentials are used here."""
from __future__ import annotations

from pathlib import Path
import re
import subprocess


def command(argv) -> dict:
    argv = [str(a) for a in argv]
    result = subprocess.run(argv, capture_output=True, text=True, timeout=120)
    return {"argv": argv, "exit": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_notarized(app: Path, dmg: Path, team: str, report: dict, *, execute=command) -> None:
    require(bool(re.fullmatch(r"[A-Z0-9]{10}", team or "")), "Strict receipt requires an expected team ID")
    report.update(expected_team_id=team, ok=False)
    for label, path in (("app", app), ("dmg", dmg)):
        assessment = (["--type", "execute"] if label == "app" else
                      ["--type", "open", "--context", "context:primary-signature"])
        report[label] = {
            "verify": execute(["/usr/bin/codesign", "--verify", "--strict", "--deep", "--verbose=2", path]),
            "details": execute(["/usr/bin/codesign", "-dv", "--verbose=4", path]),
            "ticket": execute(["xcrun", "stapler", "validate", path]),
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
