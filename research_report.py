"""Offline, escaped research reports. This module only renders verified data."""
from __future__ import annotations

import html
import re
import unicodedata
from urllib.parse import quote, urlsplit

from research_verify import EMPTY_SUMMARY, SUMMARY_LABEL, time_label

BASE_LINK_HOSTS = frozenset({"youtube.com", "www.youtube.com", "youtu.be", "news.ycombinator.com"})
FOOTER = "Receipts by Uoink, local and free: uoink.app"
_FLAG_TEXT = {
    "speaker_unconfirmed": "Speaker unconfirmed; channel attribution",
    "asr_doubt": "Transcript may be wrong here",
    "overstated": "Possibly overstated", "low_overlap": "Low claim/quote overlap",
    "needs_judge": "Needs a judge pass", "one_sided_search": "One-sided search",
    "source_quote_cap": "Source quotation limit reached",
    "quote_not_found": "Quote not found in the stored transcript",
    "excerpt_unknown": "Excerpt is not saved in this run",
    "revision_changed": "Source changed or is no longer available",
    "quote_spans_too_far": "Quote spans more than two minutes",
    "quote_too_long": "Quote exceeds the character limit",
    "quote_ambiguous": "Quote matches more than one passage",
    "duplicate_ref": "Counter-evidence repeats a supporting quote",
    "too_many_quotes": "Too many quotation references",
    "judge_no": "Judge found that the quote does not support the claim",
}


def safe_link(value, source):
    """Only HTTPS on fixed hosts or this item's stored podcast hosts."""
    from research import _url

    if not _url(value) or "\\" in value:
        return None
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.port not in (None, 443)):
            return None
        hosts = set(BASE_LINK_HOSTS)
        if source.get("kind") == "podcast":
            for field in ("episode_url", "enclosure_url", "source_url"):
                stored = urlsplit(_url(source.get(field)))
                if stored.scheme == "https" and stored.hostname and not stored.username:
                    hosts.add(stored.hostname.lower())
        return value if parsed.hostname.lower() in hosts else None
    except ValueError:
        return None


def _html(value):
    # Encoding '=' also keeps attribute-like injection text visibly inert in
    # the exported bytes, while preserving the verbatim text in the browser.
    return html.escape(str(value if value is not None else ""), quote=True).replace("=", "&#61;")


def _md(value):
    value = "".join(" " if c.isspace() or unicodedata.category(c) in {"Cc", "Cf", "Zl", "Zp"} else c
                    for c in str(value if value is not None else "")).strip()
    out = []
    for char in value:
        if char == "&":
            out.append("&amp;")
        elif char in ":.@":
            # Prevent GFM bare URL/email autolinks in any untrusted text.
            out.append(f"&#{ord(char)};")
        elif char in "[]()*_`<>#|\\-+!~":
            out.append("\\" + char)
        else:
            out.append(char)
    return "".join(out)


def _chip(ref):
    return f'{ref["time_label"]} · {ref["channel"]}, "{ref["title"]}"'


def _groups(report):
    groups = {}
    for claim in report["claims"]:
        groups.setdefault(claim["section"], []).append(claim)
    return groups.items()


def _transcription(source):
    return {"captions": "Captions", "whisper": "Local Whisper"}.get(source.get("transcript_source"), "Unknown")


def _duration(source):
    duration = source.get("duration_s")
    return time_label(duration) if isinstance(duration, (int, float)) else "Unknown"


def _count_line(report):
    stats = report["verification"]["stats"]
    return f'{stats["claims"]} claims from {stats["distinct_sources"]} sources, {stats["dropped"]} dropped'


def render_markdown(report, *, footer=False):
    sources = {s["item_id"]: s for s in report["sources"]}

    def chip(ref):
        label = _md(_chip(ref))
        link = safe_link(ref["deep_link"], sources[ref["item_id"]])
        # Percent-encode Markdown destination delimiters, retaining query syntax.
        return f'[{label}]({quote(link, safe=":/?&=%#_~-" )})' if link else label

    def claim_lines(claim, *, quotes=True):
        lines = [_md(claim["text"]), ""]
        for kind, refs in (("", claim["quotes"]), ("Others disagree: ", claim["counter_quotes"])):
            for ref in refs:
                lines.extend([kind + chip(ref), ""])
                if quotes:
                    lines.extend(["> " + _md(ref["quote"]), ""])
                if ref.get("listen_at"):
                    lines.extend([_md("Transcript may be wrong here; " + ref["listen_at"]), ""])
        lines.extend(["Channel attribution.", ""])
        if claim["flags"]:
            lines.extend([_md("; ".join(_FLAG_TEXT[f] for f in claim["flags"])), ""])
        return lines

    lines = ["# " + _md(report["title"]), "", _md(report["question"]), "",
             _md(report["date"] + " · " + _count_line(report)), "", "## " + SUMMARY_LABEL, ""]
    summary = report["summary"] if report["claims"] else EMPTY_SUMMARY
    for paragraph in re.split(r"\n\s*\n", summary):
        if paragraph.strip():
            lines.extend([_md(paragraph), ""])
    for section, claims in _groups(report):
        lines.extend(["## " + _md(section), ""])
        for claim in claims:
            lines.extend(claim_lines(claim))
    lines.extend(["## Where they disagree", ""])
    by_id = {c["id"]: c for c in report["claims"]}
    if not report["disagreements"]:
        lines.extend(["No disagreement groups supplied.", ""])
    for group in report["disagreements"]:
        lines.extend(["### " + _md(group["topic"]), ""])
        entries = [by_id[i] for i in group["claim_ids"]]
        lines.extend(["| " + " | ".join(_md(c["id"]) for c in entries) + " |",
                      "| " + " | ".join("---" for _ in entries) + " |",
                      "| " + " | ".join(" ".join(line for line in claim_lines(c, quotes=False) if line)
                                        for c in entries) + " |", ""])
    lines.extend(["## Sources", "", "| Title | Channel | Date | Duration | Transcript | Claims |",
                  "| --- | --- | --- | --- | --- | --- |"])
    for source in report["sources"]:
        lines.append("| " + " | ".join(_md(v) for v in (source.get("title"), source.get("channel"),
            source.get("published") or "Unknown", _duration(source), _transcription(source), source["claim_count"])) + " |")
    stats = report["verification"]["stats"]
    lines.extend(["", "## Method", "", f'Sources searched: {report["sources_searched"]}. '
                  f'Tiers run: {", ".join(stats["tiers_run"])}.', "",
                  f'{stats["accepted"]} accepted, {stats["flagged"]} flagged, {stats["dropped"]} dropped. '
                  f'{stats["distinct_channels"]} channels cited; largest channel share: {stats["max_channel_share"]:.0%}.', "",
                  "Receipt checks bind quotations to stored transcripts; they do not establish that a claim is true.", "",
                  f'### Didn\'t make the cut ({stats["dropped"]})', ""])
    for claim in report["verification"]["dropped"]:
        lines.extend(["- " + _md(claim["text"] + " — " + ", ".join(_FLAG_TEXT[r] for r in claim["reasons"])), ""])
    if footer:
        lines.extend([_md(FOOTER), ""])
    return "\n".join(lines).rstrip() + "\n"


_CSS = """:root{color-scheme:light;--bg:#fff;--text:#171717;--muted:#525252;
--border:#d4d4d4;--green:#166534;--green-bg:#f0fdf4;--amber:#854d0e;--amber-bg:#fffbeb;
--grey:#404040;--grey-bg:#f5f5f5}*{box-sizing:border-box}body{margin:0;background:var(--bg);
color:var(--text);font:16px/1.6 system-ui,sans-serif}main{max-width:960px;margin:auto;padding:40px 24px}
h1{font-size:2rem;line-height:1.2;text-wrap:balance}h2{font-size:1.44rem;margin-top:2.4rem}
h3{font-size:1.2rem}p,blockquote{max-width:72ch}header{border-bottom:2px solid var(--text);padding-bottom:24px}
.meta{color:var(--muted)}.claim{padding:12px 0 24px;border-bottom:1px solid var(--border)}
.chip{display:inline-block;padding:3px 9px;margin:3px 3px 3px 0;border-radius:4px;font-size:.875rem;
overflow-wrap:anywhere;color:var(--green);background:var(--green-bg)}.amber{color:var(--amber);background:var(--amber-bg)}
.grey{color:var(--grey);background:var(--grey-bg)}a:focus-visible,summary:focus-visible{outline:2px solid var(--text);outline-offset:3px}
blockquote{margin:12px 0;padding:0 0 0 16px;border-left:3px solid var(--border);white-space:pre-wrap;overflow-wrap:anywhere}
.disagreement{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:24px}
.table-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:.875rem}th,td{text-align:left;
vertical-align:top;padding:10px 8px;border-bottom:1px solid var(--border)}.method{margin-top:40px;padding:24px;background:var(--grey-bg)}
.method h2{margin-top:0}summary{cursor:pointer}footer{margin-top:32px;font-size:.875rem;color:var(--muted)}
@media(max-width:600px){main{padding:24px 16px}.disagreement{grid-template-columns:1fr}}
@media print{main{max-width:none;padding:0}.claim{break-inside:avoid}.table-wrap{overflow:visible}}"""


def render_html(report, *, footer=True):
    sources = {s["item_id"]: s for s in report["sources"]}

    def chip(ref, flags=()):
        label = _html(_chip(ref))
        link = safe_link(ref["deep_link"], sources[ref["item_id"]])
        style = "chip amber" if ref["asr_doubt"] or {"overstated", "low_overlap"}.intersection(flags) else "chip"
        return (f'<a class="{style}" href="{_html(link)}" rel="noreferrer">{label}</a>' if link
                else f'<span class="{style}">{label}</span>')

    def claim_html(claim, *, quotes=True):
        parts = ['<article class="claim">', "<p>" + _html(claim["text"]) + "</p>"]
        for prefix, refs in (("", claim["quotes"]), ("Others disagree: ", claim["counter_quotes"])):
            for ref in refs:
                parts.append("<div>" + _html(prefix) + chip(ref, claim["flags"]) + "</div>")
                if quotes:
                    parts.append("<blockquote>" + _html(ref["quote"]) + "</blockquote>")
                if ref.get("listen_at"):
                    parts.append('<p class="chip amber">' + _html("Transcript may be wrong here; " + ref["listen_at"]) + "</p>")
        parts.append('<span class="chip grey">Channel attribution</span>')
        for flag in claim["flags"]:
            style = "grey" if flag == "speaker_unconfirmed" else "amber"
            parts.append(f'<span class="chip {style}">{_html(_FLAG_TEXT[flag])}</span>')
        parts.append("</article>")
        return "\n".join(parts)

    parts = ['<!doctype html>', '<html lang="en"><head><meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width, initial-scale=1">',
             '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">',
             "<title>" + _html(report["title"]) + "</title>", "<style>" + _CSS + "</style></head><body><main>",
             "<header><h1>" + _html(report["title"]) + "</h1><p>" + _html(report["question"]) + "</p>",
             '<p class="meta">' + _html(report["date"] + " · " + _count_line(report)) + "</p></header>",
             "<section><h2>" + SUMMARY_LABEL + "</h2>"]
    summary = report["summary"] if report["claims"] else EMPTY_SUMMARY
    parts.extend("<p>" + _html(p.strip()) + "</p>" for p in re.split(r"\n\s*\n", summary) if p.strip())
    parts.append("</section>")
    for section, claims in _groups(report):
        parts.append("<section><h2>" + _html(section) + "</h2>")
        parts.extend(claim_html(c) for c in claims)
        parts.append("</section>")
    parts.append("<section><h2>Where they disagree</h2>")
    by_id = {c["id"]: c for c in report["claims"]}
    if not report["disagreements"]:
        parts.append("<p>No disagreement groups supplied.</p>")
    for group in report["disagreements"]:
        parts.append("<h3>" + _html(group["topic"]) + '</h3><div class="disagreement">')
        parts.extend(claim_html(by_id[i], quotes=False) for i in group["claim_ids"])
        parts.append("</div>")
    parts.append('</section><section><h2>Sources</h2><div class="table-wrap"><table><thead><tr>')
    parts.extend("<th scope=\"col\">" + label + "</th>" for label in ("Title", "Channel", "Date", "Duration", "Transcript", "Claims"))
    parts.append("</tr></thead><tbody>")
    for source in report["sources"]:
        parts.append("<tr>" + "".join("<td>" + _html(v) + "</td>" for v in (
            source.get("title"), source.get("channel"), source.get("published") or "Unknown",
            _duration(source), _transcription(source), source["claim_count"])) + "</tr>")
    stats = report["verification"]["stats"]
    parts.extend(["</tbody></table></div></section>", '<section class="method"><h2>Method</h2>',
                  "<p>" + _html(f'Sources searched: {report["sources_searched"]}. Tiers run: {", ".join(stats["tiers_run"])}.') + "</p>",
                  "<p>" + _html(f'{stats["accepted"]} accepted, {stats["flagged"]} flagged, {stats["dropped"]} dropped. '
                    f'{stats["distinct_channels"]} channels cited; largest channel share: {stats["max_channel_share"]:.0%}.') + "</p>",
                  "<p>Receipt checks bind quotations to stored transcripts; they do not establish that a claim is true.</p>",
                  "<details><summary>" + _html(f'Didn\'t make the cut ({stats["dropped"]})') + "</summary><ul>"])
    for claim in report["verification"]["dropped"]:
        parts.append("<li>" + _html(claim["text"] + " — " + ", ".join(_FLAG_TEXT[r] for r in claim["reasons"])) + "</li>")
    parts.append("</ul></details></section>")
    if footer:
        parts.append("<footer>" + _html(FOOTER) + "</footer>")
    parts.append("</main></body></html>")
    return "\n".join(parts) + "\n"
