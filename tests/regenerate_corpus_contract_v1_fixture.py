"""Regenerate Uoink's provider-conformance fixture for corpus read v1.

Run:
    python tests/regenerate_corpus_contract_v1_fixture.py

Check:
    python tests/regenerate_corpus_contract_v1_fixture.py --check
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import corpus_contract  # noqa: E402
import corpus_provider  # noqa: E402
import index as index_mod  # noqa: E402
import memory_layer  # noqa: E402

FIXTURE_PATH = (
    ROOT / "tests" / "fixtures" / "corpus_contract_v1" / "provider.json"
)


def build_provider(root: Path):
    data_root = root / "corpus"
    video_folder = data_root / "video-contract"
    note_folder = data_root / "note-contract"
    video_folder.mkdir(parents=True)
    note_folder.mkdir(parents=True)

    video_corpus = video_folder / "video-contract.md"
    video_sidecar = video_folder / "video-contract.json"
    video_corpus.write_bytes(
        b"# The saved hour\n\nA local workflow removed one repeated task.\n")
    (video_folder / "thumbnail.jpg").write_bytes(b"fixture-thumbnail")
    screenshots = video_folder / "screenshots"
    screenshots.mkdir()
    (screenshots / "shot_0001.jpg").write_bytes(b"fixture-screenshot")
    video_sidecar.write_text(json.dumps({
        "schema_version": 2,
        "title": "The saved hour",
        "author": "Fixture Creator",
        "url": "https://example.test/video-contract",
        "screenshots": [
            {
                "path": "screenshots/shot_0001.jpg",
                "timestamp_seconds": 12,
            },
        ],
    }), encoding="utf-8")

    note_corpus = note_folder / "note-contract.md"
    note_sidecar = note_folder / "note-contract.json"
    note_corpus.write_bytes(
        b"# Local note\n\nA short note about repeatable systems.\n")
    (note_folder / "note-image.png").write_bytes(b"fixture-note-image")
    note_sidecar.write_text(json.dumps({
        "schema_version": 2,
        "source_type": "note",
        "platform": "note",
        "author": "You",
        "title": "Local note",
        "image_filename": "note-image.png",
    }), encoding="utf-8")

    idx = index_mod.Index.open(root / "index.db")
    idx.upsert_yoink({
        "video_id": "video-contract",
        "slug": "video-contract",
        "channel": "Fixture Creator",
        "title": "The saved hour",
        "topic": "Local AI",
        "hook_type": "curiosity_gap",
        "yoinked_at": "2030-01-02T03:04:05Z",
        "corpus_path": str(video_corpus),
        "sidecar_path": str(video_sidecar),
        "metadata_json": json.dumps({
            "url": "https://example.test/video-contract",
            "duration_seconds": 42,
            "channel_url": "https://youtube.test/@FixtureCreator",
            "platform": "youtube",
            "author": "Fixture Creator",
        }),
        "source_type": "youtube",
        "platform": "youtube",
        "author": "Fixture Creator",
    }, content="saved hour local workflow repeated task")
    idx.set_facets(
        "video-contract",
        format="talking_head",
        performance_tier="over",
        length_bucket="short",
        topic="Local AI",
        hook_type="curiosity_gap",
    )
    idx.upsert_yoink({
        "video_id": "note-contract",
        "slug": "note-contract",
        "channel": "You",
        "title": "Local note",
        "topic": "Systems",
        "yoinked_at": "2030-01-01T03:04:05Z",
        "corpus_path": str(note_corpus),
        "sidecar_path": str(note_sidecar),
        "metadata_json": json.dumps({
            "platform": "note",
            "author": "You",
        }),
        "source_type": "note",
        "platform": "note",
        "author": "You",
    }, content="short note repeatable systems")
    idx.set_facets("note-contract", topic="Systems")
    memory_layer.set_anchor(
        idx, "preferred_hooks", "Open on a concrete result.")
    memory_layer.add_taste_anchor(
        idx, "video-contract", "best", "The saved hour")
    anchors = memory_layer.get_taste_anchors(idx)
    anchors["admired_channels"] = ["Fixture Creator"]
    with idx._lock:
        idx._conn.execute(
            "UPDATE memory_layer SET value=? WHERE key=?",
            (
                json.dumps(anchors),
                memory_layer.TASTE_ANCHORS_KEY,
            ),
        )
        idx._conn.commit()
    provider = corpus_provider.UoinkCorpusProvider(idx, data_root)
    return idx, provider


def generate_fixture() -> dict:
    with tempfile.TemporaryDirectory() as temp_dir:
        idx, provider = build_provider(Path(temp_dir))
        try:
            search_all = corpus_contract.success(
                "search",
                provider.search(corpus_contract.SearchRequest(limit=20)),
            )
            search_filtered = corpus_contract.success(
                "search",
                provider.search(corpus_contract.SearchRequest(
                    q="saved hour", limit=10)),
            )
            search_no_matches = corpus_contract.success(
                "search",
                provider.search(corpus_contract.SearchRequest(
                    q="definitely absent", limit=10)),
            )
            item = corpus_contract.success(
                "get", provider.get("video-contract"))
            note = corpus_contract.success(
                "get", provider.get("note-contract"))
            facets = corpus_contract.success(
                "facets", provider.facets())
            with patch.object(
                    memory_layer,
                    "_now_iso",
                    lambda: "2030-01-02T03:04:05Z"):
                taste = corpus_contract.success(
                    "taste", provider.taste())
                assembly = corpus_contract.success(
                    "assemble",
                    provider.assemble(corpus_contract.AssemblyRequest(
                        format="talking_head",
                        topic="Local AI",
                        hook_target="curiosity_gap",
                        n_examples=5,
                    )),
                )
            try:
                provider.get("missing-contract-item")
            except corpus_contract.ContractError as error:
                missing = corpus_contract.failure("get", error)
            else:  # pragma: no cover - a missing item must fail
                raise AssertionError("missing item unexpectedly resolved")
        finally:
            idx.close()
    return {
        "_fixture": {
            "contract": corpus_contract.CONTRACT_NAME,
            "version": corpus_contract.CONTRACT_VERSION,
            "provider": "UoinkCorpusProvider",
            "regenerate": (
                "python tests/regenerate_corpus_contract_v1_fixture.py"
            ),
            "check": (
                "python tests/regenerate_corpus_contract_v1_fixture.py "
                "--check"
            ),
            "data": "synthetic",
        },
        "operations": {
            "search_all": search_all,
            "search_filtered": search_filtered,
            "search_no_matches": search_no_matches,
            "get": item,
            "get_non_video": note,
            "facets": facets,
            "taste": taste,
            "assemble": assembly,
            "missing": missing,
        },
    }


def _render(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if the checked-in fixture differs; do not write",
    )
    args = parser.parse_args()
    rendered = _render(generate_fixture())
    if args.check:
        if not FIXTURE_PATH.exists():
            print(f"missing {FIXTURE_PATH.relative_to(ROOT)}")
            return 1
        if FIXTURE_PATH.read_text(encoding="utf-8") != rendered:
            print(f"stale {FIXTURE_PATH.relative_to(ROOT)}")
            return 1
        print(f"ok {FIXTURE_PATH.relative_to(ROOT)}")
        return 0
    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE_PATH.write_text(rendered, encoding="utf-8")
    print(f"wrote {FIXTURE_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
