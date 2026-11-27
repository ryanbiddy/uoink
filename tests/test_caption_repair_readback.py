"""A settled retry must still agree with the files the library exposes."""
import json

import pytest

import library_media
import server
from tests.test_caption_repair import VID, library as repaired_library


@pytest.mark.parametrize("changed", ["plain", "corpus", "missing archive", "changed archive"])
def test_report_conflicts_after_a_completed_repair(repaired_library, changed):
    _, save = repaired_library
    side, corpus, plain = save()
    original_plain, original_corpus = plain.read_bytes(), corpus.read_bytes()
    server.repair_rolling_captions(VID, dry_run=False)
    plan = server._capture_media_plan(json.loads(side.read_bytes()), side.parent)
    archive = side.parent / library_media.MEDIA_INPUTS_DIR / (plan["digest"] + ".json")
    if changed == "plain":
        plain.write_bytes(original_plain)
    elif changed == "corpus":
        corpus.write_bytes(original_corpus)
    elif changed == "missing archive":
        archive.unlink()
    else:
        archive.write_text("{}", encoding="utf-8")
    paths = [side, corpus, plain, archive]
    before = [p.read_bytes() if p.exists() else None for p in paths]
    for dry_run in (True, False):
        with pytest.raises(ValueError, match="changed|could not finish"):
            server.repair_rolling_captions(VID, dry_run=dry_run)
    assert [p.read_bytes() if p.exists() else None for p in paths] == before
