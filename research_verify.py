"""Deterministic research receipt checks. No model, network or filesystem writes."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import math
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

LOW_OVERLAP_THRESHOLD = 0.15
MAX_QUOTE_CHARS = 280
MAX_SOURCE_QUOTES = 8
MAX_SOURCE_WORDS = 600
MAX_QUOTE_SECONDS = 120
TIERS = ["0", "1", "2", "2b", "2c", "3b", "4", "5"]
EMPTY_SUMMARY = "No claim passed receipt verification."
SUMMARY_LABEL = "Summary (not verified; every claim below links to its source)"
_STOP_WORDS = frozenset("""a an and are as at be been but by can could did do does
    for from had has have he her his how i if in is it its may of on or our she
    so than that the their them there these they this those to was we were what
    when where which who will with would you your""".split())
_URL_TAIL = r"[^\s<>()\[\]\"']*"
_URL = re.compile(r"(?:\b[a-z][a-z0-9+.-]*://|\b(?:mailto|javascript|data):|\bwww\.|"
                  r"\b[\w-]+(?:\.[\w-]+)*\.[a-z]{2,}\b|\b(?:\d{1,3}\.){3}\d{1,3}\b)"
                  + _URL_TAIL, re.I)
_FILE_SUFFIXES = frozenset({"py", "pyi", "js", "jsx", "ts", "tsx", "json", "toml", "yaml", "yml",
                           "md", "txt", "csv", "html", "css", "xml", "sql", "sh", "ps1", "exe"})
_CJK = re.compile(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af\uf900-\ufaff\U00020000-\U000323af]")


class VerificationError(ValueError):
    def __init__(self, message, code="invalid_arguments"):
        super().__init__(message)
        self.code = code


def has_links(text):
    for match in _URL.finditer(text):
        value = match.group().rstrip(".,;!?")
        # A bare technical filename is ordinary prose. Explicit URL syntax,
        # including a path after a file-like host, still counts as a link.
        if re.fullmatch(r"[\w.-]+", value) and value.rsplit(".", 1)[-1].lower() in _FILE_SUFFIXES:
            continue
        return True
    return False


def _object(value, keys, required):
    if not isinstance(value, dict) or set(value) - set(keys) or set(required) - set(value):
        raise VerificationError("Invalid research publish fields.")


def _string(value, name, low, high, code="invalid_arguments"):
    if not isinstance(value, str) or not low <= len(value) <= high or (low and not value.strip()):
        raise VerificationError(f"{name} must contain {low} to {high} characters.", code)


def normalize_publish(args):
    """Validate nested input even for callers that do not use the MCP schema."""
    from research import validate_run_id

    _object(args, ("run_id", "title", "summary_md", "claims", "disagreements"),
            ("run_id", "title", "summary_md", "claims"))
    validate_run_id(args["run_id"])
    _string(args["title"], "title", 1, 200)
    _string(args["summary_md"], "summary_md", 0, 1500)
    if has_links(args["summary_md"]):
        raise VerificationError("summary_md must not contain URLs.", "summary_has_links")
    claims = args["claims"]
    if not isinstance(claims, list) or not 1 <= len(claims) <= 60:
        raise VerificationError("claims must contain 1 to 60 claims.")
    out = deepcopy(args)
    ids = set()
    for claim in out["claims"]:
        _object(claim, ("id", "text", "section", "excerpt_refs", "attribution", "contested", "counter_refs", "judge"),
                ("id", "text", "section", "excerpt_refs"))
        _string(claim["id"], "id", 1, 40)
        if not re.fullmatch(r"[A-Za-z0-9_-]+", claim["id"]) or claim["id"] in ids:
            raise VerificationError("Claim ids must be distinct letters, digits, underscores or hyphens.")
        ids.add(claim["id"])
        _string(claim["text"], "text", 1, 400)
        _string(claim["section"], "section", 1, 80)
        claim.setdefault("attribution", "channel")
        claim.setdefault("contested", False)
        claim.setdefault("counter_refs", [])
        if claim["attribution"] not in ("speaker", "channel") or type(claim["contested"]) is not bool:
            raise VerificationError("Invalid claim attribution or contested value.")
        if "judge" in claim and claim["judge"] not in ("supports", "partial", "no"):
            raise VerificationError("judge must be supports, partial or no.")
        for field, low, high in (("excerpt_refs", 1, 2), ("counter_refs", 0, 4)):
            refs = claim[field]
            if not isinstance(refs, list) or not low <= len(refs) <= high:
                code = "too_many_quotes" if isinstance(refs, list) and len(refs) > high else "invalid_arguments"
                raise VerificationError(f"{field} must contain {low} to {high} references.", code)
            for ref in refs:
                _object(ref, ("excerpt_id", "quote"), ("excerpt_id", "quote"))
                _string(ref["excerpt_id"], "excerpt_id", 1, 200)
                code = "quote_too_long" if isinstance(ref["quote"], str) and len(ref["quote"]) > MAX_QUOTE_CHARS else "invalid_arguments"
                _string(ref["quote"], "quote", 1, MAX_QUOTE_CHARS, code)
    disagreements = out.setdefault("disagreements", [])
    if not isinstance(disagreements, list) or len(disagreements) > 10:
        raise VerificationError("disagreements must contain at most 10 entries.")
    for entry in disagreements:
        _object(entry, ("topic", "claim_ids"), ("topic", "claim_ids"))
        _string(entry["topic"], "topic", 1, 200)
        linked = entry["claim_ids"]
        if (not isinstance(linked, list) or not 2 <= len(linked) <= 6
                or any(not isinstance(i, str) or i not in ids for i in linked)
                or len(set(linked)) != len(linked)):
            raise VerificationError("A disagreement must reference 2 to 6 distinct submitted claim ids.")
    return out


def normalize_quote(text, *, captions=False):
    # Keep the brief's NFC + whitespace rule, with the caption-specific fold.
    from library_briefs import _normalize_text

    text = _normalize_text(text)
    if captions:
        text = text.casefold()
        text = "".join(c if not unicodedata.category(c).startswith("P") or (
            0 < i < len(text) - 1 and text[i - 1].isdigit() and text[i + 1].isdigit()) else " "
            for i, c in enumerate(text))
        text = " ".join(text.split())
    return text


def _quote_tokens(text, *, captions=False):
    """Normalized whole tokens with offsets into the unescaped stored text.

    Normalize each complete word so combining marks and casefold expansions
    keep their original offsets. Numeric punctuation stays inside its token.
    """
    def word(char):
        return char.isalnum() or unicodedata.category(char).startswith("M") or (char == "_" and not captions)

    tokens, i = [], 0
    while i < len(text):
        char, end = text[i], i + 1
        if char.isspace():
            i = end
            continue
        if word(char):
            while end < len(text):
                if word(text[end]):
                    end += 1
                elif (unicodedata.category(text[end]).startswith("P") and text[end - 1].isdigit()
                      and end + 1 < len(text) and text[end + 1].isdigit()):
                    end += 2
                else:
                    break
        elif captions and unicodedata.category(char).startswith("P"):
            i = end
            continue
        value = unicodedata.normalize("NFC", text[i:end])
        tokens.append((value.casefold() if captions else value, i, end))
        i = end
    return tokens


def time_label(seconds):
    total = max(0, math.floor(seconds))
    hours, rest = divmod(total, 3600)
    minutes, seconds = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"


def deep_link(source, seconds):
    """Only stored source metadata supplies destinations; never claim payloads."""
    item_id = source["item_id"]
    if source.get("kind") == "youtube" and re.fullmatch(r"[A-Za-z0-9_-]{11}", item_id):
        return f"https://www.youtube.com/watch?v={item_id}&t={math.floor(seconds)}s"
    if source.get("kind") == "podcast":
        if source.get("episode_url"):
            return source["episode_url"]
        enclosure = source.get("enclosure_url") or source.get("source_url")
        if enclosure:
            return enclosure.split("#", 1)[0] + f"#t={math.floor(seconds)}"
    if source.get("kind") == "library":
        from research import _youtube_id
        url = source.get("source_url") or ""
        if _youtube_id(url):
            parsed = urlsplit(url)
            query = [(k, v) for k, v in parse_qsl(parsed.query) if k not in {"t", "start"}]
            query.append(("t", f"{math.floor(seconds)}s"))
            return urlunsplit(parsed._replace(query=urlencode(query), fragment=""))
    return source.get("source_url") or ""


def doubt_spans(source, start, end):
    return [deepcopy(span) for span in source.get("reliability_spans", [])
            if isinstance(span, dict) and all(type(span.get(key)) in (int, float)
                and math.isfinite(span[key]) for key in ("start", "end"))
            and 0 <= span["start"] < span["end"] and span["start"] < end and start < span["end"]]


def bind_ref(ref, excerpts, sources):
    """Bind a quote to current cues selected by this run's saved excerpt."""
    excerpt = excerpts.get(ref["excerpt_id"])
    if excerpt is None:
        return None, "excerpt_unknown"
    source = sources.get(excerpt["item_id"])
    if (not source or source.get("source_revision") != excerpt.get("source_revision")
            or (excerpt.get("cue_revision") and excerpt["cue_revision"] != source.get("cue_revision"))):
        return None, "revision_changed"
    if len(ref["quote"]) > MAX_QUOTE_CHARS:
        return None, "quote_too_long"
    cue_ids = excerpt.get("cue_ids", [])
    by_id = {cue["seq"]: cue for cue in source["cues"]}
    if not cue_ids or any(i not in by_id for i in cue_ids):
        return None, "revision_changed"
    cues = [by_id[i] for i in cue_ids]
    captions = source.get("transcript_source") == "captions"
    needle = [t[0] for t in _quote_tokens(ref["quote"], captions=captions)]
    if not needle:
        return None, "quote_not_found"
    raw = "\n".join(c["text"] for c in cues)
    tokens, cursor = [], 0
    for number, cue in enumerate(cues):
        part = _quote_tokens(cue["text"], captions=captions)
        if not part or (number and cue["seq"] != cues[number - 1]["seq"] + 1):
            # A sentinel prevents matching across missing or tokenless cues.
            tokens.append((None, cursor, cursor, number))
        tokens.extend((value, cursor + first, cursor + last, number) for value, first, last in part)
        cursor += len(cue["text"]) + 1
    values = [t[0] for t in tokens]
    matches, failure = [], "quote_not_found"
    for offset in range(len(tokens) - len(needle) + 1):
        if values[offset:offset + len(needle)] != needle:
            continue
        first, last = tokens[offset], tokens[offset + len(needle) - 1]
        matched = cues[first[3]:last[3] + 1]
        start, end = matched[0]["start"], max(c["end"] for c in matched)
        if end - start > MAX_QUOTE_SECONDS:
            failure = "quote_spans_too_far"
            continue
        left, right = first[1], last[2]
        if captions:
            # Preserve punctuation attached to the boundary words too. Every
            # rendered character comes from the stored slice, never the draft.
            while left and unicodedata.category(raw[left - 1]).startswith("P"):
                left -= 1
            while right < len(raw) and unicodedata.category(raw[right]).startswith("P"):
                right += 1
        stored_quote = raw[left:right]
        if len(stored_quote) > MAX_QUOTE_CHARS:
            failure = "quote_too_long"
            continue
        matches.append((start, end, stored_quote))
    if not matches:
        return None, failure
    if len(matches) != 1:
        return None, "quote_ambiguous"
    start, end, stored_quote = matches[0]
    doubt = doubt_spans(source, start, end)
    return {"excerpt_id": ref["excerpt_id"], "item_id": excerpt["item_id"], "quote": stored_quote,
            "source_revision": source["source_revision"], "start": start, "end": end,
            "t": math.floor(start), "time_label": time_label(start), "deep_link": deep_link(source, start),
            "channel": source.get("channel") or "Unknown channel", "title": source.get("title") or "Untitled",
            "asr_doubt": doubt, "listen_at": f"listen at {time_label(max(start, min(s['start'] for s in doubt)))}" if doubt else None}, None


def lexical_overlap(text, quotes):
    def tokens(value):
        return set(re.findall(r"\w+", value.casefold())) - _STOP_WORDS
    claim, evidence = tokens(text), tokens(" ".join(quotes))
    return len(claim & evidence) / len(claim | evidence) if claim | evidence else 0.0


def quote_words(text):
    """Count unspaced CJK characters as well as space-delimited words."""
    return len(_CJK.findall(text)) + len(_CJK.sub(" ", text).split())


def searched_keys(run):
    return {c["key"] for c in [*run.get("candidates_pool", []), *run.get("candidates", [])]} | set(run.get("captures", {}))


def verify_report(payload, run, sources, *, date):
    """Return a renderable report and a quote-free verification ledger.

    Failed main references drop the claim. Counter failures are listed separately.
    Source budgets count each rendered receipt, including counter-evidence.
    """
    accepted, flagged, dropped, rendered = [], [], [], []
    budget = Counter()
    words = Counter()
    counter_search = any(c.get("stance_hint") == "counter" for c in run.get("evidence_calls", []))
    judge_started = any("judge" in c for c in payload["claims"])
    for claim in payload["claims"]:
        reasons, quotes, counters, removed = [], [], [], []
        support_keys, counter_keys = set(), set()

        def ref_key(bound):
            return bound["item_id"], bound["start"], bound["end"], bound["quote"]

        for ref in claim["excerpt_refs"]:
            bound, reason = bind_ref(ref, run.get("excerpts", {}), sources)
            if reason:
                reasons.append(reason)
            elif ref_key(bound) not in support_keys:
                support_keys.add(ref_key(bound))
                quotes.append(bound)
        if len(claim["excerpt_refs"]) > 2:
            reasons.append("too_many_quotes")
        if claim.get("judge") == "no":
            reasons.append("judge_no")
        if reasons:
            dropped.append({"id": claim["id"], "text": claim["text"], "reasons": list(dict.fromkeys(reasons)),
                            "judge": claim.get("judge")})
            continue
        for ref in claim.get("counter_refs", []):
            bound, reason = bind_ref(ref, run.get("excerpts", {}), sources)
            if reason:
                removed.append({"excerpt_id": ref["excerpt_id"], "reason": reason, "kind": "counter"})
            elif ref_key(bound) in support_keys:
                removed.append({"excerpt_id": ref["excerpt_id"], "reason": "duplicate_ref", "kind": "counter"})
            elif ref_key(bound) not in counter_keys:
                counter_keys.add(ref_key(bound))
                counters.append(bound)
        valid_counters = bool(counters)

        def capped(refs, kind):
            kept = []
            for ref in refs:
                item = ref["item_id"]
                count = quote_words(ref["quote"])
                if budget[item] >= MAX_SOURCE_QUOTES or words[item] + count > MAX_SOURCE_WORDS:
                    removed.append({"excerpt_id": ref["excerpt_id"], "reason": "source_quote_cap", "kind": kind})
                else:
                    budget[item] += 1
                    words[item] += count
                    kept.append(ref)
            return kept

        quotes = capped(quotes, "support")
        if not quotes:
            dropped.append({"id": claim["id"], "text": claim["text"], "reasons": ["source_quote_cap"],
                            "judge": claim.get("judge"), "dropped_refs": removed})
            continue
        counters = capped(counters, "counter")
        flags = []
        # There is no confirmed speaker-name mapping surface yet.
        if claim.get("attribution") == "speaker":
            flags.append("speaker_unconfirmed")
        if any(q["asr_doubt"] for q in quotes + counters):
            flags.append("asr_doubt")
        if claim.get("judge") == "partial":
            flags.append("overstated")
        overlap = lexical_overlap(claim["text"], [q["quote"] for q in quotes])
        if overlap < LOW_OVERLAP_THRESHOLD:
            flags.append("low_overlap")
        if "judge" not in claim and (overlap < LOW_OVERLAP_THRESHOLD or judge_started):
            flags.append("needs_judge")
        if claim.get("contested") and (not valid_counters or not counter_search):
            flags.append("one_sided_search")
        flags.extend(r["reason"] for r in removed)
        flags = list(dict.fromkeys(flags))
        entry = {"id": claim["id"], "reasons": flags, "judge": claim.get("judge"),
                 "overlap": round(overlap, 6), "dropped_refs": removed}
        (flagged if flags else accepted).append(entry)
        rendered.append({"id": claim["id"], "text": claim["text"], "section": claim["section"],
                         "attribution": "channel", "flags": flags, "quotes": quotes, "counter_quotes": counters})
    source_claims, channel_claims = {}, {}
    for claim in rendered:
        for ref in claim["quotes"] + claim["counter_quotes"]:
            source_claims.setdefault(ref["item_id"], set()).add(claim["id"])
            channel_claims.setdefault(ref["channel"].casefold(), set()).add(claim["id"])
    tiers = TIERS.copy()
    if all("judge" in c for c in payload["claims"]):
        tiers.insert(tiers.index("3b"), "3")
    stats = {"accepted": len(accepted), "flagged": len(flagged), "dropped": len(dropped),
             "claims": len(rendered), "distinct_sources": len(source_claims), "distinct_channels": len(channel_claims),
             "max_channel_share": max((len(ids) / len(rendered) for ids in channel_claims.values()), default=0),
             "tiers_run": tiers}
    verification = {"accepted": accepted, "flagged": flagged, "dropped": dropped, "stats": stats}
    listed = []
    for item, ids in source_claims.items():
        source = sources[item]
        listed.append({key: source.get(key) for key in (
            "item_id", "title", "channel", "published", "duration_s", "transcript_source", "source_url",
            "episode_url", "enclosure_url", "kind") } | {"claim_count": len(ids)})
    live_ids = {c["id"] for c in rendered}
    disagreements = [{"topic": d["topic"], "claim_ids": [i for i in d["claim_ids"] if i in live_ids]}
                     for d in payload.get("disagreements", [])]
    return {"title": payload["title"], "question": run["scope"]["question"], "date": date,
            "summary": payload["summary_md"] if rendered else EMPTY_SUMMARY, "claims": rendered, "sources": listed,
            "disagreements": [d for d in disagreements if len(d["claim_ids"]) >= 2],
            "sources_searched": len(searched_keys(run)),
            "verification": verification}
