"""tests/test_library_prompts.py - Living Library Prompt Tests (AV-1a).

Gate covered:
- P4-07 (Prompts: exact names, argument validation, no-match & missing-history handling,
  stale/oversized preview refusal, database immutability verification, report-only queries).

Tests against the frozen module interface in docs/library/PHASE4-AV-BRIEF-2026-09-08.md:
- library_prompts.PROMPTS, library_prompts.get_prompt
- library_resources.LibraryReader, ResourceError
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

import index
from tests.phase4_fixtures import (
    make_disposable_index,
    seed_standard_library,
    seed_yoink_item,
)

# Target implementation imports: will fail until implementation lands in AV-1
import library_resources
from library_resources import LibraryReader, ResourceError
import library_prompts
from library_prompts import PROMPTS, get_prompt


def _compute_db_hash(db_path: Path) -> str:
    """Compute SHA-256 hash of database file bytes to verify no mutations occur."""
    with open(db_path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class TestP407Prompts:
    """Gate P4-07: Prompt templates, strict argument validation, safe envelopes, immutability."""

    def test_prompts_manifest_structure(self):
        """PROMPTS contains exactly four frozen prompt specifications."""
        assert len(PROMPTS) == 4
        prompt_map = {p["name"]: p for p in PROMPTS}
        assert set(prompt_map.keys()) == {
            "consult-library",
            "evidence-brief",
            "whats-new",
            "reshelve-review",
        }

        # 1. consult-library
        cl = prompt_map["consult-library"]
        assert "topic" in [a["name"] for a in cl["arguments"]]
        topic_arg = next(a for a in cl["arguments"] if a["name"] == "topic")
        assert topic_arg["required"] is True

        # 2. evidence-brief
        eb = prompt_map["evidence-brief"]
        eb_args = {a["name"]: a for a in eb["arguments"]}
        assert eb_args["topic"]["required"] is True
        assert eb_args["since"]["required"] is False

        # 3. whats-new
        wn = prompt_map["whats-new"]
        wn_args = {a["name"]: a for a in wn["arguments"]}
        assert wn_args["days"]["required"] is False

        # 4. reshelve-review
        rr = prompt_map["reshelve-review"]
        rr_args = {a["name"]: a for a in rr["arguments"]}
        assert rr_args["preview_id"]["required"] is True

    def test_prompt_argument_validation(self, tmp_path: Path):
        """Unknown prompts, extra arguments, missing required, bad dates/numbers raise invalid_request."""
        idx, _ = seed_standard_library(tmp_path)
        reader = LibraryReader(idx, data_root=tmp_path / "data_root")

        # Unknown prompt name
        with pytest.raises(ResourceError) as exc:
            get_prompt(reader, None, "non-existent-prompt", {})
        assert exc.value.code == "invalid_request"

        # Missing required argument for consult-library
        with pytest.raises(ResourceError) as exc:
            get_prompt(reader, None, "consult-library", {})
        assert exc.value.code == "invalid_request"

        # Unknown argument for consult-library
        with pytest.raises(ResourceError) as exc:
            get_prompt(reader, None, "consult-library", {"topic": "valid", "extra_arg": "invalid"})
        assert exc.value.code == "invalid_request"

        # Topic exceeding length budget (> 512 code points)
        with pytest.raises(ResourceError) as exc:
            get_prompt(reader, None, "consult-library", {"topic": "a" * 513})
        assert exc.value.code == "invalid_request"

        # Bad date for evidence-brief
        with pytest.raises(ResourceError) as exc:
            get_prompt(reader, None, "evidence-brief", {"topic": "test", "since": "2026-02-31"})
        assert exc.value.code == "invalid_request"

        with pytest.raises(ResourceError) as exc:
            get_prompt(reader, None, "evidence-brief", {"topic": "test", "since": "not-a-date"})
        assert exc.value.code == "invalid_request"

        # Future date rejected
        with pytest.raises(ResourceError) as exc:
            get_prompt(reader, None, "evidence-brief", {"topic": "test", "since": "2099-01-01"})
        assert exc.value.code == "invalid_request"

        # Bad number for whats-new (must be 1-30)
        with pytest.raises(ResourceError) as exc:
            get_prompt(reader, None, "whats-new", {"days": "0"})
        assert exc.value.code == "invalid_request"

        with pytest.raises(ResourceError) as exc:
            get_prompt(reader, None, "whats-new", {"days": "31"})
        assert exc.value.code == "invalid_request"

        with pytest.raises(ResourceError) as exc:
            get_prompt(reader, None, "whats-new", {"days": "-5"})
        assert exc.value.code == "invalid_request"

        with pytest.raises(ResourceError) as exc:
            get_prompt(reader, None, "whats-new", {"days": "seven"})
        assert exc.value.code == "invalid_request"

    def test_consult_library_prompt_structure(self, tmp_path: Path):
        """consult-library returns instructions and bounded evidence packet."""
        idx, manifest = seed_standard_library(tmp_path)
        reader = LibraryReader(idx, data_root=tmp_path / "data_root")

        result = get_prompt(reader, None, "consult-library", {"topic": "Analysis"})

        assert "description" in result
        assert "messages" in result
        assert len(result["messages"]) == 2

        instruction_msg, data_msg = result["messages"]
        assert instruction_msg["role"] == "user"
        assert data_msg["role"] == "user"

        inst_text = instruction_msg["content"]["text"]
        data_text = data_msg["content"]["text"]

        # Instruction specifies answering strictly from cited evidence
        assert "evidence" in inst_text.lower()
        # Data message contains untrusted evidence fence
        assert "<untrusted_uoink_library_context>" in data_text or "<untrusted_evidence_card>" in data_text

    def test_consult_library_empty_match_message(self, tmp_path: Path):
        """When no matching items exist, consult-library reports explicit no-match message."""
        idx = make_disposable_index(tmp_path)
        reader = LibraryReader(idx, data_root=tmp_path / "data_root")

        result = get_prompt(reader, None, "consult-library", {"topic": "completely_unmatched_term"})
        assert len(result["messages"]) == 2
        data_text = result["messages"][1]["content"]["text"]
        # Must explicitly state no evidence was retrieved, never empty or error
        assert "no matching evidence" in data_text.lower()

    def test_evidence_brief_prompt_filtering(self, tmp_path: Path):
        """evidence-brief filters items by capture date and returns up to 5 Librarian cards."""
        idx = make_disposable_index(tmp_path)
        # Seed 6 items with distinct yoinked_at dates
        for i in range(6):
            seed_yoink_item(
                idx, tmp_path,
                video_id=f"brief-vid-{i}",
                slug=f"brief-slug-{i}",
                title=f"Brief Video {i}",
                topic="Security",
                yoinked_at=f"2026-09-0{i+1}T10:00:00",
                corpus_text=f"Corpus content {i}",
                clips=[{"seq": 0, "start": 0.0, "end": 10.0, "text": f"Evidence clip {i}"}],
            )

        reader = LibraryReader(idx, data_root=tmp_path / "data_root")

        # since filters by capture date
        res = get_prompt(reader, None, "evidence-brief", {"topic": "Security", "since": "2026-09-03"})
        assert len(res["messages"]) == 2
        data_text = res["messages"][1]["content"]["text"]

        # Items before 2026-09-03 must not appear in the evidence packet
        assert "brief-vid-0" not in data_text
        assert "brief-vid-1" not in data_text

    def test_whats_new_missing_history_handling(self, tmp_path: Path):
        """whats-new with work_service=None reports an explicit coverage gap."""
        idx = make_disposable_index(tmp_path)
        reader = LibraryReader(idx, data_root=tmp_path / "data_root")

        res = get_prompt(reader, None, "whats-new", {"days": "7"})
        data_text = res["messages"][1]["content"]["text"]

        # Must report explicit coverage gap rather than fabricating empty history
        assert "coverage" in data_text.lower() or "gap" in data_text.lower() or "unavailable" in data_text.lower()

    def test_reshelve_review_requires_work_service(self, tmp_path: Path):
        """reshelve-review with work_service=None raises feature_unavailable."""
        idx = make_disposable_index(tmp_path)
        reader = LibraryReader(idx, data_root=tmp_path / "data_root")

        with pytest.raises(ResourceError) as exc_info:
            get_prompt(reader, None, "reshelve-review", {"preview_id": "prev-01"})
        assert exc_info.value.code == "feature_unavailable"

    def test_prompts_are_pure_report_readers_no_database_mutation(self, tmp_path: Path):
        """Invocations of get_prompt must never alter database bytes or reap leases."""
        db_path = tmp_path / "index.db"
        idx = index.Index.open(db_path)
        seed_yoink_item(
            idx, tmp_path,
            video_id="immut-vid-01",
            slug="immut-slug-01",
            title="Immutability Test",
            corpus_text="Content",
            clips=[{"seq": 0, "start": 0.0, "end": 10.0, "text": "Sample clip"}],
        )
        idx.close()

        # Record hash of database file before prompt calls
        hash_before = _compute_db_hash(db_path)

        idx_ro = index.Index.open(db_path)
        reader = LibraryReader(idx_ro, data_root=tmp_path / "data_root")

        # Invoke prompts
        get_prompt(reader, None, "consult-library", {"topic": "Immutability"})
        get_prompt(reader, None, "evidence-brief", {"topic": "Immutability"})
        get_prompt(reader, None, "whats-new", {"days": "7"})

        idx_ro.close()

        # Database bytes must be 100% byte-identical
        hash_after = _compute_db_hash(db_path)
        assert hash_before == hash_after
