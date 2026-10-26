"""Fetch, verify and stage the bundled Whisper model for an installer build.

Every Uoink download ships one faster-whisper model so a fresh install can
transcribe caption-less videos without a download step. The repository,
revision and per-file SHA-256 live in ``scripts/whisper_model_pin.json``;
this script is the only build path that turns that pin into files.

    python scripts/stage_whisper_model.py --cache build/cache/whisper-model \
        --dest installer/staging/models/whisper-bundled

Downloads come from the pinned Hugging Face revision (never ``main``) into
``--cache`` so a rebuild does not fetch again. Every cached or downloaded
file is checked against the pinned size and SHA-256 before use. A mismatch
deletes that cache file and fails the build: re-running fetches it fresh.
Nothing is read from or written to a Hugging Face cache on this machine.

The staged layout is one flat snapshot directory per model, which
faster-whisper loads by path without touching the network:

    <dest>/<model>/{config.json,model.bin,tokenizer.json,vocabulary.txt}
    <dest>/<model>/uoink-model.json   (pin copy; the app checks sizes against it)

Standard library only: build.ps1 runs it with the embeddable Python and the
macOS bundle build imports it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

PIN_PATH = Path(__file__).resolve().with_name("whisper_model_pin.json")
MANIFEST_NAME = "uoink-model.json"
# faster-whisper loads these from a model directory; without tokenizer.json
# it would fetch a tokenizer from the Hub at load time.
REQUIRED_FILES = ("config.json", "model.bin", "tokenizer.json")
SOURCE_URL = "https://huggingface.co/{repo}/resolve/{revision}/{name}"
_CHUNK = 1024 * 1024


class StageError(RuntimeError):
    """The pin, a download, or a staged copy failed verification."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(_CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def load_pin(path: Path = PIN_PATH) -> dict:
    """Read and validate the committed pin. Rejects anything ambiguous."""
    try:
        pin = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise StageError(f"Cannot read Whisper model pin {path}: {error}") from error
    if not isinstance(pin, dict) or pin.get("schema_version") != 1:
        raise StageError("Whisper model pin must be schema_version 1")
    model, repo, revision = pin.get("model"), pin.get("repo"), pin.get("revision")
    if not isinstance(model, str) or re.fullmatch(r"[a-z0-9][a-z0-9.-]*", model) is None:
        raise StageError(f"Invalid pinned model name: {model!r}")
    if not isinstance(repo, str) or re.fullmatch(r"[\w.-]+/[\w.-]+", repo) is None:
        raise StageError(f"Invalid pinned repository: {repo!r}")
    if not isinstance(revision, str) or re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        raise StageError("The pinned revision must be a full 40-character commit, not a branch")
    files = pin.get("files")
    if not isinstance(files, dict) or not set(REQUIRED_FILES) <= set(files):
        raise StageError(f"The pin must list {', '.join(REQUIRED_FILES)}")
    for name, meta in files.items():
        if (not isinstance(name, str) or name in {"", ".", "..", MANIFEST_NAME}
                or re.fullmatch(r"[\w.-]+", name) is None):
            raise StageError(f"Invalid pinned file name: {name!r}")
        if (not isinstance(meta, dict) or type(meta.get("size")) is not int
                or meta["size"] <= 0 or not isinstance(meta.get("sha256"), str)
                or re.fullmatch(r"[0-9a-f]{64}", meta["sha256"]) is None):
            raise StageError(f"Pinned file {name} needs a positive size and a lowercase sha256")
    return pin


def _verify(path: Path, name: str, meta: dict) -> str | None:
    """Return a mismatch description, or None when size and hash match."""
    size = path.stat().st_size
    if size != meta["size"]:
        return f"{name}: size {size} != pinned {meta['size']}"
    actual = _sha256(path)
    if actual != meta["sha256"]:
        return f"{name}: sha256 {actual} != pinned {meta['sha256']}"
    return None


def cache_dir_for(pin: dict, cache_root: Path) -> Path:
    return Path(cache_root) / ("models--" + pin["repo"].replace("/", "--")) / pin["revision"]


def _download(url: str, target: Path, opener: Callable) -> None:
    partial = target.with_name(target.name + ".part")
    try:
        with opener(url, timeout=120) as response, partial.open("wb") as out:
            shutil.copyfileobj(response, out, _CHUNK)
        os.replace(partial, target)
    finally:
        if partial.exists():
            partial.unlink()


def fetch(pin: dict, cache_root: Path, *, opener: Callable = urllib.request.urlopen,
          log: Callable[[str], None] = print) -> Path:
    """Fill the build cache from the pinned revision. Fails closed on mismatch."""
    folder = cache_dir_for(pin, cache_root)
    folder.mkdir(parents=True, exist_ok=True)
    for name, meta in sorted(pin["files"].items()):
        target = folder / name
        if target.is_symlink():
            raise StageError(f"Refusing a symlinked cache file: {target}")
        if target.exists():
            log(f"    cached: {name}")
        else:
            url = SOURCE_URL.format(repo=pin["repo"], revision=pin["revision"],
                                    name=urllib.parse.quote(name))
            log(f"    downloading {name} ({meta['size']:,} bytes) ...")
            try:
                _download(url, target, opener)
            except OSError as error:
                raise StageError(f"Download failed for {name}: {error}") from error
        problem = _verify(target, name, meta)
        if problem:
            # Do not ship it, and do not keep it: a re-run fetches fresh bytes.
            target.unlink()
            raise StageError(f"Whisper model hash mismatch, cache file removed. {problem}")
        log(f"    {name} hash OK")
    return folder


def stage(pin: dict, cache_root: Path, dest_root: Path, *, opener: Callable = urllib.request.urlopen,
          log: Callable[[str], None] = print) -> Path:
    """Copy verified files to <dest_root>/<model>/ and write the manifest."""
    source = fetch(pin, cache_root, opener=opener, log=log)
    dest = Path(dest_root) / pin["model"]
    if dest.exists() or dest.is_symlink():
        raise StageError(f"Staging target already exists: {dest}")
    dest.mkdir(parents=True)
    for name, meta in sorted(pin["files"].items()):
        shutil.copyfile(source / name, dest / name)
        problem = _verify(dest / name, name, meta)
        if problem:
            raise StageError(f"Staged copy differs from the pin. {problem}")
    manifest = {
        "schema_version": 1,
        "model": pin["model"],
        "repo": pin["repo"],
        "revision": pin["revision"],
        "license": pin.get("license"),
        "files": {name: {"size": meta["size"], "sha256": meta["sha256"]}
                  for name, meta in sorted(pin["files"].items())},
    }
    (dest / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    log(f"    staged {pin['model']} @ {pin['revision'][:12]} -> {dest}")
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage the pinned bundled Whisper model.")
    parser.add_argument("--cache", required=True, type=Path, help="download cache folder")
    parser.add_argument("--dest", required=True, type=Path,
                        help="bundled model root, e.g. <staging>/models/whisper-bundled")
    parser.add_argument("--pin", type=Path, default=PIN_PATH)
    args = parser.parse_args(argv)
    try:
        stage(load_pin(args.pin), args.cache, args.dest)
    except StageError as error:
        print(f"stage_whisper_model: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
