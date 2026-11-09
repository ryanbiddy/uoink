"""Fetch, verify and install the pinned Deno that yt-dlp uses on macOS.

Deno is a V8 engine. Under the hardened runtime V8 needs one entitlement,
com.apple.security.cs.allow-jit, and only this one binary gets it (see
sign_notarize.codesign_command). Nothing here runs at app run time.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import urllib.request
import zipfile

MAC = Path(__file__).resolve().parent
HELPER = "Contents/Helpers/deno"
ENTITLEMENTS = MAC / "deno.entitlements.plist"
ALLOWED_ENTITLEMENTS = {"com.apple.security.cs.allow-jit": True}
LICENSE_FILE = MAC.parents[1] / "third-party-notices/deno-2.9.8-MIT-LICENSE.txt"


def sha256_file(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def load_pin() -> dict:
    pin = json.loads((MAC / "payload.json").read_text(encoding="utf-8"))["deno"]
    # The entitlements file is pinned like the download: any edit must update the pin.
    if sha256_file(ENTITLEMENTS) != pin["entitlements_sha256"]:
        raise ValueError("deno.entitlements.plist does not match its pin in payload.json")
    return pin


def fetch(pin: dict, cache: Path) -> Path:
    """Return the verified zip, reusing a cached copy only if its hash matches."""
    cache.mkdir(parents=True, exist_ok=True)
    zip_path = cache / Path(pin["url"]).name
    if zip_path.is_file() and sha256_file(zip_path) == pin["sha256"]:
        return zip_path
    partial = zip_path.with_suffix(".part")
    with urllib.request.urlopen(pin["url"], timeout=120) as response, partial.open("wb") as target:
        shutil.copyfileobj(response, target)
    if partial.stat().st_size != pin["size"] or sha256_file(partial) != pin["sha256"]:
        partial.unlink()
        raise ValueError("Downloaded Deno does not match its pinned size and SHA-256")
    partial.replace(zip_path)
    return zip_path


def install(app: Path, notices: Path, cache: Path, *, download=fetch) -> dict:
    pin = load_pin()
    zip_path = download(pin, cache)
    if sha256_file(zip_path) != pin["sha256"]:
        raise ValueError("Deno zip does not match its pinned SHA-256")
    target = app / HELPER
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        if archive.namelist() != ["deno"]:
            raise ValueError(f"Unexpected Deno zip contents: {archive.namelist()}")
        with archive.open("deno") as source, target.open("wb") as out:
            shutil.copyfileobj(source, out)
    target.chmod(0o755)
    folder = notices / "deno"
    folder.mkdir(parents=True)
    shutil.copyfile(LICENSE_FILE, folder / "LICENSE.txt")
    shutil.copyfile(ENTITLEMENTS, folder / ENTITLEMENTS.name)
    return {"version": pin["version"], "url": pin["url"], "sha256": pin["sha256"],
            "binary_sha256": sha256_file(target), "license": pin["license"],
            "entitlements": sorted(ALLOWED_ENTITLEMENTS), "entitlements_sha256": pin["entitlements_sha256"]}
