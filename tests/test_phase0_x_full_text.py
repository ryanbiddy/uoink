import json
from pathlib import Path

import x_extractor


FIXTURE = Path(__file__).parent / "fixtures" / "fxtwitter_v2_long_post.json"


class _Response:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self._body


def test_fxtwitter_v2_fixture_restores_long_post_text(monkeypatch):
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    requests = []

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        if request.full_url.startswith(x_extractor.SYNDICATION_URL):
            return _Response(fixture["syndication"])
        assert request.full_url == x_extractor.FXTWITTER_STATUS_URL.format(
            tweet_id=fixture["tweet_id"])
        assert request.get_header("User-agent") == x_extractor.FXTWITTER_USER_AGENT
        return _Response(fixture["fxtwitter"])

    monkeypatch.setattr(x_extractor.urllib.request, "urlopen", fake_urlopen)

    payload = x_extractor.fetch_tweet_json(fixture["tweet_id"], timeout=7)
    result = x_extractor.extract_x_thread(
        f"https://x.com/example/status/{fixture['tweet_id']}",
        _fetch=lambda _tweet_id, **_kwargs: payload,
    )

    assert len(requests) == 2
    assert all(timeout == 7 for _request, timeout in requests)
    assert payload["text"].endswith("FULL-TEXT-END")
    assert "FULL-TEXT-END" in result["markdown"]
    assert result["metadata"]["full_text_posts"] == 1
    assert result["extraction_engine"] == "x-syndication+fxtwitter-v2"


def test_fxtwitter_failure_falls_back_to_syndication(monkeypatch):
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def fake_urlopen(request, timeout):
        assert timeout == 20
        if request.full_url.startswith(x_extractor.SYNDICATION_URL):
            return _Response(fixture["syndication"])
        raise x_extractor.urllib.error.URLError("offline")

    monkeypatch.setattr(x_extractor.urllib.request, "urlopen", fake_urlopen)

    payload = x_extractor.fetch_tweet_json(fixture["tweet_id"])

    assert payload["text"] == fixture["syndication"]["text"]
    assert "_uoink_full_text_source" not in payload
