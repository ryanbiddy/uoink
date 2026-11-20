"""Reader benchmark: how much of a web page survives as clean Markdown.

Scores the two ways a web page reaches the library against the synthetic
fixtures in tests/fixtures/reader (see make_fixtures.py there):

* ``helper``: a pasted link. The helper fetches the URL itself (here: the
  fixture's served bytes through an offline fake opener) and runs
  page_extractor.extract_page, exactly as /extract/page does.
* ``extension``: "Uoink this page" in the browser. The extension reads the
  open tab's DOM (the fixture's rendered DOM when the page renders with
  JavaScript or the user is signed in past a wall) with the vendored Defuddle
  build plus extension/lib/page-capture.js, in jsdom, and the helper's
  page_dom_capture checks the payload. Before 3.18 the extension sent only the
  URL, so the "before" for this path is the helper fetch judged against what
  the user could see in the tab.

Metrics, per path (articles = fixtures where the user should get the text):
  recall      share of gold words that came through (token multiset)
  precision   share of output words that are gold words (junk lowers it)
  block_recall share of gold blocks found whole
  junk_leaks  known junk blocks (nav, cookie text, ads, related...) found whole
  structure   headings, list items, code (+ language), table rows, links,
              images, quotes, footnotes, math, captions found in Markdown form
  metadata    title, author, publish date and site name
  outcome     article / wall / shell / thin as expected

Run:  python tests/reader_bench.py [--path helper|extension|both] [--json OUT]
                                   [--fixture NAME] [--show NAME]
tests/test_reader_benchmark.py runs the same code and enforces the floors in
tests/fixtures/reader/thresholds.json. Nothing here touches the network.
"""
from __future__ import annotations

import argparse
from collections import Counter
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "reader"
NODE_RUNNER = ROOT / "tests" / "js" / "reader_capture_bench.mjs"
JSDOM_DIR = ROOT / "tests" / "js" / "reader" / "node_modules" / "jsdom"
STRUCTURE_KINDS = ("headings", "list_items", "code", "code_lang", "tables", "links", "images", "quotes",
                   "footnotes", "math", "captions")
LANG_ALIASES = {"js": "javascript", "javascript": "javascript", "sh": "bash", "shell": "bash", "bash": "bash",
                "console": "bash", "zsh": "bash", "yml": "yaml", "yaml": "yaml", "py": "python",
                "python": "python", "json": "json", "ts": "typescript", "typescript": "typescript"}

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ---- fixtures -----------------------------------------------------------------
def load_fixtures(names=None):
    out = []
    for gold_path in sorted(FIXTURES.glob("*.gold.json")):
        gold = json.loads(gold_path.read_text(encoding="utf-8"))
        if names and gold["name"] not in names:
            continue
        served = (FIXTURES / f"{gold['name']}.html").read_bytes()
        rendered = (FIXTURES / gold["rendered"]).read_bytes() if gold.get("rendered") else None
        out.append({"gold": gold, "served": served, "rendered": rendered})
    return out


# ---- text helpers ---------------------------------------------------------------
_WORD = re.compile(r"\w+")


def words(text):
    return _WORD.findall((text or "").lower())


def norm(text):
    return " ".join(words(text))


def squash(text):
    return re.sub(r"\s+", "", text or "")


_IMG = re.compile(r"!\[([^\]]*)\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
_LINK = re.compile(r"(?<!!)\[((?:[^\[\]]|\[[^\]]*\])*)\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
_FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})\s*([\w+#.-]*)")


def md_plain(md):
    """Markdown to the words a reader sees (code kept, syntax dropped)."""
    out = []
    for line in (md or "").splitlines():
        if _FENCE.match(line):
            continue
        if re.fullmatch(r"\s*\|?[\s:|-]*-{3,}[\s:|-]*\|?\s*", line):
            continue
        s = _IMG.sub(lambda m: f" {m.group(1)} ", line)
        s = re.sub(r"\[\^[^\]]+\]:?", " ", s)
        s = _LINK.sub(lambda m: f" {m.group(1)} ", s)
        s = re.sub(r"^\s{0,3}#{1,6}\s+", "", s)
        s = re.sub(r"^\s*(?:>\s?)+", "", s)
        s = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s+)?", "", s)
        s = s.replace("|", " ")
        out.append(s)
    return "\n".join(out)


def saved_body(title, markdown):
    """What the reader opens: the title line, then the body (persist_page_yoink drops a duplicate title)."""
    body = (markdown or "").strip()
    first, _, rest = body.partition("\n")
    if re.match(r"#\s", first) and norm(first) == norm(title):
        body = rest.lstrip()
    return f"# {title}\n\n{body}" if title else body


# ---- structure extraction ----------------------------------------------------------
def md_headings(md):
    return [norm(m.group(1)) for m in re.finditer(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", md, re.M)]


def md_list_items(md):
    return [norm(md_plain(m.group(1))) for m in
            re.finditer(r"^\s*(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s+)?(.+)$", md, re.M)]


def md_fences(md):
    blocks, lines, i = [], md.splitlines(), 0
    while i < len(lines):
        m = _FENCE.match(lines[i])
        if not m:
            i += 1
            continue
        fence, lang, body = m.group(1), m.group(2).lower(), []
        i += 1
        while i < len(lines) and not lines[i].strip().startswith(fence[0] * len(fence)):
            body.append(lines[i])
            i += 1
        blocks.append({"lang": lang or None, "text": "\n".join(body)})
        i += 1
    return blocks


def md_table_rows(md):
    rows = []
    for line in md.splitlines():
        s = line.strip()
        if s.startswith("|") and not re.fullmatch(r"\|?[\s:|-]*-{3,}[\s:|-]*\|?", s):
            rows.append(tuple(norm(md_plain(c)) for c in s.strip("|").split("|")))
    return rows


def md_quotes(md):
    quotes, current = [], []
    for line in md.splitlines():
        if re.match(r"^\s*>", line):
            current.append(re.sub(r"^\s*(?:>\s?)+", "", line))
        elif current:
            quotes.append(norm(md_plain("\n".join(current))))
            current = []
    if current:
        quotes.append(norm(md_plain("\n".join(current))))
    return quotes


def md_footnotes(md):
    notes = []
    for m in re.finditer(r"^\[\^[^\]]+\]:\s*(.*(?:\n(?: {2,}|\t).*)*)", md, re.M):
        notes.append(norm(md_plain(m.group(1))))
    return notes


def md_math(md):
    found = [squash(m.group(1)) for m in re.finditer(r"\$\$(.+?)\$\$", md, re.S)]
    stripped = re.sub(r"\$\$(.+?)\$\$", " ", md, flags=re.S)
    found += [squash(m.group(1)) for m in re.finditer(r"(?<![\\$])\$([^$\n]+?)\$", stripped)]
    return found


def lang_of(lang):
    return LANG_ALIASES.get((lang or "").lower(), (lang or "").lower() or None)


def structure_scores(gold_structure, md):
    """{kind: (found, total)} for each structure kind with gold items."""
    plain_norm = norm(md_plain(md))
    heads = set(md_headings(md))
    items = set(md_list_items(md))
    fences = md_fences(md)
    rows = set(md_table_rows(md))
    links = {(norm(t), h) for t, h in _LINK.findall(md)}
    images = {(norm(a), s) for a, s in _IMG.findall(md)}
    quotes = md_quotes(md)
    notes = md_footnotes(md)
    maths = md_math(md)
    out = {}
    g = gold_structure

    def tally(kind, gold_items, hit):
        if gold_items:
            out[kind] = (sum(1 for item in gold_items if hit(item)), len(gold_items))

    tally("headings", g["headings"], lambda h: norm(h) in heads)
    tally("list_items", g["list_items"], lambda t: norm(t) in items)
    fence_by_text = {squash(f["text"]): f for f in fences}
    tally("code", g["code"], lambda c: squash(c["text"]) in fence_by_text)
    tally("code_lang", [c for c in g["code"] if c.get("lang")],
          lambda c: squash(c["text"]) in fence_by_text
          and lang_of(fence_by_text[squash(c["text"])]["lang"]) == lang_of(c["lang"]))
    gold_rows = [tuple(norm(cell) for cell in row) for table in g["tables"] for row in table]
    tally("tables", gold_rows, lambda r: r in rows)
    tally("links", g["links"], lambda link: (norm(link["text"]), link["href"]) in links)
    tally("images", g["images"], lambda img: (norm(img["alt"]), img["src"]) in images)
    tally("quotes", g["quotes"], lambda q: any(norm(q) in quote for quote in quotes))
    tally("footnotes", g["footnotes"], lambda n: any(norm(n) in note for note in notes))
    tally("math", g["math"], lambda tex: squash(tex) in maths)
    tally("captions", g["captions"], lambda c: norm(c) in plain_norm)
    return out


def date_of(value):
    m = re.search(r"\d{4}-\d{2}-\d{2}", str(value or ""))
    return m.group(0) if m else ""


def metadata_score(gold, meta):
    checks = [norm(meta.get("title")) == norm(gold["title"])]
    want = gold["metadata"]
    if want.get("author"):
        checks.append(bool(norm(want["author"])) and norm(want["author"]) in norm(meta.get("author")))
    if want.get("published"):
        checks.append(date_of(meta.get("published")) == want["published"])
    if want.get("site_name"):
        checks.append(norm(meta.get("site_name")) == norm(want["site_name"]))
    return sum(checks), len(checks)


# ---- scoring ----------------------------------------------------------------------
def score_fixture(gold, result, expected):
    """result: {outcome, title, markdown, metadata{title,author,published,site_name}}."""
    row = {"name": gold["name"], "expected": expected, "outcome": result["outcome"],
           "outcome_ok": result["outcome"] == expected}
    if expected != "article":
        return row
    meta = result.get("metadata") or {}
    row["metadata"] = metadata_score(gold, meta) if result["outcome"] == "article" else (0, 1 + len(gold["metadata"]))
    if result["outcome"] != "article":
        row.update(recall=0.0, precision=None, block_recall=0.0, junk_leaks=0, structure={
            kind: (0, total) for kind, (_, total) in structure_scores(gold["structure"], "").items()})
        return row
    md = saved_body(result.get("title") or "", result.get("markdown") or "")
    out_words = Counter(words(md_plain(md)))
    gold_words = Counter(words(" ".join(gold["keep"])))
    hit = sum((out_words & gold_words).values())
    plain_norm = norm(md_plain(md))
    row.update(
        recall=hit / max(1, sum(gold_words.values())),
        precision=hit / max(1, sum(out_words.values())),
        block_recall=sum(1 for block in gold["keep"] if norm(block) in plain_norm) / max(1, len(gold["keep"])),
        junk_leaks=sum(1 for junk in gold["junk"] if norm(junk) and norm(junk) in plain_norm),
        leaked=[junk[:60] for junk in gold["junk"] if norm(junk) and norm(junk) in plain_norm],
        structure=structure_scores(gold["structure"], md),
    )
    return row


def aggregate(rows):
    articles = [r for r in rows if r["expected"] == "article"]
    saved = [r for r in articles if r["outcome"] == "article"]
    mean = lambda values: round(sum(values) / len(values), 4) if values else None  # noqa: E731
    structure = {}
    for kind in STRUCTURE_KINDS:
        found = sum(r["structure"].get(kind, (0, 0))[0] for r in articles)
        total = sum(r["structure"].get(kind, (0, 0))[1] for r in articles)
        if total:
            structure[kind] = round(found / total, 4)
    meta_found = sum(r["metadata"][0] for r in articles)
    meta_total = sum(r["metadata"][1] for r in articles)
    recall = mean([r["recall"] for r in articles])
    precision = mean([r["precision"] for r in saved])
    return {
        "fixtures": len(rows),
        "articles_expected": len(articles),
        "articles_saved": len(saved),
        "outcome_accuracy": mean([1.0 if r["outcome_ok"] else 0.0 for r in rows]),
        "recall": recall,
        "precision": precision,
        "f1": round(2 * recall * precision / (recall + precision), 4) if recall and precision else 0.0,
        "block_recall": mean([r["block_recall"] for r in articles]),
        "junk_leaks": sum(r["junk_leaks"] for r in articles),
        "structure": structure,
        "metadata": round(meta_found / meta_total, 4) if meta_total else None,
    }


# ---- capture paths ------------------------------------------------------------------
class _Response(io.BytesIO):
    status = 200

    def __init__(self, raw, url):
        super().__init__(raw)
        self._url = url

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def _outcome_from_failure(result):
    if result.get("page_state") in {"wall", "shell", "thin"}:
        return result["page_state"]
    diagnostic = result.get("diagnostic") or result.get("error") or ""
    if "login or paywall" in diagnostic:
        return "wall"
    if "JavaScript" in diagnostic:
        return "shell"
    if "too little" in diagnostic or result.get("code") == "article_body_not_found":
        return "thin"
    return "error"


def _python_meta(result):
    meta = result.get("metadata") or {}
    return {"title": result.get("title") or meta.get("title"), "author": meta.get("author"),
            "published": meta.get("published_date"), "site_name": meta.get("site_name")}


def run_helper(fixture):
    """Pasted link: the helper fetches the served bytes and extracts them."""
    import page_extractor as pages
    pages._CRAWL4AI_AVAILABLE = False
    gold = fixture["gold"]
    result = pages.extract_page(None, gold["url"], enforce_allowlist=False,
                                http_open=lambda url, **_: _Response(fixture["served"], gold["url"]))
    if not result.get("ok"):
        return {"outcome": _outcome_from_failure(result), "markdown": "", "title": "", "metadata": {},
                "raw": result}
    return {"outcome": "article", "title": result.get("title") or "", "markdown": result.get("markdown") or "",
            "metadata": _python_meta(result), "raw": result}


def extension_available():
    return bool(shutil.which("node")) and JSDOM_DIR.is_dir() and NODE_RUNNER.is_file() and \
        (ROOT / "extension" / "lib" / "page-capture.js").is_file()


def run_extension_all(fixtures):
    """Uoink this page: Defuddle + page-capture.js on the DOM the user sees, then the helper's checks."""
    names = [f["gold"]["name"] for f in fixtures]
    proc = subprocess.run([shutil.which("node"), str(NODE_RUNNER), str(FIXTURES), *names], cwd=ROOT,
                          capture_output=True, text=True, encoding="utf-8", timeout=600)
    if proc.returncode != 0:
        raise RuntimeError(f"reader_capture_bench.mjs failed:\n{proc.stdout[-2000:]}\n{proc.stderr[-4000:]}")
    captures = json.loads(proc.stdout)["results"]
    import page_dom_capture
    out = {}
    for fixture in fixtures:
        name = fixture["gold"]["name"]
        capture = captures.get(name) or {"ok": False}
        if not capture.get("ok"):
            out[name] = {"outcome": capture.get("page_state") or "thin", "markdown": "", "title": "",
                         "metadata": {}, "raw": capture}
            continue
        result = page_dom_capture.build_extract_result(capture.get("payload") or {})
        if not result.get("ok"):
            out[name] = {"outcome": _outcome_from_failure(result), "markdown": "", "title": "", "metadata": {},
                         "raw": result}
            continue
        out[name] = {"outcome": "article", "title": result.get("title") or "",
                     "markdown": result.get("markdown") or "", "metadata": _python_meta(result), "raw": result}
    return out


def run(path, fixtures):
    """Score one path. path: helper | extension | extension-before."""
    rows = []
    if path == "extension":
        results = run_extension_all(fixtures)
    for fixture in fixtures:
        gold = fixture["gold"]
        if path == "extension":
            result = results[gold["name"]]
            expected = gold["expect"]["extension"]
        else:
            result = run_helper(fixture)
            expected = gold["expect"]["extension" if path == "extension-before" else "python"]
        row = score_fixture(gold, result, expected)
        row["_markdown"] = saved_body(result.get("title") or "", result.get("markdown") or "") \
            if result["outcome"] == "article" else ""
        rows.append(row)
    return rows, aggregate(rows)


# ---- floors -------------------------------------------------------------------------
THRESHOLDS = FIXTURES / "thresholds.json"
RATIO_KEYS = ("outcome_accuracy", "recall", "precision", "block_recall", "metadata")


def make_floors(rows, agg, slack=0.01, fixture_slack=0.05):
    """Floors a little under what the path measures now, so only a real drop fails."""
    floor = lambda value, s: round(max(0.0, value - s), 3)  # noqa: E731
    return {
        "aggregate": {key: floor(agg[key], slack) for key in RATIO_KEYS if agg.get(key) is not None},
        "junk_leaks_max": agg["junk_leaks"],
        "structure": {kind: floor(value, slack) for kind, value in agg["structure"].items()},
        "fixtures": {r["name"]: {"outcome": r["outcome"], **({"recall": floor(r["recall"], fixture_slack)}
                                                           if r.get("recall") is not None else {})}
                     for r in rows if r["outcome_ok"]},
    }


def check_floors(rows, agg, floors):
    """Every way the path got worse than its floors, as readable lines."""
    problems = []
    for key, minimum in floors["aggregate"].items():
        if agg.get(key) is None or agg[key] < minimum:
            problems.append(f"{key} {agg.get(key)} < floor {minimum}")
    if agg["junk_leaks"] > floors["junk_leaks_max"]:
        problems.append(f"junk_leaks {agg['junk_leaks']} > max {floors['junk_leaks_max']}")
    for kind, minimum in floors["structure"].items():
        if agg["structure"].get(kind, 0.0) < minimum:
            problems.append(f"structure.{kind} {agg['structure'].get(kind)} < floor {minimum}")
    by_name = {r["name"]: r for r in rows}
    for name, want in floors["fixtures"].items():
        row = by_name.get(name)
        if row is None:
            problems.append(f"{name}: fixture missing")
            continue
        if row["outcome"] != want["outcome"]:
            problems.append(f"{name}: outcome {row['outcome']} (was {want['outcome']})")
        elif "recall" in want and (row.get("recall") or 0.0) < want["recall"]:
            problems.append(f"{name}: recall {row.get('recall'):.3f} < floor {want['recall']}")
    return problems


# ---- report -------------------------------------------------------------------------
def fmt(value):
    if value is None:
        return "  -  "
    return f"{value:.3f}" if isinstance(value, float) else str(value)


def print_report(label, rows, agg, *, stream=sys.stdout):
    print(f"\n== {label} ==", file=stream)
    print(f"{'fixture':<22}{'outcome':<16}{'recall':>8}{'prec':>8}{'blocks':>8}{'junk':>6}  structure", file=stream)
    for r in rows:
        outcome = r["outcome"] + ("" if r["outcome_ok"] else f" (want {r['expected']})")
        structure = " ".join(f"{k}:{f}/{t}" for k, (f, t) in sorted((r.get("structure") or {}).items()) if f < t)
        print(f"{r['name']:<22}{outcome:<16}{fmt(r.get('recall')):>8}{fmt(r.get('precision')):>8}"
              f"{fmt(r.get('block_recall')):>8}{fmt(r.get('junk_leaks')):>6}  {structure}", file=stream)
    print(json.dumps(agg, indent=1), file=stream)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--path", choices=["helper", "extension", "extension-before", "both"], default="both")
    parser.add_argument("--fixture", action="append")
    parser.add_argument("--show", help="print the saved Markdown for one fixture")
    parser.add_argument("--json", help="write rows and aggregates to this file")
    parser.add_argument("--update-thresholds", action="store_true",
                        help="rewrite tests/fixtures/reader/thresholds.json from this run (all fixtures only)")
    args = parser.parse_args(argv)
    fixtures = load_fixtures(args.fixture)
    paths = ["helper", "extension"] if args.path == "both" else [args.path]
    report, floors = {}, {}
    for path in paths:
        if path == "extension" and not extension_available():
            print("\n== extension == skipped: run `npm ci --prefix tests/js/reader` for jsdom")
            continue
        rows, agg = run(path, fixtures)
        report[path] = {"aggregate": agg, "rows": [{k: v for k, v in r.items() if k != "_markdown"} for r in rows]}
        floors[path] = make_floors(rows, agg)
        print_report(path, rows, agg)
        if THRESHOLDS.is_file() and not args.fixture:
            saved = json.loads(THRESHOLDS.read_text(encoding="utf-8"))
            if path in saved:
                problems = check_floors(rows, agg, saved[path])
                print(f"floors: {'ok' if not problems else 'BELOW'}" + "".join(f"\n  {p}" for p in problems))
        if args.show:
            for r in rows:
                if r["name"] == args.show:
                    print(f"\n---- {path}: {args.show} ----\n{r['_markdown']}\n---- end ----")
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=1), encoding="utf-8")
    if args.update_thresholds:
        if args.fixture:
            parser.error("--update-thresholds needs the full fixture set")
        saved = json.loads(THRESHOLDS.read_text(encoding="utf-8")) if THRESHOLDS.is_file() else {}
        saved.update(floors)
        THRESHOLDS.write_text(json.dumps(saved, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {THRESHOLDS.relative_to(ROOT)} for {', '.join(sorted(floors))}")
    return 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUTF8", "1")
    sys.exit(main())
