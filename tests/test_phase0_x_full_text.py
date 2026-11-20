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

    def read(self, amount=-1):
        return self._body if amount is None or amount < 0 else self._body[:amount]


def _route(monkeypatch, fake_urlopen):
    # 3.18.0: x_extractor sends every request through its own no-redirect
    # opener (_urlopen), and FxTwitter only when the user's switch says on.
    monkeypatch.setattr(x_extractor, "_urlopen", fake_urlopen)
    monkeypatch.setattr(x_extractor, "_fxtwitter_gate", lambda: True)


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

    _route(monkeypatch, fake_urlopen)

    # 3.18.0: deliberately changed. FxTwitter is the user's opt-in now, so
    # the test turns it on. Its cache and cool-down start empty.
    x_extractor.reset_fxtwitter_state()
    payload = x_extractor.fetch_tweet_json(fixture["tweet_id"], timeout=7, fxtwitter=True)
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

    _route(monkeypatch, fake_urlopen)

    x_extractor.reset_fxtwitter_state()
    payload = x_extractor.fetch_tweet_json(fixture["tweet_id"], fxtwitter=True)

    assert payload["text"] == fixture["syndication"]["text"]
    assert "_uoink_full_text_source" not in payload
