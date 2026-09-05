"""Librarian dry run: subscription-only, apply-nothing proof harness.

Reads evidence cards from a uoink index (a COPY, never the live file), runs
taxonomy induction + assignment + a re-shelving pass through the user's own
subscription clients (Claude Code `claude -p`, Codex `codex exec`, Antigravity
`agy --print`), and writes a report. No API keys. No writes to the index.

This is the shape of the Phase 2 loop: uoink prepares bounded evidence
packets; the calling client does the thinking; uoink would persist the
structured result. Here the "persist" step is a JSON file on disk.

Usage (from the worktree root):
    python scripts/librarian/dryrun.py --index _scratch/index-copy.db --out E:/AI/projects/uoink/handoff/council/library-proof
    python scripts/librarian/dryrun.py --index ... --phase assign --client codex --limit 12
"""
from __future__ import annotations

import argparse
import shutil
import concurrent.futures as cf
import json
import os
import random
import re
import sqlite3
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROMPTS = HERE / "prompts"

def _default_codex_exe() -> str:
    """The Codex CLI: UOINK_CODEX_EXE, else `codex` on PATH, else the global npm
    install. Never a OneDrive path: npm cannot update a package there, and the
    Control Room moved to E:\\AI\\projects\\agent-control-room on 2026-09-04."""
    env = os.environ.get("UOINK_CODEX_EXE")
    if env:
        return env
    on_path = shutil.which("codex")
    if on_path:
        return on_path
    return os.path.expandvars(
        r"%APPDATA%\npm\node_modules\@openai\codex\node_modules\@openai"
        r"\codex-win32-x64\vendor\x86_64-pc-windows-msvc\bin\codex.exe")


CODEX_EXE = _default_codex_exe()
AGY_EXE = os.environ.get("UOINK_AGY_EXE", os.path.expandvars(r"%LOCALAPPDATA%\agy\bin\agy.exe"))

# ---------------------------------------------------------------------------
# Schemas (JSON Schema, enforced by the clients' structured-output modes)
# ---------------------------------------------------------------------------
NODE = {
    "type": "object",
    "properties": {
        "path": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 3},
        "definition": {"type": "string"},
        "include": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 8},
        "exclude": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
    },
    "required": ["path", "definition", "include", "exclude"],
    "additionalProperties": False,
}
INDUCE_SCHEMA = {
    "type": "object",
    "properties": {"nodes": {"type": "array", "items": NODE, "minItems": 10, "maxItems": 120}},
    "required": ["nodes"],
    "additionalProperties": False,
}
ASSIGNMENT = {
    "type": "object",
    "properties": {
        "video_id": {"type": "string"},
        "shelf_paths": {
            "type": "array",
            "items": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 3},
            "minItems": 0,
            "maxItems": 3,
        },
        "confidence": {"type": "number"},
        "evidence_quote": {"type": "string"},
        "unmapped": {"type": "boolean"},
        "proposed_new_leaf": {"type": "string"},
    },
    "required": ["video_id", "shelf_paths", "confidence", "evidence_quote", "unmapped", "proposed_new_leaf"],
    "additionalProperties": False,
}
ASSIGN_SCHEMA = {
    "type": "object",
    "properties": {"assignments": {"type": "array", "items": ASSIGNMENT}},
    "required": ["assignments"],
    "additionalProperties": False,
}
RESHELVE_ITEM = {
    "type": "object",
    "properties": {
        "video_id": {"type": "string"},
        "belongs": {"type": "boolean"},
        "confidence": {"type": "number"},
        "evidence_quote": {"type": "string"},
    },
    "required": ["video_id", "belongs", "confidence", "evidence_quote"],
    "additionalProperties": False,
}
RESHELVE_SCHEMA = {
    "type": "object",
    "properties": {"verdicts": {"type": "array", "items": RESHELVE_ITEM}},
    "required": ["verdicts"],
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# Evidence cards (read-only over the index copy)
# ---------------------------------------------------------------------------
def _connect(path: Path) -> sqlite3.Connection:
    uri = f"file:{path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _pick_spread(clips: list[sqlite3.Row], k: int) -> list[sqlite3.Row]:
    """k clips spread across the timeline, preferring longer text in each bin."""
    if len(clips) <= k:
        return list(clips)
    bins: list[list[sqlite3.Row]] = [[] for _ in range(k)]
    n = len(clips)
    for i, c in enumerate(clips):
        bins[min(k - 1, i * k // n)].append(c)
    out = []
    for b in bins:
        if b:
            out.append(max(b, key=lambda r: len(r["text"] or "")))
    return out


def build_cards(conn: sqlite3.Connection, *, per_item: int = 6, clip_chars: int = 240) -> list[dict]:
    have_clips = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='clips'"
    ).fetchone() is not None
    rows = conn.execute(
        "SELECT video_id, slug, title, channel, topic, hook_type, yoinked_at, "
        "source_type, platform, author, metadata_json FROM yoinks "
        "WHERE deleted_at IS NULL ORDER BY yoinked_at"
    ).fetchall()
    cards = []
    for y in rows:
        vid = y["video_id"]
        if have_clips:
            clips = conn.execute(
                "SELECT start, end, text, source_deep_link FROM clips WHERE video_id=? ORDER BY seq",
                (vid,),
            ).fetchall()
        else:
            clips = conn.execute(
                "SELECT timestamp_start AS start, timestamp_end AS end, text, source_deep_link "
                "FROM citations WHERE video_id=? AND kind='transcript_chunk' ORDER BY seq",
                (vid,),
            ).fetchall()
        picked = _pick_spread(clips, per_item)
        meta = {}
        try:
            meta = json.loads(y["metadata_json"] or "{}")
        except json.JSONDecodeError:
            pass
        desc = (meta.get("description") or "") if isinstance(meta, dict) else ""
        cards.append({
            "video_id": vid,
            "slug": y["slug"],
            "title": y["title"],
            "channel": y["channel"] or y["author"],
            "current_topic": y["topic"],
            "hook_type": y["hook_type"],
            "yoinked_at": y["yoinked_at"],
            "source_type": y["source_type"],
            "platform": y["platform"],
            "description": re.sub(r"\s+", " ", desc)[:300],
            "clips": [
                {
                    "t": round(float(c["start"] or 0)),
                    "text": re.sub(r"\s+", " ", c["text"] or "")[:clip_chars],
                    "link": c["source_deep_link"],
                }
                for c in picked
            ],
            "clip_count": len(clips),
        })
    return cards


def card_text(card: dict) -> str:
    lines = [
        f"### {card['video_id']}",
        f"title: {card['title']}",
        f"channel: {card['channel']} · source: {card['platform'] or card['source_type'] or 'unknown'} · saved: {str(card['yoinked_at'])[:10]}",
    ]
    if card["description"]:
        lines.append(f"description: {card['description']}")
    for c in card["clips"]:
        lines.append(f"[{c['t']}s] {c['text']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Subscription clients
# ---------------------------------------------------------------------------
class ClientError(RuntimeError):
    pass


def run_client(client: str, prompt: str, schema: dict, *, model: str | None, scratch: Path, tag: str) -> tuple[dict, dict]:
    """Return (structured_json, usage_meta). Raises ClientError on failure."""
    scratch.mkdir(parents=True, exist_ok=True)
    schema_path = scratch / f"schema-{tag}.json"
    schema_path.write_text(json.dumps(schema), encoding="utf-8")
    prompt_path = scratch / f"prompt-{tag}.txt"
    prompt_path.write_text(prompt, encoding="utf-8")
    t0 = time.time()
    if client == "claude":
        # Prompt goes over stdin: Windows caps argv at ~8K chars via a shell
        # and ~32K without; a 12-card batch is bigger than both.
        exe = shutil.which("claude") or "claude"
        cmd = [exe, "-p", "--json-schema", json.dumps(schema), "--output-format", "json",
               "--tools", "", "--no-session-persistence"]
        if model:
            cmd += ["--model", model]
        res = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if res.returncode != 0 or not res.stdout.strip():
            raise ClientError(f"claude exit {res.returncode}: {res.stderr[:400]}")
        env = json.loads(res.stdout)
        if env.get("is_error") or env.get("structured_output") is None:
            raise ClientError(f"claude no structured_output: {str(env.get('result'))[:300]}")
        u = env.get("usage", {})
        meta = {
            "client": "claude", "model": model or "default", "ms": int((time.time() - t0) * 1000),
            "input_tokens": u.get("input_tokens", 0), "cache_read": u.get("cache_read_input_tokens", 0),
            "cache_create": u.get("cache_creation_input_tokens", 0), "output_tokens": u.get("output_tokens", 0),
            "list_price_usd_estimate": env.get("total_cost_usd", 0.0),
        }
        return env["structured_output"], meta
    if client == "codex":
        last = scratch / f"codex-last-{tag}.txt"
        cmd = [CODEX_EXE, "exec", "--skip-git-repo-check", "--ephemeral", "--output-schema", str(schema_path), "-o", str(last)]
        if model:
            cmd += ["-m", model]
        cmd.append("-")  # read the prompt from stdin
        res = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if res.returncode != 0 or not last.exists():
            raise ClientError(f"codex exit {res.returncode}: {res.stderr[:400]} {res.stdout[-400:]}")
        raw = last.read_text(encoding="utf-8").strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ClientError(f"codex non-JSON last message: {raw[:200]}") from e
        m = re.search(r"tokens used\D*(\d[\d,]*)", res.stdout + res.stderr, re.I)
        meta = {"client": "codex", "model": model or "default", "ms": int((time.time() - t0) * 1000),
                "tokens_used_reported": int(m.group(1).replace(",", "")) if m else None}
        return data, meta
    if client == "gemini":
        # Antigravity headless: prompt must be an argument (stdin bodies make it
        # reach for file tools it cannot get permission for). Short prompts only.
        if len(prompt) > 7000:
            raise ClientError("gemini/agy: prompt too long for argv; use --client claude or codex for batches")
        cmd = [AGY_EXE, f"--print={prompt}", "--json-schema", json.dumps(schema), "--output-format", "json",
               "--new-project", "--disable-slash-commands", "--print-timeout", "5m"]
        if model:
            cmd += ["--model", model]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        try:
            env = json.loads(res.stdout)
        except json.JSONDecodeError as e:
            raise ClientError(f"agy non-JSON: {res.stdout[:300]} {res.stderr[:300]}") from e
        if env.get("status") != "SUCCESS":
            raise ClientError(f"agy status {env.get('status')}: {env.get('error')}")
        data = json.loads(env["response"])
        u = env.get("usage", {})
        meta = {"client": "gemini", "model": model or "default", "ms": int((time.time() - t0) * 1000),
                "input_tokens": u.get("input_tokens", 0), "cache_read": u.get("cache_read_tokens", 0),
                "output_tokens": u.get("output_tokens", 0)}
        return data, meta
    raise ClientError(f"unknown client {client}")


def with_retry(fn, tries: int = 3):
    last = None
    for i in range(tries):
        try:
            return fn()
        except ClientError as e:  # noqa: PERF203
            last = e
            time.sleep(2 * (i + 1))
    raise last  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Phases
# ---------------------------------------------------------------------------
def load_prompt(name: str) -> str:
    return (PROMPTS / name).read_text(encoding="utf-8")


def taxonomy_text(nodes: list[dict]) -> str:
    out = []
    for n in sorted(nodes, key=lambda n: n["path"]):
        out.append(" > ".join(n["path"]))
        out.append(f"  def: {n['definition']}")
        out.append(f"  include: {'; '.join(n['include'])}")
        if n.get("exclude"):
            out.append(f"  exclude: {'; '.join(n['exclude'])}")
    return "\n".join(out)


def stratified_sample(cards: list[dict], n: int, seed: int = 7) -> list[dict]:
    rnd = random.Random(seed)
    by_topic: dict[str, list[dict]] = defaultdict(list)
    for c in cards:
        by_topic[c["current_topic"] or "None"].append(c)
    # Oversample Uncategorized: it is the pile the Librarian must fix.
    weights = {t: (2.0 if t == "Uncategorized" else 1.0) for t in by_topic}
    total_w = sum(weights[t] * len(v) for t, v in by_topic.items())
    picked: list[dict] = []
    for t, v in by_topic.items():
        k = max(1, round(n * weights[t] * len(v) / total_w))
        picked += rnd.sample(v, min(k, len(v)))
    rnd.shuffle(picked)
    return picked[:n]


def phase_induce(cards, args, scratch) -> list[dict]:
    sample = stratified_sample(cards, args.sample)
    prompt = load_prompt("induce.md").replace("{{CARDS}}", "\n\n".join(card_text(c) for c in sample))
    data, meta = with_retry(lambda: run_client(args.client, prompt, INDUCE_SCHEMA, model=args.induce_model, scratch=scratch, tag="induce"))
    nodes = data["nodes"]
    # Normalize: unique paths, ensure parents exist.
    seen = {}
    for n in nodes:
        key = tuple(p.strip() for p in n["path"])
        n["path"] = list(key)
        seen[key] = n
    for key in list(seen):
        for depth in range(1, len(key)):
            parent = key[:depth]
            if parent not in seen:
                seen[parent] = {"path": list(parent), "definition": f"Parent shelf for {' > '.join(key)}", "include": [], "exclude": []}
    nodes = list(seen.values())
    return nodes, meta, sample


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def phase_assign(cards, nodes, args, scratch):
    tax = taxonomy_text(nodes)
    base = load_prompt("assign.md").replace("{{TAXONOMY}}", tax)
    batches = list(_chunks(cards, args.batch))
    results: list[dict] = []
    metas: list[dict] = []
    errors: list[str] = []

    def one(i, batch):
        prompt = base.replace("{{CARDS}}", "\n\n".join(card_text(c) for c in batch))
        ids = {c["video_id"] for c in batch}
        data, meta = with_retry(lambda: run_client(args.client, prompt, ASSIGN_SCHEMA, model=args.assign_model, scratch=scratch, tag=f"assign-{i}"))
        out = [a for a in data["assignments"] if a["video_id"] in ids]
        missing = ids - {a["video_id"] for a in out}
        return i, out, meta, missing

    with cf.ThreadPoolExecutor(max_workers=args.parallel) as ex:
        futs = [ex.submit(one, i, b) for i, b in enumerate(batches)]
        for f in cf.as_completed(futs):
            try:
                i, out, meta, missing = f.result()
                results += out
                metas.append(meta)
                if missing:
                    errors.append(f"batch {i}: {len(missing)} items not returned: {sorted(missing)[:5]}")
                print(f"  batch {i+1}/{len(batches)} ok ({meta['ms']} ms)", file=sys.stderr)
            except Exception as e:  # noqa: BLE001
                errors.append(str(e)[:300])
                print(f"  batch failed: {str(e)[:120]}", file=sys.stderr)
    return results, metas, errors


def phase_reshelve(cards, assignments, args, scratch, concept: dict):
    """Introduce a new shelf and re-check every item under its parent."""
    parent = concept["path"][:-1]
    by_id = {a["video_id"]: a for a in assignments}
    candidates = [c for c in cards if any(list(p[:len(parent)]) == parent for p in by_id.get(c["video_id"], {}).get("shelf_paths", []))]
    if not candidates:  # fallback: everything currently in the parent's old topic bucket
        candidates = [c for c in cards if (c["current_topic"] or "") == parent[0]]
    base = load_prompt("reshelve.md").replace("{{CONCEPT}}", json.dumps(concept, indent=1))
    batches = list(_chunks(candidates, args.batch))
    verdicts: list[dict] = []
    metas: list[dict] = []
    errors: list[str] = []

    def one(i, batch):
        prompt = base.replace("{{CARDS}}", "\n\n".join(card_text(c) for c in batch))
        ids = {c["video_id"] for c in batch}
        data, meta = with_retry(lambda: run_client(args.client, prompt, RESHELVE_SCHEMA, model=args.assign_model, scratch=scratch, tag=f"reshelve-{i}"))
        return [v for v in data["verdicts"] if v["video_id"] in ids], meta

    with cf.ThreadPoolExecutor(max_workers=args.parallel) as ex:
        futs = [ex.submit(one, i, b) for i, b in enumerate(batches)]
        for f in cf.as_completed(futs):
            try:
                out, meta = f.result()
                verdicts += out
                metas.append(meta)
            except Exception as e:  # noqa: BLE001
                errors.append(str(e)[:300])
    return candidates, verdicts, metas, errors


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def summarize_usage(metas: list[dict]) -> dict:
    tot = Counter()
    for m in metas:
        for k in ("input_tokens", "cache_read", "cache_create", "output_tokens", "ms"):
            tot[k] += int(m.get(k) or 0)
        tot["calls"] += 1
        tot["list_price_usd_estimate"] += float(m.get("list_price_usd_estimate") or 0.0)
    return dict(tot)


def write_report(out: Path, *, cards, nodes, assignments, metas, errors, reshelve, sample_ids, args, wall_s):
    out.mkdir(parents=True, exist_ok=True)
    (out / "cards.json").write_text(json.dumps(cards, indent=1), encoding="utf-8")
    (out / "taxonomy.json").write_text(json.dumps(nodes, indent=1), encoding="utf-8")
    (out / "assignments.json").write_text(json.dumps(assignments, indent=1), encoding="utf-8")
    (out / "usage.json").write_text(json.dumps({"assign": metas, "errors": errors}, indent=1), encoding="utf-8")
    if reshelve:
        (out / "reshelve.json").write_text(json.dumps(reshelve, indent=1), encoding="utf-8")

    by_id = {c["video_id"]: c for c in cards}
    before = Counter((c["current_topic"] or "None") for c in cards)
    top = Counter()
    leaf = Counter()
    multi = 0
    unmapped = []
    low = []
    for a in assignments:
        if a["unmapped"] or not a["shelf_paths"]:
            unmapped.append(a)
            continue
        if len(a["shelf_paths"]) > 1:
            multi += 1
        p = a["shelf_paths"][0]
        top[p[0]] += 1
        leaf[" > ".join(p)] += 1
        if a["confidence"] < 0.6:
            low.append(a)
    assigned_ids = {a["video_id"] for a in assignments}

    lines = [
        "# Librarian dry run — proof report",
        "",
        f"Generated {time.strftime('%Y-%m-%d %H:%M')} · client `{args.client}` · induce model `{args.induce_model}` · assign model `{args.assign_model}` · **no API keys, subscription clients only** · nothing written to any index.",
        "",
        "## Numbers",
        "",
        f"- Items (cards): **{len(cards)}** · assigned: **{len(assignments)}** · unmapped: **{len(unmapped)}** · multi-shelf: {multi} · low-confidence (<0.6): {len(low)} · missing from responses: {len(cards) - len(assigned_ids)}",
        f"- Taxonomy nodes: **{len(nodes)}** (top shelves: {len([n for n in nodes if len(n['path'])==1])}) induced from a stratified sample of {len(sample_ids)} cards",
        f"- Wall time: **{wall_s:.0f} s** · calls: {summarize_usage(metas).get('calls')} · parallel: {args.parallel} · batch: {args.batch}",
        f"- Client-reported usage (assignment phase): {json.dumps(summarize_usage(metas))}",
        f"- Errors: {len(errors)}",
        "",
        "## Before → after: top-level distribution",
        "",
        "| Before (keyword `topics.json`) | n | After (Librarian, primary shelf) | n |",
        "|---|---|---|---|",
    ]
    b = before.most_common()
    a_ = top.most_common()
    for i in range(max(len(b), len(a_))):
        l = f"{b[i][0]} | {b[i][1]}" if i < len(b) else " | "
        r = f"{a_[i][0]} | {a_[i][1]}" if i < len(a_) else " | "
        lines.append(f"| {l} | {r} |")
    lines += ["", f"Uncategorized before: **{before.get('Uncategorized', 0)}** → unmapped after: **{len(unmapped)}**", ""]

    lines += ["## Shelves (primary assignments, with counts)", ""]
    tree: dict[str, dict] = {}
    for path, n in leaf.items():
        parts = path.split(" > ")
        d = tree
        for p in parts:
            d = d.setdefault(p, {})
        d["__n"] = d.get("__n", 0) + n

    def walk(d, depth=0):
        for k, v in sorted(d.items(), key=lambda kv: -(kv[1].get("__n", 0) if isinstance(kv[1], dict) else 0)):
            if k == "__n":
                continue
            n = sum_n(v)
            lines.append(f"{'  ' * depth}- {k} ({n})")
            walk(v, depth + 1)

    def sum_n(v):
        if not isinstance(v, dict):
            return 0
        return v.get("__n", 0) + sum(sum_n(x) for k, x in v.items() if k != "__n")

    walk(tree)

    lines += ["", "## Sample assignments with evidence (first 25 by confidence)", "", "| Item | Shelf | Conf | Evidence quote |", "|---|---|---|---|"]
    for a in sorted([x for x in assignments if not x["unmapped"] and x["shelf_paths"]], key=lambda x: -x["confidence"])[:25]:
        c = by_id.get(a["video_id"], {})
        lines.append(f"| {str(c.get('title',''))[:60]} | {' > '.join(a['shelf_paths'][0])} | {a['confidence']:.2f} | {a['evidence_quote'][:110]} |")

    if unmapped:
        lines += ["", "## Unmapped (Librarian asks for a new leaf)", "", "| Item | Proposed leaf |", "|---|---|"]
        for a in unmapped[:40]:
            c = by_id.get(a["video_id"], {})
            lines.append(f"| {str(c.get('title',''))[:70]} | {a.get('proposed_new_leaf','')[:80]} |")

    if reshelve:
        r = reshelve
        moved = [v for v in r["verdicts"] if v["belongs"]]
        lines += ["", f"## Re-shelving pass: new concept `{' > '.join(r['concept']['path'])}`", "",
                  f"Trigger: {r['trigger']}", "",
                  f"Re-checked **{len(r['candidates'])}** items already filed under `{' > '.join(r['concept']['path'][:-1])}` against the new shelf. **{len(moved)}** belong on it. Calls: {r['usage'].get('calls')} · {r['usage'].get('ms',0)/1000:.0f} s.", "",
                  "| Item (saved) | Conf | Evidence quote |", "|---|---|---|"]
        for v in sorted(moved, key=lambda v: -v["confidence"]):
            c = by_id.get(v["video_id"], {})
            lines.append(f"| {str(c.get('title',''))[:60]} ({str(c.get('yoinked_at',''))[:10]}) | {v['confidence']:.2f} | {v['evidence_quote'][:120]} |")

    if errors:
        lines += ["", "## Errors", ""] + [f"- {e}" for e in errors]
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"report: {out / 'report.md'}", file=sys.stderr)


# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", required=True, help="path to a COPY of index.db (opened read-only)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--client", default="claude", choices=["claude", "codex", "gemini"])
    ap.add_argument("--induce-model", default="opus")
    ap.add_argument("--assign-model", default="sonnet")
    ap.add_argument("--phase", default="all", choices=["cards", "induce", "assign", "reshelve", "all"])
    ap.add_argument("--sample", type=int, default=80)
    ap.add_argument("--batch", type=int, default=12)
    ap.add_argument("--parallel", type=int, default=3)
    ap.add_argument("--limit", type=int, default=0, help="only the first N cards (testing)")
    ap.add_argument("--taxonomy", help="reuse an existing taxonomy.json")
    ap.add_argument("--assignments", help="reuse an existing assignments.json (for reshelve)")
    ap.add_argument("--concept", help="path to a concept JSON for the reshelve phase")
    args = ap.parse_args(argv)

    out = Path(args.out)
    scratch = out / "_scratch"
    t0 = time.time()
    conn = _connect(Path(args.index))
    cards = build_cards(conn)
    if args.limit:
        cards = cards[: args.limit]
    has_clips = conn.execute("SELECT name FROM sqlite_master WHERE name='clips'").fetchone() is not None
    print(f"cards: {len(cards)} (clips table: {'yes' if has_clips else 'no'})", file=sys.stderr)
    if args.phase == "cards":
        out.mkdir(parents=True, exist_ok=True)
        (out / "cards.json").write_text(json.dumps(cards, indent=1), encoding="utf-8")
        return 0

    nodes, sample = [], []
    if args.taxonomy:
        nodes = json.loads(Path(args.taxonomy).read_text(encoding="utf-8"))
    if args.phase in ("induce", "all") and not nodes:
        print("inducing taxonomy…", file=sys.stderr)
        nodes, meta, sample = phase_induce(cards, args, scratch)
        out.mkdir(parents=True, exist_ok=True)
        (out / "taxonomy.json").write_text(json.dumps(nodes, indent=1), encoding="utf-8")
        (out / "induce-usage.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
        print(f"  {len(nodes)} nodes in {meta['ms']} ms", file=sys.stderr)
        if args.phase == "induce":
            return 0

    assignments, metas, errors = [], [], []
    if args.assignments:
        assignments = json.loads(Path(args.assignments).read_text(encoding="utf-8"))
    if args.phase in ("assign", "all"):
        if not nodes:
            raise SystemExit("assign needs --taxonomy or phase all")
        print(f"assigning {len(cards)} cards in batches of {args.batch}…", file=sys.stderr)
        assignments, metas, errors = phase_assign(cards, nodes, args, scratch)

    reshelve = None
    if args.phase in ("reshelve", "all"):
        concept = json.loads(Path(args.concept).read_text(encoding="utf-8")) if args.concept else json.loads(load_prompt("concept-loop-engineering.json"))
        # Trigger evidence: how often the concept's cue terms hit the clip index today.
        hits = 0
        for term in concept.get("include", [])[:6]:
            try:
                hits += conn.execute(
                    "SELECT count(*) FROM clips WHERE text LIKE ?", (f"%{term}%",)
                ).fetchone()[0]
            except sqlite3.OperationalError:
                pass
        trigger = f"cue-term hits in the clip layer today: {hits}; concept coined {concept.get('coined','?')}; re-check requested for everything under `{' > '.join(concept['path'][:-1])}`"
        print("re-shelving pass…", file=sys.stderr)
        candidates, verdicts, rmetas, rerrors = phase_reshelve(cards, assignments, args, scratch, concept)
        reshelve = {"concept": concept, "trigger": trigger, "candidates": [c["video_id"] for c in candidates],
                    "verdicts": verdicts, "usage": summarize_usage(rmetas), "errors": rerrors}
        nodes = nodes + [concept] if not any(n["path"] == concept["path"] for n in nodes) else nodes

    write_report(out, cards=cards, nodes=nodes, assignments=assignments, metas=metas, errors=errors,
                 reshelve=reshelve, sample_ids=[c["video_id"] for c in sample], args=args, wall_s=time.time() - t0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
