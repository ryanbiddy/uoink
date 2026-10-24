"""UX1: synthetic saved responses only. Never contact capture providers."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import library_cards
import page_extractor
import x_article_extractor
from uoink_core import x_evidence
import x_extractor


FIXTURES = json.loads((Path(__file__).parent / "fixtures/x_capture_evidence.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("X evidence tests must use saved fixtures")
    monkeypatch.setattr(x_extractor.urllib.request, "urlopen", forbidden)


def extract(name):
    fixture = copy.deepcopy(FIXTURES["cases"][name])
    def fetch(post_id, **kwargs):
        if post_id != fixture["tweet_id"]:
            raise ValueError(fixture.get("ancestor_error", "unavailable"))
        return x_extractor._merge_fxtwitter_full_text(fixture["syndication"], fixture["fxtwitter"])
    def supplement(post_id, **kwargs):
        assert post_id == fixture["syndication"]["parent"]["id_str"]
        return fixture.get("parent_fxtwitter")
    result = x_extractor.extract_x_thread(f"https://x.com/example/status/{fixture['tweet_id']}",
                                          _fetch=fetch, _supplement=supplement)
    assert result["ok"], result
    return result


def post(result):
    return result["metadata"]["x_capture"]["posts"][-1]


@pytest.mark.parametrize("name", FIXTURES["cases"])
def test_every_capture_discloses_completeness_provider_scope_and_missing_metrics(name):
    result = extract(name)
    evidence = post(result)
    assert evidence["text_completeness"] in {"complete", "truncated", "unknown"}
    assert evidence["capture_provider"] in {"syndication", "FxTwitter"}
    assert set(evidence["engagement"]) == set(x_evidence.METRICS)
    assert f"Text: {evidence['text_completeness']}" in result["markdown"]
    assert "Replies below the shared post" in result["markdown"]
    assert result["metadata"]["capture_scope"] == x_evidence.SCOPE


def test_long_text_and_embedded_parent_both_supplement():
    result = extract("long_post")
    assert post(result)["text"].endswith("FULL-TEXT-END")
    assert post(result)["text_completeness"] == "complete"
    embedded = extract("embedded_parent")
    parent = embedded["metadata"]["x_capture"]["posts"][0]
    assert parent["text"].endswith("FULL-TEXT-END")
    assert parent["text_completeness"] == "complete"
    assert embedded["tweets_captured"] == 2


def test_quote_keeps_relationship_full_text_entities_media_and_metrics():
    result = extract("quote_post")
    quote = post(result)["quote"]
    assert quote["id"] == "200"
    assert quote["author"]["handle"] == "quoted"
    assert quote["url"] == "https://x.com/quoted/status/200"
    assert quote["text"].endswith("QUOTE-END")
    assert quote["text_completeness"] == "complete"
    assert quote["entities"]["hashtags"][0]["text"] == "evidence"
    assert quote["media"][0]["alt_text"] == "Quoted chart"
    assert quote["engagement"]["likes"] == 0
    assert "QUOTE-END" in result["markdown"]
    assert "Quoted chart" in result["markdown"]


def test_photos_alt_links_entities_and_zero_survive_without_downloads():
    result = extract("photos")
    evidence = post(result)
    assert len(evidence["media"]) == 2
    assert result["metadata"]["photo_count"] == 2
    assert len(result["images"]) == 2
    assert evidence["media"][0]["alt_text"] == "A blue square beside a red circle."
    assert evidence["media"][1]["alt_text"] is None
    assert evidence["entities"]["user_mentions"][0]["screen_name"] == "mention"
    assert evidence["raw_text"]["facets"][1]["type"] == "bold"
    assert evidence["engagement"]["likes"] == 0
    assert evidence["engagement"]["views"] is None
    assert "Photo evidence https://example.invalid/report" in result["markdown"]
    assert result["links"][0]["href"] == "https://example.invalid/report"
    assert "Some photo alt text is unavailable" in result["markdown"]
    assert "Media files were not downloaded" in result["markdown"]


def test_video_and_gif_keep_all_variants_and_posters():
    result = extract("video")
    evidence = post(result)
    assert len(evidence["media"]) == 2
    video, gif = evidence["media"]
    assert video["type"] == "video" and gif["type"] == "gif"
    assert {v["url"] for v in video["variants"]} == {
        "https://example.invalid/video-low.mp4", "https://example.invalid/video.mp4", "https://example.invalid/video.m3u8"}
    assert video["poster"] == "https://example.invalid/poster.jpg"
    assert gif["poster"] == "https://example.invalid/gif.jpg"
    assert result["images"] == []
    assert result["metadata"]["has_video"] is True
    retained = [source for media in evidence["media"] for source in media["source_descriptors"]]
    fixture = FIXTURES["cases"]["video"]
    assert all(source in retained for source in fixture["syndication"]["mediaDetails"])
    assert all(source in retained for source in fixture["fxtwitter"]["status"]["media"]["videos"])


@pytest.mark.parametrize("name", ["video", "quote_post", "photos"])
def test_media_and_quote_only_posts_are_not_rejected_as_empty(name):
    fixture = copy.deepcopy(FIXTURES["cases"][name])
    fixture["syndication"]["text"] = ""
    fixture["fxtwitter"]["status"]["text"] = ""
    payload = x_extractor._merge_fxtwitter_full_text(fixture["syndication"], fixture["fxtwitter"])
    result = x_extractor.extract_x_thread(f"https://x.com/example/status/{fixture['tweet_id']}",
                                          _fetch=lambda *a, **k: payload)
    assert result["ok"]
    assert post(result)["media"] or post(result)["quote"]


def test_missing_ancestor_is_visible_and_machine_readable():
    result = extract("missing_ancestor")
    assert post(result)["missing_parent"] == {"id": "404", "reason": "unavailable or request failed"}
    assert "Parent 404 not captured" in result["markdown"]


@pytest.mark.parametrize("failure", [TimeoutError, OSError])
def test_supplement_transport_failure_keeps_text_and_marks_it(monkeypatch, failure):
    fixture = FIXTURES["cases"]["provider_failure"]
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self): return json.dumps(fixture["syndication"]).encode()
    calls = []
    def urlopen(request, **kwargs):
        calls.append(request.full_url)
        if len(calls) == 1:
            return Response()
        raise failure("fixture failure")
    monkeypatch.setattr(x_extractor.urllib.request, "urlopen", urlopen)
    payload = x_extractor.fetch_tweet_json(fixture["tweet_id"])
    evidence = payload["_uoink_x_evidence"]
    assert len(calls) == 2
    assert evidence["text"] == fixture["syndication"]["text"]
    assert evidence["text_completeness"] == "truncated"
    assert evidence["capture_provider"] == "syndication"
    assert evidence["provider_status"]["FxTwitter"] != "captured"


def test_shorter_response_and_later_failure_cannot_remove_fuller_evidence():
    fixture = FIXTURES["cases"]["shorter_response"]
    payload = x_extractor._merge_fxtwitter_full_text(fixture["syndication"], fixture["fxtwitter"])
    evidence = payload["_uoink_x_evidence"]
    assert evidence["text"].endswith("ORIGINAL-END")
    assert evidence["capture_provider"] == "syndication"
    assert len(evidence["media"]) == 2
    failed = x_extractor._merge_fxtwitter_full_text(payload, None)["_uoink_x_evidence"]
    assert failed["text"] == evidence["text"]
    assert failed["media"] == evidence["media"]
    long = FIXTURES["cases"]["long_post"]
    payload = x_extractor._merge_fxtwitter_full_text(long["syndication"], long["fxtwitter"])
    payload = x_extractor._merge_fxtwitter_full_text(payload, fixture["fxtwitter"])
    assert payload["text"].endswith("FULL-TEXT-END")
    assert payload["_uoink_x_evidence"]["text_completeness"] == "complete"


def test_quote_failure_keeps_captured_fragment_and_discloses_missing_part():
    quote = post(extract("quote_tombstone"))["quote"]
    assert quote["text"] == "Quoted opening..."
    assert quote["text_completeness"] == "truncated"
    assert quote["unavailable_reason"] == "unavailable"
    fixture = copy.deepcopy(FIXTURES["cases"]["quote_tombstone"])
    del fixture["fxtwitter"]["status"]["quote"]["id"]
    merged = x_extractor._merge_fxtwitter_full_text(fixture["syndication"], fixture["fxtwitter"])
    assert merged["_uoink_x_evidence"]["quote"]["id"] == "200"
    assert merged["_uoink_x_evidence"]["quote"]["unavailable_reason"] == "unavailable"


def test_dom_capture_has_explicit_unknown_completeness():
    result = x_article_extractor.build_extract_result(FIXTURES["extension_dom"])
    evidence = post(result)
    assert evidence["capture_provider"] == "extension DOM"
    assert evidence["text_completeness"] == "unknown"
    assert evidence["media"][0]["alt_text"] == "Article chart"
    assert "Text completeness is unknown" in result["markdown"]


def test_sidecar_cards_mcp_cli_and_fixed_corpus_contract(tmp_path, monkeypatch, capsys):
    import index
    import corpus_contract
    import corpus_provider
    import library_resources
    import uoink_cli
    import uoink_mcp_tools
    result = extract("quote_post")
    idx = index.Index.open(tmp_path / "index.db")
    try:
        item_id = page_extractor.persist_page_yoink(idx, result, data_root=tmp_path,
                                                  source_type="x_thread", subfolder="X", slug_prefix="x")
        row = idx.get_yoink(item_id)
        sidecar = json.loads(Path(row["sidecar_path"]).read_text(encoding="utf-8"))
        assert sidecar["metadata"]["x_capture"] == result["metadata"]["x_capture"]
        card = library_cards.build_card(row, [], corpus_text=result["markdown"])
        assert card["x_capture"] == result["metadata"]["x_capture"]
        backend = SimpleNamespace(_get_index=lambda: idx)
        monkeypatch.setattr(uoink_mcp_tools, "_b", lambda: backend)
        envelope = uoink_mcp_tools.get_evidence_card({"video_id": item_id})
        assert envelope["x_capture"] == card["x_capture"]
        assert uoink_cli.emit(envelope) == 0
        assert json.loads(capsys.readouterr().out)["x_capture"] == card["x_capture"]
        assert "Text: complete" in uoink_cli.human(envelope)
        assert "Quoted post 200" in uoink_cli.human(envelope)
        reader = library_resources.LibraryReader(idx, data_root=tmp_path)
        with reader.request() as scope:
            library_item = scope.get_item(video_id=item_id)
        assert "x_capture" in library_item["card"]
        assert "Capture scope" in uoink_cli.human(library_item)
        provider = corpus_provider.UoinkCorpusProvider(idx, tmp_path)
        with_capture = provider._item_ref(row)
        metadata = json.loads(row["metadata_json"])
        del metadata["x_capture"]
        without_capture = provider._item_ref(dict(row, metadata_json=json.dumps(metadata)))
        assert with_capture == without_capture
        corpus_contract.validate_item_ref(with_capture)
        assert "x_capture" not in with_capture
    finally:
        idx.close()


def test_bounded_card_never_silently_drops_evidence():
    result = extract("photos")
    item = {"video_id": "x_fixture", "source_type": "x_thread", "metadata_json": json.dumps(result["metadata"])}
    card = library_cards.build_card(item, [], corpus_text=result["markdown"], profile="librarian", byte_budget=4096)
    assert len(library_cards.card_text(card).encode()) <= 4096
    assert card["x_capture"]["details_omitted"] is True
    assert "x_capture" in card["truncation"]["fields"]
    assert card["x_capture"]["posts"][0]["text_completeness"] == "complete"


def test_long_thread_card_keeps_limits_when_per_post_details_do_not_fit():
    result = extract("photos")
    evidence = result["metadata"]["x_capture"]
    evidence["posts"] = evidence["posts"] * 26
    item = {"video_id": "x_fixture", "source_type": "x_thread", "metadata_json": json.dumps(result["metadata"])}
    card = library_cards.build_card(item, [], corpus_text=result["markdown"], profile="librarian", byte_budget=4096)
    assert len(library_cards.card_text(card).encode()) <= 4096
    assert card["x_capture"]["summary"]["post_count"] == 26
    assert card["x_capture"]["summary"]["text_completeness"]["complete"] == 26
    assert card["x_capture"]["details_omitted"] is True
    assert "same-author" in " ".join(x_evidence.summary_lines(card["x_capture"]))


@pytest.mark.parametrize("boundary", ["cycle", "cap", "different_author", "unknown_author"])
def test_ancestor_boundaries_are_marked(boundary, monkeypatch):
    fixture = copy.deepcopy(FIXTURES["cases"]["embedded_parent"])
    payload = fixture["syndication"]
    if boundary == "cycle":
        payload["in_reply_to_status_id_str"] = payload["id_str"]
    elif boundary == "cap":
        monkeypatch.setattr(x_extractor, "MAX_THREAD_HOPS", 0)
    elif boundary == "different_author":
        # The embedded parent's identity, not just the child's reply hint, matters.
        payload["parent"]["user"]["screen_name"] = "other"
    else:
        payload["in_reply_to_screen_name"] = ""
    result = x_extractor.extract_x_thread(f"https://x.com/example/status/{fixture['tweet_id']}",
                                          _fetch=lambda *a, **k: payload)
    assert result["ok"] and result["tweets_captured"] == 1
    assert post(result)["missing_parent"]
    assert "not captured" in result["markdown"]


def test_wrong_id_and_malformed_supplements_preserve_available_capture():
    fixture = copy.deepcopy(FIXTURES["cases"]["photos"])
    fixture["fxtwitter"]["status"]["id"] = "wrong-id"
    merged = x_extractor._merge_fxtwitter_full_text(fixture["syndication"], fixture["fxtwitter"])
    assert merged["text"] == fixture["syndication"]["text"]
    assert merged["_uoink_x_evidence"]["provider_status"]["FxTwitter"] != "captured"
    assert len(merged["_uoink_x_evidence"]["media"]) == 1
    invalid = x_extractor._merge_fxtwitter_full_text(merged, {"code": 200, "status": []})
    assert invalid["_uoink_x_evidence"]["media"] == merged["_uoink_x_evidence"]["media"]
