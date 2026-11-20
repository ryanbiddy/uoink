"""Build the reader benchmark fixtures: made-up pages in real layouts plus gold.

Every word here is synthetic. No text is copied from a real site, and every
name, handle and domain is invented (example.* and .test only). Each fixture
is written once as `<name>.html` (the bytes a plain fetch of the URL gets) and,
when a browser shows something else (a JavaScript shell, a wall the user is
signed in past), `<name>.rendered.html` (the page after it rendered in the
user's tab). `<name>.gold.json` says what a reader should keep and drop.

Regenerate after editing:  python tests/fixtures/reader/make_fixtures.py
tests/test_reader_benchmark.py checks the committed files match this script.
"""
from __future__ import annotations

from html import escape
import json
from pathlib import Path
import random
import re
import sys

HERE = Path(__file__).resolve().parent

# ---- synthetic prose --------------------------------------------------------
TOPICS = {
    "harbor": dict(
        n=["lantern", "quay wall", "ferry ramp", "net loft", "tide gauge", "boathouse", "mooring post",
           "signal mast", "fish market roof", "breakwater", "rope store", "harbor office"],
        place=["the north quay", "Gullhaven", "the old customs house", "the east breakwater", "Saltmarsh Lane",
               "the ferry slip"],
        group=["the harbor trust", "volunteer crews", "the ferry pilots", "the net menders", "the lantern committee",
               "two apprentices"],
        past=["repaired", "repainted", "measured", "rebuilt", "logged", "tested", "reopened", "sorted", "mapped",
              "restored"],
        inf=["replace", "inspect", "rig", "sand", "document", "patch", "light", "clear", "survey", "haul"],
        adj=["salt-worn", "heavy", "fragile", "brass", "weathered", "bright", "narrow", "crooked", "patient",
             "costly"],
        event=["the autumn storm", "a spring tide", "the winter closure", "the regatta", "a long fog",
               "the annual survey"]),
    "orchard": dict(
        n=["pear row", "cider press", "grafting bench", "frost fan", "packing shed", "seed ledger", "hedge line",
           "beehive stand", "pruning ladder", "storage cellar", "irrigation valve", "apple crate"],
        place=["the upper terrace", "Millbrook", "the south slope", "the old barn", "Cobble Hill",
               "the river field"],
        group=["the cooperative", "seasonal pickers", "the grafting class", "three neighbours", "the cellar team",
               "the orchard board"],
        past=["pruned", "grafted", "pressed", "stored", "counted", "replanted", "mended", "sorted", "labelled",
              "cleared"],
        inf=["thin", "graft", "press", "store", "count", "replant", "mend", "label", "water", "shelter"],
        adj=["late", "sturdy", "bitter", "knotted", "early", "damp", "crisp", "uneven", "generous", "stubborn"],
        event=["the first frost", "a dry summer", "the harvest fair", "a hail storm", "bud break",
               "the pressing week"]),
    "transit": dict(
        n=["tram stop", "signal box", "ticket machine", "depot roof", "timetable board", "track switch",
           "night service", "bike rack", "platform canopy", "overhead wire", "fare reader", "route map"],
        place=["Ferrow Square", "the canal depot", "Eastgate", "the hospital loop", "Market Row", "the bridge stop"],
        group=["the transit board", "night drivers", "the depot crew", "rider panels", "the signal engineers",
               "a student survey team"],
        past=["rerouted", "upgraded", "inspected", "timed", "rebuilt", "extended", "paused", "repainted",
              "rewired", "tested"],
        inf=["reroute", "upgrade", "inspect", "retime", "rebuild", "extend", "pause", "rewire", "test", "publish"],
        adj=["crowded", "late", "quiet", "noisy", "reliable", "temporary", "narrow", "new", "rusty", "shared"],
        event=["the summer works", "a power cut", "the marathon weekend", "the snow week", "a timetable change",
               "the depot audit"]),
    "observatory": dict(
        n=["refractor", "dome shutter", "star chart", "camera mount", "dew heater", "log book", "filter wheel",
           "focus knob", "guide scope", "power bank", "observing deck", "light shield"],
        place=["Hollow Ridge", "the club hut", "the west field", "Pinecrest", "the car park", "the library roof"],
        group=["the astronomy club", "first-year members", "the imaging group", "two retired pilots",
               "the outreach team", "night owls"],
        past=["aligned", "cleaned", "calibrated", "logged", "replaced", "rebalanced", "tested", "sketched",
              "measured", "mounted"],
        inf=["align", "clean", "calibrate", "log", "replace", "rebalance", "sketch", "measure", "mount", "cover"],
        adj=["dewy", "steady", "faint", "cold", "clear", "shaky", "patient", "bright", "borrowed", "careful"],
        event=["the meteor shower", "a cloudy month", "the open night", "a full moon", "the eclipse watch",
               "the winter solstice"]),
    "bakery": dict(
        n=["starter jar", "proofing basket", "deck oven", "flour bin", "bench scraper", "rye loaf",
           "levain schedule", "cooling rack", "dough trough", "steam tray", "order book", "bread stamp"],
        place=["the corner bakery", "Wheatley Road", "the back kitchen", "the Saturday market", "Larkspur",
               "the cold room"],
        group=["the night bakers", "two apprentices", "the counter staff", "regular customers", "the owners",
               "a baking class"],
        past=["fed", "shaped", "scored", "baked", "weighed", "proofed", "rotated", "cooled", "tested", "adjusted"],
        inf=["feed", "shape", "score", "bake", "weigh", "proof", "rotate", "cool", "test", "adjust"],
        adj=["sour", "airy", "dense", "golden", "sticky", "warm", "slow", "crusty", "pale", "lively"],
        event=["the heat wave", "a flour shortage", "the holiday rush", "a broken oven", "the spring fair",
               "the long weekend"]),
    "software": dict(
        n=["retry queue", "config loader", "worker pool", "cache layer", "schema check", "release script",
           "test runner", "log rotation", "plugin hook", "lock file", "build step", "error budget"],
        place=["the main branch", "the staging cluster", "the nightly build", "the docs site", "version two",
               "the CLI"],
        group=["the maintainers", "first-time contributors", "the release team", "two reviewers",
               "plugin authors", "the triage rota"],
        past=["refactored", "deprecated", "benchmarked", "documented", "patched", "split", "merged", "profiled",
              "renamed", "pinned"],
        inf=["refactor", "deprecate", "benchmark", "document", "patch", "split", "merge", "profile", "rename",
             "pin"],
        adj=["flaky", "slow", "stable", "verbose", "brittle", "lean", "optional", "strict", "lazy", "noisy"],
        event=["the last release", "a security report", "the freeze", "a large migration", "the beta",
               "the code sprint"]),
    "garden": dict(
        n=["raised bed", "compost bay", "tomato cage", "rain barrel", "seed tray", "bean trellis", "cold frame",
           "herb spiral", "tool shed", "mulch pile", "soil test", "watering rota"],
        place=["plot nine", "the allotment gate", "Fenwick Gardens", "the shady corner", "the greenhouse",
               "the south fence"],
        group=["the plot holders", "the Saturday crew", "the school club", "two neighbours", "the committee",
               "new members"],
        past=["mulched", "watered", "staked", "turned", "sowed", "harvested", "weeded", "fenced", "tested",
              "moved"],
        inf=["mulch", "water", "stake", "turn", "sow", "harvest", "weed", "fence", "test", "move"],
        adj=["leggy", "damp", "sunny", "sandy", "crowded", "tender", "hardy", "shallow", "rich", "tidy"],
        event=["the late frost", "a wet spring", "the open day", "a slug year", "the drought", "the plant swap"]),
    "river": dict(
        n=["sampling point", "weir gate", "reed bed", "litter boom", "flow meter", "bank survey", "otter camera",
           "footbridge", "silt trap", "kayak launch", "water report", "volunteer map"],
        place=["Alder Bend", "the mill race", "the lower meadow", "Kestrel Bridge", "the old ford",
               "the estuary path"],
        group=["the river keepers", "school volunteers", "the paddling club", "the survey team", "two ecologists",
               "local anglers"],
        past=["sampled", "cleared", "mapped", "measured", "photographed", "recorded", "rebuilt", "planted",
              "checked", "reported"],
        inf=["sample", "clear", "map", "measure", "photograph", "record", "rebuild", "plant", "check", "report"],
        adj=["murky", "swollen", "clear", "shallow", "fast", "silty", "quiet", "fragile", "busy", "cold"],
        event=["the spring flood", "a dry August", "the cleanup day", "a pollution scare", "the fish count",
               "the autumn rains"]),
}

TEMPLATES = [
    "The {n} at {place} was {past} by {group} after {event}, and the work took {num} {unit}.",
    "{Group} {past} the {n} first, because the {n2} near {place} looked too {adj} to trust.",
    "By {month}, {group} had {past} the {n} twice, which left the {n2} {adj} but usable.",
    "Nobody expected {event} to {inf} the {n} so quickly, yet {group} had to {inf2} it again.",
    "The plan was to {inf} the {n}, {inf2} the {n2}, and keep {place} open for {group}.",
    "Records from {month} show that {group} {past} the {adj} {n} near {place} at least {num} times.",
    "When {event} arrived, the {n} held, although the {n2} beside it was {past} within {num} {unit}.",
    "{Group} still argue about whether the {n} should be {past} or left {adj} for another year.",
    "A {adj} {n} is easy to miss, so {group} now {inf} it every {unit1} and write the result down.",
    "Costs rose after {event}, mostly because the {n2} at {place} had to be {past} by hand.",
    "Each {unit1}, {group} walk past {place} to {inf} the {n} and check the {n2}.",
    "It helped that the {n2} was {adj}, since {group} could {inf} the {n} without waiting for {event}.",
    "Some of {group} wanted to {inf} the {n} at once, while others asked for {num} more {unit} of notes.",
    "Old photographs of {place} show a {adj} {n}, long before anyone {past} the {n2}.",
]
NUMS = ["two", "three", "four", "five", "six", "eight", "ten", "twelve"]
UNITS = ["days", "weeks", "months", "evenings", "weekends"]
UNIT1 = ["week", "month", "morning", "season"]
MONTHS = ["March", "April", "May", "June", "July", "August", "September", "October"]


class Prose:
    def __init__(self, topic, seed):
        self.t = TOPICS[topic]
        self.rng = random.Random(seed)

    def sentence(self):
        r, t = self.rng, self.t
        n, n2 = r.sample(t["n"], 2)
        inf, inf2 = r.sample(t["inf"], 2)
        group = r.choice(t["group"])
        text = r.choice(TEMPLATES).format(
            n=n, n2=n2, place=r.choice(t["place"]), group=group, Group=group[0].upper() + group[1:],
            past=r.choice(t["past"]), inf=inf, inf2=inf2, adj=r.choice(t["adj"]), event=r.choice(t["event"]),
            num=r.choice(NUMS), unit=r.choice(UNITS), unit1=r.choice(UNIT1), month=r.choice(MONTHS))
        return text[0].upper() + text[1:]

    def para(self, lo=3, hi=5):
        return " ".join(self.sentence() for _ in range(self.rng.randint(lo, hi)))

    def phrase(self):
        """A short title-like phrase for headings and list items."""
        r, t = self.rng, self.t
        return r.choice([
            f"Why the {r.choice(t['n'])} was {r.choice(t['past'])}",
            f"What {r.choice(t['group'])} learned at {r.choice(t['place'])}",
            f"The {r.choice(t['adj'])} {r.choice(t['n'])}",
            f"After {r.choice(t['event'])}",
            f"How to {r.choice(t['inf'])} a {r.choice(t['n'])}",
        ])

    def item(self):
        r, t = self.rng, self.t
        return f"{r.choice(t['inf']).capitalize()} the {r.choice(t['n'])} before {r.choice(t['event'])}"


SPANISH = [
    "El {n} de {place} fue reparado por {group} después de {event}, y el trabajo duró {num} semanas.",
    "{Group} revisaron primero el {n}, porque el {n2} cerca de {place} parecía demasiado frágil.",
    "Nadie esperaba que {event} cambiara tanto el {n}, pero {group} tuvieron que volver a medirlo.",
    "Los registros de {month} muestran que {group} limpiaron el {n} junto a {place} varias veces.",
    "Cada semana, {group} pasan por {place} para revisar el {n} y anotar el estado del {n2}.",
    "Algunas personas querían cambiar el {n} enseguida, mientras otras pedían más datos del {n2}.",
]
SPANISH_VOCAB = dict(
    n=["puente", "molino", "huerto", "faro", "mercado", "camino", "pozo", "tejado", "muelle", "jardín"],
    place=["la plaza vieja", "Valdeluz", "el barrio del río", "la estación", "el monte", "la escuela"],
    group=["los vecinos", "el equipo municipal", "los voluntarios", "dos aprendices", "la cooperativa"],
    event=["la tormenta de otoño", "la sequía", "la fiesta del pueblo", "el invierno largo", "las obras"],
    month=["marzo", "abril", "mayo", "junio", "julio", "agosto"])


def spanish_para(rng, count=4):
    out = []
    for _ in range(count):
        v = SPANISH_VOCAB
        n, n2 = rng.sample(v["n"], 2)
        group = rng.choice(v["group"])
        text = rng.choice(SPANISH).format(n=n, n2=n2, place=rng.choice(v["place"]), group=group,
                                          Group=group[0].upper() + group[1:], event=rng.choice(v["event"]),
                                          num=rng.choice(["dos", "tres", "cuatro", "seis"]),
                                          month=rng.choice(v["month"]))
        out.append(text[0].upper() + text[1:])
    return " ".join(out)


# ---- page builder with gold bookkeeping -------------------------------------
INLINE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)|\*\*([^*]+)\*\*|\*([^*]+)\*|`([^`]+)`")


class Page:
    def __init__(self, name, url, title, *, layout, expect=("article", "article"), lang="en",
                 author=None, published=None, site=None):
        self.name, self.url, self.title, self.lang = name, url, title, lang
        self.gold = {
            "name": name, "url": url, "layout": layout, "title": title,
            "expect": {"python": expect[0], "extension": expect[1]},
            "metadata": {k: v for k, v in (("author", author), ("published", published), ("site_name", site)) if v},
            "keep": [], "junk": [],
            "structure": {k: [] for k in ("headings", "list_items", "code", "tables", "links", "images",
                                          "quotes", "footnotes", "math", "captions")},
        }
        self.rendered = None
        self.origin = re.match(r"https?://[^/]+", url)[0]

    # gold
    def keep(self, text):
        self.gold["keep"].append(re.sub(r"\s+", " ", text).strip())

    def junk(self, text):
        self.gold["junk"].append(re.sub(r"\s+", " ", text).strip())

    def s(self, kind, value):
        self.gold["structure"][kind].append(value)

    def absolute(self, href):
        if href.startswith(("http://", "https://")):
            return href
        if href.startswith("/"):
            return self.origin + href
        return self.url.rsplit("/", 1)[0] + "/" + href

    # inline mini markup -> (html, plain)
    def inline(self, text, *, track_links=True):
        html, plain, pos = [], [], 0
        for m in INLINE.finditer(text):
            html.append(escape(text[pos:m.start()], quote=False))
            plain.append(text[pos:m.start()])
            link_text, href, strong, em, code = m.groups()
            if link_text:
                html.append(f'<a href="{escape(href)}">{escape(link_text, quote=False)}</a>')
                plain.append(link_text)
                if track_links:
                    self.s("links", {"text": link_text, "href": self.absolute(href)})
            elif strong:
                html.append(f"<strong>{escape(strong, quote=False)}</strong>")
                plain.append(strong)
            elif em:
                html.append(f"<em>{escape(em, quote=False)}</em>")
                plain.append(em)
            else:
                html.append(f"<code>{escape(code, quote=False)}</code>")
                plain.append(code)
            pos = m.end()
        html.append(escape(text[pos:], quote=False))
        plain.append(text[pos:])
        return "".join(html), "".join(plain)

    # keep builders
    def p(self, text, attrs=""):
        html, plain = self.inline(text)
        self.keep(plain)
        return f"<p{attrs}>{html}</p>"

    def h(self, level, text, attrs=""):
        self.keep(text)
        self.s("headings", text)
        return f"<h{level}{attrs}>{escape(text, quote=False)}</h{level}>"

    def ul(self, items, ordered=False, attrs="", item_attrs=""):
        tag = "ol" if ordered else "ul"
        out = []
        for item in items:
            if isinstance(item, tuple):  # (text, [children])
                text, children = item
                html, plain = self.inline(text)
                self.keep(plain)
                self.s("list_items", plain)
                out.append(f"<li{item_attrs}>{html}{self.ul(children, ordered=False)}</li>")
            else:
                html, plain = self.inline(item)
                self.keep(plain)
                self.s("list_items", plain)
                out.append(f"<li{item_attrs}>{html}</li>")
        return f"<{tag}{attrs}>" + "".join(out) + f"</{tag}>"

    def code(self, code, lang=None, style="plain"):
        self.keep(code)
        self.s("code", {"text": code, "lang": lang})
        esc = escape(code, quote=False)
        if style == "plain":
            cls = f' class="language-{lang}"' if lang else ""
            return f"<pre><code{cls}>{esc}</code></pre>"
        if style == "highlight":  # GitHub-like source highlight wrapper with token spans
            spans = re.sub(r"\b(def|return|const|let|import|from|if|else|for|in|async|await|function)\b",
                           r'<span class="pl-k">\1</span>', esc)
            spans = re.sub(r"(&quot;[^&]*&quot;|&#x27;[^&]*&#x27;|\"[^\"]*\")", r'<span class="pl-s">\1</span>', spans)
            return (f'<div class="highlight highlight-source-{lang}"><pre>{spans}</pre>'
                    f'<button class="copy-btn" aria-label="Copy">Copy</button></div>')
        if style == "lineno":  # table with line numbers next to the code
            lines = esc.split("\n")
            nums = "\n".join(str(i + 1) for i in range(len(lines)))
            return (f'<div class="codehilite" data-lang="{lang}"><table class="codehilitetable"><tr>'
                    f'<td class="linenos"><div class="linenodiv"><pre>{nums}</pre></div></td>'
                    f'<td class="code"><pre><span></span><code>{esc}</code></pre></td></tr></table></div>')
        if style == "prism":
            return (f'<div class="code-toolbar"><pre class="language-{lang}" tabindex="0">'
                    f'<code class="language-{lang}">{esc}</code></pre>'
                    f'<div class="toolbar"><button>Copy</button></div></div>')
        raise ValueError(style)

    def table(self, header, rows, caption=None, attrs=""):
        self.s("tables", [header] + rows)
        for row in [header] + rows:
            self.keep(" ".join(row))
        cap = ""
        if caption:
            self.keep(caption)
            self.s("captions", caption)
            cap = f"<caption>{escape(caption, quote=False)}</caption>"
        head = "".join(f"<th>{escape(c, quote=False)}</th>" for c in header)
        body = "".join("<tr>" + "".join(f"<td>{escape(c, quote=False)}</td>" for c in row) + "</tr>"
                       for row in rows)
        return f"<table{attrs}>{cap}<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"

    def quote(self, text, attrs=""):
        html, plain = self.inline(text)
        self.keep(plain)
        self.s("quotes", plain)
        return f"<blockquote{attrs}><p>{html}</p></blockquote>"

    def figure(self, src, alt, caption=None, lazy=None, width=960, height=640):
        absolute = self.absolute(src)
        self.s("images", {"alt": alt, "src": absolute})
        if caption:
            self.keep(caption)
            self.s("captions", caption)
        a = escape(alt)
        if lazy == "data-src":
            img = (f'<img class="lazyload" src="data:image/gif;base64,R0lGODlhAQABAAAAACw=" data-src="{src}" '
                   f'alt="{a}" width="{width}" height="{height}">'
                   f'<noscript><img src="{src}" alt="{a}" width="{width}" height="{height}"></noscript>')
        elif lazy == "srcset":
            img = (f'<img loading="lazy" src="{src}" srcset="{src} 960w, {src.replace(".jpg", "-480.jpg")} 480w" '
                   f'sizes="(max-width: 600px) 480px, 960px" alt="{a}" width="{width}" height="{height}">')
        elif lazy == "picture":
            img = (f'<picture><source type="image/webp" srcset="{src.replace(".jpg", ".webp")}">'
                   f'<img src="{src}" alt="{a}" width="{width}" height="{height}"></picture>')
        else:
            img = f'<img src="{src}" alt="{a}" width="{width}" height="{height}">'
        cap = f"<figcaption>{escape(caption, quote=False)}</figcaption>" if caption else ""
        return f"<figure>{img}{cap}</figure>"

    def dl(self, pairs):
        out = []
        for term, definition in pairs:
            self.keep(term)
            self.keep(definition)
            out.append(f"<dt>{escape(term, quote=False)}</dt><dd>{escape(definition, quote=False)}</dd>")
        return "<dl>" + "".join(out) + "</dl>"

    # junk builders: each returns html, registers a distinctive junk sentence
    def nav(self, labels, cls="site-nav", tagline=None):
        self.junk(" ".join(labels))
        links = "".join(f'<li><a href="/{re.sub(r"[^a-z]+", "-", l.lower())}">{escape(l)}</a></li>' for l in labels)
        tag = ""
        if tagline:
            self.junk(tagline)
            tag = f'<p class="tagline">{escape(tagline)}</p>'
        return (f'<header class="site-header"><a class="skip-link" href="#main">Skip to main content</a>'
                f'<a class="logo" href="/">{escape(self.gold["metadata"].get("site_name", "Home"))}</a>{tag}'
                f'<nav class="{cls}" aria-label="Main"><ul>{links}</ul></nav>'
                f'<form class="search" role="search"><input type="search" placeholder="Search"><button>Go</button></form>'
                f'</header>')

    def footer(self, text):
        self.junk(text)
        return (f'<footer class="site-footer"><p>{escape(text)}</p><ul class="footer-links">'
                f'<li><a href="/privacy">Privacy policy</a></li><li><a href="/terms">Terms of use</a></li>'
                f'<li><a href="/contact">Contact us</a></li></ul></footer>')

    def cookie_banner(self, overlay=False):
        text = ("We use cookies and similar tools to keep this site working, to remember your choices and to "
                "measure how pages are used. You can accept all of them, or pick which kinds we may store.")
        self.junk(text)
        if overlay:
            vendors = " ".join(f"Vendor partner number {i} may store identifiers for audience measurement."
                               for i in range(1, 9))
            self.junk(vendors[:120])
            return (f'<div id="consent-overlay" class="cmp-overlay" role="dialog" aria-modal="true" '
                    f'aria-label="Privacy choices"><div class="cmp-dialog"><h2>Your privacy choices</h2>'
                    f'<p>{text}</p><p class="cmp-vendors">{vendors}</p><button class="cmp-accept">Accept all</button>'
                    f'<button class="cmp-manage">Manage choices</button></div></div>')
        return (f'<div class="cookie-banner" id="cookie-notice" role="region" aria-label="Cookie notice">'
                f'<p>{text}</p><button>Accept all</button><button>Manage choices</button></div>')

    def newsletter(self, cls="newsletter-signup"):
        text = "Get the morning briefing in your inbox every weekday, free, with one tap to unsubscribe."
        self.junk(text)
        return (f'<aside class="{cls}"><h3>Sign up for the briefing</h3><p>{text}</p>'
                f'<form><input type="email" placeholder="Email address"><button>Sign me up</button></form></aside>')

    def related(self, heads, title="More from the desk", cls="related-stories"):
        self.junk(" ".join(heads))
        items = "".join(f'<li><a href="/story/{i}">{escape(h)}</a></li>' for i, h in enumerate(heads))
        return f'<aside class="{cls}"><h3>{escape(title)}</h3><ul>{items}</ul></aside>'

    def share(self):
        self.junk("Share this story Copy link Email Print")
        return ('<div class="share-bar"><span>Share this story</span><a href="#">Copy link</a>'
                '<a href="mailto:?subject=x">Email</a><a href="#" onclick="print()">Print</a></div>')

    def ad(self, text):
        self.junk(text)
        return (f'<div class="ad-slot ad-container" data-ad-unit="mid"><span class="ad-label">Advertisement</span>'
                f'<p>{escape(text)}</p></div>')

    def comments(self, entries, heading="Comments"):
        self.junk(entries[0][1])
        out = "".join(f'<li class="comment"><span class="comment-author">{escape(a)}</span>'
                      f'<p>{escape(t)}</p><a class="reply" href="#">Reply</a></li>' for a, t in entries)
        return (f'<section class="comments" id="comments"><h2>{escape(heading)} ({len(entries)})</h2>'
                f'<ol class="comment-list">{out}</ol><form class="comment-form"><textarea placeholder="Join the '
                f'discussion"></textarea><button>Post comment</button></form></section>')

    def breadcrumbs(self, parts):
        self.junk(" ".join(parts))
        links = " &gt; ".join(f'<a href="/{p.lower()}">{escape(p)}</a>' for p in parts)
        return f'<nav class="breadcrumbs" aria-label="Breadcrumb">{links}</nav>'

    # documents
    def head(self, extra="", *, og=True, ld=None, desc=None):
        meta = self.gold["metadata"]
        bits = [f'<meta charset="utf-8"><title>{escape(self.title)}'
                + (f' | {escape(meta["site_name"])}' if meta.get("site_name") else "") + "</title>",
                '<meta name="viewport" content="width=device-width, initial-scale=1">']
        if desc:
            bits.append(f'<meta name="description" content="{escape(desc)}">')
        if og:
            bits.append(f'<meta property="og:title" content="{escape(self.title)}">')
            if meta.get("site_name"):
                bits.append(f'<meta property="og:site_name" content="{escape(meta["site_name"])}">')
            bits.append(f'<meta property="og:url" content="{self.url}">')
        if ld:
            bits.append(f'<script type="application/ld+json">{json.dumps(ld)}</script>')
        bits.append(extra)
        bits.append('<link rel="stylesheet" href="/static/site.css">')
        return "<head>" + "".join(bits) + "</head>"

    def doc(self, head, body, body_attrs=""):
        return (f'<!doctype html>\n<html lang="{self.lang}">{head}\n<body{body_attrs}>\n{body}\n'
                f'<script src="/static/analytics.js" async></script>\n</body></html>\n')


def junk_heads(seed, count=4):
    rng = random.Random(seed)
    nouns = ["phone plan", "sneaker drop", "streaming series", "celebrity kitchen", "gadget sale", "travel card",
             "fitness tracker", "lottery winner", "smart speaker", "game console"]
    forms = ["The {} everyone is talking about this weekend", "Ten reasons the {} sold out in hours",
             "Is the {} worth it? Readers weigh in", "Inside the strange rise of the {}",
             "What nobody tells you about the {}"]
    return [rng.choice(forms).format(n) for n in rng.sample(nouns, count)]


# ---- fixtures ------------------------------------------------------------------
FIXTURES = []


def fixture(fn):
    FIXTURES.append(fn)
    return fn


@fixture
def news_semantic():
    pr = Prose("harbor", 101)
    pg = Page("news-semantic", "https://news.example.org/2026/10/harbor-lanterns-relit", "Harbor lanterns are lit again",
              layout="news article, semantic tags, JSON-LD", author="Odile Fenwright", published="2026-10-12",
              site="Gullhaven Gazette")
    ld = {"@context": "https://schema.org", "@type": "NewsArticle", "headline": pg.title,
          "datePublished": "2026-10-12T07:30:00Z", "author": {"@type": "Person", "name": "Odile Fenwright"},
          "publisher": {"@type": "Organization", "name": "Gullhaven Gazette"}}
    body = [pg.nav(["Harbor", "Town hall", "Weather", "Sport", "Letters"], tagline="Independent harbor news since the year the ferry first ran"),
            pg.cookie_banner(),
            '<main id="main"><article class="story">',
            f'<header class="story-header">{pg.h(1, pg.title)}'
            '<p class="byline">By <a rel="author" href="/people/odile-fenwright">Odile Fenwright</a> '
            '<time datetime="2026-10-12T07:30:00Z">October 12, 2026</time></p></header>',
            pg.share(),
            pg.figure("/media/2026/lanterns-quay.jpg", "Lanterns along the north quay at dusk",
                      "The restored lanterns along the north quay, photographed at dusk."),
            '<div class="story-body">', pg.p(pr.para()), pg.p(pr.para()),
            pg.quote("We rebuilt every bracket by hand, and the salt still finds a way in."),
            pg.p(pr.para() + " The full survey is on [the harbor trust site](https://trust.example.org/survey)."),
            pg.newsletter(), pg.h(2, "What the repairs cost"), pg.p(pr.para()), pg.p(pr.para()),
            pg.ul(["Brackets and glass: four weeks", "Wiring and timers: two weeks", "Paint and sealing: one week"]),
            pg.p(pr.para()), "</div>",
            pg.related(junk_heads(1)), "</article></main>",
            pg.ad("Save thirty percent on the spring planner bundle, today only"),
            pg.footer("Copyright Gullhaven Gazette Media. All rights reserved. Registered in the harbor district.")]
    return pg, pg.doc(pg.head(ld=ld, desc="The harbor trust finished relighting the quay lanterns."), "\n".join(body))


@fixture
def news_divsoup():
    pr = Prose("transit", 102)
    pg = Page("news-divsoup", "https://metro.example.com/news/tram-loop-extension", "Tram loop extension opens early",
              layout="news, div soup with class names and ad slots", author="Caspar Lune", published="2026-09-03",
              site="Metro Ledger")
    head = pg.head('<meta name="author" content="Caspar Lune">'
                   '<meta property="article:published_time" content="2026-09-03T06:00:00+02:00">')
    body = ['<div id="page-wrap"><div class="top-bar">', pg.nav(["News", "Opinion", "Business", "Culture", "Puzzles"], cls="menu-main"),
            '</div><div class="layout-grid"><div class="col-main"><div class="story-wrapper">',
            f'<div class="headline-block">{pg.h(1, pg.title)}<div class="byline-block">'
            '<span class="author-name">Caspar Lune</span> <span class="pubdate">3 September 2026</span></div></div>',
            '<div class="story-body__inner">',
            pg.p(pr.para()), pg.p(pr.para()), pg.ad("Upgrade your commute with the new travel card offer"),
            pg.p(pr.para()), pg.p(pr.para()), '<div class="story-body__crosshead">', pg.h(2, "Night service changes"), "</div>",
            pg.p(pr.para()), pg.p(pr.para() + " Riders can read [the full timetable](/timetables/loop)."),
            "</div></div></div>",
            '<div class="col-side">', pg.related(junk_heads(2, 5), title="Most read", cls="most-read-list"),
            pg.ad("Win a weekend away with our partner hotels"), "</div></div>",
            pg.footer("Metro Ledger is part of an example media group. All rights reserved."), "</div>"]
    return pg, pg.doc(head, "\n".join(body))


@fixture
def news_liveblog():
    pr = Prose("river", 103)
    pg = Page("news-liveblog", "https://live.example.net/river-flood-updates", "River flood: live updates",
              layout="live blog with timestamped entries", site="Valley Live", published="2026-03-14")
    ld = {"@context": "https://schema.org", "@type": "LiveBlogPosting", "headline": pg.title,
          "datePublished": "2026-03-14T05:00:00Z", "publisher": {"@type": "Organization", "name": "Valley Live"}}
    entries = []
    for i, stamp in enumerate(["09:40", "08:55", "08:10", "07:25", "06:30"]):
        entries.append(f'<article class="live-entry" id="entry-{i}"><time class="entry-time">{stamp}</time>'
                       f'{pg.h(2, pr.phrase())}{pg.p(pr.para(2, 3))}</article>')
    body = [pg.nav(["Live", "Local", "Traffic", "Weather"]), '<main>', pg.h(1, pg.title),
            pg.p("Updates on the spring flood along Alder Bend and the lower meadow, newest first."),
            '<div class="live-feed">', *entries, '</div>',
            '<button class="load-more">Load earlier updates</button>', "</main>",
            pg.related(junk_heads(3), title="Trending now"),
            pg.footer("Valley Live. Local news for the valley, all rights reserved.")]
    return pg, pg.doc(pg.head(ld=ld), "\n".join(body))


@fixture
def docs_code():
    pr = Prose("software", 104)
    pg = Page("docs-code", "https://docs.example.dev/quill/guide/retries", "Retries and backoff",
              layout="docs page, sidebar nav, TOC, code blocks with languages, admonition", site="Quill Docs")
    side = "".join(f'<li><a href="/quill/guide/{i}">{escape(t)}</a></li>' for i, t in enumerate(
        ["Installation", "Quick start", "Configuration", "Workers", "Retries and backoff", "Scheduling",
         "Plugins", "Logging", "Testing", "Deployment", "Upgrading", "FAQ"]))
    pg.junk("Installation Quick start Configuration Workers")
    toc = ('<nav class="toc" aria-label="On this page"><p>On this page</p><ul>'
           '<li><a href="#basic">Basic retries</a></li><li><a href="#backoff">Backoff</a></li>'
           '<li><a href="#limits">Limits</a></li></ul></nav>')
    pg.junk("On this page Basic retries Backoff Limits")
    note_text = "Retries run in the same worker pool, so a slow retry can delay new jobs."
    pg.keep(note_text)
    body = [pg.nav(["Docs", "API", "Blog", "Community", "GitHub"], cls="navbar"),
            f'<div class="docs-layout"><aside class="sidebar"><ul class="menu">{side}</ul></aside>',
            '<main class="docs-content"><div class="theme-doc-markdown markdown">', pg.h(1, pg.title),
            pg.p(pr.para(2, 3) + " Use `retry_on` to pick which errors retry."),
            pg.h(2, "Basic retries", ' id="basic"'), pg.p(pr.para(2, 3)),
            pg.code("from quill import Queue\n\nqueue = Queue(\"emails\", retries=3)\n\n@queue.task(retry_on=(TimeoutError,))\ndef send(message):\n    return deliver(message)", "python"),
            f'<div class="admonition note"><p class="admonition-title">Note</p><p>{note_text}</p></div>',
            pg.h(2, "Backoff", ' id="backoff"'), pg.p(pr.para(2, 3)),
            pg.code("quill worker --backoff exponential --max-delay 300", "bash"),
            pg.h(3, "Choosing a delay"), pg.p(pr.para(2, 3)),
            pg.h(2, "Limits", ' id="limits"'),
            pg.ul(["`retries` caps the attempts per job", "`max_delay` caps the wait in seconds",
                   "`jitter` spreads retries so workers do not wake together"]),
            '</div><nav class="pagination-nav"><a href="/quill/guide/3">Previous: Workers</a>'
            '<a href="/quill/guide/5">Next: Scheduling</a></nav>'
            '<p class="edit-this-page"><a href="https://git.example.dev/quill/edit/docs/retries.md">Edit this page</a></p>',
            f"</main>{toc}</div>", pg.footer("Quill is released under the MIT license. Docs built with a static site generator.")]
    pg.junk("Previous: Workers Next: Scheduling")
    return pg, pg.doc(pg.head(), "\n".join(body))


@fixture
def docs_highlight():
    pr = Prose("software", 105)
    pg = Page("docs-highlight", "https://guide.example.dev/caching/layers", "Caching layers explained",
              layout="docs, syntax-highlight spans, line-number tables, prism toolbars", site="Example Dev Guide")
    body = [pg.nav(["Guides", "Reference", "Changelog", "Support"]), '<div class="container"><div class="row">',
            '<div class="col-md-3 sidebar-left"><ul class="nav-list">'
            + "".join(f'<li><a href="/caching/{i}">Chapter {i}</a></li>' for i in range(1, 9)) + "</ul></div>",
            '<div class="col-md-9 main-col"><div class="post-content">', pg.h(1, pg.title), pg.p(pr.para()),
            pg.h(2, "A small read-through cache"),
            pg.code("const cache = new Map();\n\nasync function getUser(id) {\n  if (cache.has(id)) return cache.get(id);\n  const user = await fetchUser(id);\n  cache.set(id, user);\n  return user;\n}", "js", "highlight"),
            pg.p(pr.para(2, 3)), pg.h(2, "Expiring entries"),
            pg.code("def expired(entry, now):\n    return now - entry.stored_at > entry.ttl", "python", "lineno"),
            pg.p(pr.para(2, 3)), pg.h(2, "Configuration"),
            pg.code("cache:\n  layers: [memory, disk]\n  ttl_seconds: 600", "yaml", "prism"),
            pg.p(pr.para(2, 3)), "</div></div></div></div>",
            pg.footer("Example Dev Guide. Content licensed for reuse with attribution.")]
    pg.junk("Chapter 1 Chapter 2 Chapter 3")
    return pg, pg.doc(pg.head(), "\n".join(body))


@fixture
def api_reference():
    pr = Prose("software", 106)
    pg = Page("api-reference", "https://api.example.dev/reference/jobs-create", "Create a job",
              layout="API reference, parameter tables with code cells", site="Example API")
    body = [pg.nav(["Reference", "Guides", "SDKs", "Status"]),
            '<div class="api-page"><nav class="api-sidebar"><ul><li><a href="#">Jobs</a></li><li><a href="#">Workers</a>'
            '</li><li><a href="#">Queues</a></li><li><a href="#">Webhooks</a></li></ul></nav><main class="api-main">',
            pg.h(1, pg.title), pg.p(pr.para(2, 3)), pg.code("POST /v2/jobs", None),
            pg.h(2, "Body parameters"),
            pg.table(["Name", "Type", "Required", "Description"],
                     [["queue", "string", "yes", "Name of the queue that runs the job"],
                      ["payload", "object", "yes", "Data passed to the task"],
                      ["retries", "integer", "no", "Attempts before the job fails"],
                      ["run_at", "timestamp", "no", "Earliest start time in UTC"]]),
            pg.h(2, "Example request"),
            pg.code('{\n  "queue": "emails",\n  "payload": {"to": "reader@example.com"},\n  "retries": 3\n}', "json"),
            pg.h(2, "Errors"),
            pg.table(["Code", "Meaning"], [["400", "The body is not valid JSON"], ["409", "A job with this key exists"]]),
            pg.p(pr.para(2, 3)), "</main></div>",
            pg.footer("Example API reference. Status and uptime are listed on the status page.")]
    pg.junk("Jobs Workers Queues Webhooks")
    return pg, pg.doc(pg.head(), "\n".join(body))


@fixture
def blog_footnotes():
    pr = Prose("garden", 107)
    pg = Page("blog-footnotes", "https://wren.example.net/posts/soil-notes", "Notes on stubborn soil",
              layout="personal blog with footnotes, author bio, comments, tags", author="Nell Brightwater",
              published="2026-05-02", site="Wren Field Notes")
    ld = {"@context": "https://schema.org", "@type": "BlogPosting", "headline": pg.title,
          "datePublished": "2026-05-02", "author": {"@type": "Person", "name": "Nell Brightwater"}}
    notes = ["The soil test kit came from the allotment shed and was two seasons old.",
             "Plot nine has always drained badly, according to the committee minutes.",
             "We used leaf mould rather than bark because it was free."]
    for n in notes:
        pg.keep(n)
        pg.s("footnotes", n)
    fn_list = "".join(f'<li id="fn{i}"><p>{escape(n)} <a href="#fnref{i}" class="footnote-back">↩</a></p></li>'
                      for i, n in enumerate(notes, 1))
    def ref(i):
        return f'<sup class="footnote-ref"><a href="#fn{i}" id="fnref{i}">{i}</a></sup>'
    bio = "Nell writes about small gardens, slow repairs and the weather on the allotment."
    pg.junk(bio)
    paras = [pr.para() for _ in range(5)]
    for t in paras:
        pg.keep(t)
    body = [pg.nav(["Home", "Archive", "About", "Feed"]), '<main><article class="post h-entry">',
            pg.h(1, pg.title, ' class="p-name"'),
            '<p class="post-meta">Posted on <time class="dt-published" datetime="2026-05-02">May 2, 2026</time> by '
            '<span class="p-author">Nell Brightwater</span></p><div class="e-content">',
            f"<p>{escape(paras[0])}{ref(1)}</p>", f"<p>{escape(paras[1])}</p>",
            f"<p>{escape(paras[2])}{ref(2)}</p>", pg.h(2, "What changed"), f"<p>{escape(paras[3])}{ref(3)}</p>",
            f"<p>{escape(paras[4])}</p>",
            f'<section class="footnotes" role="doc-endnotes"><hr><ol>{fn_list}</ol></section></div>',
            '<p class="tags">Tagged: <a href="/tags/soil">soil</a> <a href="/tags/compost">compost</a></p>',
            f'<div class="author-bio"><img src="/img/avatar.png" alt="" width="48" height="48"><p>{bio}</p></div>',
            "</article>",
            pg.comments([("leafy_ana", "Lovely write-up, our plot has the same clay problem every single spring."),
                         ("rootsandrain", "Did the leaf mould help with drainage by the second year?")]),
            "</main>", pg.footer("Wren Field Notes. Written by hand, hosted on a small server.")]
    return pg, pg.doc(pg.head(ld=ld), "\n".join(body))


@fixture
def github_readme():
    pr = Prose("software", 108)
    pg = Page("github-readme", "https://git.example.dev/acme-labs/quill", "quill: a small job queue",
              layout="code host README, markdown-body, anchors, badges, task list, file list")
    readme_title = "Quill"
    body = [pg.nav(["Pull requests", "Issues", "Marketplace", "Explore"], cls="header-nav"),
            '<div class="repo-layout"><div class="file-navigation"><ul class="file-list">'
            + "".join(f'<li><a href="/acme-labs/quill/blob/main/{f}">{f}</a></li>' for f in
                      ["src", "tests", "docs", "LICENSE", "pyproject.toml", "README.md"]) + "</ul></div>",
            '<div class="Box-body readme"><article class="markdown-body entry-content" itemprop="text">',
            '<div class="markdown-heading"><h1 class="heading-element">Quill</h1>'
            '<a id="user-content-quill" class="anchor" href="#quill" aria-label="Permalink: Quill"></a></div>',
            '<p><a href="https://ci.example.dev/quill"><img src="https://img.example.dev/badge/build-passing.svg" alt="build"></a> '
            '<a href="/acme-labs/quill/blob/main/LICENSE"><img src="https://img.example.dev/badge/license-MIT.svg" alt="license"></a></p>',
            pg.p(pr.para(2, 3)),
            '<div class="markdown-heading">', pg.h(2, "Install", ' class="heading-element"'),
            '<a id="user-content-install" class="anchor" href="#install"></a></div>',
            pg.code("pip install quill-queue", "shell", "highlight"),
            '<div class="markdown-heading">', pg.h(2, "Features", ' class="heading-element"'), '</div>',
            pg.ul(["Retries with backoff", "Scheduled jobs", "Plugin hooks for metrics"], attrs=' class="contains-task-list"'),
            '<div class="markdown-heading">', pg.h(2, "Compatibility", ' class="heading-element"'), '</div>',
            pg.table(["Python", "Status"], [["3.10", "supported"], ["3.11", "supported"], ["3.12", "supported"]]),
            '<div class="markdown-heading">', pg.h(2, "Contributing", ' class="heading-element"'), '</div>',
            pg.p(pr.para(2, 3) + " Read [the contributing guide](/acme-labs/quill/blob/main/CONTRIBUTING.md) first."),
            "</article></div>",
            '<div class="BorderGrid about-box"><h2>About</h2><p>A small, boring job queue for Python services.</p>'
            '<p>Releases 14 Contributors 23 Stars 1.2k</p></div></div>',
            pg.footer("Example code hosting service. Terms Privacy Security Status Docs")]
    pg.keep(readme_title)
    pg.s("headings", readme_title)
    pg.junk("Releases 14 Contributors 23 Stars")
    pg.junk("src tests docs LICENSE pyproject.toml")
    return pg, pg.doc(pg.head(og=False), "\n".join(body))


@fixture
def forum_thread():
    pr = Prose("orchard", 109)
    pg = Page("forum-thread", "https://forum.example.org/t/pressing-tips-for-a-first-season/4410",
              "Pressing tips for a first season", layout="forum thread with replies, signatures, vote buttons",
              site="Orchard Hands Forum")
    posts = []
    users = ["cobble_hill_kit", "pear_row_pat", "millbrook_sam", "frostfan_jo", "cellar_rue"]
    for i, user in enumerate(users):
        text = pr.para(2, 4)
        posts.append(
            f'<article class="topic-post" id="post_{i + 1}"><div class="topic-avatar"><img src="/u/{user}.png" alt="" '
            f'width="40" height="40"></div><div class="topic-body"><div class="topic-meta-data">'
            f'<span class="username"><a href="/u/{user}">{user}</a></span><span class="post-date">Oct {3 + i}</span></div>'
            f'<div class="cooked">{pg.p(text)}</div>'
            f'<div class="post-controls"><button class="like">Like</button><button class="reply">Reply</button>'
            f'<button class="flag">Flag</button></div>'
            f'<div class="signature">Growing pears since the barn roof came down</div></div></article>')
    pg.junk("Growing pears since the barn roof came down")
    body = [pg.nav(["Latest", "Categories", "Top", "Groups"], cls="d-header-nav"), '<div id="main-outlet">',
            f'<div class="title-wrapper">{pg.h(1, pg.title)}<span class="category">Equipment</span></div>',
            '<div class="post-stream">', *posts, "</div>",
            pg.related(["Best ladder for steep rows?", "Cider yeast questions", "Frost fans worth it?"],
                       title="Suggested topics", cls="suggested-topics"),
            "</div>", pg.footer("Powered by community forum software. Be kind, stay on topic.")]
    return pg, pg.doc(pg.head(), "\n".join(body))


@fixture
def qa_page():
    pr = Prose("software", 110)
    pg = Page("qa-page", "https://ask.example.dev/questions/8812/why-does-my-worker-pool-stall",
              "Why does my worker pool stall after a deploy?", layout="Q and A page with votes and related questions",
              site="Ask Example")
    ld = {"@context": "https://schema.org", "@type": "QAPage",
          "mainEntity": {"@type": "Question", "name": pg.title}}
    def answer(i, text, code):
        return (f'<div class="answer" id="answer-{i}"><div class="votecell"><button>Up</button>'
                f'<span class="vote-count">{12 - i * 5}</span><button>Down</button></div>'
                f'<div class="answercell"><div class="s-prose js-post-body">{pg.p(text)}{pg.code(code, "python")}'
                f'</div><div class="user-info">answered Oct {4 + i} by <a href="/users/{i}">helper_{i}</a></div></div></div>')
    body = [pg.nav(["Questions", "Tags", "Users", "Unanswered"]), '<div id="content"><div id="mainbar">',
            f'<div id="question-header">{pg.h(1, pg.title)}</div>',
            '<div class="question"><div class="votecell"><span class="vote-count">7</span></div><div class="postcell">'
            '<div class="s-prose js-post-body">', pg.p(pr.para(2, 3)),
            pg.code("pool = WorkerPool(size=4)\npool.start()\n# hangs here after deploy", "python"),
            "</div></div></div>", '<h2 class="answers-header">2 Answers</h2>',
            answer(1, pr.para(2, 3), "pool = WorkerPool(size=4, drain_timeout=30)"),
            answer(2, pr.para(2, 3), "signal.signal(signal.SIGTERM, pool.drain)"),
            "</div>", '<div id="sidebar">',
            pg.related(["How to profile a flaky test?", "Lock file keeps changing", "Retry storms after outage"],
                       title="Related", cls="sidebar-related"),
            pg.related(["Which keyboard layout for coding?", "Best desk plant for low light"],
                       title="Hot network questions", cls="hot-network-questions"),
            "</div></div>", pg.footer("Ask Example. User contributions licensed for reuse with attribution.")]
    return pg, pg.doc(pg.head(ld=ld), "\n".join(body))


@fixture
def tables_report():
    pr = Prose("river", 111)
    pg = Page("tables-report", "https://data.example.org/reports/river-quality-2026", "River quality report, spring 2026",
              layout="report with data tables, captions and notes", site="Valley Water Data", published="2026-06-30")
    head = pg.head('<meta property="article:published_time" content="2026-06-30">')
    body = [pg.nav(["Reports", "Maps", "Methods", "Downloads"]), '<main class="report">', pg.h(1, pg.title),
            pg.p(pr.para()),
            pg.table(["Site", "Nitrate (mg/l)", "Oxygen (%)", "Rating"],
                     [["Alder Bend", "2.1", "94", "good"], ["Mill race", "3.8", "81", "fair"],
                      ["Kestrel Bridge", "1.6", "97", "good"], ["Old ford", "4.4", "72", "poor"]],
                     caption="Table 1. Spring sampling results by site"),
            pg.p(pr.para(2, 3)), pg.h(2, "Changes since last year"),
            pg.table(["Measure", "2025", "2026", "Change"],
                     [["Sites rated good", "5", "7", "+2"], ["Sites rated poor", "3", "1", "-2"],
                      ["Volunteer hours", "410", "530", "+120"]], caption="Table 2. Year on year"),
            pg.p(pr.para(2, 3)), "</main>",
            pg.footer("Valley Water Data. Figures may be revised as samples are rechecked.")]
    return pg, pg.doc(head, "\n".join(body))


@fixture
def newsletter_email():
    pr = Prose("bakery", 112)
    pg = Page("newsletter-email", "https://letters.example.com/p/crumb-dispatch-31", "Crumb Dispatch, issue 31",
              layout="email newsletter web view, nested layout tables, inline styles", site="Crumb Dispatch")
    pg.junk("View this email in your browser")
    pg.junk("You are receiving this because you signed up at the counter. Unsubscribe or update your preferences.")
    cell = 'style="font-family: Georgia, serif; font-size: 17px; line-height: 1.6; color: #222; padding: 0 24px;"'
    rows = [pg.p(pr.para(), f" {cell}"), pg.h(2, "This week at the bench", ' style="font-size:22px"'),
            pg.p(pr.para(), f" {cell}"),
            pg.ul(["Rye loaves return on Thursday", "Starter workshop has four places left",
                   "Holiday orders open next Monday"]),
            pg.p(pr.para(2, 3), f" {cell}")]
    h1 = pg.h(1, pg.title, ' style="font-size:28px"')
    body = ['<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4efe6">'
            '<tr><td align="center"><table role="presentation" width="600" cellpadding="0" cellspacing="0">',
            '<tr><td style="font-size:12px;color:#888;text-align:center;padding:8px">'
            '<a href="https://letters.example.com/web">View this email in your browser</a></td></tr>',
            f'<tr><td style="padding:24px">{h1}'
            '<p style="color:#777">From the Larkspur Bakery night shift</p></td></tr>',
            *(f"<tr><td>{r}</td></tr>" for r in rows),
            '<tr><td style="padding:24px;text-align:center"><a href="https://social.example/larkspur">'
            '<img src="https://letters.example.com/i/social.png" alt="Follow us" width="24" height="24"></a></td></tr>',
            '<tr><td style="font-size:11px;color:#999;padding:24px">You are receiving this because you signed up at '
            'the counter. Unsubscribe or update your preferences.</td></tr>',
            "</table></td></tr></table>"]
    pg.keep("From the Larkspur Bakery night shift")
    return pg, pg.doc(pg.head(og=False), "\n".join(body))


def full_article(pg, pr, *, sections=3):
    """Shared article body (keep) for fixtures whose layout is the point."""
    out = [pg.p(pr.para()), pg.p(pr.para())]
    for _ in range(sections):
        out += [pg.h(2, pr.phrase()), pg.p(pr.para()), pg.p(pr.para())]
    return out


@fixture
def js_shell():
    pr = Prose("observatory", 113)
    pg = Page("js-shell", "https://app.example.net/notes/meteor-night", "Meteor night field notes",
              layout="single-page app shell; content appears only after JavaScript", expect=("shell", "article"),
              site="Skylog")
    served = pg.doc(pg.head(og=False), '<div id="root"><div class="spinner" aria-busy="true">Loading...</div></div>\n'
                    '<noscript>You need to enable JavaScript to run this app.</noscript>\n'
                    '<script src="/static/js/main.4f1c2d.js"></script>')
    content = full_article(pg, pr)
    rendered = pg.doc(pg.head(og=False),
                      '<div id="root"><div class="app"><div class="topbar"><span class="brand">Skylog</span>'
                      '<button class="menu-button">Menu</button></div><div class="note-view">'
                      + pg.h(1, pg.title) + "".join(content) +
                      '</div><div class="app-footer">Synced a moment ago</div></div></div>\n'
                      '<script src="/static/js/main.4f1c2d.js"></script>')
    pg.junk("Synced a moment ago")
    pg.rendered = rendered
    return pg, served


@fixture
def next_data():
    pr = Prose("garden", 114)
    pg = Page("next-data", "https://plots.example.com/stories/plant-swap-recap", "Plant swap recap",
              layout="framework shell with page data in a JSON script tag", expect=("shell", "article"),
              site="Plots Weekly")
    content = full_article(pg, pr, sections=2)
    data = {"props": {"pageProps": {"title": pg.title, "html": "".join(content)}}, "page": "/stories/[slug]"}
    served = pg.doc(pg.head(), '<div id="__next"><div class="skeleton-header"></div><div class="skeleton-line"></div>'
                    '<div class="skeleton-line"></div></div>\n'
                    f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script>')
    pg.rendered = pg.doc(pg.head(), '<div id="__next"><header class="masthead"><a href="/">Plots Weekly</a></header>'
                         f'<main><article>{pg.h(1, pg.title)}{"".join(content)}</article></main></div>')
    return pg, served


@fixture
def cookie_overlay():
    pr = Prose("orchard", 115)
    pg = Page("cookie-overlay", "https://press.example.org/orchard-cooperative-harvest", "Cooperative reports a late harvest",
              layout="article behind a large consent dialog", author="Bram Oakhollow", published="2026-10-01",
              site="Valley Press")
    head = pg.head('<meta name="author" content="Bram Oakhollow">'
                   '<meta property="article:published_time" content="2026-10-01T09:00:00Z">')
    body = [pg.cookie_banner(overlay=True), pg.nav(["Home", "Farming", "Food", "Weather"]),
            '<main><article class="article">', pg.h(1, pg.title),
            '<div class="article-meta">By Bram Oakhollow, October 1, 2026</div>', *full_article(pg, pr),
            "</article></main>", pg.footer("Valley Press. Reporting from the river valley.")]
    return pg, pg.doc(head, "\n".join(body))


@fixture
def recipe():
    pr = Prose("bakery", 116)
    pg = Page("recipe", "https://kitchen.example.com/recipes/overnight-rye", "Overnight rye loaf",
              layout="recipe with long intro, ingredients, steps, nutrition table, JSON-LD", author="Tamsin Orrow",
              site="Larder Notes", published="2026-02-11")
    ld = {"@context": "https://schema.org", "@type": "Recipe", "name": pg.title, "author": {"@type": "Person", "name": "Tamsin Orrow"},
          "datePublished": "2026-02-11", "recipeIngredient": ["500 g rye flour"]}
    pg.junk("Jump to recipe Print recipe")
    body = [pg.nav(["Recipes", "Bread", "Cakes", "Basics"]), '<main><article class="post">',
            pg.h(1, pg.title), '<div class="recipe-actions"><a href="#recipe">Jump to recipe</a><a href="#">Print recipe</a></div>',
            pg.p(pr.para()), pg.p(pr.para()), pg.ad("Our favourite stand mixer is on sale this week"), pg.p(pr.para()),
            '<div class="wprm-recipe-container" id="recipe"><div class="wprm-recipe">', pg.h(2, "Ingredients"),
            pg.ul(["500 g rye flour", "350 g water, warm", "100 g active starter", "10 g salt", "1 tbsp caraway seeds"],
                  attrs=' class="wprm-recipe-ingredients"'),
            pg.h(2, "Method"),
            pg.ul(["Mix the flour, water and starter until no dry flour remains.",
                   "Cover and leave overnight in a cool room.", "Add the salt and caraway, then shape into a tin.",
                   "Bake for fifty minutes until the crust sounds hollow."], ordered=True),
            pg.h(3, "Nutrition"),
            pg.table(["Per slice", "Amount"], [["Energy", "180 kcal"], ["Fibre", "5 g"], ["Salt", "0.4 g"]]),
            "</div></div></article>",
            pg.comments([("crumb_fan", "Made this twice now and the caraway really makes it, thank you so much."),
                         ("ryeguy", "Can I use a banneton instead of the tin for this one?")], heading="Reviews"),
            "</main>", pg.footer("Larder Notes. Recipes tested in a small home kitchen.")]
    return pg, pg.doc(pg.head(ld=ld), "\n".join(body))


@fixture
def long_essay_images():
    pr = Prose("harbor", 117)
    pg = Page("long-essay-images", "https://essays.example.net/the-weight-of-salt", "The weight of salt",
              layout="long essay with lazy images, figcaptions, pull quote", author="Joss Penhallow",
              published="2026-08-19", site="Tidewater Review")
    head = pg.head('<meta name="author" content="Joss Penhallow">'
                   '<meta property="article:published_time" content="2026-08-19">')
    parts = [pg.p(pr.para(4, 6)) for _ in range(2)]
    parts.append(pg.figure("/img/salt-store.jpg", "The salt store with its doors open", "The salt store in early spring.", lazy="data-src"))
    parts += [pg.p(pr.para(4, 6)) for _ in range(2)]
    parts.append(pg.h(2, "The ledger"))
    parts += [pg.p(pr.para(4, 6)) for _ in range(2)]
    parts.append(pg.figure("/img/ledger-page.jpg", "A ledger page with tide times", "Tide times in a ledger from the harbor office.", lazy="srcset"))
    parts.append(pg.quote("Every repair is a guess about the next storm."))
    parts += [pg.p(pr.para(4, 6)) for _ in range(2)]
    parts.append(pg.h(2, "What the water keeps"))
    parts.append(pg.figure("/img/breakwater.jpg", "Waves over the east breakwater", "The east breakwater during a spring tide.", lazy="picture"))
    parts += [pg.p(pr.para(4, 6)) for _ in range(3)]
    pull = "Every repair is a guess about the next storm."
    body = [pg.nav(["Essays", "Fiction", "Archive", "Subscribe"]), '<main><article class="essay">',
            f'<header>{pg.h(1, pg.title)}<p class="dek">An essay about harbors, ledgers and patience.</p>'
            '<p class="byline">Joss Penhallow</p></header>',
            '<div class="essay-body">', *parts[:5], f'<aside class="pullquote">{pull}</aside>', *parts[5:], "</div>",
            "</article></main>", pg.newsletter(cls="subscribe-box"),
            pg.footer("Tidewater Review is a reader-supported magazine of long essays.")]
    pg.keep("An essay about harbors, ledgers and patience.")
    return pg, pg.doc(head, "\n".join(body))


@fixture
def math_page():
    pr = Prose("observatory", 118)
    pg = Page("math-page", "https://notes.example.edu/optics/magnification", "Telescope magnification, worked through",
              layout="lecture notes with KaTeX and MathML", site="Club Optics Notes")

    def katex(tex, display=False):
        pg.s("math", tex)
        pg.keep(tex)
        mode = ' display="block"' if display else ""
        span = "katex-display" if display else "katex"
        return (f'<span class="{span}"><span class="katex"><span class="katex-mathml"><math xmlns="http://www.w3.org/1998/Math/MathML"{mode}>'
                f'<semantics><mrow><mi>M</mi></mrow><annotation encoding="application/x-tex">{escape(tex)}</annotation></semantics></math></span>'
                f'<span class="katex-html" aria-hidden="true"><span class="base">M</span></span></span></span>')
    def mathml(tex):
        pg.s("math", tex)
        pg.keep(tex)
        return (f'<math xmlns="http://www.w3.org/1998/Math/MathML" alttext="{escape(tex)}"><mi>f</mi><mo>/</mo><mi>D</mi></math>')
    intro = pr.para(2, 3)
    pg.keep(intro)
    title = pg.h(1, pg.title)
    inline_mag = katex("M = \\frac{f_o}{f_e}")
    shown_mag = katex("M = \\frac{1200}{25} = 48", display=True)
    inline_ratio = mathml("N = f / D")
    body = [pg.nav(["Notes", "Optics", "Mechanics", "Problems"]), '<main class="lecture">', title,
            f"<p>{escape(intro)}</p>",
            f"<p>The magnification is {inline_mag}, where both focal lengths are in millimetres.</p>",
            shown_mag, f"<p>The focal ratio is written {inline_ratio} for an aperture of diameter D.</p>",
            pg.h(2, "Exit pupil"), pg.p(pr.para(2, 3)), katex("d_{exit} = \\frac{D}{M}", display=True),
            pg.p(pr.para(2, 3)), "</main>", pg.footer("Club Optics Notes. Corrections welcome at the club hut.")]
    pg.keep("The magnification is")
    pg.keep("where both focal lengths are in millimetres.")
    pg.keep("The focal ratio is written")
    pg.keep("for an aperture of diameter D.")
    return pg, pg.doc(pg.head(), "\n".join(body))


def wall_fixture(name, url, title, topic, seed, wall_html, layout, wall_kind, site, **meta):
    pr = Prose(topic, seed)
    pg = Page(name, url, title, layout=layout, expect=(wall_kind, "article"), site=site, **meta)
    first = pr.para()
    second = pr.para()
    rest = []
    pg_rest = Page(name, url, title, layout=layout, site=site, **meta)  # throwaway: served teaser bookkeeping
    teaser = [pg_rest.p(first), pg_rest.p(second)] if wall_kind == "wall" and "teaser" in layout else []
    content = [pg.p(first), pg.p(second)] + [pg.h(2, pr.phrase())] + [pg.p(pr.para()) for _ in range(3)] + \
              [pg.h(2, pr.phrase())] + [pg.p(pr.para()) for _ in range(2)]
    chrome_top = pg.nav(["Home", "Local", "Features", "Account"])
    chrome_end = pg.footer(f"{site}. Thanks for reading and for supporting local journalism.")
    head = pg.head('<meta name="author" content="%s">' % meta["author"] if meta.get("author") else "")
    served = pg.doc(head, "\n".join([chrome_top, f'<main><article>{pg_rest.h(1, title)}',
                                      *teaser, wall_html, "</article></main>", chrome_end]))
    pg.rendered = pg.doc(head, "\n".join([chrome_top, f"<main><article>{pg.h(1, title)}", *content,
                                          "</article></main>", chrome_end]))
    return pg, served


@fixture
def paywall_teaser():
    wall = ('<div class="paywall" id="regwall"><h2>Keep reading with a subscription</h2>'
            '<p>Subscribe to continue reading. Subscribers get every story, the archive and the weekend edition.</p>'
            '<a class="btn" href="/subscribe">Subscribe now</a><p>Already a subscriber? <a href="/login">Sign in</a></p></div>')
    return wall_fixture("paywall-teaser", "https://ledger.example.com/2026/11/ferry-fares-rise", "Ferry fares rise for winter",
                        "harbor", 119, wall, "news teaser then subscription wall", "wall", "Harbor Ledger",
                        author="Ilse Marrow")


@fixture
def signin_community():
    wall = ('<div class="auth-gate" role="dialog"><h2>Sign in to view this post</h2><p>This post is for members only. '
            'Sign in or create an account to continue.</p><a href="/login">Sign in</a> <a href="/join">Create an account</a></div>')
    return wall_fixture("signin-community", "https://club.example.net/posts/winter-pruning-plan", "Winter pruning plan",
                        "orchard", 120, wall, "members-only community post, sign-in gate", "wall", "Orchard Club")


@fixture
def bot_check():
    wall = ('<div class="challenge"><h2>Checking your browser before accessing club.example.net</h2>'
            '<p>This process is automatic. Your browser will redirect to your requested content shortly.</p>'
            '<p>Please enable JavaScript and cookies to continue.</p><p class="ray">Request reference 7f3a91c2</p></div>')
    return wall_fixture("bot-check", "https://club.example.net/guides/repainting-signal-mast", "Repainting the signal mast",
                        "harbor", 121, wall, "bot check page instead of the article", "wall", "Harbor Crafts Guild")


@fixture
def listicle():
    pr = Prose("garden", 122)
    pg = Page("listicle", "https://picks.example.com/best-tools-for-small-plots", "Seven tools for a small plot",
              layout="listicle with numbered headings, images and buy buttons", site="Plot Picks", author="Wren Fernsby")
    head = pg.head('<meta name="author" content="Wren Fernsby">')
    items = []
    for i in range(1, 8):
        items += [pg.h(2, f"{i}. {pr.phrase()}"),
                  pg.figure(f"/img/pick-{i}.jpg", f"Tool number {i} on a potting bench"),
                  pg.p(pr.para(2, 3)),
                  f'<div class="buy-box"><a class="btn-buy" rel="sponsored" href="https://shop.example/p/{i}">Check price at the shop</a></div>']
    pg.junk("Check price at the shop")
    body = [pg.nav(["Reviews", "Deals", "Guides"]), '<main><article>', pg.h(1, pg.title),
            '<p class="disclosure">We may earn a commission when you buy through links on this page.</p>',
            pg.p(pr.para()), *items, "</article></main>", pg.footer("Plot Picks. Independent reviews of garden gear.")]
    pg.junk("We may earn a commission when you buy through links on this page.")
    return pg, pg.doc(head, "\n".join(body))


@fixture
def wiki_style():
    pr = Prose("river", 123)
    pg = Page("wiki-style", "https://wiki.example.org/wiki/Alder_Bend", "Alder Bend",
              layout="wiki article with infobox, TOC, edit links, references, navbox", site="Valleypedia")
    refs = ["Valley Water Data, spring report, 2026.", "Survey team field notes, volume three.",
            "River keepers newsletter, issue 12."]
    for r in refs:
        pg.keep(r)
    infobox = ('<table class="infobox"><tr><th colspan="2">Alder Bend</th></tr><tr><th>Type</th><td>River meander</td></tr>'
               '<tr><th>Length</th><td>2.4 km</td></tr></table>')
    toc = ('<div id="toc" class="toc"><div class="toctitle"><h2>Contents</h2></div><ul><li><a href="#History">1 History</a></li>'
           '<li><a href="#Ecology">2 Ecology</a></li><li><a href="#References">3 References</a></li></ul></div>')
    pg.junk("Contents 1 History 2 Ecology 3 References")
    navbox = ('<div class="navbox"><table><tr><th>Rivers of the valley</th></tr><tr><td><a href="#">Mill race</a> '
              '<a href="#">Kestrel Brook</a> <a href="#">Old ford stream</a> <a href="#">Estuary reach</a></td></tr></table></div>')
    pg.junk("Rivers of the valley Mill race Kestrel Brook")
    edit = '<span class="mw-editsection">[<a href="#">edit</a>]</span>'
    lead = pr.para()
    pg.keep(lead)
    body = ['<div id="mw-head"><a href="#">Read</a> <a href="#">Edit</a> <a href="#">View history</a></div>',
            '<div id="mw-panel"><ul><li><a href="#">Main page</a></li><li><a href="#">Random article</a></li></ul></div>',
            '<div id="content" class="mw-body">', f'<h1 id="firstHeading">{escape(pg.title)}</h1>',
            '<div id="bodyContent"><div class="mw-parser-output">', infobox,
            f"<p><b>Alder Bend</b> {escape(lead)}</p>", toc,
            f'<h2><span class="mw-headline" id="History">History</span>{edit}</h2>', pg.p(pr.para()), pg.p(pr.para()),
            f'<h2><span class="mw-headline" id="Ecology">Ecology</span>{edit}</h2>', pg.p(pr.para()),
            f'<h2><span class="mw-headline" id="References">References</span>{edit}</h2>',
            '<ol class="references">' + "".join(f"<li><span class=\"reference-text\">{escape(r)}</span></li>" for r in refs) + "</ol>",
            navbox, '<div class="catlinks">Categories: <a href="#">Meanders</a> <a href="#">Valley geography</a></div>',
            "</div></div></div>", '<div id="footer">This page was last edited on 3 October 2026. Text is available under an open license.</div>']
    for h in ("History", "Ecology", "References"):
        pg.keep(h)
        pg.s("headings", h)
    pg.keep("Alder Bend")
    pg.junk("Categories: Meanders Valley geography")
    pg.junk("This page was last edited on 3 October 2026")
    return pg, pg.doc(pg.head(og=False), "\n".join(body))


@fixture
def changelog():
    pr = Prose("software", 124)
    pg = Page("changelog", "https://quill.example.dev/changelog", "Changelog",
              layout="release notes with version headings and lists", site="Quill")
    body = [pg.nav(["Docs", "Changelog", "Roadmap"]), '<main class="changelog">', pg.h(1, "Changelog"),
            pg.p("All notable changes to Quill are listed here, newest first.")]
    for version, items in [("2.4.0", ["Added `jitter` to retries", "Faster worker start on large queues",
                                       "Fixed a lock file race on Windows"]),
                           ("2.3.1", ["Fixed the schema check for nested payloads", "Docs now cover plugin hooks"]),
                           ("2.3.0", ["New `run_at` scheduling option", "Deprecated the old config loader"])]:
        body += [pg.h(2, version), pg.p(pr.para(1, 2)), pg.ul(items)]
    body += ["</main>", pg.footer("Quill changelog. Subscribe to release feeds for updates.")]
    return pg, pg.doc(pg.head(), "\n".join(body))


@fixture
def interview():
    pr = Prose("transit", 125)
    pg = Page("interview", "https://voices.example.org/interviews/night-driver", "Six questions for a night tram driver",
              layout="interview transcript with bold speakers", site="City Voices", author="Rue Wrenfield",
              published="2026-07-08")
    head = pg.head('<meta name="author" content="Rue Wrenfield"><meta property="article:published_time" content="2026-07-08">')
    qa = []
    for _ in range(6):
        q = pr.sentence()
        a = pr.para(2, 3)
        pg.keep(f"City Voices: {q}")
        pg.keep(f"Driver: {a}")
        qa += [f"<p><strong>City Voices:</strong> {escape(q)}</p>", f"<p><strong>Driver:</strong> {escape(a)}</p>"]
    body = [pg.nav(["Interviews", "Neighbourhoods", "Podcast"]), "<main><article>", pg.h(1, pg.title),
            pg.p(pr.para(2, 3)), *qa, pg.p("This interview has been edited for length and clarity."),
            "</article></main>", pg.related(junk_heads(4, 3), title="You might also like"),
            pg.footer("City Voices. Conversations with the people who keep the city running.")]
    return pg, pg.doc(head, "\n".join(body))


@fixture
def callouts_guide():
    pr = Prose("software", 126)
    pg = Page("callouts-guide", "https://handbook.example.dev/ops/on-call", "On-call handbook",
              layout="handbook with alert callouts and a glossary", site="Example Handbook")
    def callout(kind, title, text, style):
        pg.keep(text)
        if style == "github":
            return (f'<div class="markdown-alert markdown-alert-{kind}"><p class="markdown-alert-title">{title}</p>'
                    f"<p>{escape(text)}</p></div>")
        if style == "bootstrap":
            return f'<div class="alert alert-{kind}" role="alert">{escape(text)}</div>'
        return f'<div class="admonition {kind}"><p class="admonition-title">{title}</p><p>{escape(text)}</p></div>'
    body = [pg.nav(["Handbook", "Runbooks", "Teams"]), '<main class="handbook">', pg.h(1, pg.title), pg.p(pr.para()),
            callout("warning", "Warning", "Never restart the worker pool during a schema migration.", "github"),
            pg.h(2, "Before your shift"), pg.p(pr.para(2, 3)),
            callout("info", "Info", "The pager rota is published every Friday at noon.", "bootstrap"),
            pg.h(2, "Glossary"),
            pg.dl([("Error budget", "The share of failed requests a service may spend in a month."),
                   ("Freeze", "A period when only urgent fixes are merged."),
                   ("Drain", "Letting running jobs finish before a worker stops.")]),
            callout("tip", "Tip", "Write the incident timeline while it is fresh, not the next morning.", "admonition"),
            "</main>", pg.footer("Example Handbook. Internal style, public copy.")]
    return pg, pg.doc(pg.head(), "\n".join(body))


@fixture
def utility_classes():
    pr = Prose("river", 127)
    pg = Page("utility-classes", "https://stories.example.com/s/otter-camera-season", "A season on the otter camera",
              layout="utility-class layout with no semantic hints", site="Stories Example", published="2026-04-21")
    ld = {"@context": "https://schema.org", "@type": "Article", "headline": pg.title, "datePublished": "2026-04-21"}
    promo = ('<div class="bg-amber-100 text-sm py-2 text-center">Spring sale: two years of membership for the price '
             'of one</div>')
    pg.junk("Spring sale: two years of membership for the price of one")
    paras = "".join(f'<div class="text-lg leading-8 text-gray-800 mb-6">{pg.p(pr.para())}</div>' for _ in range(5))
    body = [promo, '<div class="flex flex-col min-h-screen"><div class="h-16 flex items-center px-4 border-b">'
            '<a class="font-bold" href="/">Stories</a><div class="ml-auto flex gap-4"><a href="/s">Latest</a>'
            '<a href="/topics">Topics</a><a href="/login">Log in</a></div></div>',
            '<div class="mx-auto max-w-prose px-4 py-12">', f'<div class="text-4xl font-serif mb-8">{pg.h(1, pg.title)}</div>',
            paras, f'<div class="mt-8">{pg.h(2, pr.phrase())}</div>',
            f'<div class="text-lg leading-8">{pg.p(pr.para())}</div>', "</div>",
            '<div class="grid grid-cols-3 gap-4 px-4">' + "".join(
                f'<a class="block p-4 rounded border" href="/s/{i}"><div class="text-sm">{escape(h)}</div></a>'
                for i, h in enumerate(junk_heads(5, 3))) + "</div>",
            '<div class="text-xs text-gray-500 p-8">Stories Example, made with care. Cookie settings.</div></div>']
    pg.junk(" ".join(junk_heads(5, 3)))
    pg.junk("Stories Example, made with care. Cookie settings.")
    return pg, pg.doc(pg.head(ld=ld), "\n".join(body))


@fixture
def short_post():
    pr = Prose("bakery", 128)
    pg = Page("short-post", "https://crumbs.example.net/2026/10/oven-is-back", "The oven is back",
              layout="short blog note with heavy sidebar, archive and tag cloud", site="Crumbs", published="2026-10-28")
    head = pg.head('<meta property="article:published_time" content="2026-10-28">')
    archive = "".join(f'<li><a href="/2026/{m:02d}">{name} 2026</a></li>' for m, name in
                      enumerate(["January", "February", "March", "April", "May", "June", "July", "August"], 1))
    pg.junk("January 2026 February 2026 March 2026")
    tags = " ".join(f'<a class="tag" href="/tag/{t}">{t}</a>' for t in
                    ["rye", "starter", "ovens", "market", "flour", "holidays", "workshop"])
    pg.junk("rye starter ovens market flour holidays workshop")
    note = ("The deck oven came back from the repair shop on Tuesday, a week earlier than promised. "
            "Rye returns on Thursday and the Saturday market stall opens again this weekend, so come early.")
    body = [pg.nav(["Home", "About", "Order"]), '<div class="wrap"><main class="content"><article class="post">',
            pg.h(1, pg.title), '<span class="date">October 28, 2026</span>', pg.p(note), "</article></main>",
            f'<aside class="widget-area"><section class="widget"><h3>Archive</h3><ul>{archive}</ul></section>'
            f'<section class="widget"><h3>Tags</h3><div class="tagcloud">{tags}</div></section>'
            '<section class="widget"><h3>About</h3><p>A small bakery blog about bread and the people who buy it.</p></section></aside></div>',
            pg.footer("Crumbs bakery blog. Baked fresh, posted occasionally.")]
    pg.junk("A small bakery blog about bread and the people who buy it.")
    return pg, pg.doc(head, "\n".join(body))


@fixture
def press_release():
    pr = Prose("transit", 129)
    pg = Page("press-release", "https://press.example.com/releases/canal-depot-solar", "Canal depot adds solar roof",
              layout="press release with dateline, boilerplate and media contact", site="Example Transit Press Room",
              published="2026-09-15")
    head = pg.head('<meta property="article:published_time" content="2026-09-15">')
    about = ("About Example Transit: Example Transit runs trams and night buses across the city and publishes its "
             "timetables and audits in the open.")
    body = [pg.nav(["Releases", "Media kit", "Contacts"]), '<main><div class="release">', pg.h(1, pg.title),
            pg.p("FERROW SQUARE, September 15, 2026. " + pr.para()), pg.p(pr.para()),
            pg.quote("The canal depot roof now powers the night service lights."), pg.p(pr.para()),
            pg.p(about), pg.p("Media contact: press office, press@example.com"), "</div></main>",
            pg.footer("Example Transit Press Room. All releases are free to republish.")]
    return pg, pg.doc(head, "\n".join(body))


@fixture
def spanish_article():
    rng = random.Random(130)
    pg = Page("spanish-article", "https://diario.example.es/local/obras-del-muelle", "Terminan las obras del muelle",
              layout="Spanish-language news article", lang="es", site="Diario Ejemplo", author="Marta Olivar",
              published="2026-06-05")
    head = pg.head('<meta name="author" content="Marta Olivar"><meta property="article:published_time" content="2026-06-05">')
    body = [pg.nav(["Portada", "Local", "Deportes", "Opinión"]), '<main><article>', pg.h(1, pg.title),
            pg.p(spanish_para(rng)), pg.p(spanish_para(rng)), pg.h(2, "Lo que viene ahora"), pg.p(spanish_para(rng)),
            pg.p(spanish_para(rng)), "</article></main>",
            pg.related(["Las mejores ofertas de teléfonos del fin de semana", "Cinco series que no te puedes perder"],
                       title="Lo más leído"),
            pg.footer("Diario Ejemplo. Todos los derechos reservados.")]
    return pg, pg.doc(head, "\n".join(body))


@fixture
def embeds_article():
    pr = Prose("observatory", 131)
    pg = Page("embeds-article", "https://news.example.org/2026/08/eclipse-watch-night", "Eclipse watch draws a crowd",
              layout="article with an embedded social post, video iframe and audio player", site="Ridge News",
              author="Ines Harrowgate")
    head = pg.head('<meta name="author" content="Ines Harrowgate">')
    social = "Clouds parted at the last minute and the whole field cheered."
    pg.keep(social)
    body = [pg.nav(["News", "Science", "Video"]), "<main><article>", pg.h(1, pg.title), pg.p(pr.para()),
            f'<blockquote class="social-embed" data-platform="example-social"><p>{social}</p>'
            '<p>@ridge_watcher, <a href="https://social.example/ridge_watcher/1">August 12</a></p></blockquote>',
            pg.p(pr.para()), '<div class="video-embed"><iframe src="https://video.example/embed/eclipse" '
            'title="Eclipse time-lapse" width="640" height="360"></iframe></div>', pg.p(pr.para()),
            '<figure class="audio"><audio controls src="/audio/field-sounds.mp3"></audio>'
            "<figcaption>Listen: the field at totality.</figcaption></figure>", pg.p(pr.para()),
            "</article></main>", pg.footer("Ridge News. Stories from the ridge and the club hut.")]
    pg.keep("Listen: the field at totality.")
    return pg, pg.doc(head, "\n".join(body))


@fixture
def paginated_article():
    pr = Prose("orchard", 132)
    pg = Page("paginated-article", "https://farmlife.example.com/features/cellar-ledger?page=1",
              "The cellar ledger, part one", layout="article page one of three with pagination", site="Farm Life",
              author="Hollis Pembury")
    head = pg.head('<meta name="author" content="Hollis Pembury">')
    pager = ('<nav class="pagination"><span>Page 1 of 3</span><a href="?page=2" rel="next">Next page</a>'
             '<a href="?page=3">Last</a></nav>')
    pg.junk("Page 1 of 3 Next page Last")
    body = [pg.nav(["Features", "Markets", "Machinery", "Weather"]), "<main><article>", pg.h(1, pg.title),
            *full_article(pg, pr, sections=2), pager, "</article></main>",
            pg.ad("Tractor tyres at trade prices this month only"),
            pg.footer("Farm Life magazine. Stories from working farms.")]
    return pg, pg.doc(head, "\n".join(body))


@fixture
def comments_heavy():
    pr = Prose("bakery", 133)
    pg = Page("comments-heavy", "https://crumbs.example.net/2026/09/why-rye-is-slow", "Why rye takes its time",
              layout="short post followed by a comment section longer than the post", site="Crumbs",
              published="2026-09-09")
    head = pg.head('<meta property="article:published_time" content="2026-09-09">')
    comments = []
    for i, user in enumerate(["dough_dan", "seedy_sal", "proofer9", "crusty_k", "levain_lu", "bench_bo", "rye_rita"]):
        text = pr.para(3, 4)
        pg.junk(text)
        comments.append(f'<li class="comment depth-1" id="comment-{i}"><article class="comment-body">'
                        f'<footer class="comment-meta"><b class="fn">{user}</b> <time>September {10 + i}, 2026</time>'
                        f'</footer><div class="comment-content"><p>{escape(text)}</p></div>'
                        f'<div class="reply"><a class="comment-reply-link" href="#">Reply</a></div></article></li>')
    body = [pg.nav(["Home", "About", "Order"]), '<div class="site-content"><main><article class="post">',
            pg.h(1, pg.title), '<div class="entry-content">', pg.p(pr.para()), pg.p(pr.para()), pg.p(pr.para(2, 3)),
            "</div></article>",
            f'<div id="comments" class="comments-area"><h2 class="comments-title">7 thoughts on this post</h2>'
            f'<ol class="comment-list">{"".join(comments)}</ol></div>', "</main></div>",
            pg.footer("Crumbs bakery blog. Baked fresh, posted occasionally.")]
    pg.junk("7 thoughts on this post")
    return pg, pg.doc(head, "\n".join(body))


@fixture
def split_body():
    pr = Prose("harbor", 134)
    pg = Page("split-body", "https://coast.example.com/news/2026/07/ferry-ramp-rebuilt", "The ferry ramp is rebuilt",
              layout="article body split into several containers by ads and promos", author="Pell Ashgrove",
              published="2026-07-22", site="Coast Courier")
    head = pg.head('<meta name="author" content="Pell Ashgrove">'
                   '<meta property="article:published_time" content="2026-07-22T08:00:00Z">')
    promo = "Read next: the lighthouse keeper who never missed a night"
    pg.junk(promo)
    body = [pg.nav(["News", "Coast", "Boats", "Opinion"]), "<main><article>",
            f'<div class="article-header">{pg.h(1, pg.title)}<span class="byline">Pell Ashgrove</span></div>',
            f'<div class="article-body-text">{pg.p(pr.para())}{pg.p(pr.para())}</div>',
            pg.ad("Marine insurance quotes in under two minutes"),
            f'<div class="article-body-text">{pg.p(pr.para())}{pg.h(2, pr.phrase())}{pg.p(pr.para())}</div>',
            f'<div class="inline-promo"><a href="/news/lighthouse-keeper">{promo}</a></div>',
            f'<div class="article-body-text">{pg.p(pr.para())}{pg.p(pr.para(2, 3))}</div>',
            "</article></main>", pg.related(junk_heads(6), title="Around the coast"),
            pg.footer("Coast Courier. News from the harbors and beaches.")]
    return pg, pg.doc(head, "\n".join(body))


@fixture
def links_roundup():
    pr = Prose("software", 135)
    pg = Page("links-roundup", "https://weekly.example.dev/issues/88", "Tooling weekly, issue 88",
              layout="weekly roundup where most content is annotated links", site="Tooling Weekly",
              published="2026-10-30")
    head = pg.head('<meta property="article:published_time" content="2026-10-30">')
    sections = []
    for s in range(3):
        items = []
        for i in range(4):
            slug = f"post-{s}-{i}"
            items.append(f"[{pr.phrase()}](https://blog{s}.example.org/{slug}): {pr.sentence()}")
        sections += [pg.h(2, ["Releases", "Reading", "Tools"][s]), pg.ul(items)]
    body = [pg.nav(["Issues", "Sponsor", "About"]), '<main class="issue">', pg.h(1, pg.title), pg.p(pr.para(2, 3)),
            *sections, pg.p("That is all for this week. Reply to this email with links for the next issue."),
            "</main>", pg.footer("Tooling Weekly is written by volunteers and sent every Friday.")]
    return pg, pg.doc(head, "\n".join(body))


@fixture
def faq_details():
    pr = Prose("garden", 136)
    pg = Page("faq-details", "https://plots.example.org/help/faq", "Allotment questions, answered",
              layout="FAQ built from details and summary elements", site="Fenwick Plots")
    entries = []
    for _ in range(6):
        question = pr.phrase() + "?"
        answer = pr.para(2, 3)
        pg.keep(question)
        pg.keep(answer)
        entries.append(f'<details class="faq-item"><summary>{escape(question)}</summary>'
                       f'<div class="faq-answer"><p>{escape(answer)}</p></div></details>')
    body = [pg.nav(["Plots", "Waiting list", "Help", "Contact"]), '<main class="help">', pg.h(1, pg.title),
            pg.p(pr.para(2, 3)), '<div class="faq-list">', *entries, "</div>",
            '<div class="help-contact"><h2>Still stuck?</h2><p>Write to the committee and we will get back to you.</p></div>',
            "</main>", pg.footer("Fenwick Plots. Run by plot holders for plot holders.")]
    return pg, pg.doc(pg.head(), "\n".join(body))


def build():
    written = {}
    for fn in FIXTURES:
        page, served = fn()
        written[f"{page.name}.html"] = served
        if page.rendered:
            written[f"{page.name}.rendered.html"] = page.rendered
            page.gold["rendered"] = f"{page.name}.rendered.html"
        else:
            page.gold["rendered"] = None
        written[f"{page.name}.gold.json"] = json.dumps(page.gold, indent=1, ensure_ascii=False) + "\n"
    return written


def main(check=False):
    written = build()
    stale = []
    for name, text in written.items():
        path = HERE / name
        if check:
            if not path.is_file() or path.read_text(encoding="utf-8") != text:
                stale.append(name)
        else:
            path.write_text(text, encoding="utf-8", newline="\n")
    if check and stale:
        print("stale fixtures:", ", ".join(sorted(stale)))
        return 1
    print(f"{len(FIXTURES)} fixtures, {len(written)} files" + (" (checked)" if check else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(check="--check" in sys.argv))
