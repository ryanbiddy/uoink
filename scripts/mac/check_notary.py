"""Check existing notarization submissions once, using only the API key."""
from __future__ import annotations

import argparse
import base64
import html
import os
from pathlib import Path
import shutil
import sys

from sign_notarize import notary_request, public_json, public_output, submission_id

MAX_IDS = 5
REQUEST_TIMEOUT_SECONDS = 30
TERMINAL_STATUSES = {"Accepted", "Invalid", "Rejected"}


def parse_submission_ids(value: str) -> list[str]:
    parts = value.split(",")
    if not 1 <= len(parts) <= MAX_IDS:
        raise ValueError(f"Provide 1 to {MAX_IDS} comma-separated submission UUIDs")
    return list(dict.fromkeys(submission_id(part) for part in parts))


def private_path() -> Path:
    return Path(os.environ["RUNNER_TEMP"]).resolve() / "uoink-notary-check-private"


def cleanup(private: Path) -> None:
    if private.is_symlink():
        raise ValueError("Private notary directory must not be a symlink")
    if private.exists():
        shutil.rmtree(private)


def check(value: str, private: Path, evidence: Path, summary: Path) -> None:
    ids = parse_submission_ids(value)  # Validate the whole list before decoding a key.
    evidence.mkdir(parents=True, exist_ok=True)
    rows = []
    failed = False
    try:
        private.mkdir(mode=0o700)
        private.chmod(0o700)
        key = private / "notary.p8"
        with key.open("xb") as stream:
            key.chmod(0o600)
            stream.write(base64.b64decode("".join(os.environ["NOTARY_API_KEY_P8_BASE64"].split()),
                                         validate=True))
        for ident in ids:
            row = {"id": ident, "status": "Unknown", "createdDate": "Unknown"}
            try:
                result, response = notary_request("info", ident, private, evidence, f"{ident}-info",
                                                  timeout=REQUEST_TIMEOUT_SECONDS)
                row["infoExit"] = result.returncode
                if response.get("id", "").lower() != ident or not response.get("status"):
                    raise RuntimeError("Notary info failed")
                row.update(status=response["status"], createdDate=response.get("createdDate", "Unknown"))
                if row["status"] in TERMINAL_STATUSES:
                    result, response = notary_request("log", ident, private, evidence, f"{ident}-log",
                                                      timeout=REQUEST_TIMEOUT_SECONDS)
                    row["logExit"] = result.returncode
                    if result.returncode or not response:
                        raise RuntimeError("Notary log failed")
                if row["infoExit"]:
                    raise RuntimeError("Notary info failed")
            except Exception as exc:
                # Exception messages can include argv and credentials. Keep the other IDs useful.
                row["error"] = f"Query failed ({type(exc).__name__}); see public tool evidence"
                failed = True
            rows.append(row)
    finally:
        cleanup(private)
        public_json(evidence / "submissions.json", rows)
        def cell(value):
            return html.escape(public_output(str(value))).replace("|", "&#124;").replace("\r", " ").replace("\n", " ")
        with summary.open("a", encoding="utf-8") as stream:
            stream.write("\n| ID | Status | Created date |\n| --- | --- | --- |\n")
            for row in rows:
                status = str(row["status"]) + (" (query failed)" if "error" in row else "")
                stream.write(f"| {cell(row['id'])} | {cell(status)} | {cell(row['createdDate'])} |\n")
    if failed:
        raise RuntimeError("Some notary queries failed; see mac-notary-check evidence")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("check", "cleanup"))
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    if args.phase == "cleanup":
        cleanup(private_path())
    else:
        if sys.platform != "darwin":
            raise RuntimeError("Notary checks require macOS")
        check(os.environ["NOTARY_CHECK_IDS"], private_path(), args.evidence,
              Path(os.environ["GITHUB_STEP_SUMMARY"]))


if __name__ == "__main__":
    main()
