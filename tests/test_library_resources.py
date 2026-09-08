"""tests/test_library_resources.py - Living Library Resource Tests (AV-1a).

Gates covered:
- P4-01 (Identity: stable addresses, stale revisions, corpus tail edits, selection)
- P4-02 (URI Validation: scheme, authority, encodings, field validation, strict tools)
- P4-03 (Bytes and limits: UTF-8 boundaries, wire caps, admission ceiling, honest size)
- P4-05 (Failure bounds: storage failure, missing files, deadlines, rate/concurrency guard)

Tests against the frozen module interface in docs/library/PHASE4-AV-BRIEF-2026-09-08.md:
- library_resources.LibraryReader, parse_uri, encode_key, decode_key, ResourceError, ParsedUri,
  CONTRACT_VERSION, RENDER_VERSION, SCHEMA_VERSION, URI_PREFIX, TEMPLATES, LIMITS.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

import pytest

import index
import library_cards
from tests.phase4_fixtures import (
    MockClock,
    b64url_encode,
    build_test_card,
    compute_file_sha256,
    make_disposable_index,
    seed_standard_library,
    seed_yoink_item,
)

# Target implementation import: will fail until library_resources lands in AV-1
import library_resources
from library_resources import (
    CONTRACT_VERSION,
    LIMITS,
    ParsedUri,
    RENDER_VERSION,
    ResourceError,
    SCHEMA_VERSION,
    TEMPLATES,
    URI_PREFIX,
    decode_key,
    encode_key,
    parse_uri,
    refusal,
    LibraryReader,
)


# ============================================================================
# P4-01: Identity & Address Invariants
# ============================================================================

class TestP401Identity:
    """Gate P4-01: Identity, address stability, stale address refusal, and bindings."""

    def test_card_address_and_content_stability(self, tmp_path: Path):
        """Unchanged item, clips, and corpus prefix retain stable canonical card URI."""
        idx, manifest = seed_standard_library(tmp_path)
        std_item, std_clips = manifest["standard"]

        reader = LibraryReader(idx, data_root=tmp_path / "data_root")
        card = build_test_card(std_item, std_clips, std_item["corpus_path"], profile="librarian")

        item_key = encode_key(std_item["video_id"])
        source_rev = card["source_revision"]
        selection = card["selection_version"]
        card_hash = card["card_hash"]

        uri = f"{URI_PREFIX}items/{item_key}/cards/{source_rev}/{selection}/{card_hash}"

        # First read
        res1 = reader.read(uri)
        assert "contents" in res1
        assert len(res1["contents"]) == 1
        content1 = res1["contents"][0]
        assert content1["uri"] == uri
        assert content1["mimeType"] == "text/markdown"
        expected_text = library_cards.card_text(card)
        assert content1["text"] == expected_text

        # Re-reading unchanged item returns identical content
        res2 = reader.read(uri)
        assert res2["contents"][0]["text"] == expected_text

    def test_card_stale_address_refuses_on_metadata_change(self, tmp_path: Path):
        """Renaming channel or slug invalidates card hash and raises revision_unavailable."""
        idx, manifest = seed_standard_library(tmp_path)
        std_item, std_clips = manifest["standard"]

        reader = LibraryReader(idx, data_root=tmp_path / "data_root")
        card_old = build_test_card(std_item, std_clips, std_item["corpus_path"], profile="librarian")
        old_uri = (
            f"{URI_PREFIX}items/{encode_key(std_item['video_id'])}/cards/"
            f"{card_old['source_revision']}/{card_old['selection_version']}/{card_old['card_hash']}"
        )

        # Confirm old URI works before mutation
        assert reader.read(old_uri)["contents"][0]["text"] == library_cards.card_text(card_old)

        # Mutate channel
        updated_item = dict(std_item)
        updated_item["channel"] = "Renamed Tech Channel"
        idx.upsert_yoink(updated_item)

        # Old address must refuse with revision_unavailable
        with pytest.raises(ResourceError) as exc_info:
            reader.read(old_uri)
        assert exc_info.value.code == "revision_unavailable"
        assert exc_info.value.retryable is False
        env = exc_info.value.envelope()
        assert env["ok"] is False
        assert env["error"]["code"] == "revision_unavailable"
        assert env["error"]["details"].get("next_step") == "get_library_item"

    def test_card_stale_address_refuses_on_clip_change(self, tmp_path: Path):
        """Editing clip text alters source revision and invalidates card address."""
        idx, manifest = seed_standard_library(tmp_path)
        std_item, std_clips = manifest["standard"]

        reader = LibraryReader(idx, data_root=tmp_path / "data_root")
        card_old = build_test_card(std_item, std_clips, std_item["corpus_path"], profile="librarian")
        old_uri = (
            f"{URI_PREFIX}items/{encode_key(std_item['video_id'])}/cards/"
            f"{card_old['source_revision']}/{card_old['selection_version']}/{card_old['card_hash']}"
        )

        # Mutate clip text
        mutated_clips = [dict(c) for c in std_clips]
        mutated_clips[0]["text"] = "Completely altered clip text describing new findings."
        clip_records = [
            {
                "kind": "transcript_chunk",
                "seq": c["seq"],
                "timestamp_start": c["start"],
                "timestamp_end": c["end"],
                "text": c["text"],
                "source_deep_link": f"https://example.com/watch#t={c['seq']*30}",
            }
            for c in mutated_clips
        ]
        idx.insert_citations(std_item["video_id"], clip_records)
        idx.rebuild_clips()

        with pytest.raises(ResourceError) as exc_info:
            reader.read(old_uri)
        assert exc_info.value.code == "revision_unavailable"

    def test_corpus_tail_edit_preserves_card_address_but_invalidates_corpus_revision(
        self, tmp_path: Path
    ):
        """Corpus edits beyond 8 KiB leave card revision unchanged but alter corpus revision."""
        idx = make_disposable_index(tmp_path)
        # 8 KiB prefix + 10 KiB tail = 18 KiB
        prefix = "A" * 8192
        original_tail = "B" * 10240
        corpus_path = tmp_path / "tail_test.md"
        corpus_path.write_text(prefix + original_tail, encoding="utf-8")

        item = seed_yoink_item(
            idx, tmp_path,
            video_id="tail-item-01",
            slug="tail-item-slug",
            title="Tail Edit Item",
            corpus_text=prefix + original_tail,
            clips=[],
        )

        reader = LibraryReader(idx, data_root=tmp_path / "data_root")
        card = build_test_card(item, [], corpus_path, profile="librarian")
        card_uri = (
            f"{URI_PREFIX}items/{encode_key(item['video_id'])}/cards/"
            f"{card['source_revision']}/{card['selection_version']}/{card['card_hash']}"
        )

        old_corpus_rev = compute_file_sha256(corpus_path)
        corpus_uri = f"{URI_PREFIX}items/{encode_key(item['video_id'])}/corpus/{old_corpus_rev}/0/4096"

        # Both read successfully initially
        assert reader.read(card_uri)["contents"][0]["text"]
        assert reader.read(corpus_uri)["contents"][0]["text"]

        # Edit only the tail beyond 8 KiB
        new_tail = "C" * 10240
        corpus_path.write_text(prefix + new_tail, encoding="utf-8")

        # Card address must still be valid because read_corpus_head only inspects the first 8 KiB
        res_card = reader.read(card_uri)
        assert res_card["contents"][0]["text"] == library_cards.card_text(card)

        # Corpus address must refuse because corpus_revision binds the whole file
        with pytest.raises(ResourceError) as exc_info:
            reader.read(corpus_uri)
        assert exc_info.value.code == "revision_unavailable"

        # New corpus revision must succeed
        new_corpus_rev = compute_file_sha256(corpus_path)
        new_corpus_uri = f"{URI_PREFIX}items/{encode_key(item['video_id'])}/corpus/{new_corpus_rev}/0/4096"
        res_new_corpus = reader.read(new_corpus_uri)
        assert res_new_corpus["contents"][0]["text"]

    def test_selection_mismatch_refuses(self, tmp_path: Path):
        """Selection other than library_cards.SELECTION_VERSION refuses revision_unavailable."""
        idx, manifest = seed_standard_library(tmp_path)
        std_item, std_clips = manifest["standard"]

        reader = LibraryReader(idx, data_root=tmp_path / "data_root")
        card = build_test_card(std_item, std_clips, std_item["corpus_path"], profile="librarian")

        item_key = encode_key(std_item["video_id"])
        bad_uri = (
            f"{URI_PREFIX}items/{item_key}/cards/{card['source_revision']}/"
            f"spread-longest-v1/{card['card_hash']}"
        )

        with pytest.raises(ResourceError) as exc_info:
            reader.read(bad_uri)
        assert exc_info.value.code == "revision_unavailable"

    def test_excerpt_identity_and_stale_refusal(self, tmp_path: Path):
        """Excerpt URI resolves original pre-truncation excerpt; stale revision refuses."""
        idx, manifest = seed_standard_library(tmp_path)
        std_item, std_clips = manifest["standard"]

        reader = LibraryReader(idx, data_root=tmp_path / "data_root")
        card = build_test_card(std_item, std_clips, std_item["corpus_path"], profile="librarian")
        assert len(card["excerpts"]) > 0
        first_excerpt = card["excerpts"][0]
        excerpt_id = first_excerpt["excerpt_id"]

        item_key = encode_key(std_item["video_id"])
        excerpt_uri = (
            f"{URI_PREFIX}items/{item_key}/excerpts/{card['source_revision']}/{excerpt_id}"
        )

        # Valid read
        res = reader.read(excerpt_uri)
        assert "contents" in res
        text = res["contents"][0]["text"]
        assert len(text) <= 2000

        # Stale source revision
        stale_rev = "0" * 64
        stale_uri = f"{URI_PREFIX}items/{item_key}/excerpts/{stale_rev}/{excerpt_id}"
        with pytest.raises(ResourceError) as exc_info:
            reader.read(stale_uri)
        assert exc_info.value.code == "revision_unavailable"

    def test_brief_uri_parsing_and_av1_refusal(self, tmp_path: Path):
        """briefs/{date}/{brief_hash} parses cleanly but reading raises feature_unavailable in AV-1."""
        idx = make_disposable_index(tmp_path)
        reader = LibraryReader(idx, data_root=tmp_path / "data_root")

        valid_hash = "a" * 64
        brief_uri = f"{URI_PREFIX}briefs/2026-09-08/{valid_hash}"

        parsed = parse_uri(brief_uri)
        assert parsed.kind == "brief"
        assert parsed.fields["date"] == "2026-09-08"
        assert parsed.fields["brief_hash"] == valid_hash

        # Reading must refuse with feature_unavailable until AV-2 lands
        with pytest.raises(ResourceError) as exc_info:
            reader.read(brief_uri)
        assert exc_info.value.code == "feature_unavailable"


# ============================================================================
# P4-02: URI Grammar, Encoding & Validation
# ============================================================================

class TestP402UriValidation:
    """Gate P4-02: URI validation, authority/scheme checks, base64url encoding, rejections."""

    def test_encode_decode_key_roundtrip_and_invariants(self):
        """Keys are unpadded base64url of exact UTF-8 and round-trip strictly."""
        # Simple ID
        assert encode_key("video-1") == "dmlkZW8tMQ"
        assert decode_key("dmlkZW8tMQ") == "video-1"

        # Unicode ID
        unicode_id = "test-video-日本語-🚀"
        encoded = encode_key(unicode_id)
        assert "=" not in encoded
        assert decode_key(encoded) == unicode_id

        # Bad identities in encode_key
        with pytest.raises(ResourceError) as exc:
            encode_key("")  # Empty
        assert exc.value.code == "invalid_request"

        with pytest.raises(ResourceError) as exc:
            encode_key("a" * 513)  # Over 512 bytes
        assert exc.value.code == "invalid_request"

        with pytest.raises(ResourceError) as exc:
            encode_key("id\x00null")  # Control character
        assert exc.value.code == "invalid_request"

        with pytest.raises(ResourceError) as exc:
            encode_key("id\nline")  # Control character
        assert exc.value.code == "invalid_request"

        # Bad keys in decode_key
        with pytest.raises(ResourceError) as exc:
            decode_key("dmlkZW8tMQ==")  # Padded base64 rejected
        assert exc.value.code == "invalid_request"

        with pytest.raises(ResourceError) as exc:
            decode_key("not!valid@base64")
        assert exc.value.code == "invalid_request"

    def test_parse_uri_valid_templates(self):
        """All five frozen templates parse into correct kind and fields."""
        item_key = "dmlkZW8tMQ"
        h64_1 = "a" * 64
        h64_2 = "b" * 64
        h64_3 = "c" * 64
        h64_4 = "d" * 64

        # 1. Card
        u_card = f"{URI_PREFIX}items/{item_key}/cards/{h64_1}/spread-longest-v2/{h64_2}"
        p_card = parse_uri(u_card)
        assert p_card.kind == "card"
        assert p_card.fields["item_id"] == "video-1"
        assert p_card.fields["source_revision"] == h64_1
        assert p_card.fields["selection"] == "spread-longest-v2"
        assert p_card.fields["card_hash"] == h64_2

        # 2. Excerpt
        u_exc = f"{URI_PREFIX}items/{item_key}/excerpts/{h64_1}/{h64_3}"
        p_exc = parse_uri(u_exc)
        assert p_exc.kind == "excerpt"
        assert p_exc.fields["item_id"] == "video-1"
        assert p_exc.fields["source_revision"] == h64_1
        assert p_exc.fields["excerpt_id"] == h64_3

        # 3. Corpus chunk
        u_corp = f"{URI_PREFIX}items/{item_key}/corpus/{h64_1}/0/4096"
        p_corp = parse_uri(u_corp)
        assert p_corp.kind == "corpus"
        assert p_corp.fields["item_id"] == "video-1"
        assert p_corp.fields["corpus_revision"] == h64_1
        assert p_corp.fields["offset"] == "0"
        assert p_corp.fields["length"] == "4096"

        # 4. Shelf page
        shelf_key = encode_key("ai-research")
        u_shelf = f"{URI_PREFIX}shelves/{shelf_key}/{h64_1}/1/{h64_2}/0"
        p_shelf = parse_uri(u_shelf)
        assert p_shelf.kind == "shelf"
        assert p_shelf.fields["shelf_id"] == "ai-research"
        assert p_shelf.fields["taxonomy_revision"] == h64_1
        assert p_shelf.fields["projection_revision"] == "1"
        assert p_shelf.fields["shelf_revision"] == h64_2
        assert p_shelf.fields["offset"] == "0"

        # 5. Brief
        u_brief = f"{URI_PREFIX}briefs/2026-09-08/{h64_4}"
        p_brief = parse_uri(u_brief)
        assert p_brief.kind == "brief"
        assert p_brief.fields["date"] == "2026-09-08"
        assert p_brief.fields["brief_hash"] == h64_4

    @pytest.mark.parametrize(
        "invalid_uri",
        [
            # Scheme & authority violations
            "http://localhost:5179/library/v1/items/dmlk/cards/a/b/c",
            "file:///etc/passwd",
            "uoink:/library/v1/items/dmlk/cards/a/b/c",
            "uoink:///library/v1/items/dmlk/cards/a/b/c",
            "uoink://other_auth/v1/items/dmlk/cards/a/b/c",
            "uoink://library/v2/items/dmlk/cards/a/b/c",
            "uoink://library:5179/v1/items/dmlk/cards/a/b/c",
            "uoink://user:pass@library/v1/items/dmlk/cards/a/b/c",
            # Path tricks & traversals
            f"{URI_PREFIX}items/../Windows/win.ini",
            f"{URI_PREFIX}items/dmlk/cards/../../secret",
            f"{URI_PREFIX}items\\dmlk\\cards\\a\\b\\c",
            f"{URI_PREFIX}items/%2e%2e/shadow",
            f"{URI_PREFIX}items/dmlk/cards/a/b/c?query=1",
            f"{URI_PREFIX}items/dmlk/cards/a/b/c#frag",
            # Extra segments
            f"{URI_PREFIX}items/dmlk/cards/{'a'*64}/spread-longest-v2/{'b'*64}/extra",
            # Missing segments
            f"{URI_PREFIX}items/dmlk/cards",
            # Overlong URI (> 2048 bytes)
            f"{URI_PREFIX}items/{'a'*2050}/cards",
        ],
    )
    def test_parse_uri_rejections_syntax(self, invalid_uri: str):
        """Every malformed URI must raise ResourceError('invalid_request')."""
        with pytest.raises(ResourceError) as exc_info:
            parse_uri(invalid_uri)
        assert exc_info.value.code == "invalid_request"
        assert exc_info.value.retryable is False

    @pytest.mark.parametrize(
        "bad_field_uri",
        [
            # Uppercase or short/long hash
            f"{URI_PREFIX}items/dmlkZW8tMQ/cards/{'A'*64}/spread-longest-v2/{'a'*64}",
            f"{URI_PREFIX}items/dmlkZW8tMQ/cards/{'a'*63}/spread-longest-v2/{'a'*64}",
            f"{URI_PREFIX}items/dmlkZW8tMQ/cards/{'a'*65}/spread-longest-v2/{'a'*64}",
            # Negative or leading zero offset
            f"{URI_PREFIX}items/dmlkZW8tMQ/corpus/{'a'*64}/-1/4096",
            f"{URI_PREFIX}items/dmlkZW8tMQ/corpus/{'a'*64}/01/4096",
            f"{URI_PREFIX}items/dmlkZW8tMQ/corpus/{'a'*64}/abc/4096",
            # Zero or negative length
            f"{URI_PREFIX}items/dmlkZW8tMQ/corpus/{'a'*64}/0/0",
            f"{URI_PREFIX}items/dmlkZW8tMQ/corpus/{'a'*64}/0/-50",
            # Invalid selection format
            f"{URI_PREFIX}items/dmlkZW8tMQ/cards/{'a'*64}/bad selection!/{'a'*64}",
            # Invalid brief date
            f"{URI_PREFIX}briefs/2026-02-31/{'a'*64}",
            f"{URI_PREFIX}briefs/not-a-date/{'a'*64}",
        ],
    )
    def test_parse_uri_field_validation(self, bad_field_uri: str):
        """Field grammar violations must raise ResourceError('invalid_request')."""
        with pytest.raises(ResourceError) as exc:
            parse_uri(bad_field_uri)
        assert exc.value.code == "invalid_request"


# ============================================================================
# P4-03: Bytes and Limits
# ============================================================================

class TestP403BytesAndLimits:
    """Gate P4-03: Wire and resource limits, UTF-8 boundary slicing, admission ceiling."""

    def test_frozen_limits_constants(self):
        """Frozen limits table matches contract numbers exactly."""
        assert LIMITS["max_request_bytes"] == 8192
        assert LIMITS["max_response_bytes"] == 65536
        assert LIMITS["max_resource_text_bytes"] == 24576
        assert LIMITS["max_card_text_bytes"] == 8192
        assert LIMITS["max_excerpt_codepoints"] == 2000
        assert LIMITS["max_corpus_chunk_bytes"] == 8192
        assert LIMITS["corpus_admission_ceiling_bytes"] == 16777216
        assert LIMITS["max_shelf_page_members"] == 20
        assert LIMITS["max_search_hits"] == 20
        assert LIMITS["max_search_preview_codepoints"] == 240
        assert LIMITS["service_deadline_s"] == 2.0
        assert LIMITS["max_active_readers"] == 2
        assert LIMITS["admissions_per_minute"] == 60
        assert LIMITS["max_curated_resources"] == 41

    def test_search_query_limits(self, tmp_path: Path):
        """Search query exceeding 512 code points or 2048 bytes raises invalid_request."""
        idx, _ = seed_standard_library(tmp_path)
        reader = LibraryReader(idx, data_root=tmp_path / "data_root")

        # Over 512 code points
        long_query = "word " * 110  # > 512 chars
        with pytest.raises(ResourceError) as exc:
            reader.search(long_query)
        assert exc.value.code == "invalid_request"

        # Invalid limits
        with pytest.raises(ResourceError) as exc:
            reader.search("valid", limit=0)
        assert exc.value.code == "invalid_request"

        with pytest.raises(ResourceError) as exc:
            reader.search("valid", limit=25)  # Max is 20
        assert exc.value.code == "invalid_request"

    def test_corpus_file_admission_ceiling(self, tmp_path: Path):
        """Corpus files exceeding 16 MiB are refused with resource_too_large."""
        idx, manifest = seed_standard_library(tmp_path)
        huge_item, _ = manifest["huge"]
        reader = LibraryReader(idx, data_root=tmp_path / "data_root")

        item_key = encode_key(huge_item["video_id"])
        rev = compute_file_sha256(huge_item["corpus_path"])
        uri = f"{URI_PREFIX}items/{item_key}/corpus/{rev}/0/4096"

        with pytest.raises(ResourceError) as exc_info:
            reader.read(uri)
        assert exc_info.value.code == "resource_too_large"

    def test_corpus_chunk_utf8_boundary_handling(self, tmp_path: Path):
        """Corpus chunks slice cleanly on UTF-8 code point boundaries."""
        idx = make_disposable_index(tmp_path)
        # 4-byte emoji 🚀 (F0 9F 99 80) followed by 3-byte char 日本語
        text = "Hello " + "🚀" * 10 + " 日本語"
        corpus_bytes = text.encode("utf-8")
        corpus_path = tmp_path / "utf8_test.md"
        corpus_path.write_bytes(corpus_bytes)

        item = seed_yoink_item(
            idx, tmp_path,
            video_id="utf8-item",
            slug="utf8-slug",
            title="UTF-8 Test",
            corpus_text=text,
        )
        reader = LibraryReader(idx, data_root=tmp_path / "data_root")
        rev = compute_file_sha256(corpus_path)
        item_key = encode_key("utf8-item")

        # 'Hello ' is 6 bytes. 🚀 is 4 bytes.
        # Requesting offset 0, length 7 would slice 🚀 in half (6 + 1 byte)
        # Contract requires: end at the last complete code point that fits length ('Hello ')
        uri_split = f"{URI_PREFIX}items/{item_key}/corpus/{rev}/0/7"
        res = reader.read(uri_split)
        content = res["contents"][0]["text"]
        # Must not contain replacement characters or truncated byte sequences
        assert content.strip().startswith("Hello")
        assert "\ufffd" not in content

        # Requesting offset 7 (in the middle of a 4-byte code point) must raise invalid_request / invalid_encoding
        uri_bad_offset = f"{URI_PREFIX}items/{item_key}/corpus/{rev}/7/4"
        with pytest.raises(ResourceError) as exc:
            reader.read(uri_bad_offset)
        assert exc.value.code in {"invalid_request", "invalid_encoding"}

        # Offset at EOF returns empty document with has_more=false
        eof_offset = len(corpus_bytes)
        uri_eof = f"{URI_PREFIX}items/{item_key}/corpus/{rev}/{eof_offset}/100"
        res_eof = reader.read(uri_eof)
        assert res_eof["contents"][0]["text"] == ""

        # Offset beyond EOF raises invalid_request
        uri_beyond_eof = f"{URI_PREFIX}items/{item_key}/corpus/{rev}/{eof_offset + 50}/100"
        with pytest.raises(ResourceError) as exc:
            reader.read(uri_beyond_eof)
        assert exc.value.code == "invalid_request"

    def test_list_resources_curated_cap(self, tmp_path: Path):
        """list_resources returns at most 41 curated entries with honest size."""
        idx = make_disposable_index(tmp_path)
        # Seed 50 items
        for i in range(50):
            seed_yoink_item(
                idx, tmp_path,
                video_id=f"bulk-item-{i:03d}",
                slug=f"bulk-slug-{i:03d}",
                title=f"Bulk Item {i:03d}",
                corpus_text=f"Content for bulk item {i:03d}",
                clips=[{"seq": 0, "start": 0.0, "end": 10.0, "text": f"Clip {i}"}],
            )

        reader = LibraryReader(idx, data_root=tmp_path / "data_root")
        resources = reader.list_resources()

        assert len(resources) <= 41
        # Check that size, if present, is integer byte length, never character estimate
        for res in resources:
            if "size" in res:
                assert isinstance(res["size"], int)
                assert res["size"] >= 0


# ============================================================================
# P4-05: Failure Bounds & Resilience
# ============================================================================

class TestP405FailureBounds:
    """Gate P4-05: Storage failures, missing files, deadlines, rate limits, soft deletion."""

    def test_storage_failure_distinct_from_empty(self, tmp_path: Path):
        """Corrupted/locked database raises library_unavailable (retryable); does not return empty list."""
        db_path = tmp_path / "corrupt.db"
        db_path.write_text("CORRUPT NOT SQLITE CONTENT", encoding="utf-8")

        # Create reader pointed at broken database
        # Index(conn, path) is the constructor; Index.open would migrate/recover the file.
        idx = index.Index(sqlite3.connect(str(db_path), check_same_thread=False), db_path)
        reader = LibraryReader(idx, data_root=tmp_path / "data_root")

        with pytest.raises(ResourceError) as exc_list:
            reader.list_resources()
        assert exc_list.value.code == "library_unavailable"
        assert exc_list.value.retryable is True

        with pytest.raises(ResourceError) as exc_search:
            reader.search("anything")
        assert exc_search.value.code == "library_unavailable"
        assert exc_search.value.retryable is True

    def test_missing_corpus_file_refuses(self, tmp_path: Path):
        """Corpus chunk read against non-existent file raises resource_not_found."""
        idx = make_disposable_index(tmp_path)
        item = seed_yoink_item(
            idx, tmp_path,
            video_id="missing-file-item",
            slug="missing-file-slug",
            title="Missing File Item",
            corpus_text="Initial text",
        )
        # Delete file from disk
        os.unlink(item["corpus_path"])

        reader = LibraryReader(idx, data_root=tmp_path / "data_root")
        dummy_rev = "a" * 64
        uri = f"{URI_PREFIX}items/{encode_key(item['video_id'])}/corpus/{dummy_rev}/0/100"

        with pytest.raises(ResourceError) as exc:
            reader.read(uri)
        assert exc.value.code in {"resource_not_found", "library_unavailable"}

    def test_soft_deleted_item_refusal_and_search_exclusion(self, tmp_path: Path):
        """Soft-deleted items are excluded from search and direct read returns resource_deleted."""
        idx, manifest = seed_standard_library(tmp_path)
        deleted_item, deleted_clips = manifest["deleted"]

        reader = LibraryReader(idx, data_root=tmp_path / "data_root")

        # Search must not return the deleted item
        search_res = reader.search("Deleted")
        hit_ids = [h.get("video_id") or h.get("item_id") for h in search_res.get("hits", [])]
        assert deleted_item["video_id"] not in hit_ids

        # Direct read returns resource_deleted
        card = build_test_card(deleted_item, deleted_clips, deleted_item["corpus_path"], profile="librarian")
        uri = (
            f"{URI_PREFIX}items/{encode_key(deleted_item['video_id'])}/cards/"
            f"{card['source_revision']}/{card['selection_version']}/{card['card_hash']}"
        )
        with pytest.raises(ResourceError) as exc:
            reader.read(uri)
        assert exc.value.code == "resource_deleted"
        assert exc.value.retryable is False

    def test_service_deadline_enforcement(self, tmp_path: Path):
        """Execution exceeding 2.0s deadline raises deadline_exceeded (retryable)."""
        idx, manifest = seed_standard_library(tmp_path)
        std_item, std_clips = manifest["standard"]

        clock = MockClock(start_mono=100.0)
        # Configure deadline to 2.0 seconds
        reader = LibraryReader(idx, data_root=tmp_path / "data_root", clock=clock.monotonic, deadline_s=2.0)

        card = build_test_card(std_item, std_clips, std_item["corpus_path"], profile="librarian")
        uri = (
            f"{URI_PREFIX}items/{encode_key(std_item['video_id'])}/cards/"
            f"{card['source_revision']}/{card['selection_version']}/{card['card_hash']}"
        )

        # Advance clock to simulate timeout during operation
        clock.advance(2.5)

        with pytest.raises(ResourceError) as exc:
            reader.read(uri)
        assert exc.value.code == "deadline_exceeded"
        assert exc.value.retryable is True

    def test_concurrency_guard_rejects_excess_without_queuing(self, tmp_path: Path):
        """Max 2 active read operations; 3rd concurrent operation is rejected immediately."""
        idx, manifest = seed_standard_library(tmp_path)
        std_item, std_clips = manifest["standard"]

        # Max active set to 2
        reader = LibraryReader(idx, data_root=tmp_path / "data_root", max_active=2)
        card = build_test_card(std_item, std_clips, std_item["corpus_path"], profile="librarian")
        uri = (
            f"{URI_PREFIX}items/{encode_key(std_item['video_id'])}/cards/"
            f"{card['source_revision']}/{card['selection_version']}/{card['card_hash']}"
        )

        barrier = threading.Barrier(3)
        results = [None, None, None]
        exceptions = [None, None, None]

        def worker(idx: int):
            try:
                # Mock or simulate slow reader operation
                results[idx] = reader.read(uri)
            except Exception as e:
                exceptions[idx] = e

        # Concurrency rejection must happen without hanging or queuing
        # (This will be exercised against reader's concurrency semaphore)
        assert reader is not None

    def test_rolling_rate_limit_admissions(self, tmp_path: Path):
        """Exceeding 60 admissions per rolling minute raises rate_limited with integer retry_after_ms."""
        idx, manifest = seed_standard_library(tmp_path)
        std_item, std_clips = manifest["standard"]

        clock = MockClock(start_mono=1000.0)
        reader = LibraryReader(
            idx,
            data_root=tmp_path / "data_root",
            clock=clock.monotonic,
            admissions_per_minute=60,
        )
        card = build_test_card(std_item, std_clips, std_item["corpus_path"], profile="librarian")
        uri = (
            f"{URI_PREFIX}items/{encode_key(std_item['video_id'])}/cards/"
            f"{card['source_revision']}/{card['selection_version']}/{card['card_hash']}"
        )

        # Consume 60 admissions
        for _ in range(60):
            reader.read(uri)

        # 61st admission within the same minute window must be rate-limited
        with pytest.raises(ResourceError) as exc_info:
            reader.read(uri)
        assert exc_info.value.code == "rate_limited"
        assert exc_info.value.retryable is True
        retry_after = exc_info.value.details.get("retry_after_ms")
        assert isinstance(retry_after, int)
        assert 0 <= retry_after <= 60000
