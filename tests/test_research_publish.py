"""Verification, quotation budgets and inert report exports, entirely offline."""
from copy import deepcopy
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil

import pytest

import research
import research_report
import research_verify as verify
import uoink_mcp_tools as tools
from tests.test_research_evidence import FIXTURES, NOW, evidence, excerpt_data, load_fixture, make_run, rig, seed


class Links(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.hrefs, self.tags, self.attrs = [], [], []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attrs.extend(attrs)
        self.hrefs.extend(v for k, v in attrs if k == "href")


def claim(excerpt_id, quote="evals catch regressions before deployment", **extra):
    return {"id": "c1", "text": quote, "section": "Evaluations",
            "excerpt_refs": [{"excerpt_id": excerpt_id, "quote": quote}], **extra}


def payload(run, claims):
    return {"run_id": run["run_id"], "title": "Evaluation receipts", "summary_md": "Evals catch regressions.",
            "claims": claims}


def prepared(rig):
    run = make_run(rig, [seed(rig)])
    excerpt = evidence(run)["excerpts"][0]
    return run, excerpt["excerpt_id"]


def publish(run, claims, **extra):
    result = tools.call_tool("research_publish", {**payload(run, claims), **extra})
    assert result["ok"], result
    return result


def html_report(result):
    return Path(result["report_html_path"]).read_text(encoding="utf-8")


@pytest.mark.parametrize("fault,reason", [("wrong", "quote_not_found"), ("foreign", "excerpt_unknown"),
                                          ("revision", "revision_changed")])
def test_hard_binding_failures(rig, fault, reason):
    run, excerpt = prepared(rig)
    submitted = claim(excerpt, judge="supports")
    if fault == "wrong":
        submitted["excerpt_refs"][0]["quote"] = "A planted invented sentence never spoken."
    elif fault == "foreign":
        run = make_run(rig)
    else:
        changed = load_fixture()
        changed["cues"][2]["text"] = "These cues were revised after evidence retrieval."
        seed(rig, fixture=changed)
    result = publish(run, [submitted])
    assert result["verification"]["dropped"][0]["reasons"] == [reason]
    assert "<blockquote>" not in html_report(result)
    if fault == "wrong":
        assert submitted["excerpt_refs"][0]["quote"] not in html_report(result)


@pytest.mark.parametrize("claim_count,source_count,expected", [
    (0, 0, "0 claims from 0 sources"), (1, 1, "1 claim from 1 source"),
    (2, 1, "2 claims from 1 source"), (2, 2, "2 claims from 2 sources"),
])
def test_report_and_share_text_pluralize_claims_and_sources(rig, claim_count, source_count, expected):
    run = make_run(rig, [seed(rig, video_id=f"talk{i:07d}") for i in range(source_count or 1)])
    excerpts = evidence(run)["excerpts"]
    claims = [claim(excerpts[i % source_count]["excerpt_id"], id=f"c{i}") for i in range(claim_count)]
    if not claims:
        claims = [claim(excerpts[0]["excerpt_id"], judge="no")]
    result = publish(run, claims)
    dropped = 0 if claim_count else 1
    assert expected + ", each linked to the second it was said." in result["share_text"]
    for key in ("report_md_path", "report_html_path"):
        assert expected + f", {dropped} dropped" in Path(result[key]).read_text(encoding="utf-8")


def test_published_markdown_uses_markdown_escapes_and_html_stays_escaped(rig):
    run, excerpt = prepared(rig)
    result = publish(run, [claim(excerpt)],
                     summary_md='Evals & R&D: [checks] for @reviewer <b>catch regressions</b>.')
    markdown = Path(result["report_md_path"]).read_text(encoding="utf-8")
    assert r'Evals \& R\&D\: \[checks\] for \@reviewer \<b\>catch regressions\</b\>\.' in markdown
    assert "&#" not in markdown and "&amp;" not in markdown
    rendered = html_report(result)
    assert "Evals &amp; R&amp;D: [checks] for @reviewer &lt;b&gt;catch regressions&lt;/b&gt;." in rendered
    assert "b" not in Links(rendered).tags


def test_reanchors_third_cue_and_caption_folding(rig):
    run, excerpt = prepared(rig)
    result = publish(run, [claim(excerpt, "Evals catch regressions, before deployment!")])
    assert result["verification"]["stats"]["dropped"] == 0
    assert Links(html_report(result)).hrefs == ["https://www.youtube.com/watch?v=talk0000001&t=27s"]
    assert "00:27" in html_report(result)


def test_cross_cue_quote_and_excessive_span(rig):
    run, excerpt = prepared(rig)
    result = publish(run, [claim(excerpt, "deployment however benchmarks miss failures")])
    assert result["verification"]["stats"]["claims"] == 1
    saved = research.load_run(rig.root, run["run_id"])
    saved["excerpts"][excerpt]["cue_ids"] = [4, 5]
    research.save_run(rig.root, saved)
    result = publish(run, [claim(excerpt, "miss. The final evaluation")])
    assert result["verification"]["dropped"][0]["reasons"] == ["quote_spans_too_far"]


def test_doubt_and_speaker_downgrade(rig):
    run, excerpt = prepared(rig)
    result = publish(run, [claim(excerpt, "Human review catches failures", attribution="speaker")])
    assert set(result["verification"]["flagged"][0]["reasons"]) == {"asr_doubt", "speaker_unconfirmed"}
    text = html_report(result)
    assert 'class="chip amber"' in text and "listen at 00:49" in text
    assert 'class="chip grey"' in text and "Speaker unconfirmed" in text


@pytest.mark.parametrize("judge,status,reason", [("no", "dropped", "judge_no"),
    ("partial", "flagged", "overstated"), ("supports", "accepted", None)])
def test_judge_is_only_a_downgrade(rig, judge, status, reason):
    run, excerpt = prepared(rig)
    result = publish(run, [claim(excerpt, judge=judge)])
    assert len(result["verification"][status]) == 1
    assert result["verification"][status][0]["judge"] == judge
    if reason:
        assert reason in result["verification"][status][0]["reasons"]


def test_low_overlap_and_counter_requirements(rig):
    run, excerpt = prepared(rig)
    result = publish(run, [claim(excerpt, text="Bananas power orbital engines.", contested=True)])
    assert set(result["verification"]["flagged"][0]["reasons"]) == {"low_overlap", "needs_judge", "one_sided_search"}
    evidence(run, stance_hint="counter")
    counter = {"excerpt_id": excerpt, "quote": "however benchmarks miss failures in real workflows"}
    result = publish(run, [claim(excerpt, contested=True, counter_refs=[counter])])
    assert result["verification"]["accepted"]
    counter["quote"] = "This counter quote is invented."
    result = publish(run, [claim(excerpt, contested=True, counter_refs=[counter])])
    record = result["verification"]["flagged"][0]
    assert record["dropped_refs"] == [{"excerpt_id": excerpt, "reason": "quote_not_found", "kind": "counter"}]
    assert "one_sided_search" in record["reasons"] and "invented" not in html_report(result)


def test_quote_caps_and_summary_validation(rig):
    run, excerpt = prepared(rig)
    submitted = claim(excerpt)
    submitted["excerpt_refs"] *= 3
    invalid = tools.call_tool("research_publish", payload(run, [submitted]))
    assert invalid["code"] == "too_many_quotes"
    for summary in ("See https://evil.example/a", "See www.example.com", "See example.com/a"):
        invalid = tools.call_tool("research_publish", {**payload(run, [claim(excerpt)]), "summary_md": summary})
        assert invalid["code"] == "summary_has_links"
    invalid = tools.call_tool("research_publish", payload(run, [claim(excerpt, "a" * 281)]))
    assert invalid["code"] == "quote_too_long"
    result = publish(run, [claim(excerpt, id=f"c{n}") for n in range(9)])
    assert result["verification"]["stats"]["claims"] == 8
    assert result["verification"]["dropped"][0]["reasons"] == ["source_quote_cap"]
    assert html_report(result).count("<blockquote>") == 8


def test_six_hundred_word_cap_includes_counter_quotes(rig):
    fixture = load_fixture()
    quote = " ".join(["a"] * 130)
    counter = " ".join(["b"] * 130)
    fixture["cues"] = [{"start": 0, "end": 10, "text": quote}, {"start": 12, "end": 20, "text": counter}]
    run = make_run(rig, [seed(rig, fixture=fixture)])
    excerpt = evidence(run, query="a")["excerpts"][0]["excerpt_id"]
    claims = [claim(excerpt, quote, id=f"c{n}", judge="supports") for n in range(5)]
    result = publish(run, claims)
    assert result["verification"]["stats"]["claims"] == 4
    assert result["verification"]["dropped"][0]["reasons"] == ["source_quote_cap"]
    claims[0]["counter_refs"] = [{"excerpt_id": excerpt, "quote": counter}]
    result = publish(run, claims)
    assert result["verification"]["stats"]["claims"] == 3


def test_partial_source_cap_keeps_other_source_quote(rig):
    run, excerpt = prepared(rig)
    second = seed(rig, "talk0000002")
    saved = research.load_run(rig.root, run["run_id"])
    saved["candidates"].append(second)
    research.save_run(rig.root, saved)
    other = next(e["excerpt_id"] for e in evidence(run)["excerpts"] if e["item_id"] == second["video_id"])
    claims = [claim(excerpt, id=f"c{n}") for n in range(9)]
    claims[-1]["excerpt_refs"].append({"excerpt_id": other, "quote": "evals catch regressions before deployment"})
    result = publish(run, claims)
    assert result["verification"]["stats"]["claims"] == 9
    assert result["verification"]["flagged"][-1]["reasons"] == ["source_quote_cap"]
    assert result["verification"]["stats"]["distinct_sources"] == 2


def test_idempotency_and_new_payload(rig):
    run, excerpt = prepared(rig)
    first = publish(run, [claim(excerpt)])
    paths = [Path(first[k]) for k in ("report_md_path", "report_html_path", "verification_path")]
    before = [(p.stat().st_mtime_ns, p.read_bytes()) for p in paths]
    second = publish(run, [claim(excerpt)])
    assert second == first
    assert [(p.stat().st_mtime_ns, p.read_bytes()) for p in paths] == before
    third = publish(run, [claim(excerpt, judge="no")])
    assert third["verification"] != first["verification"]
    assert paths[-1].read_bytes() != before[-1][1]


def test_injection_is_only_data_and_writes_stay_in_run(rig):
    fixture = load_fixture("transcript_injection.json")
    run = make_run(rig, [seed(rig, fixture=fixture)])
    before = {p.relative_to(rig.root): p.read_bytes() for p in rig.root.rglob("*") if p.is_file()}
    excerpts = evidence(run, query="Ignore")["excerpts"]
    assert excerpt_data(excerpts[0])["text"] == fixture["cues"][0]["text"]
    assert excerpts[0]["fence"]["begin"] == "<untrusted_uoink_library_context>"
    result = publish(run, [claim(excerpts[0]["excerpt_id"], fixture["cues"][0]["text"], judge="supports"),
                           claim(excerpts[0]["excerpt_id"], "Secret invented instructions", id="invented")],
                     summary_md="<b>Plain text only</b>")
    rendered = html_report(result)
    assert "<script" not in rendered and "onerror=" not in rendered and "<img" not in rendered
    assert "&lt;script&gt;" in rendered and "&lt;b&gt;Plain text only&lt;/b&gt;" in rendered
    parsed = Links(rendered)
    assert all(h.startswith("https://www.youtube.com/") for h in parsed.hrefs)
    assert not any(k.startswith("on") for k, _ in parsed.attrs)
    markdown = Path(result["report_md_path"]).read_text(encoding="utf-8")
    assert "https://evil.example" not in markdown and "](javascript:" not in markdown
    assert result["verification"]["dropped"][0]["reasons"] == ["quote_not_found"]
    after = {p.relative_to(rig.root): p.read_bytes() for p in rig.root.rglob("*") if p.is_file()}
    changed = {p for p in after if before.get(p) != after[p]}
    assert changed == {Path("research") / run["run_id"] / name for name in ("run.json", "report.md", "report.html", "verification.json")}
    rig.forbidden.assert_not_called()


@pytest.mark.parametrize("url,allowed", [("https://youtube.com/watch?v=x", True),
    ("http://youtube.com/watch?v=x", False), ("https://youtube.com.evil.example/", False),
    ("https://youtube.com@evil.example/", False), ("javascript:alert(1)", False),
    ("https://evil.example/", False), ("https://episodes.example.org/episode", True),
    ("https://youtube.com./watch?v=x", True), ("https://episodes.example.org./episode", True)])
def test_link_allowlist(url, allowed):
    source = {"kind": "podcast", "episode_url": "https://episodes.example.org/show"}
    assert bool(research_report.safe_link(url, source)) is allowed


def test_podcast_stored_host_with_trailing_dots():
    source = {"kind": "podcast", "episode_url": "https://episodes.example.org../show"}
    assert research_report.safe_link("https://episodes.example.org/episode", source)
    assert not research_report.safe_link("https://evil.example/episode", source)


def test_podcast_link_priority_and_time_labels():
    source = {"item_id": "ep_fixture", "kind": "podcast", "episode_url": "https://episodes.example.org/show",
              "enclosure_url": "https://audio.example.org/file.mp3"}
    assert verify.deep_link(source, 3601.9) == source["episode_url"]
    source.pop("episode_url")
    assert verify.deep_link(source, 3601.9) == "https://audio.example.org/file.mp3#t=3601"
    assert verify.time_label(3601.9) == "1:00:01"


def test_library_discovery_keeps_podcast_page_and_enclosure():
    candidate = research.parse_library([{"video_id": "ep_fixture", "title": "Fixture episode",
        "source_url": "https://episodes.example.org/page", "enclosure_url": "https://audio.example.org/episode.mp3"}])[0]
    assert candidate["trackViewUrl"] == "https://episodes.example.org/page"
    assert candidate["episodeUrl"] == "https://audio.example.org/episode.mp3"


def test_summary_plain_paragraphs_and_markdown_syntax():
    report = golden_report()
    report["summary"] = '<b>Raw HTML</b>\n\n[Link](javascript:alert(1))'
    rendered = research_report.render_html(report)
    assert "<p>&lt;b&gt;Raw HTML&lt;/b&gt;</p>" in rendered
    assert "javascript:" not in " ".join(Links(rendered).hrefs)
    report["claims"][0]["text"] = '- + []()*_`<>#|\\ https://evil.example/x www.evil.example'
    markdown = research_report.render_markdown(report)
    assert '\\- \\+ \\[\\]\\(\\)\\*\\_\\`\\<\\>\\#\\|\\\\' in markdown
    assert "https://evil.example" not in markdown and "www.evil.example" not in markdown


def golden_report():
    source = {"item_id": "talk0000001", "source_revision": "fixture-revision", "cue_revision": "fixture-cues",
        "title": "Evaluation practice", "channel": "Fixture talks", "kind": "youtube", "transcript_source": "captions",
        "published": "2026-10-30", "duration_s": 210, "source_url": "https://www.youtube.com/watch?v=talk0000001",
        "reliability_spans": [{"start": 40, "end": 42, "reason": "low_confidence"}],
        "cues": [{"seq": 0, "start": 27.8, "end": 36, "text": "evals catch regressions before deployment"},
                 {"seq": 1, "start": 38, "end": 46, "text": "however benchmarks miss failures in real workflows"}]}
    run = {"run_id": "rr_20261103120000_01234567", "scope": {"question": "How do evals catch regressions?"},
           "excerpts": {"ex_fixture": {"item_id": source["item_id"], "source_revision": source["source_revision"],
                                      "cue_revision": source["cue_revision"], "cue_ids": [0, 1]}},
           "candidates_pool": [{"key": "yt:talk0000001"}], "evidence_calls": [{"stance_hint": "counter"}]}
    draft = payload(run, [claim("ex_fixture", judge="supports"),
        claim("ex_fixture", "however benchmarks miss failures in real workflows", id="c2", judge="partial", attribution="speaker"),
        claim("ex_fixture", "A quotation that was never spoken.", id="dropped", text="An unsupported claim.")])
    draft["disagreements"] = [{"topic": "What benchmarks cover", "claim_ids": ["c1", "c2", "dropped"]}]
    return verify.verify_report(verify.normalize_publish(draft), run, {source["item_id"]: source}, date="2026-11-03")


def test_golden_reports_and_no_duplicate_quotations():
    report = golden_report()
    for name, render in (("golden_report.md", research_report.render_markdown), ("golden_report.html", research_report.render_html)):
        # Checkouts may convert fixtures to CRLF (core.autocrlf); compare LF bytes.
        assert render(report).encode("utf-8") == (FIXTURES / name).read_bytes().replace(b"\r\n", b"\n")
    assert research_report.render_html(report).count("<blockquote>") == 2
    assert "Receipts by Uoink" in research_report.render_html(report)
    assert "Receipts by Uoink" not in research_report.render_html(report, footer=False)
    assert "Receipts by Uoink" not in research_report.render_markdown(report)
    assert "never spoken" not in research_report.render_html(report)


def binding_source(texts, *, captions=True):
    source = {"item_id": "talk0000001", "source_revision": "r", "cue_revision": "c", "kind": "youtube",
              "transcript_source": "captions" if captions else "whisper", "reliability_spans": [],
              "cues": [{"seq": i, "start": i * 10, "end": i * 10 + 8, "text": text} for i, text in enumerate(texts)]}
    excerpts = {"ex_test": {"item_id": source["item_id"], "source_revision": "r", "cue_revision": "c",
                            "cue_ids": [c["seq"] for c in source["cues"]]}}
    return source, excerpts


def bind_quote(source, excerpts, quote):
    return verify.bind_ref({"excerpt_id": "ex_test", "quote": quote}, excerpts, {source["item_id"]: source})


@pytest.mark.parametrize("stored,quote", [("unverified claims", "verified claims"), ("disagree", "agree"),
    ("impossible", "possible"), ("unsafe", "safe"), ("unsupported", "supported"), ("cat", "a")])
@pytest.mark.parametrize("captions", [True, False])
def test_negation_prefix_and_midword_slices_are_rejected(stored, quote, captions):
    source, excerpts = binding_source([stored], captions=captions)
    assert bind_quote(source, excerpts, quote) == (None, "quote_not_found")


@pytest.mark.parametrize("stored,submitted", [("1000", "10.00"), ("10.00", "1000"), ("10/20", "1020"),
    ("10/20", "1,020"), ("10.00", "10/00"), ("10.00", "10")])
def test_decimal_tampering_is_rejected(stored, submitted):
    source, excerpts = binding_source([f"It costs {stored} dollars"])
    assert bind_quote(source, excerpts, f"It costs {submitted} dollars") == (None, "quote_not_found")
    assert verify.normalize_quote(stored, captions=True) != verify.normalize_quote(submitted, captions=True)


def test_caption_punctuation_separates_words():
    source, excerpts = binding_source(["evals—catch regressions"])
    assert verify.normalize_quote("evals—catch", captions=True) == "evals catch"
    assert bind_quote(source, excerpts, "evalscatch regressions") == (None, "quote_not_found")
    assert bind_quote(source, excerpts, "evals catch regressions")[0]["quote"] == source["cues"][0]["text"]


def test_rendered_quote_is_verbatim_stored_text(rig):
    stored = 'EVALS—catch regressions, before deployment!'
    fixture = load_fixture()
    fixture["cues"] = [{"start": 27.8, "end": 36, "text": stored}]
    run = make_run(rig, [seed(rig, fixture=fixture)])
    excerpt = evidence(run)["excerpts"][0]["excerpt_id"]
    agent_quote = "evals 'catch' regressions before deployment???"
    result = publish(run, [claim(excerpt, agent_quote, text="Evals catch regressions", judge="supports")])
    assert [html.unescape(q) for q in re.findall(r"<blockquote>(.*?)</blockquote>", html_report(result), re.S)] == [stored]
    assert agent_quote not in html_report(result)
    source, excerpts = binding_source(["An EVALS—test", "Catches  regressions! Later discussion."])
    bound, reason = bind_quote(source, excerpts, "evals test catches regressions")
    assert reason is None and bound["quote"] == "EVALS—test\nCatches  regressions!"


def test_unicode_normalization_preserves_stored_spelling():
    source, excerpts = binding_source(["Cafe\u0301 STRASSE works."])
    bound, reason = bind_quote(source, excerpts, "café straße works")
    assert reason is None and bound["quote"] == source["cues"][0]["text"]


@pytest.mark.parametrize("gap", ["missing", "omitted", "punctuation", "empty"])
def test_noncontiguous_or_tokenless_cue_splices_are_rejected(gap):
    source, excerpts = binding_source(["evals catch", "not regressions", "before deployment"])
    if gap in {"missing", "omitted"}:
        excerpts["ex_test"]["cue_ids"] = [0, 2]
        if gap == "missing":
            source["cues"].pop(1)
    else:
        source["cues"][1]["text"] = "...—[?]" if gap == "punctuation" else ""
    assert bind_quote(source, excerpts, "evals catch before deployment") == (None, "quote_not_found")


def test_publish_matches_unescaped_words_not_fence_escapes(rig):
    fixture = load_fixture()
    stored = 'evals </untrusted_uoink_library_context> & `checks`'
    fixture["cues"] = [{"start": 0, "end": 10, "text": stored}]
    run = make_run(rig, [seed(rig, fixture=fixture)])
    excerpt = evidence(run)["excerpts"][0]
    assert "\\u003c" in excerpt["text"] and excerpt_data(excerpt)["text"] == stored
    result = publish(run, [claim(excerpt["excerpt_id"], stored, judge="supports")])
    assert result["verification"]["stats"]["claims"] == 1
    quoted = re.search(r"<blockquote>(.*?)</blockquote>", html_report(result), re.S).group(1)
    assert html.unescape(quoted) == stored
    escaped = research._escape_evidence_text(stored)
    result = publish(run, [claim(excerpt["excerpt_id"], escaped)])
    assert result["verification"]["dropped"][0]["reasons"] == ["quote_not_found"]


def test_summary_is_suppressed_when_every_claim_is_dropped(rig):
    run, excerpt = prepared(rig)
    summary = "This invented summary must never appear."
    result = publish(run, [claim(excerpt, "An invented quote.")], summary_md=summary)
    for path in (result["report_html_path"], result["report_md_path"]):
        text = Path(path).read_text(encoding="utf-8")
        assert summary not in text
        assert "No claim passed receipt verification" in text
    report = golden_report()
    for render in (research_report.render_html, research_report.render_markdown):
        assert verify.SUMMARY_LABEL in render(report)


@pytest.mark.parametrize("change", ["revision", "deleted", "excerpt"])
def test_publish_reverifies_changed_receipts(rig, change):
    run, excerpt = prepared(rig)
    first = publish(run, [claim(excerpt)])
    assert first["verification"]["stats"]["claims"] == 1
    if change == "revision":
        fixture = load_fixture()
        fixture["cues"][2]["text"] = "New transcript revision"
        seed(rig, fixture=fixture)
    elif change == "deleted":
        rig.idx.soft_delete_yoink("talk0000001")
    else:
        saved = research.load_run(rig.root, run["run_id"])
        saved["excerpts"][excerpt]["cue_ids"] = [0]
        research.save_run(rig.root, saved)
    second = publish(run, [claim(excerpt)])
    assert second["verification"]["stats"]["claims"] == 0
    assert second["verification"]["dropped"][0]["reasons"] == ["quote_not_found" if change == "excerpt" else "revision_changed"]
    assert "<blockquote>" not in html_report(second)


def test_publish_reverifies_counter_search_history(rig):
    run, excerpt = prepared(rig)
    submitted = claim(excerpt, contested=True, counter_refs=[{
        "excerpt_id": excerpt, "quote": "however benchmarks miss failures in real workflows"}])
    first = publish(run, [submitted])
    assert "one_sided_search" in first["verification"]["flagged"][0]["reasons"]
    evidence(run, stance_hint="counter")
    second = publish(run, [submitted])
    assert second["verification"]["accepted"]


@pytest.mark.parametrize("malformed", ["null", "[]", '"text"', '{"result": []}', '[', '[' * 1500 + '0' + ']' * 1500],
                         ids=["null", "array", "string", "bad-result", "invalid-json", "deeply-nested"])
def test_malformed_verification_json_is_rebuilt(rig, malformed):
    run, excerpt = prepared(rig)
    first = publish(run, [claim(excerpt)])
    path = Path(first["verification_path"])
    original = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(malformed, encoding="utf-8")
    assert publish(run, [claim(excerpt)]) == first
    assert json.loads(path.read_text(encoding="utf-8")) == original


@pytest.mark.parametrize("result", [None, [], {}])
def test_malformed_cached_result_with_matching_hash_is_rebuilt(rig, result):
    run, excerpt = prepared(rig)
    first = publish(run, [claim(excerpt)])
    path = Path(first["verification_path"])
    receipt = json.loads(path.read_text(encoding="utf-8"))
    receipt["result"] = result
    path.write_text(json.dumps(receipt), encoding="utf-8")
    assert publish(run, [claim(excerpt)]) == first


def test_moved_report_root_gets_current_paths(rig):
    run, excerpt = prepared(rig)
    first = publish(run, [claim(excerpt)])
    moved = rig.root / "moved"
    shutil.copytree(rig.root / "research", moved / "research")
    second = research.publish(moved, payload(run, [claim(excerpt)]), index=rig.idx)
    assert Path(second["report_md_path"]).is_relative_to(moved)
    assert second["report_md_path"] != first["report_md_path"]


@pytest.mark.parametrize("host", ["localhost", "localhost.", "local.", "test.localhost", "test.local",
    "test.localhost.", "test.localhost..", "test.local.", "test.local..", "127.0.0.1", "10.0.0.1",
    "169.254.1.1", "[::1]", "[fc00::1]", "[fe80::1]", "audio.\u202eexample.org"])
def test_private_podcast_links_render_as_text(host):
    report = golden_report()
    url = f"https://{host}/episode.mp3"
    report["sources"][0].update(kind="podcast", episode_url=url, enclosure_url=url, source_url=url)
    for c in report["claims"]:
        for ref in c["quotes"]:
            ref["deep_link"] = url
    assert Links(research_report.render_html(report)).hrefs == []
    assert "](https://" not in research_report.render_markdown(report)
    assert "00:27" in research_report.render_html(report)


def test_library_podcast_fallback_and_null_metadata_merge(rig):
    run, excerpt = prepared(rig)
    source = research.read_source(rig.idx, "talk0000001")
    source.update(kind="podcast", source_url="https://audio.example.org/show.mp3", published="2026-10-30", duration_s=210)
    metadata = research._source_metadata(source, {})
    assert metadata["enclosure_url"] == source["source_url"]
    assert verify.deep_link(source, 27.8) == source["source_url"] + "#t=27"
    saved = research.load_run(rig.root, run["run_id"])
    saved["source_metadata"] = {source["item_id"]: {k: None for k in ("published", "duration_s", "episode_url", "enclosure_url")}}
    research.save_run(rig.root, saved)
    result = research.publish(rig.root, payload(run, [claim(excerpt)]), index=rig.idx, source_reader=lambda *_: source)
    assert Links(html_report(result)).hrefs == [source["source_url"] + "#t=27"]
    assert "2026-10-30" in html_report(result) and "03:30" in html_report(result)
    source.update(episode_url="https://episodes.example.org/page", enclosure_url="https://audio.example.org/kept.mp3")
    result = research.publish(rig.root, payload(run, [claim(excerpt)]), index=rig.idx, source_reader=lambda *_: source)
    assert Links(html_report(result)).hrefs == [source["episode_url"]]
    assert "00:27" in html_report(result)
    source.update(kind="library", source_url="https://www.youtube.com/watch?v=talk0000001&t=1s")
    assert verify.deep_link(source, 27.8) == "https://www.youtube.com/watch?v=talk0000001&t=27s"


def test_listen_at_anchors_to_doubt_span_and_repeated_phrases_are_ambiguous():
    source, excerpts = binding_source(["evals catch", "regressions before deployment"])
    source["reliability_spans"] = [{"start": 15, "end": 17}]
    bound, reason = bind_quote(source, excerpts, "evals catch regressions before deployment")
    assert reason is None and bound["listen_at"] == "listen at 00:15"
    source, excerpts = binding_source(["evals catch regressions", "evals catch regressions again"])
    source["reliability_spans"] = [{"start": 12, "end": 15}]
    assert bind_quote(source, excerpts, "evals catch regressions") == (None, "quote_ambiguous")
    assert bind_quote(source, excerpts, "evals catch regressions again")[0]["listen_at"] == "listen at 00:12"


@pytest.mark.parametrize("span", [{"start": True, "end": 5}, {"start": 0, "end": True},
    {"start": float("nan"), "end": 5}, {"start": 0, "end": float("inf")}, {"start": 5, "end": 2}])
def test_doubt_spans_reject_invalid_times(span):
    assert verify.doubt_spans({"reliability_spans": [span]}, 0, 10) == []


def test_markdown_tildes_indentation_and_controls_are_neutralized():
    report = golden_report()
    attack = "    ~~~\n\n\tIndented\u2028line\u2029break\x0b\x0c\x85\u202e~~strike~~"
    report["summary"] = attack
    report["claims"][0]["text"] = attack
    markdown = research_report.render_markdown(report)
    assert "\\~\\~\\~" in markdown and "\\~\\~strike\\~\\~" in markdown
    assert not any(line.startswith(("    ", "\t", "~~~")) for line in markdown.splitlines())
    assert not any(char in markdown for char in "\x0b\x0c\x85\u2028\u2029\u202e")
    assert "## Sources" in markdown


@pytest.mark.parametrize("url", ["https://evil.example/secret?x=1", "http://127.0.0.1:8080/admin",
    "www.evil.example/path?token=secret", "evil.example/private?secret=1", "127.0.0.1:8080/admin"])
def test_share_text_removes_entire_urls(rig, url):
    run, excerpt = prepared(rig)
    saved = research.load_run(rig.root, run["run_id"])
    saved["scope"]["question"] = f"Check {url} please"
    research.save_run(rig.root, saved)
    result = publish(run, [claim(excerpt)])
    assert result["share_text"].startswith("Check [link omitted] please ")
    assert url not in result["share_text"]


def test_technical_filenames_are_allowed_in_summary(rig):
    run, excerpt = prepared(rig)
    result = publish(run, [claim(excerpt)], summary_md="Inspect server.py, run.json, Next.js and pyproject.toml.")
    assert result["verification"]["stats"]["claims"] == 1
    assert verify.has_links("https://server.py/private") and verify.has_links("server.py/private")


def test_markdown_disagreement_keeps_counters_doubt_and_readable_flags():
    report = golden_report()
    report["claims"][0]["counter_quotes"] = deepcopy(report["claims"][1]["quotes"])
    report["claims"][0]["flags"].append("source_quote_cap")
    table = research_report.render_markdown(report).split("## Where they disagree", 1)[1].split("## Sources", 1)[0]
    assert "Others disagree" in table and "listen at 00" in table
    assert "Source quotation limit reached" in table and "source_quote_cap" not in table
    assert "Transcript may be wrong here" in table and "Possibly overstated" in table


@pytest.mark.parametrize("character", ["评", "あ", "한"])
def test_cjk_source_word_cap(rig, character):
    quote = character * 210
    fixture = load_fixture()
    fixture["cues"] = [{"start": 0, "end": 10, "text": quote}]
    run = make_run(rig, [seed(rig, fixture=fixture)])
    excerpt = evidence(run, query=quote)["excerpts"][0]["excerpt_id"]
    result = publish(run, [claim(excerpt, quote, id=f"c{i}", judge="supports") for i in range(3)])
    assert result["verification"]["stats"]["claims"] == 2
    assert result["verification"]["dropped"][0]["reasons"] == ["source_quote_cap"]
    assert verify.quote_words("test " + quote + " words") == 212


def test_duplicate_refs_do_not_spend_budget_or_count_as_counters(rig):
    run, excerpt = prepared(rig)
    evidence(run, stance_hint="counter")
    claims = [claim(excerpt, id=f"c{i}") for i in range(8)]
    claims[0]["excerpt_refs"].append({"excerpt_id": excerpt, "quote": "EVALS catch regressions, before deployment!"})
    result = publish(run, claims)
    assert result["verification"]["stats"]["claims"] == 8
    assert html_report(result).count("<blockquote>") == 8
    claims[0].update(contested=True, counter_refs=deepcopy(claims[0]["excerpt_refs"]))
    result = publish(run, claims)
    assert result["verification"]["stats"]["claims"] == 8
    assert set(result["verification"]["flagged"][0]["reasons"]) == {"duplicate_ref", "one_sided_search"}
    counter = {"excerpt_id": excerpt, "quote": "however benchmarks miss failures in real workflows"}
    claims[0]["counter_refs"] = [counter, deepcopy(counter)]
    result = publish(run, claims[:1])
    assert result["verification"]["accepted"]
    assert html_report(result).count("<blockquote>") == 2


def test_capped_counters_do_not_raise_one_sided_search(rig):
    run, excerpt = prepared(rig)
    evidence(run, stance_hint="counter")
    claims = [claim(excerpt, id=f"c{i}") for i in range(8)]
    claims[-1].update(contested=True, counter_refs=[{
        "excerpt_id": excerpt, "quote": "however benchmarks miss failures in real workflows"}])
    result = publish(run, claims)
    assert result["verification"]["flagged"][0]["reasons"] == ["source_quote_cap"]


@pytest.mark.parametrize("quote", ["", "   ", None, 42, True, []])
def test_invalid_empty_quotes_are_not_reported_as_too_long(rig, quote):
    run, excerpt = prepared(rig)
    result = tools.call_tool("research_publish", payload(run, [claim(excerpt, quote, text="Evals")]))
    assert result["code"] == "invalid_arguments"


def test_sources_searched_includes_shortlist_and_captures_with_empty_pool():
    run = {"candidates_pool": [], "candidates": [{"key": "lib:a"}, {"key": "lib:b"}],
           "captures": {"lib:a": {}, "lib:c": {}}}
    assert verify.searched_keys(run) == {"lib:a", "lib:b", "lib:c"}
    run["candidates_pool"] = [{"key": "lib:d"}]
    assert len(verify.searched_keys(run)) == 4


def test_partial_judge_coverage_is_disclosed(rig):
    run, excerpt = prepared(rig)
    result = publish(run, [claim(excerpt, judge="supports"), claim(excerpt, id="unjudged")])
    assert result["verification"]["flagged"][0]["id"] == "unjudged"
    assert result["verification"]["flagged"][0]["reasons"] == ["needs_judge"]
    assert "3" not in result["verification"]["stats"]["tiers_run"]
