"""3.18 reader lane: what the pasted-link extractor now keeps, and how it says
it could not save a page. Synthetic pages only, offline."""
from __future__ import annotations

import io
import json
import socket

import pytest

import article_extractor as article
import page_extractor as pages

URL = "https://news.example.org/2026/notes"
PROSE = ("The harbor trust rebuilt the ferry ramp after the autumn storm, and the work took six weeks. "
         "Records from April show the crews measured the quay wall at least ten times. ")


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("reader tests must not access the network")
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(pages, "_CRAWL4AI_AVAILABLE", False)


def page(body, head="<title>Ferry notes</title>"):
    return f"<!doctype html><html><head>{head}</head><body><article>{body}</article></body></html>"


def md(body, **kw):
    result = article.extract(page(body, **kw), URL)
    assert result["ok"], result
    return result["markdown"]


def test_code_blocks_keep_their_language_and_drop_line_numbers():
    out = md(f"<p>{PROSE * 2}</p>"
             '<pre><code class="language-python">x = 1</code></pre>'
             '<div class="highlight highlight-source-shell"><pre>pip install quill</pre></div>'
             '<div class="codehilite" data-lang="yaml"><table><tr><td class="linenos"><pre>1\n2</pre></td>'
             '<td class="code"><pre>a: 1\nb: 2</pre></td></tr></table></div>')
    assert "```python\nx = 1\n```" in out
    assert "```shell\npip install quill\n```" in out
    assert "```yaml\na: 1\nb: 2\n```" in out and "1\n2\n```" not in out


def test_images_lazy_sources_and_captions():
    out = md(f"<p>{PROSE * 2}</p>"
             '<figure><img src="data:image/gif;base64,R0lGOD" data-src="/img/quay.jpg" alt="The quay at dusk">'
             "<figcaption>The quay after the repair</figcaption></figure>"
             '<p><img src="/px.gif" width="1" height="1" alt=""></p>'
             '<table><caption>Ferry times</caption><tr><th>Day</th><th>First</th></tr>'
             "<tr><td>Monday</td><td>6:10</td></tr></table>")
    assert "![The quay at dusk](https://news.example.org/img/quay.jpg)" in out
    assert "\n\nThe quay after the repair\n\n" in out
    assert "px.gif" not in out and "data:" not in out
    assert "Ferry times\n\n| Day | First |\n| --- | --- |\n| Monday | 6:10 |" in out


def test_footnotes_and_math():
    out = md(f"<p>{PROSE} The ramp held.<sup><a href=\"#fn1\" id=\"fnref1\">1</a></sup></p><p>{PROSE}</p>"
             '<p>The ratio <math alttext="N = f / D"><mi>N</mi></math> is fixed.</p>'
             '<math display="block"><semantics><mi>x</mi><annotation encoding="application/x-tex">'
             "E = mc^2</annotation></semantics></math>"
             '<section class="footnotes"><ol><li id="fn1"><p>Measured at low tide. '
             '<a href="#fnref1" class="footnote-back">↩</a></p></li></ol></section>')
    assert "The ramp held.[^1]" in out
    assert out.endswith("\n[^1]: Measured at low tide.") and "↩" not in out
    assert "$N = f / D$" in out and "$$E = mc^2$$" in out


def test_layout_tables_become_blocks():
    cell = (f"<h2>This week</h2><p>{PROSE * 2}</p>"
            "<ul><li>Rye returns Thursday</li><li>Workshop has places</li></ul>")
    out = md(f'<table role="presentation"><tr><td><table><tr><td>{cell}</td></tr></table></td></tr></table>')
    assert "## This week" in out and "- Rye returns Thursday" in out and "| " not in out


def test_question_and_every_answer_are_kept():
    def post(cls, words):
        return (f'<div class="{cls}"><div class="votecell"><span>3</span></div><div class="cell">'
                f'<div class="s-prose"><p>{words} {PROSE}</p><p>{PROSE}</p></div></div></div>')
    out = md('<div id="mainbar"><h1>Why does the ramp creak?</h1>' + post("question", "Asked:")
             + post("answer", "First answer:") + post("answer", "Second answer:") + "</div>")
    assert "Asked:" in out and "First answer:" in out and "Second answer:" in out


def test_title_loses_the_site_suffix_and_recipe_metadata_is_read():
    head = ('<title>Overnight rye loaf | Larder Notes</title><meta property="og:site_name" content="Larder Notes">'
            '<script type="application/ld+json">{"@type": "Recipe", "name": "Overnight rye loaf", '
            '"author": {"@type": "Person", "name": "Tamsin Orrow"}, "datePublished": "2026-02-11"}</script>')
    meta = article.extract(page(f"<p>{PROSE * 3}</p>", head=head), URL)["metadata"]
    assert meta["title"] == "Overnight rye loaf" and meta["site_name"] == "Larder Notes"
    assert meta["author"] == "Tamsin Orrow" and meta["published_date"] == "2026-02-11"
    wiki = article.extract(page(f"<h1>Alder Bend</h1><p>{PROSE * 3}</p>", head="<title>Alder Bend | Valleypedia</title>"),
                           URL)["metadata"]
    assert wiki["title"] == "Alder Bend" and wiki["site_name"] == "Valleypedia"


def response(raw):
    body = io.BytesIO(raw.encode())
    body.status = 200
    return body


@pytest.mark.parametrize("body,state", [
    (f"<h1>Ferry fares rise</h1><p>{PROSE * 3}</p><h2>Keep reading with a subscription</h2>"
     "<p>Subscribe to continue reading. Subscribers get every story and the archive.</p>"
     '<p>Already a subscriber? <a href="/login">Sign in</a></p>', "wall"),
    ("<h1>Checking your browser before accessing news.example.org</h1><p>This process is automatic.</p>"
     "<p>Please enable JavaScript and cookies to continue.</p><p>Request reference 7f3a91c2</p>", "wall"),
    ("<p>Menu</p>", "thin"),
])
def test_walls_teasers_and_thin_pages_say_so_and_offer_the_browser(body, state):
    result = pages.extract_page(None, URL, enforce_allowlist=False, http_open=lambda *a, **k: response(page(body)))
    assert not result["ok"] and result["code"] == "article_body_not_found"
    assert result["page_state"] == state and result["open_url"] == URL
    assert result["error"] == pages.PAGE_STATE_COPY[state]
    assert "Uoink this page" in result["error"] and "nothing was saved" in result["error"]
    assert "—" not in result["error"] and ";" not in result["error"]


def test_dashboard_row_says_what_the_fetch_got_and_offers_the_page():
    from test_dashboard_runthrough_fixes import run_js
    copy = pages.PAGE_STATE_COPY["wall"]
    result = run_js("""(() => {
      refreshActivity = () => {};
      const run = {id: "run1", url: "https://news.example.org/a", label: "Article / web page", state: "running",
        startedAt: new Date().toISOString(), jobIdsAtStart: new Set(), jobId: "", ref: ""};
      state.libraryRuns = [run];
      failLibraryRun(run, {data: {ok: false, code: "article_body_not_found", page_state: "wall",
        open_url: "https://news.example.org/a", error: %s}});
      const plain = {id: "run2", url: "javascript:alert(1)", label: "Link", state: "running",
        startedAt: new Date().toISOString(), jobIdsAtStart: new Set(), jobId: "", ref: ""};
      state.libraryRuns.push(plain);
      failLibraryRun(plain, {data: {ok: false, code: "article_body_not_found", page_state: "thin",
        open_url: "javascript:alert(1)", error: "Too little text."}});
      const rows = libraryCaptureItems();
      return {wall: rows.find((r) => r.key === "run1"), thin: rows.find((r) => r.key === "run2")};
    })()""" % json.dumps(copy))
    assert result["wall"]["detail"] == copy
    assert ('<a class="button" data-source-link href="https://news.example.org/a" target="_blank" '
            'rel="noreferrer">Open page</a>') in result["wall"]["actions"]
    assert "data-library-retry" in result["wall"]["actions"]
    assert "Open page" not in result["thin"]["actions"] and result["thin"]["detail"] == "Too little text."


def test_a_full_article_with_a_subscribe_box_is_still_saved():
    paragraphs = "".join(f"<p>On day {i} the crews checked berth {i}. The ramp at berth {i} held its line, "
                         f"and the tide gauge read {i + 2} metres at dawn.</p>" for i in range(30))
    body = (f"<h1>Ferry fares rise</h1>{paragraphs}"
            "<p>Subscribe to continue reading stories like this. Already a subscriber? Sign in.</p>")
    result = pages.extract_page(None, URL, enforce_allowlist=False, http_open=lambda *a, **k: response(page(body)))
    assert result["ok"], result


def test_review_round_pixels_math_footnotes_and_inline_names():
    out = md(f"<p>{PROSE} As <span class=\"author-name\">Mira Holt</span> wrote, the ramp held."
             '<sup><a href="#user-content-fn-100" id="user-content-fnref-100">[100]</a></sup></p>'
             f"<p>{PROSE}</p>"
             '<p><img src="https://cdn.example.org/a.png" width="1px" alt="a">'
             '<img src="https://www.facebook.com/tr?id=1&amp;ev=PageView" alt="b">'
             '<img src="https://stats.example.org/pixel.gif" alt="c">'
             '<img src="https://news.example.org/blank.gif" data-src="/img/real.jpg" alt="Real"></p>'
             '<p>Then <math alttext="a &lt; b"><mi>a</mi></math> holds.</p>'
             r'<math display="block" alttext="a = 1 \\&#10;b = 2"><mi>a</mi></math>'
             '<section class="footnotes"><ol><li id="user-content-fn-100"><p>Low tide.</p></li></ol></section>')
    assert "Mira Holt wrote" in out
    assert "[^100]" in out and out.endswith("[^100]: Low tide.")
    assert "a.png" not in out and "facebook.com/tr" not in out and "pixel.gif" not in out
    assert "![Real](https://news.example.org/img/real.jpg)" in out and "blank.gif" not in out
    assert r"$a \lt b$" in out and "<" not in out
    assert "$$\na = 1 " + "\\\\" + "\nb = 2\n$$" in out
