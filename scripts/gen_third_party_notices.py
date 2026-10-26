"""Generate THIRD-PARTY-NOTICES.md from the installed dependency tree (C-02).

Run with the interpreter whose site-packages you want to document -- in the
build that's the bundled embeddable Python, so the notices match exactly
what ships:

    python scripts/gen_third_party_notices.py [OUTPUT_PATH]

Uses pip-licenses' JSON output when available (build path); falls back to
importlib.metadata so a dev run without pip-licenses still produces an
honest, if terser, file. ffmpeg is not a pip package, so its LGPL notice is
appended from a fixed block (the BtbN win64-lgpl build, per build.ps1). The
bundled Whisper model's entry is rendered from scripts/whisper_model_pin.json.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


FFMPEG_BLOCK = """\
## ffmpeg (bundled binary, not a Python package)

- **Component:** ffmpeg / ffprobe, BtbN `win64-lgpl` build (see build.ps1
  `$FFMPEG_URL`), plus the LGPL shared FFmpeg 7.1.5 runtime in
  `bin/torchcodec` (see `$FFMPEG_SHARED_URL`). TorchCodec 0.7 requires this
  separate FFmpeg 7 ABI; the standalone CLI remains FFmpeg 8.1.2.
- **License:** LGPL v2.1+ (this build is compiled without the GPL-only
  encoders such as libx264/libx265).
- **Source:** https://ffmpeg.org/download.html and
  https://github.com/BtbN/FFmpeg-Builds . Uoink uses ffmpeg only to decode
  and extract audio and video frames for transcription and cited evidence.
- **Pinned shared build and source recipe:**
  https://github.com/BtbN/FFmpeg-Builds/releases/tag/autobuild-2026-07-31-14-10 .
  Shared libraries may be replaced with compatible LGPL FFmpeg 7 libraries
  in `bin/torchcodec`; Uoink does not statically link them into its own code.
- LGPL text: https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html
"""


BUNDLED_FONTS_BLOCK = """\
## Bundled fonts (not Python packages)

The dashboard and the Chrome extension ship their own copies of three
typefaces (the same WOFF files the uoink.app site uses), so neither loads
fonts from the network. Each font is licensed under the
SIL Open Font License 1.1. The licence text, with that font's copyright
line, sits beside the font files in `assets/brand/fonts/` and
`extension/brand/fonts/`.

- **Inter**, copyright 2020 The Inter Project Authors
  (https://github.com/rsms/inter): `inter.woff` and `inter-italic.woff`,
  licence `inter-OFL.txt`.
- **Bungee**, copyright 2023 The Bungee Project Authors
  (https://github.com/djrrb/Bungee): `bungee.woff`, licence `bungee-OFL.txt`.
- **JetBrains Mono**, copyright 2020 The JetBrains Mono Project Authors
  (https://github.com/JetBrains/JetBrainsMono): `jetbrains-mono.woff`,
  licence `jetbrains-mono-OFL.txt`.
- OFL text: https://openfontlicense.org
"""


ADAPTED_TEXT_BLOCK = """\
## Adapted documentation text

The five local research-playbook instructions adapt workflow steps, output
templates, outlier thresholds and pitfalls from
[ScrapeCreators/social-media-research-skills](https://github.com/ScrapeCreators/social-media-research-skills)
at commit `64ba7b4dea71e130d2712ffb6c1c1024b3b7c4b2` (MIT).
Copyright (c) 2026 ScrapeCreators. No upstream script or code is shipped.
See the [complete MIT license](third-party-notices/scrapecreators-social-media-research-skills-MIT-LICENSE.txt)
and [adapted file list](third-party-notices/README.md).

`article_extractor.py` adapts the scoring, class/id hints, ancestor score
propagation and sibling selection from
[Mozilla Readability 0.6.0](https://github.com/mozilla/readability/blob/0.6.0/Readability.js)
(Apache-2.0). Copyright (c) 2010 Arc90 Inc. Uoink replaces the browser DOM
with Python's html.parser and adds resource limits, shell detection,
metadata handling and Markdown output. This is a limited adaptation, not
the upstream JavaScript implementation. See the
[Apache-2.0 license](third-party-notices/mozilla-readability-APACHE-2.0.txt).
"""


WHISPER_PIN = Path(__file__).resolve().with_name("whisper_model_pin.json")


def whisper_model_block(pin_path: Path = WHISPER_PIN) -> str:
    """The bundled Whisper model's entry, rendered from the build pin.

    build.ps1 and the macOS bundle stage exactly the files the pin names, so
    the notice cannot drift from what ships.
    """
    pin = json.loads(Path(pin_path).read_text(encoding="utf-8"))
    model, repo, revision = pin["model"], pin["repo"], pin["revision"]
    files = "\n".join(f"  - `{name}`: {meta['size']:,} bytes, SHA-256 `{meta['sha256']}`"
                      for name, meta in sorted(pin["files"].items()))
    return f"""\
## Bundled Whisper model (not a Python package)

- **Component:** OpenAI Whisper `{model}` weights, converted to the
  CTranslate2 format by SYSTRAN for faster-whisper:
  https://huggingface.co/{repo} at pinned revision
  `{revision}`. Installed read-only at
  `models/whisper-bundled/{model}/` (macOS: `Contents/Resources/models/whisper-bundled/{model}/`).
- **License:** MIT. OpenAI releases Whisper's code and model weights under
  the MIT License (Copyright (c) 2022 OpenAI); the SYSTRAN model card
  declares `license: mit` for the conversion.
- **Files** (the build refuses any size or hash mismatch):
{files}
- Provenance and the full license text:
  [model notice](third-party-notices/faster-whisper-{model}-NOTICE.md).
"""


EMBEDDINGGEMMA_BLOCK = """\
## Optional EmbeddingGemma search

The search code ships in Uoink. Model weights are downloaded separately after
explicit acceptance and are never bundled. See the bundled
[model notice](third-party-notices/EmbeddingGemma-NOTICE.md),
[Gemma Terms of Use](third-party-notices/Gemma-Terms-of-Use.txt) and
[Prohibited Use Policy](third-party-notices/Gemma-Prohibited-Use-Policy.txt).
"""


SUPPLEMENTAL_NOTICE_BLOCK = """\
## Supplemental upstream notices

The two cached wheels below omit license-text members. Their exact upstream
texts, source bindings and recorded metadata conflict are listed in
[the supplemental notice index](third-party-notices/README.md).

- antlr4-python3-runtime 4.9.3: [full upstream license](third-party-notices/antlr4-python3-runtime-4.9.3-LICENSE.txt).
  The reviewed Python source header identifies the BSD 3-clause notice. The file
  also retains an MIT section scoped to two JavaScript files; their presence in
  that notice does not establish that they ship in this Python wheel.
- proxy-tools 0.1.0: [full upstream license](third-party-notices/proxy-tools-0.1.0-UPSTREAM-LICENSE.txt).
  Wheel/PyPI metadata and historical setup.py say MIT; the matching source
  header and repository license say BSD. Both declarations are retained here.
  The upstream text is unchanged, including its placeholder and trailing text.
  This notice does not resolve that conflict or grant legal clearance.
"""


def _supplemental_notices(rows: list[dict]) -> str:
    versions = {re.sub(r"[-_.]+", "-", row.get("Name", "")).lower():
                row.get("Version", "") for row in rows}
    for name, version in (("antlr4-python3-runtime", "4.9.3"), ("proxy-tools", "0.1.0")):
        if versions.get(name) != version:
            raise RuntimeError(f"Supplemental notice requires review: {name}=={versions.get(name)}")
    return SUPPLEMENTAL_NOTICE_BLOCK


def _from_pip_licenses() -> list[dict] | None:
    try:
        out = subprocess.check_output(
            [sys.executable, "-m", "piplicenses", "--format=json",
             "--with-system", "--with-urls", "--with-license-file", "--no-license-path"],
            text=True, stderr=subprocess.DEVNULL)
        return json.loads(out)
    except Exception:
        pass
    try:
        out = subprocess.check_output(
            [sys.executable, "-m", "pip_licenses", "--format=json",
             "--with-system", "--with-urls"], text=True, stderr=subprocess.DEVNULL)
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


def _fill_license_expressions(rows: list[dict]) -> list[dict]:
    """Prefer the installed distribution's PEP 639 ``License-Expression``.

    Classifiers can be less precise, such as ``BSD License`` instead of
    ``BSD-3-Clause``. Use the declared SPDX expression when present; otherwise
    retain the collector's existing licence value, including UNKNOWN.
    """
    import importlib.metadata as md
    normalize = lambda name: re.sub(r"[-_.]+", "-", name).lower()
    expressions: dict[str, str] = {}
    for dist in md.distributions():
        meta = dist.metadata
        name = meta.get("Name")
        expression = (meta.get("License-Expression") or "").strip()
        if name and expression:
            expressions.setdefault(normalize(name), expression)
    for row in rows:
        expression = expressions.get(normalize(row.get("Name") or ""))
        if expression:
            row["License"] = expression
    return rows


def _dedupe(rows: list[dict]) -> list[dict]:
    seen = {}
    for row in rows:
        key = (row.get("Name") or "").lower()
        if key and key not in seen:
            seen[key] = row
    return sorted(seen.values(), key=lambda r: (r.get("Name") or "").lower())


def _runtime_rows(rows: list[dict]) -> list[dict]:
    """Include required system packages while omitting build-only tooling."""
    lock = Path(__file__).resolve().parents[1] / "requirements-installer-lock.txt"
    normalize = lambda name: re.sub(r"[-_.]+", "-", name).lower()
    required = {normalize(line.split("==", 1)[0]) for line in
                lock.read_text(encoding="utf8").splitlines()
                if line.strip() and not line.lstrip().startswith("#")}
    runtime = [row for row in rows if normalize(row.get("Name") or "") in required]
    missing = required - {normalize(row["Name"]) for row in runtime}
    if missing:
        raise RuntimeError("Missing runtime notices: " + ", ".join(sorted(missing)))
    return runtime


def _stamp_date() -> str:
    """The generation date, source-bound when SOURCE_DATE_EPOCH is set.

    build.ps1 exports the same epoch it normalizes installer input mtimes to,
    so a rebuild from unchanged source regenerates a byte-identical notices
    file. Without this the wall-clock date changed on every build, leaving the
    tree dirty after each one and making the file the one part of the build
    that could not reproduce. Falls back to the current date when generated by
    hand outside a build.
    """
    epoch = os.environ.get("SOURCE_DATE_EPOCH", "").strip()
    if epoch.isdigit():
        return datetime.fromtimestamp(int(epoch), timezone.utc).strftime("%Y-%m-%d")
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def main() -> int:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("THIRD-PARTY-NOTICES.md")
    rows = _from_pip_licenses()
    source = "pip-licenses"
    if rows is None:
        rows = _from_importlib()
        source = "importlib.metadata (pip-licenses unavailable)"
    rows = _fill_license_expressions(_dedupe(_runtime_rows(rows)))
    supplemental = _supplemental_notices(rows)

    stamp = _stamp_date()
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
        if re.sub(r"[-_.]+", "-", name).lower() == "proxy-tools" and version == "0.1.0":
            lic += " (metadata; see upstream conflict below)"
        url = row.get("URL") or row.get("Home-page") or ""
        lines.append(f"| {name} | {version} | {lic} | {url} |")
    if any(row.get("Name", "").lower() == "nltk" and
           row.get("Version") == "3.10.3+uoink.pathsec1" for row in rows):
        lines += ["", "NLTK 3.10.3+uoink.pathsec1 is a local path-policy backport of upstream "
                  "3.10.3. Its Apache 2.0 licence is retained. The exact patch, original "
                  "source and build provenance are in vendor/nltk-pathsec in the source "
                  "repository. This modification does not qualify model loading or "
                  "clear unrelated dependency advisories."]
    lines += ["", supplemental, "", EMBEDDINGGEMMA_BLOCK, "", ADAPTED_TEXT_BLOCK, "", FFMPEG_BLOCK,
              "", whisper_model_block(), "", BUNDLED_FONTS_BLOCK, ""]
    output.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {output} ({len(rows)} python packages, source: {source})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
