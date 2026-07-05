"""Generate THIRD-PARTY-NOTICES.md from the installed dependency tree (C-02).

Run with the interpreter whose site-packages you want to document -- in the
build that's the bundled embeddable Python, so the notices match exactly
what ships:

    python scripts/gen_third_party_notices.py [OUTPUT_PATH]

Uses pip-licenses' JSON output when available (build path); falls back to
importlib.metadata so a dev run without pip-licenses still produces an
honest, if terser, file. ffmpeg is not a pip package, so its LGPL notice is
appended from a fixed block (the BtbN win64-lgpl build, per build.ps1).
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


FFMPEG_BLOCK = """\
## ffmpeg (bundled binary, not a Python package)

- **Component:** ffmpeg / ffprobe, BtbN `win64-lgpl` build (see build.ps1
  `$FFMPEG_URL`).
- **License:** LGPL v2.1+ (this build is compiled without the GPL-only
  encoders such as libx264/libx265).
- **Source:** https://ffmpeg.org/download.html and
  https://github.com/BtbN/FFmpeg-Builds . Uoink uses ffmpeg only to decode
  and extract audio for transcription.
- LGPL text: https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html
"""


def _from_pip_licenses() -> list[dict] | None:
    try:
        out = subprocess.check_output(
            [sys.executable, "-m", "piplicenses", "--format=json",
             "--with-urls", "--with-license-file", "--no-license-path"],
            text=True, stderr=subprocess.DEVNULL)
        return json.loads(out)
    except Exception:
        pass
    try:
        out = subprocess.check_output(
            [sys.executable, "-m", "pip_licenses", "--format=json",
             "--with-urls"], text=True, stderr=subprocess.DEVNULL)
        return json.loads(out)
    except Exception:
        return None


def _from_importlib() -> list[dict]:
    import importlib.metadata as md
    rows = []
    for dist in md.distributions():
        meta = dist.metadata
        name = meta.get("Name")
        if not name:
            continue
        rows.append({
            "Name": name,
            "Version": meta.get("Version", ""),
            "License": meta.get("License") or _classifier_license(meta),
            "URL": meta.get("Home-page", ""),
        })
    return rows


def _classifier_license(meta) -> str:
    for value in meta.get_all("Classifier") or []:
        if value.startswith("License ::"):
            return value.split("::")[-1].strip()
    return "UNKNOWN"


def _dedupe(rows: list[dict]) -> list[dict]:
    seen = {}
    for row in rows:
        key = (row.get("Name") or "").lower()
        if key and key not in seen:
            seen[key] = row
    return sorted(seen.values(), key=lambda r: (r.get("Name") or "").lower())


def main() -> int:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("THIRD-PARTY-NOTICES.md")
    rows = _from_pip_licenses()
    source = "pip-licenses"
    if rows is None:
        rows = _from_importlib()
        source = "importlib.metadata (pip-licenses unavailable)"
    rows = _dedupe(rows)

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        "# Third-Party Notices",
        "",
        "Uoink is MIT-licensed. It bundles the third-party components below.",
        f"This file is generated from the installed dependency tree "
        f"(source: {source}) on {stamp}; regenerate with "
        "`python scripts/gen_third_party_notices.py`.",
        "",
        "| Package | Version | License | Project |",
        "|---|---|---|---|",
    ]
    for row in rows:
        name = row.get("Name", "")
        version = row.get("Version", "")
        lic = (row.get("License") or "UNKNOWN").replace("|", "/")
        url = row.get("URL") or row.get("Home-page") or ""
        lines.append(f"| {name} | {version} | {lic} | {url} |")
    lines += ["", FFMPEG_BLOCK, ""]
    output.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {output} ({len(rows)} python packages, source: {source})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
