"""Operator statements and unreviewed images are not playback acceptance."""
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/install_receipt"))
import p4_collect_evidence as collector
from p4_common import OPTIONAL_PLAYER_JUMP, PROTECTED_SENTINEL_BYTES


@pytest.fixture
def receipt(tmp_path, monkeypatch):
    profile = tmp_path / "profile"
    (profile / "records").mkdir(parents=True)
    (profile / "client").mkdir()
    (profile / "client/protected-sentinel.bin").write_bytes(PROTECTED_SENTINEL_BYTES)
    expected = {"items": {}, "chapter": {"title": "Synthetic chapter", "start": 34.0},
                "brief": {}, "protected_sentinel": {"path": str(profile / "client/protected-sentinel.bin")}}
    (profile / "expected.json").write_text(json.dumps(expected), encoding="utf8")
    (profile / "preparation.json").write_text(json.dumps({"product_findings": []}), encoding="utf8")
    monkeypatch.setattr(collector, "execute_checks", lambda binding: {"checkpoints": [], "product_findings": []})
    binding = {"isolated_profile": str(profile), "isolated_port": 18081,
               "instrument_only": True, "installed_credit": False}
    return profile, binding


def checkpoint(binding, operator, name):
    result = collector.collect(binding, operator)
    return next(row for row in result["checkpoints"] if row["name"] == name)


def test_matching_chapter_fields_without_an_image_remain_unobserved(receipt):
    profile, binding = receipt
    row = checkpoint(binding, {"chapter": {"title": "Synthetic chapter", "start": 34.0}}, "jump_chapter_fixture")
    assert row["status"] == "unobserved"


def test_player_boolean_and_url_without_an_image_remain_unobserved(receipt):
    profile, binding = receipt
    row = checkpoint(binding, {"optional_player_jump": {"observed": True, "url": OPTIONAL_PLAYER_JUMP["url"]}}, "optional_player_jump")
    assert row["status"] == "unobserved"


def test_unreviewed_image_file_does_not_prove_displayed_player_time(receipt):
    profile, binding = receipt
    image = profile / "not-a-player.png"
    image.write_bytes(b"This file contains no verified player observation.")
    row = checkpoint(binding, {"chapter": {"title": "Synthetic chapter", "start": 34.0,
                                           "screenshot": str(image)}}, "jump_chapter_fixture")
    assert row["status"] != "passed"
