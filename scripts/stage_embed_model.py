"""Fetch, verify and stage the bundled text-embedding model for a build.

Uoink 3.18 ships minishlab/potion-base-8M, a static embedding table
(local_embed.py) used to suggest shelves. The repository, revision and
per-file SHA-256 live in ``scripts/embed_model_pin.json``; the download,
hash check and layout are the Whisper stager's (stage_whisper_model.py), so
a mismatch fails the build the same way.

    python scripts/stage_embed_model.py --cache build/cache/embed-model \
        --dest installer/staging/models/embed-bundled

Staged layout: ``<dest>/potion-base-8m/{config.json,model.safetensors,
tokenizer.json,uoink-model.json}``. Standard library only.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stage_whisper_model as base  # noqa: E402

PIN_PATH = Path(__file__).resolve().with_name("embed_model_pin.json")
REQUIRED_FILES = ("model.safetensors", "tokenizer.json")
LABEL = "Embedding model"
StageError = base.StageError


def load_pin(path: Path = PIN_PATH) -> dict:
    return base.load_pin(path, required=REQUIRED_FILES, label=LABEL)


def stage(pin: dict, cache_root: Path, dest_root: Path, **kwargs) -> Path:
    return base.stage(pin, cache_root, dest_root, label=LABEL, **kwargs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage the pinned bundled embedding model.")
    parser.add_argument("--cache", required=True, type=Path, help="download cache folder")
    parser.add_argument("--dest", required=True, type=Path,
                        help="bundled model root, e.g. <staging>/models/embed-bundled")
    parser.add_argument("--pin", type=Path, default=PIN_PATH)
    args = parser.parse_args(argv)
    try:
        stage(load_pin(args.pin), args.cache, args.dest)
    except StageError as error:
        print(f"stage_embed_model: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
