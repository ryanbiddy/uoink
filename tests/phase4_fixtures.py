"""tests/phase4_fixtures.py - Shared test fixtures and helpers for Phase 4.

Provides isolated index.Index instances on temporary paths, synthetic corpus
generators, adversarial text fixtures, and mock clock utilities. Never imports
or starts the real backend against default settings, touches port 5179, or
accesses the live index.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any, Generator

import index
import library_cards
from tests.security.fixtures import (
    ADVERSARIAL_CLIPS,
    ADVERSARIAL_TITLES,
    FENCE_BREAKING_MARKDOWN,
)


def b64url_encode(s: str) -> str:
    """Unpadded base64url of UTF-8 encoded string."""
    return base64.urlsafe_b64encode(s.encode("utf-8")).rstrip(b"=").decode("ascii")


def compute_file_sha256(path: Path | str) -> str:
    """Compute SHA-256 over exact file bytes using 1 MiB blocks."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


class MockClock:
    """Controllable monotonic and wall-clock time for deadline and rate guard tests."""

    def __init__(self, start_mono: float = 1000.0, start_wall: float = 1788825600.0):
        self._mono = start_mono
        self._wall = start_wall

    def monotonic(self) -> float:
        return self._mono

    def wall(self) -> float:
        return self._wall

    def advance(self, seconds: float) -> None:
        self._mono += seconds
        self._wall += seconds


def make_disposable_index(tmp_path: Path) -> index.Index:
    """Create a clean, isolated SQLite index on a temporary path."""
    db_path = tmp_path / "index.db"
    return index.Index.open(db_path)


def seed_yoink_item(
    idx: index.Index,
    tmp_path: Path,
    *,
    video_id: str,
    slug: str,
    title: str,
    channel: str = "Test Channel",
    topic: str = "Technology",
    platform: str = "youtube",
    source_type: str = "video",
    url: str | None = None,
    corpus_text: str = "",
    clips: list[dict[str, Any]] | None = None,
    yoinked_at: str = "2026-09-08T01:00:00",
    deleted_at: str | None = None,
) -> dict[str, Any]:
    """Seed a single item into the index and write its corpus file."""
    corpus_path = tmp_path / f"{video_id}.md"
    corpus_path.write_text(corpus_text, encoding="utf-8")

    meta = {}
    if url is not None:
        meta["url"] = url
    else:
        meta["url"] = f"https://example.com/watch?v={video_id}"

    item_row = {
        "video_id": video_id,
        "slug": slug,
        "channel": channel,
        "title": title,
        "topic": topic,
        "hook_type": None,
        "yoinked_at": yoinked_at,
        "corpus_path": str(corpus_path),
        "sidecar_path": str(tmp_path / f"{video_id}.json"),
        "metadata_json": json.dumps(meta),
        "schema_version": 2,
        "source_type": source_type,
        "platform": platform,
        "author": channel,
    }
    idx.upsert_yoink(item_row)

    if deleted_at is not None:
        # Index._conn is the sqlite3.Connection attribute, guarded by Index._lock.
        with idx._lock:
            idx._conn.execute(
                "UPDATE yoinks SET deleted_at = ? WHERE video_id = ?",
                (deleted_at, video_id),
            )
            idx._conn.commit()

    clip_records = []
    if clips:
        for i, c in enumerate(clips):
            clip_records.append({
                "kind": c.get("kind", "transcript_chunk"),
                "seq": c.get("seq", i),
                "timestamp_start": c.get("start", float(i * 30)),
                "timestamp_end": c.get("end", float((i + 1) * 30)),
                "text": c.get("text", f"Clip text segment {i}"),
                "source_deep_link": c.get(
                    "source_deep_link", f"https://example.com/watch?v={video_id}#t={i*30}"
                ),
            })
        idx.insert_citations(video_id, clip_records)
        idx.rebuild_clips()

    return item_row


def build_test_card(
    idx: index.Index,
    video_id: str,
    profile: str = "librarian",
) -> dict[str, Any]:
    """Build a deterministic card by reading item and clips coherently from index."""
    with idx._lock:
        item = idx.get_yoink(video_id)
        if item is None:
            raise ValueError(f"Item not found: {video_id}")
        clips = idx.get_clips(video_id)
    head = library_cards.read_corpus_head(item.get("corpus_path"))
    return library_cards.build_card(item, clips, corpus_text=head, profile=profile)


def parse_fenced_document(text: str) -> dict[str, Any]:
    """Verify the exact preface/opening/closing fence, then JSON-decode the enclosed body."""
    import library_resources
    preface = library_resources.DOCUMENT_PREFACE
    assert text.startswith(preface), f"Text does not start with expected preface: {text[:100]!r}"
    rest = text[len(preface):]
    if rest.startswith("<untrusted_uoink_library_context>\n"):
        open_fence = "<untrusted_uoink_library_context>\n"
        close_fence = "\n</untrusted_uoink_library_context>"
    elif rest.startswith("<untrusted_evidence_card>\n"):
        open_fence = "<untrusted_evidence_card>\n"
        close_fence = "\n</untrusted_evidence_card>"
    else:
        raise AssertionError(f"Text does not have expected opening fence: {text[:100]!r}")
    assert text.endswith(close_fence), f"Text does not end with expected fence {close_fence!r}: {text[-100:]!r}"
    raw_json = text[len(preface) + len(open_fence) : -len(close_fence)]
    return json.loads(raw_json)


def seed_shelf(
    idx: index.Index,
    shelf_id: str = "shelf-test-01",
    name: str = "Test Shelf",
    version_id: str = "v0000000001",
    revision_hash: str | None = None,
    projection_revision: int = 1,
    member_video_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Seed a valid Phase 2 shelf and assign items to it."""
    if revision_hash is None:
        revision_hash = "a" * 64
    with idx._lock:
        idx._conn.execute(
            "INSERT OR REPLACE INTO shelves(shelf_id, created_at) VALUES(?, '2026-09-08T00:00:00Z')",
            (shelf_id,),
        )
        idx._conn.execute(
            "INSERT OR REPLACE INTO shelf_versions(version_id, revision_hash, status, created_at) VALUES(?, ?, 'active', '2026-09-08T00:00:00Z')",
            (version_id, revision_hash),
        )
        idx._conn.execute(
            "INSERT OR REPLACE INTO library_meta(singleton, projection_revision, active_version_id) VALUES(1, ?, ?)",
            (projection_revision, version_id),
        )
        idx._conn.execute(
            "INSERT OR REPLACE INTO shelf_nodes(version_id, shelf_id, parent_shelf_id, name, path_json, definition, include_json, exclude_json, retired) "
            "VALUES(?, ?, NULL, ?, ?, 'Test definition', '[]', '[]', 0)",
            (version_id, shelf_id, name, json.dumps([name])),
        )
        if member_video_ids:
            for vid in member_video_ids:
                card = build_test_card(idx, vid)
                idx._conn.execute(
                    "INSERT OR REPLACE INTO item_shelves(video_id, shelf_id, version_id, source_revision, source, locked, is_primary, confidence, evidence_json, assigned_at) "
                    "VALUES(?, ?, ?, ?, 'user', 0, 1, NULL, NULL, '2026-09-08T00:00:00Z')",
                    (vid, shelf_id, version_id, card["source_revision"]),
                )
        idx._conn.commit()
    return {
        "shelf_id": shelf_id,
        "name": name,
        "version_id": version_id,
        "taxonomy_revision": revision_hash,
        "projection_revision": projection_revision,
    }


def seed_standard_library(tmp_path: Path) -> tuple[index.Index, dict[str, Any]]:
    """Seed a representative library covering diverse item kinds, evidence, and bounds."""
    idx = make_disposable_index(tmp_path)

    # 1. Standard video with 8 clips (exceeds librarian's 6-excerpt budget to test spread)
    clips_std = [
        {"seq": i, "start": float(i * 60), "end": float((i + 1) * 60),
         "text": f"Timed evidence point {i} detailing system behavior in depth with significant analysis."}
        for i in range(8)
    ]
    std_row = seed_yoink_item(
        idx, tmp_path,
        video_id="vid-standard-01",
        slug="standard-video-slug",
        title="Standard Analysis Video",
        channel="Tech Channel",
        url="https://youtube.example/vid-standard-01",
        corpus_text="# Standard Video\n\nOpening description of the video content.\n",
        clips=clips_std,
    )

    # 2. Prose-eligible article with opening prose and NO clips
    prose_corpus = (
        "---\ntitle: Architectural Review\n---\n"
        "Architectural decisions require explicit trade-off balancing across boundaries. "
        "Every boundary should be guarded by canonical serialization and bounds checking. "
        "Verifying identity at rest prevents spoofing across sessions.\n"
    )
    prose_row = seed_yoink_item(
        idx, tmp_path,
        video_id="doc-prose-02",
        slug="architectural-review-slug",
        title="Architectural Review Document",
        channel="Architecture Team",
        source_type="page",
        platform="web",
        url="https://docs.example/arch-review",
        corpus_text=prose_corpus,
        clips=[],
    )

    # 3. Mixed item: prose-eligible article with BOTH opening prose and timed clips
    mixed_corpus = (
        "Executive summary: Distributed systems require bounded retry loops and immutable logs. "
        "Secondary observations follow below.\n"
    )
    mixed_clips = [
        {"seq": 0, "start": 10.0, "end": 40.0, "text": "Clip one discusses failure isolation."},
        {"seq": 1, "start": 50.0, "end": 80.0, "text": "Clip two details heartbeat mechanics."},
    ]
    mixed_row = seed_yoink_item(
        idx, tmp_path,
        video_id="doc-mixed-03",
        slug="distributed-systems-slug",
        title="Distributed Systems Note",
        channel="Systems Group",
        source_type="note",
        platform="local",
        url="https://notes.example/distributed",
        corpus_text=mixed_corpus,
        clips=mixed_clips,
    )

    # 4. Soft-deleted item
    deleted_row = seed_yoink_item(
        idx, tmp_path,
        video_id="vid-deleted-04",
        slug="deleted-video-slug",
        title="Deleted Video",
        deleted_at="2026-09-08T00:00:00Z",
        clips=[{"seq": 0, "start": 0.0, "end": 10.0, "text": "Deleted clip."}],
    )

    # 5. Empty item (no clips, no prose)
    empty_row = seed_yoink_item(
        idx, tmp_path,
        video_id="vid-empty-05",
        slug="empty-video-slug",
        title="Empty Video",
        corpus_text="",
        clips=[],
    )

    # 6. Item with huge corpus file (> 16 MiB admission ceiling)
    huge_path = tmp_path / "vid-huge-06.md"
    with open(huge_path, "wb") as f:
        # Write 16 MiB + 1024 bytes (16,778,240 bytes)
        f.seek(16 * 1024 * 1024 + 1024 - 1)
        f.write(b"X")
    huge_row = {
        "video_id": "vid-huge-06",
        "slug": "huge-video-slug",
        "channel": "Big Data Channel",
        "title": "Huge Corpus Video",
        "topic": "Data",
        "hook_type": None,
        "yoinked_at": "2026-09-08T01:00:00",
        "corpus_path": str(huge_path),
        "sidecar_path": str(tmp_path / "vid-huge-06.json"),
        "metadata_json": json.dumps({"url": "https://example.com/huge"}),
        "schema_version": 2,
        "source_type": "video",
        "platform": "youtube",
        "author": "Big Data Channel",
    }
    idx.upsert_yoink(huge_row)

    manifest = {
        "standard": (std_row, clips_std),
        "prose": (prose_row, []),
        "mixed": (mixed_row, mixed_clips),
        "deleted": (deleted_row, [{"seq": 0, "start": 0.0, "end": 10.0, "text": "Deleted clip."}]),
        "empty": (empty_row, []),
        "huge": (huge_row, []),
    }
    return idx, manifest
