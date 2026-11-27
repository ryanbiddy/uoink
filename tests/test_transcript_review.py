"""Offline signal, storage and publication regressions for transcript review."""
import json
from pathlib import Path

import pytest


@pytest.fixture
def segments():
    return json.loads((Path(__file__).parent / "fixtures" / "quiet_transcript.json").read_text("utf-8"))


def test_only_supported_lines_are_held(segments):
    import transcript_review as review
    kept, held = review.partition(segments, whisper=True, duration=60)
    assert [row["text"] for row in kept] == [
        "Bonjour à toutes et à tous.", "Thanks for watching!", "La discussion continue."]
    assert [row["line"] for row in held] == [3, 4, 5, 6, 7, 8, 9, 11]
    assert [row["reason"] for row in held] == [
        "repetition", "repetition", "repetition", "non_speech", "non_speech",
        "non_speech", "non_speech", "outro"]
    assert review.all_rows(kept, held) == segments


def test_two_signals_and_clear_speech_veto():
    import transcript_review as r
    def why(text="Thanks for watching!", **scores):
        return r.reasons([dict(text=text, end=10, **scores)], whisper=True, duration=10)[0]
    assert why(no_speech_prob=.04, avg_logprob=-.1) is None
    assert why(no_speech_prob=.35, avg_logprob=-.2) is None
    assert why("An ordinary sentence.", no_speech_prob=.7) is None
    assert why("An ordinary sentence.", avg_logprob=-1.2) is None
    assert why("An ordinary sentence.", no_speech_prob=.7, avg_logprob=-1.2) == "low_confidence"
    assert why("Sottotitoli creati dalla comunità Amara.org.") == "outro"
    assert why("ご視聴ありがとうございました。", no_speech_prob=.02) is None
    assert why("We discussed the phrase thanks for watching.") is None
    assert why("The [Music] label appears here.") is None
    assert why("(je suis ici)") is None


def test_caption_cache_all_held_never_falls_through(tmp_path, monkeypatch):
    import server
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(server, "_library_transcript", lambda _: None)
    record = {"video_id": "abcde123456", "version": server._TRANSCRIPT_CACHE_VERSION,
              "segments": [(0., 1., "[Music]")], "source": "captions"}
    server._review_transcript_record(record)
    server._write_transcript_cache(record, None)
    assert server.get_transcript_cascade(record["video_id"])["segments"] == []
    raw = server.get_transcript_cascade(record["video_id"], include_held=True)
    assert raw["segments"] == [(0., 1., "[Music]")] and raw["cached"]


@pytest.mark.parametrize("interrupt", [False, True])
def test_old_save_review_and_restore_updates_search_and_citations(
        segments, tmp_path, monkeypatch, interrupt):
    import server
    import transcript_review as review
    import timed_cues
    import uoink_mcp_tools as tools
    from tests.test_transcript_backfill import Library
    lib = Library(tmp_path, monkeypatch)
    vid = "abcde123456"
    url = "https://www.youtube.com/watch?v=" + vid
    folder = lib.add_video("quiet-talk", url=url, video_id=vid, title="A talk", duration=60,
                           saved_at="2026-01-01", words=[(r["start"], r["end"], r["text"]) for r in segments])
    path = folder / "quiet-talk.json"
    doc = folder / "quiet-talk.md"
    side = json.loads(path.read_text("utf-8"))
    side.update(transcript=segments, transcript_source="asr")
    path.write_text(json.dumps(side), "utf-8")
    before = lib.snapshot(folder)
    monkeypatch.setattr(tools, "_backend", server)
    try:
        assert review.tidy(server)["changed"] == 8
        assert lib.snapshot(folder) == before
        assert lib.idx.search("applause")
        if interrupt:
            with monkeypatch.context() as m:
                def stopped(*args, **kwargs):
                    raise OSError("fixture interruption")
                m.setattr(server, "_index_yoink", stopped)
                assert not review.tidy(server, apply=True)["ok"]
        result = review.tidy(server, apply=True)
        assert result["ok"], result
        assert "[Applause]" not in doc.read_text("utf-8")
        assert not lib.idx.search("applause") and not lib.idx.search("repeat")
        assert lib.idx.search("discussion")
        assert [r["text"] for r in lib.idx.get_citations(vid) if r["kind"] == "transcript_chunk"] == [
            segments[i]["text"] for i in (0, 1, 9)]
        clean = tools.get_transcript({"url": url, "include_timestamps": True})
        assert len(clean["segments"]) == 3 and clean["held_count"] == 8
        raw = tools.get_transcript({"url": url, "include_held": True, "include_timestamps": True})
        assert [r["text"] for r in raw["segments"]] == [r["text"] for r in segments]
        assert raw["segments"][-1]["held_line"] == 11 and raw["segments"][-1]["held_reason"] == "outro"
        assert "held_line" not in raw["segments"][1]
        assert "[held line 11] Thanks for watching!" in raw["transcript"]
        export = timed_cues.get_item(lib.idx, vid, {"include_held": ["1"]})
        assert len(export["cues"]) == 11 and export["held_count"] == 8
        assert export["cues"][6]["held_line"] == 7
        assert len(timed_cues.get_item(lib.idx, vid)["cues"]) == 3
        assert "[Applause]" not in tools.get_uoink_corpus({"slug": folder.name})["corpus_md"]
        raw_md = tools.get_uoink_corpus({"slug": folder.name, "include_held": True})
        assert "[Applause]" in raw_md["corpus_md"].split("## Held transcript lines")[1]
        assert review.tidy(server, restore=(vid, 7))["ok"]
        assert lib.idx.search("applause") and not lib.idx.search("repeat")
        assert review.tidy(server, apply=True)["changed"] == 0
        assert "[Applause]" in tools.get_transcript({"url": url})["transcript"]
    finally:
        lib.idx.close()


def test_child_frame_round_trip_and_scoreless_legacy(segments, tmp_path):
    import uoink_reliability as rel
    import transcript_review as review
    audio = tmp_path / "fixture"
    audio.touch()
    rows = rel.transcribe_media(audio, _transcribe=lambda _: segments, duration_seconds=60)
    wire = json.loads(json.dumps([rel.entry_to_json(row) for row in rows]))
    restored = [rel.entry_from_json(row) for row in wire]
    assert restored[1].scores == {"no_speech_prob": .02, "avg_logprob": -.16}
    assert restored[-1].held_reason == "outro"
    assert restored[2].held_reason == "repetition"
    no_scores = [{k: row[k] for k in ("start", "end", "text")} for row in segments]
    _, held = review.partition(no_scores, whisper=True, duration=60)
    assert [h["line"] for h in held] == [6, 7, 8, 9, 11]
    _, captions = review.partition(segments, whisper=False, duration=60)
    assert [h["line"] for h in captions] == [6, 7, 8, 9]


def test_new_backfill_excludes_held_lines_at_publication(segments, tmp_path, monkeypatch):
    from tests.test_transcript_backfill import Library
    import server
    import uoink_reliability as rel
    lib = Library(tmp_path, monkeypatch)
    vid = "abcde123456"
    url = "https://www.youtube.com/watch?v=" + vid
    folder = lib.add_video("new-talk", video_id=vid, url=url, title="New talk",
                           duration=60, saved_at="2026-01-01")
    path, corpus = folder / "new-talk.json", folder / "new-talk.md"
    rows = rel._transcript_entries_from_segments(segments)
    try:
        assert server._transcript_backfill_apply(
            {"folder": folder, "sidecar_path": path, "corpus_path": corpus, "url": url},
            rows, "asr", {"status": "completed", "model": "base"}) == "applied"
        side = json.loads(path.read_text("utf-8"))
        assert len(side["transcript"]) == 3 and len(side["held_transcript_lines"]) == 8
        assert side["transcript"][1]["no_speech_prob"] == .02
        assert not lib.idx.search("repeat")
        for export in (corpus, folder / "transcript.txt"):
            assert "[Music]" not in export.read_text("utf-8")
        handler = server.Handler.__new__(server.Handler)
        handler._send_json = lambda status, data: data["details"]
        route = f"/yoinks/{vid}/details"
        data = handler._handle_yoink_details(route)
        assert "4 lines" in data["review_note"] and "4 non-speech labels" in data["review_note"]
        assert "held_transcript_lines" not in data
        handler.path = route + "?include_held=1"
        assert handler._handle_yoink_details(route)["held_transcript_lines"][0]["line"] == 3
    finally:
        lib.idx.close()


def test_podcast_review_preserves_speaker_and_restored_line(tmp_path, monkeypatch):
    from tests.test_podcast_corpus_bridge import _seed_episode
    import library_media
    import podcasts
    import server
    import transcript_review as review
    idx, episode_id, _, _ = _seed_episode(tmp_path)
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
    producer = tmp_path / "Podcasts" / "fixture" / "episode.transcript.json"
    producer.parent.mkdir(parents=True)
    raw = json.loads((tmp_path / "episode.transcript.json").read_text("utf-8"))
    raw["segments"].insert(1, {"start": 7., "end": 8., "text": "[Applause]"})
    producer.write_text(json.dumps(raw), "utf-8")
    with idx.write_transaction() as db:
        db.execute("UPDATE podcast_episodes SET transcript_local_path=? WHERE id=?",
                   (str(producer), episode_id))
    try:
        record = podcasts.episode_to_corpus(idx, episode_id, data_root=tmp_path)
        vid = record["video_id"]
        assert idx.search("applause")
        result = review.tidy(server, apply=True)
        assert result["ok"] and result["changed"] == 1, result
        assert not idx.search("applause")
        handler = server.Handler.__new__(server.Handler)
        handler._send_json = lambda status, data: (status, data)
        status, details = handler._handle_yoink_details(f"/yoinks/{vid}/details")
        assert status == 200 and "1 non-speech label" in details["details"]["review_note"]
        cited = library_media.export_cited_range(idx._conn, {"video_id": vid, "start": 64.2, "end": 70})
        assert cited["ok"], cited
        assert idx.get_citations(vid)[-1]["speaker"] == "GUEST"
        assert review.tidy(server, restore=(vid, 2))["ok"]
        podcasts.episode_to_corpus(idx, episode_id, data_root=tmp_path)
        assert idx.search("applause") and review.tidy(server, apply=True)["changed"] == 0
    finally:
        idx.close()


def test_large_library_cli_resumes_from_checkpoint(tmp_path, monkeypatch, capsys):
    import server
    import transcript_review as review
    import uoink_cli as cli
    from tests.test_transcript_backfill import Library
    lib = Library(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, "backend", lambda: server)
    calls = []
    original = review._item_review
    def stop_once(server, item, restore, write):
        calls.append(item["video_id"])
        if len(calls) == 67:
            raise KeyboardInterrupt
        return original(server, item, restore, write)
    monkeypatch.setattr(review, "_item_review", stop_once)
    try:
        # Each lightweight text save has no transcript. The final video has
        # only a scoreless outro, distinguishable by its real duration.
        with lib.idx.write_transaction() as db:
            db.executemany("INSERT INTO yoinks(video_id,slug,yoinked_at,corpus_path,sidecar_path) "
                           "VALUES(?,?,?,'','')", [(f"a{i:04}", f"s{i}", "2026-01-01") for i in range(1000)])
        vid = "zbcde123456"
        folder = lib.add_video("old-talk", url="https://www.youtube.com/watch?v=" + vid, video_id=vid,
                               title="Old talk", duration=60, saved_at="2026-01-01",
                               words=[(58., 60., "Thanks for watching!")])
        path = folder / "old-talk.json"
        side = json.loads(path.read_text("utf-8"))
        side["transcript_source"] = "asr"
        path.write_text(json.dumps(side), "utf-8")
        assert cli.main(["tidy-transcripts", "--dry-run"]) != 0
        assert "resume" in json.loads(capsys.readouterr().out)["error"]
        def resumed(server, item, restore, write):
            if not write:
                assert item["video_id"] >= "a0066"
            return original(server, item, restore, write)
        monkeypatch.setattr(review, "_item_review", resumed)
        assert cli.main(["tidy-transcripts", "--dry-run"]) == 0
        assert json.loads(capsys.readouterr().out)["changed"] == 1
        assert cli.main(["tidy-transcripts", "--apply"]) == 0
        assert json.loads(capsys.readouterr().out)["held_count"] == 1
        assert cli.main(["cues", vid, "--include-held"]) == 0
        assert json.loads(capsys.readouterr().out)["data"]["cues"][0]["held_line"] == 1
        assert cli.main(["tidy-transcripts", "--restore", vid, "1"]) == 0
        assert lib.idx.search("watching")
    finally:
        lib.idx.close()
