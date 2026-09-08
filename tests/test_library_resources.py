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
    parse_fenced_document,
    seed_shelf,
    seed_standard_library,
    seed_yoink_item,
)

# Target implementation import: will fail until library_resources lands in AV-1
import library_resources
from library_resources import (
    CONTRACT_VERSION,
    LIMITS,
    ParsedUri,
    ReadGuard,
    RENDER_VERSION,
    ResourceError,
    SCHEMA_VERSION,
    TEMPLATES,
    URI_PREFIX,
    decode_key,
    encode_key,
    parse_uri,
    refusal,
    shelf_uri,
    wire_bytes,
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
        std_item, _ = manifest["standard"]

        reader = LibraryReader(idx, data_root=tmp_path / "data_root")
        card = build_test_card(idx, std_item["video_id"], profile="librarian")

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
        std_item, _ = manifest["standard"]

        reader = LibraryReader(idx, data_root=tmp_path / "data_root")
        card_old = build_test_card(idx, std_item["video_id"], profile="librarian")
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
        card_old = build_test_card(idx, std_item["video_id"], profile="librarian")
        old_uri = (
            f"{URI_PREFIX}items/{encode_key(std_item['video_id'])}/cards/"
            f"{card_old['source_revision']}/{card_old['selection_version']}/{card_old['card_hash']}"
        )

        # Assert old URI resolves before mutation
        assert reader.read(old_uri)["contents"][0]["text"] == library_cards.card_text(card_old)

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

        item = seed_yoink_item(
            idx, tmp_path,
            video_id="tail-item-01",
            slug="tail-item-slug",
            title="Tail Edit Item",
            corpus_text=prefix + original_tail,
            clips=[],
        )
        corpus_path = Path(item["corpus_path"])

        reader = LibraryReader(idx, data_root=tmp_path / "data_root")
        card = build_test_card(idx, item["video_id"], profile="librarian")
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

        new_corpus_rev = compute_file_sha256(corpus_path)
        assert new_corpus_rev != old_corpus_rev

        # Card address must still be valid because read_corpus_head only inspects the first 8 KiB
        res_card = reader.read(card_uri)
        assert res_card["contents"][0]["text"] == library_cards.card_text(card)

        # Corpus address must refuse because corpus_revision binds the whole file
        with pytest.raises(ResourceError) as exc_info:
            reader.read(corpus_uri)
        assert exc_info.value.code == "revision_unavailable"

        # New corpus revision must succeed
        new_corpus_uri = f"{URI_PREFIX}items/{encode_key(item['video_id'])}/corpus/{new_corpus_rev}/0/4096"
        res_new_corpus = reader.read(new_corpus_uri)
        assert res_new_corpus["contents"][0]["text"]

    def test_selection_mismatch_refuses(self, tmp_path: Path):
        """Selection other than library_cards.SELECTION_VERSION refuses revision_unavailable."""
        idx, manifest = seed_standard_library(tmp_path)
        std_item, _ = manifest["standard"]

        reader = LibraryReader(idx, data_root=tmp_path / "data_root")
        card = build_test_card(idx, std_item["video_id"], profile="librarian")

        item_key = encode_key(std_item["video_id"])
        valid_uri = (
            f"{URI_PREFIX}items/{item_key}/cards/{card['source_revision']}/"
            f"{card['selection_version']}/{card['card_hash']}"
        )
        assert reader.read(valid_uri)["contents"][0]["text"] == library_cards.card_text(card)

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
        std_item, _ = manifest["standard"]

        reader = LibraryReader(idx, data_root=tmp_path / "data_root")
        card = build_test_card(idx, std_item["video_id"], profile="librarian")
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
        body = parse_fenced_document(text)
        assert len(body["text"]) <= 2000
        assert len(text.encode("utf-8")) <= LIMITS["max_resource_text_bytes"]
        assert wire_bytes(res) <= LIMITS["max_response_bytes"]

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
        body = parse_fenced_document(content)
        assert body["text"] == "Hello "
        assert body["bytes"]["start"] == 0
        assert body["bytes"]["end"] == 6
        assert body["bytes"]["returned"] == 6
        assert body["boundary_adjusted"] is True
        assert body["has_more"] is True
        assert body["continuation"]["next_uri"].endswith("/6/7")
        assert "\ufffd" not in content

        # Length smaller than next code point (🚀 is 4 bytes; requesting length 2 from byte 6)
        uri_too_small = f"{URI_PREFIX}items/{item_key}/corpus/{rev}/6/2"
        with pytest.raises(ResourceError) as exc:
            reader.read(uri_too_small)
        assert exc.value.code == "invalid_request"

        # Requesting offset 7 (in the middle of a 4-byte code point) must raise invalid_request / invalid_encoding
        uri_bad_offset = f"{URI_PREFIX}items/{item_key}/corpus/{rev}/7/4"
        with pytest.raises(ResourceError) as exc:
            reader.read(uri_bad_offset)
        assert exc.value.code in {"invalid_request", "invalid_encoding"}

        # Offset at EOF returns empty document with has_more=false
        eof_offset = len(corpus_bytes)
        uri_eof = f"{URI_PREFIX}items/{item_key}/corpus/{rev}/{eof_offset}/100"
        res_eof = reader.read(uri_eof)
        body_eof = parse_fenced_document(res_eof["contents"][0]["text"])
        assert body_eof["text"] == ""
        assert body_eof["bytes"]["start"] == eof_offset
        assert body_eof["bytes"]["end"] == eof_offset
        assert body_eof["bytes"]["returned"] == 0
        assert body_eof["bytes"]["total"] == eof_offset
        assert body_eof["complete"] is True
        assert body_eof["has_more"] is False
        assert body_eof["continuation"]["next_uri"] is None

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
        deleted_item, _ = manifest["deleted"]

        reader = LibraryReader(idx, data_root=tmp_path / "data_root")

        # Search must not return the deleted item
        search_res = reader.search("Deleted")
        hit_ids = [h.get("video_id") or h.get("item_id") for h in search_res.get("hits", [])]
        assert deleted_item["video_id"] not in hit_ids

        # Direct read returns resource_deleted
        card = build_test_card(idx, deleted_item["video_id"], profile="librarian")
        uri = (
            f"{URI_PREFIX}items/{encode_key(deleted_item['video_id'])}/cards/"
            f"{card['source_revision']}/{card['selection_version']}/{card['card_hash']}"
        )
        with pytest.raises(ResourceError) as exc:
            reader.read(uri)
        assert exc.value.code == "resource_deleted"
        assert exc.value.retryable is False

    def test_service_deadline_enforcement(self, tmp_path: Path):
        """Execution exceeding 2.0s deadline raises deadline_exceeded (retryable); idle reader accepts next."""
        idx, manifest = seed_standard_library(tmp_path)
        std_item, _ = manifest["standard"]

        clock = MockClock(start_mono=100.0)
        # Configure deadline to 2.0 seconds
        reader = LibraryReader(idx, data_root=tmp_path / "data_root", clock=clock.monotonic, deadline_s=2.0)

        card = build_test_card(idx, std_item["video_id"], profile="librarian")
        uri = (
            f"{URI_PREFIX}items/{encode_key(std_item['video_id'])}/cards/"
            f"{card['source_revision']}/{card['selection_version']}/{card['card_hash']}"
        )

        # Baseline read succeeds initially
        res0 = reader.read(uri)
        assert res0["contents"][0]["text"] == library_cards.card_text(card)

        # Advance mock clock inside a read/lock/serialization operation
        orig_get_yoink = idx.get_yoink
        def slow_get_yoink(vid):
            clock.advance(2.5)
            return orig_get_yoink(vid)

        idx.get_yoink = slow_get_yoink
        try:
            with pytest.raises(ResourceError) as exc:
                reader.read(uri)
            assert exc.value.code == "deadline_exceeded"
            assert exc.value.retryable is True
        finally:
            idx.get_yoink = orig_get_yoink

        # Fresh request after idle must succeed without inheriting expired deadline
        clock.advance(10.0)
        res_fresh = reader.read(uri)
        assert res_fresh["contents"][0]["text"] == library_cards.card_text(card)

    def test_concurrency_guard_rejects_excess_without_queuing(self, tmp_path: Path):
        """Max 2 active read operations; 3rd concurrent operation is rejected immediately."""
        idx, manifest = seed_standard_library(tmp_path)
        std_item, _ = manifest["standard"]

        # Max active set to 2
        reader = LibraryReader(idx, data_root=tmp_path / "data_root", max_active=2)
        card = build_test_card(idx, std_item["video_id"], profile="librarian")
        uri = (
            f"{URI_PREFIX}items/{encode_key(std_item['video_id'])}/cards/"
            f"{card['source_revision']}/{card['selection_version']}/{card['card_hash']}"
        )

        # Two held admissions
        admit1 = reader.guard.admit()
        admit2 = reader.guard.admit()

        # Third admission is immediately refused with rate_limited and reason concurrency
        with pytest.raises(ResourceError) as exc_info:
            reader.read(uri)
        assert exc_info.value.code == "rate_limited"
        assert exc_info.value.retryable is True
        assert exc_info.value.details.get("reason") == "concurrency"
        retry_delay = exc_info.value.details.get("retry_after_ms")
        assert isinstance(retry_delay, int)
        assert 0 < retry_delay <= 2000

        # Release one held admission
        reader.guard.release()

        # Admission now succeeds
        res = reader.read(uri)
        assert res["contents"][0]["text"] == library_cards.card_text(card)

        # Clean up remaining admission
        reader.guard.release()

    def test_rolling_rate_limit_admissions(self, tmp_path: Path):
        """Exceeding 60 admissions per rolling minute raises rate_limited with integer retry_after_ms."""
        idx, manifest = seed_standard_library(tmp_path)
        std_item, _ = manifest["standard"]

        card = build_test_card(idx, std_item["video_id"], profile="librarian")
        uri = (
            f"{URI_PREFIX}items/{encode_key(std_item['video_id'])}/cards/"
            f"{card['source_revision']}/{card['selection_version']}/{card['card_hash']}"
        )

        clock = MockClock(start_mono=1000.0)
        guard = ReadGuard(clock=clock.monotonic, max_active=100, admissions_per_minute=60, window_s=60.0)

        def make_reader():
            return LibraryReader(idx, data_root=tmp_path / "data_root", guard=guard, clock=clock.monotonic)

        # At t0, admit exactly 60 requests
        t0 = clock.monotonic()
        for _ in range(60):
            res = make_reader().read(uri)
            assert res["contents"][0]["text"]

        # Request 61 must return retryable rate_limited, reason rate, retry_after_ms == 60000
        with pytest.raises(ResourceError) as exc_info:
            make_reader().read(uri)
        assert exc_info.value.code == "rate_limited"
        assert exc_info.value.retryable is True
        assert exc_info.value.details["reason"] == "rate"
        assert exc_info.value.details["retry_after_ms"] == 60000

        # Rejected admissions must not add timestamps or extend the window
        assert len(guard._admissions) == 60

        # At t0 + 59.999, still refuse with 1 ms
        clock.advance(59.999)
        with pytest.raises(ResourceError) as exc_info:
            make_reader().read(uri)
        assert exc_info.value.code == "rate_limited"
        assert exc_info.value.details["reason"] == "rate"
        assert exc_info.value.details["retry_after_ms"] == 1
        assert len(guard._admissions) == 60

        # At t0 + 60.0, admit
        clock.advance(0.001)  # now at t0 + 60.0
        res = make_reader().read(uri)
        assert res["contents"][0]["text"]

        # An admitted request that later fails still consumes its admission
        admissions_before = len(guard._admissions)
        bad_uri = f"{URI_PREFIX}items/{encode_key(std_item['video_id'])}/cards/{card['source_revision']}/spread-longest-v1/{card['card_hash']}"
        with pytest.raises(ResourceError) as exc:
            make_reader().read(bad_uri)
        assert exc.value.code == "revision_unavailable"
        assert len(guard._admissions) == admissions_before + 1

        # Staggered timestamps prove rolling expiry rather than a calendar-minute reset
        clock2 = MockClock(start_mono=2000.0)
        guard2 = ReadGuard(clock=clock2.monotonic, max_active=100, admissions_per_minute=60, window_s=60.0)
        def make_reader2():
            return LibraryReader(idx, data_root=tmp_path / "data_root", guard=guard2, clock=clock2.monotonic)

        # 30 requests at t=2000.0
        for _ in range(30):
            make_reader2().read(uri)

        # Advance 20 seconds to t=2020.0, admit 30 more (total 60)
        clock2.advance(20.0)
        for _ in range(30):
            make_reader2().read(uri)

        # 61st request at t=2020.0 refused (window [1960.0, 2020.0] has 60 requests)
        with pytest.raises(ResourceError) as exc:
            make_reader2().read(uri)
        assert exc.value.code == "rate_limited"
        assert exc.value.details["retry_after_ms"] == 40000

        # At t=2060.0 (40s later), first 30 have expired, but second 30 (from 2020.0) are still active
        clock2.advance(40.0)
        # We can admit exactly 30 more, not 60
        for _ in range(30):
            make_reader2().read(uri)
        # The 31st (61st in rolling window) must be refused
        with pytest.raises(ResourceError) as exc:
            make_reader2().read(uri)
        assert exc.value.code == "rate_limited"
        assert exc.value.details["retry_after_ms"] == 20000

    def test_search_hit_outside_selected_six_excerpts(self, tmp_path: Path):
        """Search hit identifies clip outside the Librarian card's 6 excerpts; resolves canonical identity."""
        idx, manifest = seed_standard_library(tmp_path)
        std_item, clips_std = manifest["standard"]

        reader = LibraryReader(idx, data_root=tmp_path / "data_root")
        card = build_test_card(idx, std_item["video_id"], profile="librarian")
        card_excerpt_ids = {e["excerpt_id"] for e in card["excerpts"]}
        assert len(card_excerpt_ids) <= 6

        # Search for clip 7 (outside the card's 6 excerpts)
        res_search = reader.search("Timed evidence point 7")
        assert len(res_search.get("hits", [])) > 0
        hit = res_search["hits"][0]
        assert hit["excerpt_id"] not in card_excerpt_ids

        # Resolve excerpt via reader
        excerpt_uri = hit["uris"]["excerpt"]
        res_excerpt = reader.read(excerpt_uri)
        assert "contents" in res_excerpt
        text = res_excerpt["contents"][0]["text"]
        body = parse_fenced_document(text)
        assert body["identity"]["excerpt_id"] == hit["excerpt_id"]
        assert body["text"] == clips_std[7]["text"]
        assert len(body["text"]) <= LIMITS["max_excerpt_codepoints"]
        assert len(text.encode("utf-8")) <= LIMITS["max_resource_text_bytes"]
        assert wire_bytes(res_excerpt) <= LIMITS["max_response_bytes"]

    def test_shelf_revision_binding_and_mutations(self, tmp_path: Path):
        """Shelf revision binds all members; clip, opening-prose, off-page edits and deletions invalidate old URI."""
        idx = make_disposable_index(tmp_path)
        reader = LibraryReader(idx, data_root=tmp_path / "data_root")

        # 1. Standard video with timed clips
        clips1 = [{"seq": 0, "start": 0.0, "end": 10.0, "text": "Clip 1 content"}]
        item1 = seed_yoink_item(idx, tmp_path, video_id="shelf-vid-01", slug="shelf-vid-01", title="Shelf Vid 1",
                                clips=clips1, corpus_text="Corpus 1")

        # 2. Prose item with opening prose
        item2 = seed_yoink_item(idx, tmp_path, video_id="shelf-prose-02", slug="shelf-prose-02", title="Shelf Prose 2",
                                clips=[], corpus_text="Opening prose for item 2.\n")

        # 3. Third item for off-page testing
        item3 = seed_yoink_item(idx, tmp_path, video_id="shelf-item-03", slug="shelf-item-03", title="Shelf Item 3",
                                clips=[], corpus_text="Corpus 3")

        # 4. Fourth item for deletion testing
        item4 = seed_yoink_item(idx, tmp_path, video_id="shelf-del-04", slug="shelf-del-04", title="Shelf Del 4",
                                clips=[], corpus_text="Corpus 4")

        # 5. Fifth item for tail-only edit testing
        prefix5 = "T" * 8192
        tail5 = "U" * 10240
        item5 = seed_yoink_item(idx, tmp_path, video_id="shelf-tail-05", slug="shelf-tail-05", title="Shelf Tail 5",
                                clips=[], corpus_text=prefix5 + tail5)

        member_ids = ["shelf-vid-01", "shelf-prose-02", "shelf-item-03", "shelf-del-04", "shelf-tail-05"]
        shelf_info = seed_shelf(idx, shelf_id="s-main", member_video_ids=member_ids)

        # Obtain shelf snapshot and URI
        with reader._operation() as op:
            snap = reader._shelf_snapshot(op, "s-main")
        shelf_rev_orig = snap["shelf_revision"]
        page_uri = shelf_uri("s-main", shelf_info["taxonomy_revision"], shelf_info["projection_revision"],
                             shelf_rev_orig, 0)

        # Baseline: initial read must succeed
        res = reader.read(page_uri)
        assert res["contents"][0]["text"]

        # Unchanged rebuild must retain identical address
        with reader._operation() as op:
            snap_rebuild = reader._shelf_snapshot(op, "s-main")
        assert snap_rebuild["shelf_revision"] == shelf_rev_orig

        # Tail-only edit on item5 outside card's bounded source inputs changes corpus binding, NOT shelf binding
        Path(item5["corpus_path"]).write_text(prefix5 + ("V" * 10240), encoding="utf-8")
        res_after_tail = reader.read(page_uri)
        assert res_after_tail["contents"][0]["text"]

        # 1. Clip-only edit on item1 with unchanged projection revision: old page URI must refuse
        mutated_clips = [{"kind": "transcript_chunk", "seq": 0, "timestamp_start": 0.0, "timestamp_end": 10.0,
                          "text": "Mutated clip text", "source_deep_link": "https://example.com"}]
        idx.insert_citations(item1["video_id"], mutated_clips)
        idx.rebuild_clips()
        with pytest.raises(ResourceError) as exc_info:
            reader.read(page_uri)
        assert exc_info.value.code == "revision_unavailable"

        # Update shelf baseline after clip-only edit
        with reader._operation() as op:
            snap2 = reader._shelf_snapshot(op, "s-main")
        page_uri2 = shelf_uri("s-main", shelf_info["taxonomy_revision"], shelf_info["projection_revision"],
                              snap2["shelf_revision"], 0)
        assert reader.read(page_uri2)["contents"][0]["text"]

        # 2. Opening-prose edit on item2 with unchanged projection revision: old page URI must refuse
        Path(item2["corpus_path"]).write_text("Completely altered opening prose for item 2.\n", encoding="utf-8")
        with pytest.raises(ResourceError) as exc_info:
            reader.read(page_uri2)
        assert exc_info.value.code == "revision_unavailable"

        # Update shelf baseline after opening-prose edit
        with reader._operation() as op:
            snap3 = reader._shelf_snapshot(op, "s-main")
        page_uri3 = shelf_uri("s-main", shelf_info["taxonomy_revision"], shelf_info["projection_revision"],
                              snap3["shelf_revision"], 0)
        assert reader.read(page_uri3)["contents"][0]["text"]

        # 3. Off-page edit: item3 edit affects page 0 when page size is small or offset is used
        # Note: D2 states all ordered nondeleted members are bound into shelf_revision, including outside requested page
        Path(item3["corpus_path"]).write_text("Edited corpus for item 3.\n", encoding="utf-8")
        with pytest.raises(ResourceError) as exc_info:
            reader.read(page_uri3)
        assert exc_info.value.code == "revision_unavailable"

        # Update shelf baseline after off-page edit
        with reader._operation() as op:
            snap4 = reader._shelf_snapshot(op, "s-main")
        page_uri4 = shelf_uri("s-main", shelf_info["taxonomy_revision"], shelf_info["projection_revision"],
                              snap4["shelf_revision"], 0)
        assert reader.read(page_uri4)["contents"][0]["text"]

        # 4. Deletion with unchanged projection revision: old page URI must refuse
        with idx._lock:
            idx._conn.execute("UPDATE yoinks SET deleted_at = '2026-09-08T00:00:00Z' WHERE video_id = ?",
                              (item4["video_id"],))
            idx._conn.commit()
        with pytest.raises(ResourceError) as exc_info:
            reader.read(page_uri4)
        assert exc_info.value.code == "revision_unavailable"
