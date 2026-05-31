"""Empirical tests for the Writing Studio composer backend (D-19 char count /
thread builder + D-18 native attribution).

Run: python tests/test_composer.py
Tests writing_studio.tweet_length / assemble_footer / validate_composition
directly with a fake index. No server boot, no network.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import writing_studio as ws  # noqa: E402


class FakeIndex:
    def __init__(self, rows):
        self._rows = rows

    def get_yoink(self, video_id):
        return self._rows.get(video_id)


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


YOINK = {
    "video_id": "v1",
    "title": "Intro to LLMs",
    "channel": "Andrej Karpathy",
    "channel_url": "https://www.youtube.com/@AndrejKarpathy",
    "url": "https://youtu.be/abc",
}


def test_tweet_length():
    _assert(ws.tweet_length("") == 0, "empty should be 0")
    _assert(ws.tweet_length("hello") == 5, "plain len wrong")
    # a 100-char URL still counts as 23
    long_url = "https://example.com/" + ("a" * 200)
    _assert(ws.tweet_length(long_url) == 23, f"URL should weight 23, got {ws.tweet_length(long_url)}")
    mixed = "see this " + long_url + " now"
    # "see this " = 9, " now" = 4, url = 23 -> 36
    _assert(ws.tweet_length(mixed) == 9 + 4 + 23, f"mixed wrong: {ws.tweet_length(mixed)}")
    print("ok  tweet_length: empty / plain / url-weighted / mixed")


def test_assemble_footer():
    idx = FakeIndex({"v1": YOINK})
    credit = ws.build_credit_line(YOINK, kind=ws.KIND_TWEET)
    _assert("via @AndrejKarpathy" in credit, f"credit handle wrong: {credit}")
    # tweet, attribution on -> appends " · uoink.app"
    f_on = ws.assemble_footer(credit, ws.KIND_TWEET, attribution_enabled=True)
    _assert(f_on.endswith(" · uoink.app"), f"tweet footer missing attribution: {f_on}")
    # tweet, attribution off -> just the credit (non-suppressible stays)
    f_off = ws.assemble_footer(credit, ws.KIND_TWEET, attribution_enabled=False)
    _assert(f_off == credit and "uoink.app" not in f_off, f"off should drop attribution: {f_off}")
    # blog on -> attribution line on its own line
    blog_credit = ws.build_credit_line(YOINK, kind=ws.KIND_BLOG)
    fb = ws.assemble_footer(blog_credit, ws.KIND_BLOG, attribution_enabled=True)
    _assert(ws.BLOG_ATTRIBUTION_LINE in fb and "\n" in fb, f"blog footer wrong: {fb}")
    _assert("—" not in fb and "—" not in ws.BLOG_ATTRIBUTION_LINE, "no em dash allowed in attribution")
    print("ok  assemble_footer: tweet on/off, blog on, no em dash")


def test_validate_tweet():
    idx = FakeIndex({"v1": YOINK})
    res = ws.validate_composition(idx, yoink_id="v1", kind=ws.KIND_TWEET,
                                  tweets=["short tweet"], attribution_enabled=True)
    _assert(res["total_tweets"] == 1, "tweet total wrong")
    t0 = res["tweets"][0]
    _assert(t0["char_count"] == len("short tweet"), "tweet count wrong")
    _assert(t0["over_limit"] is False, "short tweet not over")
    _assert("char_count_with_footer" in t0, "missing footer count on last tweet")
    _assert(res["footer_text"].endswith("uoink.app"), "footer attribution missing")
    print("ok  validate_composition: single tweet + footer count")


def test_validate_thread_over_limit():
    idx = FakeIndex({"v1": YOINK})
    big = "x" * 290
    res = ws.validate_composition(idx, yoink_id="v1", kind=ws.KIND_THREAD,
                                  tweets=["ok tweet", big], attribution_enabled=True)
    _assert(res["total_tweets"] == 2, "thread total wrong")
    _assert(res["tweets"][0]["over_limit"] is False, "tweet 0 should be fine")
    _assert(res["tweets"][1]["over_limit"] is True, "tweet 1 (290) should be over 280")
    _assert(res["over_limit_any"] is True, "over_limit_any should be True")
    _assert(res["footer_target_index"] == 1, "footer should target last tweet")
    print("ok  validate_composition: thread over-280 detection")


def test_validate_blog():
    idx = FakeIndex({"v1": YOINK})
    res = ws.validate_composition(idx, yoink_id="v1", kind=ws.KIND_BLOG,
                                  attribution_enabled=True)
    _assert(res["kind"] == "blog", "kind wrong")
    _assert(res["attribution_line"] == ws.BLOG_ATTRIBUTION_LINE, "blog attribution line missing")
    _assert("tweets" not in res, "blog should not return tweet counts")
    res_off = ws.validate_composition(idx, yoink_id="v1", kind=ws.KIND_BLOG,
                                      attribution_enabled=False)
    _assert(res_off["attribution_line"] == "", "blog attribution should be empty when off")
    print("ok  validate_composition: blog attribution on/off")


def test_validate_no_yoink():
    idx = FakeIndex({})
    # no source yoink -> credit falls back, still computes counts, no crash
    res = ws.validate_composition(idx, yoink_id=None, kind=ws.KIND_TWEET,
                                  tweets=["hi"], attribution_enabled=True)
    _assert(res["credit_line"], "fallback credit should be non-empty")
    _assert(res["total_tweets"] == 1, "should still count tweets")
    print("ok  validate_composition: no source yoink fallback")


def test_bad_kind():
    idx = FakeIndex({})
    try:
        ws.validate_composition(idx, yoink_id=None, kind="bogus", tweets=[])
    except ValueError as e:
        _assert(getattr(e, "http_status", None) == 400, "bad kind should carry http_status 400")
        print("ok  validate_composition: bad kind -> ValueError(400)")
        return
    raise AssertionError("bad kind should have raised")


def main():
    test_tweet_length()
    test_assemble_footer()
    test_validate_tweet()
    test_validate_thread_over_limit()
    test_validate_blog()
    test_validate_no_yoink()
    test_bad_kind()
    print("\nALL COMPOSER TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
