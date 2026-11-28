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


@pytest.mark.parametrize("whisper", [False, True])
def test_note_wrapped_lyrics_survive_review(whisper):
    import transcript_review as review
    lyrics = ["♪ The last light finds the river ♪", "♫ Le jour se lève ♫",
              "♪ Thank you ♪", "♪ 風が吹く ♪"]
    labels = ["♪", "♫ … ♫", "♪ ... ♪", "♪ [Applause] ♪", "♫ instrumental ♫"]
    rows = [dict(text=text, no_speech_prob=.91, avg_logprob=-1.4) for text in lyrics + labels]
    kept, held = review.partition(rows, whisper=whisper)
    assert [r["text"] for r in kept] == lyrics
    assert [h["segment"]["text"] for h in held] == labels
    assert review.all_rows(kept, held) == rows


@pytest.mark.parametrize("text", ["Thanks for watching!", "Thank you."])
def test_confident_phrase_stays_even_at_the_end(text):
    import transcript_review as review
    row = dict(text=text, end=10, no_speech_prob=.45, avg_logprob=-.2)
    assert review.reasons([row], whisper=True, duration=10) == [None]


@pytest.mark.parametrize("ratio,logprob", [(1.5, -.3), (3.1, -.3), (1.5, -.8)])
def test_repetition_requires_compression_and_respects_confidence(ratio, logprob):
    import transcript_review as review
    rows = [dict(text=text, no_speech_prob=.65, avg_logprob=logprob, compression_ratio=ratio)
            for text in ["Yes."] * 3 + ["Count me in. " * 4]]
    assert review.reasons(rows, whisper=True) == [None] * 4


@pytest.fixture
def library(tmp_path, monkeypatch):
    from tests.test_transcript_backfill import Library
    lib = Library(tmp_path, monkeypatch)
    try:
        yield lib
    finally:
        lib.idx.close()


def add_talk(lib, words, vid="abcde123456"):
    folder = lib.add_video(vid, video_id=vid, url="https://www.youtube.com/watch?v=" + vid,
                           title="Talk", duration=10, saved_at="2026-01-01", words=words, media=True)
    return folder / (vid + ".json")


def test_tidy_releases_previously_held_lyric_to_search_and_citations(library, monkeypatch):
    import server
    import transcript_review as review
    lyric = "♪ I saw the river rising ♪"
    path = add_talk(library, [(0, 2, lyric), (3, 4, "[Music]")])
    with monkeypatch.context() as m:
        m.setattr(review, "reasons", lambda rows, **kw: ["non_speech"] * len(rows))
        assert review.tidy(server, apply=True)["held_count"] == 2
    assert not library.idx.search("river")
    assert review.tidy(server)["held_count"] == 1
    assert not library.idx.search("river")
    assert review.tidy(server, apply=True)["changed"] == 1
    assert library.idx.search("river")
    side = json.loads(path.read_bytes())
    assert [r["text"] for r in side["transcript"]] == [lyric]
    assert [r["line"] for r in side["held_transcript_lines"]] == [2]
    assert [c["text"] for c in library.idx.get_citations(path.stem) if c["kind"] == "transcript_chunk"] == [lyric]


def test_scoreless_thank_you_stays_and_cli_explains_fallback(library, monkeypatch, capsys):
    import server
    import uoink_cli as cli
    path = add_talk(library, [(8, 10, "Thank you.")])
    side = json.loads(path.read_bytes())
    side["transcript_source"] = "asr"
    path.write_text(json.dumps(side), "utf-8")
    monkeypatch.setattr(cli, "backend", lambda: server)
    for mode in ("--dry-run", "--apply"):
        assert cli.main(["tidy-transcripts", mode]) == 0
        result = json.loads(capsys.readouterr().out)
        assert result["held_count"] == 0
        summary = result["review_summary"].lower()
        assert all(word in summary for word in ("scores", "phrase", "end"))
    assert json.loads(path.read_bytes())["transcript"] == side["transcript"]


def test_library_blank_cues_preserve_held_line_numbers(library, monkeypatch):
    import server
    import transcript_review as review
    import uoink_mcp_tools as tools
    vid = "abcde123456"
    path = add_talk(library, [(0, 1, " "), (1, 2, "[Music]"), (2, 3, "Hello"),
                              (3, 4, ""), (4, 5, "[Applause]")], vid)
    side = json.loads(path.read_bytes())
    side.update(review.reviewed_fields(side["transcript"], whisper=False))
    path.write_text(json.dumps(side), "utf-8")
    monkeypatch.setattr(tools, "_backend", server)
    args = {"url": vid, "include_timestamps": True}
    assert [r["text"] for r in tools.get_transcript(args)["segments"]] == ["Hello"]
    rows = tools.get_transcript(dict(args, include_held=True))["segments"]
    assert [(r["text"], r.get("held_line")) for r in rows] == [
        ("[Music]", 2), ("Hello", None), ("[Applause]", 5)]


def test_corpus_returns_valid_held_rows_with_a_damaged_timestamp(library, monkeypatch):
    import server
    import uoink_mcp_tools as tools
    path = add_talk(library, [(0, 1, "Kept words")])
    side = json.loads(path.read_bytes())
    bad = [{"text": "Missing"}, {"start": "later", "text": "String"},
           {"start": True, "text": "Boolean"}, {"start": 0}]
    good = {"text": "[Music]", "start": 4}
    side["held_transcript_lines"] = [dict(line=n, reason="non_speech", segment=row)
                                     for n, row in enumerate([*bad, good], 2)]
    path.write_text(json.dumps(side), "utf-8")
    monkeypatch.setattr(tools, "_backend", server)
    result = tools.get_uoink_corpus({"slug": path.stem, "include_held": True})
    assert result["ok"] and "Kept words" in result["corpus_md"]
    assert result["corpus_md"].split("## Held transcript lines")[1].strip() == "- Line 6 [0:04] [Music]"


def test_failed_citation_publication_resumes_at_unfinished_item(library, monkeypatch):
    import server
    import transcript_review as review
    first = add_talk(library, [(0, 1, "[Music]")], "abcde123450")
    second = add_talk(library, [(0, 1, "[Applause]")], "abcde123451")
    checkpoint = library.data / "transcript-review-apply.json"
    publish = library.idx.publish_media_snapshot

    def fail_second(video_id, **kwargs):
        if video_id == second.stem:
            raise OSError("citation publication interrupted")
        return publish(video_id, **kwargs)

    with monkeypatch.context() as m:
        m.setattr(library.idx, "publish_media_snapshot", fail_second)
        failed = review.tidy(server, apply=True)
    assert not failed["ok"] and "citation publication interrupted" in str(failed["errors"])
    assert json.loads(checkpoint.read_bytes())["cursor"] == first.stem
    assert library.idx.search("applause")
    assert any(c["text"] == "[Applause]" for c in library.idx.get_citations(second.stem))
    pending = json.loads(second.read_bytes())
    assert pending["held_transcript_lines"][0]["segment"]["text"] == "[Applause]"
    assert pending["pending_transcript_review"]
    queued = {"folder": second.parent, "sidecar_path": second, "corpus_path": second.with_suffix(".md"),
              "url": pending["url"]}
    assert server._transcript_backfill_apply(queued, [(0, 1, "Other words")], "captions") == "busy"
    assert json.loads(second.read_bytes()) == pending
    done = review.tidy(server, apply=True)
    assert done["ok"] and done["held_count"] == done["changed"] == 2
    assert not checkpoint.exists() and not library.idx.search("applause")
    assert all(c.get("text") != "[Applause]" for c in library.idx.get_citations(second.stem))
    assert "pending_transcript_review" not in json.loads(second.read_bytes())


@pytest.mark.parametrize("old_backfill", [False, True])
def test_all_held_capture_can_backfill_words(library, old_backfill):
    import threading
    import library_media
    import server
    import transcript_review as review
    if old_backfill:
        path = add_talk(library, [])
        item, = server._transcript_backfill_scan()["items"]
        assert server._transcript_backfill_apply(item, [(1, 2, "[Applause]")], "captions") == "applied"
        # Older no-words backfills could omit the chapter list when all cues were held.
        side = json.loads(path.read_bytes())
        side.pop("source_chapters", None)
        path.write_text(json.dumps(side), "utf-8")
    else:
        path = add_talk(library, [(1, 2, "[Applause]")])
        assert review.tidy(server, apply=True)["ok"]
    before = json.loads(path.read_bytes())
    assert not before["transcript"] and before["held_transcript_lines"]
    items = server._transcript_backfill_scan()["items"]
    assert [item["key"] for item in items] == [path.stem]
    library.caption_urls.add(items[0]["url"])
    outcome = server._transcript_backfill_item(items[0], lambda position, wait: None,
                                              threading.Event(), lambda host: True)
    assert outcome["outcome"] == "transcribed"
    after = json.loads(path.read_bytes())
    assert [s["text"] for s in after["transcript"]] == ["caption words from the source"]
    assert not after.get("held_transcript_lines") and library.idx.search("caption words")
    assert not server._transcript_backfill_scan()["items"]
    backup = path.parent / library_media.MEDIA_INPUTS_DIR / ("transcript-before-" + after["transcript_backup"][:16] + ".json")
    assert json.loads(backup.read_bytes()) == before
    restored = server.retranscribe_item(path.stem, "base", restore=after["transcript_backup"])
    assert restored["restored"]
    assert json.loads(path.read_bytes())["held_transcript_lines"] == before["held_transcript_lines"]
    assert [i["key"] for i in server._transcript_backfill_scan()["items"]] == [path.stem]


@pytest.mark.parametrize("mode,payload", [("--dry-run", b'{"cursor":'), ("--apply", b'["invalid"]')])
def test_invalid_checkpoint_explains_how_to_resume(library, monkeypatch, capsys, mode, payload):
    import server
    import uoink_cli as cli
    monkeypatch.setattr(cli, "backend", lambda: server)
    path = library.data / f"transcript-review-{mode[2:]}.json"
    path.write_bytes(payload)
    assert cli.main(["tidy-transcripts", mode]) != 0
    message = json.loads(capsys.readouterr().out)["error"]
    assert str(path) in message and "repair" in message.lower() and mode in message
    assert path.read_bytes() == payload


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


def test_cached_lyrics_from_the_previous_review_are_available_offline(tmp_path, monkeypatch):
    import server
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(server, "_library_transcript", lambda _: None)
    vid = "abcde123456"
    lyric = "♪ The last light finds the river ♪"
    held = [{"line": 1, "reason": "non_speech", "segment": {"start": 0, "end": 1, "text": lyric}},
            {"line": 3, "reason": "non_speech", "segment": {"start": 3, "end": 4, "text": "[Music]"}}]
    record = {"video_id": vid, "version": 2, "source": "captions", "held_transcript_lines": held,
              "segments": [[1, 2, "Thank you."]]}
    server._write_transcript_cache(record, None)
    cached = server.get_transcript_cascade(vid)
    assert cached["cached"] and cached["segments"] == [(0, 1, lyric), (1, 2, "Thank you.")]
    assert cached["held_count"] == 1
    assert server.get_transcript_cascade(vid, include_held=True)["segments"][-1] == (3, 4, "[Music]")


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
    producer = Path(podcasts.get_episode(idx, episode_id)["transcript_local_path"])
    raw = json.loads(producer.read_text("utf-8"))
    raw["segments"].insert(1, {"start": 7., "end": 8., "text": "[Applause]"})
    producer.write_text(json.dumps(raw), "utf-8")
    with idx.write_transaction() as db:
        db.execute("UPDATE podcast_episodes SET transcript_local_path=? WHERE id=?",
                   (str(producer), episode_id))
    try:
        record = podcasts.episode_to_corpus(idx, episode_id, data_root=tmp_path)
        vid = record["video_id"]
        assert idx.search("applause")
        with monkeypatch.context() as m:
            def stopped(*args, **kwargs):
                raise OSError("episode publication interrupted")
            m.setattr(podcasts, "episode_to_corpus", stopped)
            failed = review.tidy(server, apply=True)
            assert not failed["ok"] and "episode publication interrupted" in str(failed["errors"])
        checkpoint = tmp_path / "transcript-review-apply.json"
        assert json.loads(checkpoint.read_bytes())["cursor"] == ""
        result = review.tidy(server, apply=True)
        assert result["ok"] and result["changed"] == 1, result
        assert not checkpoint.exists()
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
