"""tests/test_library_word_cap_audit.py - Independent word-cap checks for stage 2 (run S).

Written by the claude engine from PHASE2-STAGE2-BRIEF-2026-09-05.md (reservation 5 and the
claude section) and the stage 2 sketch, not from Astra's diff. The contract under test:

    Every membership quote has 1 to 24 words after NFC normalisation and whitespace
    collapse. Case and punctuation are preserved. 25 or more words are rejected with a
    field-specific reason; the rejected submission is preserved; nothing is staged from
    it; the planned retry remains available. Every membership is validated, including
    secondaries. The 1,000-character defensive limit stays. Both the packet path and the
    supported full-card path go through the common service.

Design: each case builds a disposable index whose single clip is a 30-word excerpt. Every
quote is a prefix of that excerpt, so the occurrence check passes for 23, 24, 25 and 26
words alike and only the word cap can separate acceptance from rejection. The rejection
code is Astra's choice; these checks require the rejection to name the quote field and to
give a reason that mentions the cap, and they never accept a harness-side `client_error`
as the service's answer.

Expected on the dispatch base (04cf29c, service without a cap): every "rejected" case for
25+ words is red; every acceptance case and the whitespace-only, 1,001-character and
control cases are green. After Astra's cap lands, all cases must be green. Nothing here
runs a model, opens the live index, or touches port 5179. The source is ASCII only: the
composed and decomposed forms are built with chr() so no editor can normalise them.
"""
from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

import pytest

import library_cards
from index import Index
from library_work import LibraryWorkService, RequestContext

GATE = "Stage 2 word cap: 1 to 24 words per membership quote"

# Thirty distinct short words; the joined excerpt is 182 characters, inside the librarian
# profile's 240-character excerpt limit, so the packet carries it untruncated.
BASE_WORDS = (
    "alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel", "india", "juliet",
    "kilo", "lima", "mike", "november", "oscar", "papa", "quebec", "romeo", "sierra", "tango",
    "uniform", "victor", "whiskey", "xray", "yankee", "zulu", "one", "two", "three", "four",
)
assert len(BASE_WORDS) == 30 and len(set(BASE_WORDS)) == 30

COMPOSED = "caf" + chr(0x00E9)          # NFC: one code point, LATIN SMALL LETTER E WITH ACUTE
DECOMPOSED = "cafe" + chr(0x0301)       # NFD: plain e followed by COMBINING ACUTE ACCENT
assert COMPOSED != DECOMPOSED
assert unicodedata.normalize("NFC", DECOMPOSED) == COMPOSED
assert len(DECOMPOSED.split()) == 1

# Reasons that count as naming the cap. The existing occurrence message ("Quote must occur
# in one specified excerpt") matches none of them, so an unimplemented cap cannot pass.
WORD_CAP_HINTS = ("word", "24", "25", "cap", "length", "long")

SHELF_PRIMARY = "shelf_valid"
SHELF_SECONDARY = "shelf_other"
PATH_PRIMARY = ["Valid Shelf"]
PATH_SECONDARY = ["Other Shelf"]


def accented(form: str) -> tuple:
    """BASE_WORDS with the fifth word replaced, so it sits inside every 23+ word prefix."""
    words = list(BASE_WORDS)
    words[4] = form
    return tuple(words)


def quote_of(n: int, words: Sequence[str] = BASE_WORDS, sep: str = " ") -> str:
    assert 1 <= n <= len(words)
    return sep.join(words[:n])


def word_count(text: str) -> int:
    """The brief's count: NFC, then split on whitespace and rejoin with single spaces."""
    return len(" ".join(unicodedata.normalize("NFC", text).split()).split())


@dataclass
class Env:
    idx: Any
    svc: LibraryWorkService
    ctx: RequestContext
    work: Dict[str, Any]
    clock: List[int]
    run_id: str
    video_id: str
    client_id: str

    def count(self, table: str) -> int:
        return self.idx._conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]

    def claim(self) -> Dict[str, Any]:
        res = self.svc.claim_work(self.ctx, {
            "action": "claim", "run_id": self.run_id, "client_id": self.client_id,
            "max_items": 1, "lease_seconds": 600,
        })
        assert res.get("ok") is True, res
        assert len(res["work"]) == 1, res
        return res["work"][0]


def build_env(root, excerpt_text: str, *, video_id: str = "vid_cap_01") -> Env:
    root.mkdir(parents=True, exist_ok=True)
    idx = Index.open(root / "test.db")
    clock = [1_000_000]
    svc = LibraryWorkService(idx, root / "library", clock=lambda: clock[0])
    operator = RequestContext(authenticated=True, client_id="operator", session_id="s_op",
                              operator=True, local_user_confirmed=True)
    idx.upsert_yoink(dict(
        video_id=video_id, slug=video_id, title="Word cap fixture", topic="Old",
        yoinked_at="2026-09-05", corpus_path="", sidecar_path="",
    ))
    with idx.write_transaction() as conn:
        conn.execute(
            "INSERT INTO clips(video_id, seq, start, end, text) VALUES (?, 0, 10.0, 25.0, ?)",
            (video_id, excerpt_text),
        )
    tax = svc.approve_taxonomy(operator, {
        "version_id": "tax_cap_v1",
        "nodes": [
            {"shelf_id": SHELF_PRIMARY, "path": PATH_PRIMARY, "definition": "Primary fixture shelf",
             "include": ["valid"], "exclude": ["invalid"]},
            {"shelf_id": SHELF_SECONDARY, "path": PATH_SECONDARY, "definition": "Secondary fixture shelf",
             "include": ["other"], "exclude": ["valid"]},
        ],
    })
    assert tax.get("ok") is True, tax
    run_id = "run_cap_01"
    run = svc.prepare_run(operator, {
        "run_id": run_id, "version_id": "tax_cap_v1", "video_ids": [video_id], "prompt_hash": "0" * 64,
    })
    assert run.get("ok") is True, run
    client_id = "client_cap"
    ctx = RequestContext(authenticated=True, client_id=client_id, session_id="s_cap")
    env = Env(idx=idx, svc=svc, ctx=ctx, work={}, clock=clock, run_id=run_id,
              video_id=video_id, client_id=client_id)
    env.work = env.claim()
    # Fixture sanity: a short excerpt reaches the packet whole; the librarian profile cuts
    # anything longer at 240 characters, which the character-limit case relies on.
    excerpt = env.work["card"]["excerpts"][0]
    if len(excerpt_text) <= 240:
        assert excerpt["text"] == excerpt_text and excerpt["truncated"] is False, excerpt
    else:
        assert excerpt["text"] == excerpt_text[:240] and excerpt["truncated"] is True, excerpt
    return env


@pytest.fixture
def make_env(tmp_path):
    opened: List[Any] = []

    def factory(excerpt_text: str = " ".join(BASE_WORDS), *, name: str = "one", video_id: str = "vid_cap_01") -> Env:
        env = build_env(tmp_path / name, excerpt_text, video_id=video_id)
        opened.append(env.idx)
        return env

    yield factory
    for idx in opened:
        try:
            idx.close()
        except Exception:
            pass


def membership(env: Env, quote: str, *, shelf_id: str = SHELF_PRIMARY, shelf_path: Optional[List[str]] = None,
               basis: str = "packet", card_hash: Optional[str] = None, confidence: float = 0.85) -> Dict[str, Any]:
    card = env.work["card"]
    excerpt = card["excerpts"][0]
    return {
        "shelf_id": shelf_id,
        "shelf_path": list(shelf_path or (PATH_PRIMARY if shelf_id == SHELF_PRIMARY else PATH_SECONDARY)),
        "confidence": confidence,
        "evidence": {
            "basis": basis,
            "kind": excerpt["evidence_kind"],
            "excerpt_id": excerpt["excerpt_id"],
            "card_hash": card_hash or card["card_hash"],
            "quote": quote,
        },
    }


def submission(env: Env, memberships: List[Dict[str, Any]], *, key: str = "key_cap_01",
               work: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    work = work or env.work
    return {
        "work_id": work["work_id"],
        "client_id": env.client_id,
        "attempt_token": work["attempt_token"],
        "submission_key": key,
        "schema_version": 1,
        "video_id": work["video_id"],
        "source_revision": work["source_revision"],
        "taxonomy_revision": work["taxonomy_revision"],
        "packet_hash": work["packet_hash"],
        "result": {"outcome": "assigned", "memberships": memberships},
        "usage": {"status": "unavailable", "reason": "fixture: no model ran"},
    }


def full_card(env: Env) -> Dict[str, Any]:
    """The same full-profile card the service rebuilds for `basis=fetched_full`."""
    conn = env.idx._conn
    item = dict(conn.execute("SELECT * FROM yoinks WHERE video_id=?", (env.video_id,)).fetchone())
    clips = [dict(c) for c in conn.execute("SELECT * FROM clips WHERE video_id=? ORDER BY seq", (env.video_id,))]
    card = library_cards.build_card(item, clips, profile="full",
                                    corpus_text=library_cards.read_corpus_head(item.get("corpus_path")))
    packet_card = env.work["card"]
    assert card["source_revision"] == packet_card["source_revision"]
    assert card["excerpts"][0]["excerpt_id"] == packet_card["excerpts"][0]["excerpt_id"]
    assert card["card_hash"] != packet_card["card_hash"], "profiles must hash differently"
    return card


def assert_accepted(env: Env, res: Dict[str, Any], *, staged: int) -> None:
    assert res.get("ok") is True, res
    assert res.get("outcome") == "accepted", res
    assert res.get("rejected") == [], res
    assert len(res.get("accepted_memberships") or []) == staged, res
    assert env.count("library_proposals") == staged
    assert env.count("item_shelves") == 0


def assert_rejected_on_quote(env: Env, res: Dict[str, Any], *, membership_index: Optional[int] = None,
                             require_cap_hint: bool = True) -> Dict[str, Any]:
    """A service rejection that names the quote field; nothing staged; retry left open."""
    assert res.get("ok") is True, res
    assert res.get("outcome") == "rejected", res
    assert res.get("accepted_memberships") == [], res
    assert res.get("retryable") is True, res
    entries = res.get("rejected") or []
    assert entries, res
    hits = [e for e in entries if "quote" in str(e.get("field", ""))]
    assert hits, f"rejection must name the quote field: {entries}"
    entry = hits[0]
    assert entry.get("code") != "client_error", entry
    reason = str(entry.get("reason", ""))
    assert reason.strip(), entry
    if require_cap_hint:
        assert any(hint in reason.lower() for hint in WORD_CAP_HINTS), entry
    if membership_index is not None and "memberships[" in str(entry["field"]):
        assert f"memberships[{membership_index}]" in entry["field"], entry
    assert env.count("library_proposals") == 0
    assert env.count("item_shelves") == 0
    return entry


# ---------------------------------------------------------------------------------------
# Boundaries: 1, 23 and 24 words accepted; 25 and 26 rejected.
# ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("n,accepted", [(1, True), (23, True), (24, True), (25, False), (26, False)],
                         ids=["1-word", "23-words", "24-words", "25-words", "26-words"])
def test_word_count_boundary(make_env, n, accepted):
    """The cap is inclusive at 24 and exclusive at 25; every quote here occurs verbatim."""
    env = make_env()
    quote = quote_of(n)
    assert word_count(quote) == n
    assert quote in env.work["card"]["excerpts"][0]["text"]
    res = env.svc.submit_result(env.ctx, submission(env, [membership(env, quote)]))
    if accepted:
        assert_accepted(env, res, staged=1)
    else:
        assert_rejected_on_quote(env, res, membership_index=0)


def test_whitespace_only_quote_is_zero_words_and_rejected(make_env):
    """Lower bound of "1 to 24": a quote that collapses to nothing is rejected, not staged."""
    env = make_env()
    quote = " \t \n "
    assert word_count(quote) == 0
    res = env.svc.submit_result(env.ctx, submission(env, [membership(env, quote)]))
    assert_rejected_on_quote(env, res, membership_index=0, require_cap_hint=False)


# ---------------------------------------------------------------------------------------
# NFC: composed and decomposed forms count and match identically.
# ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("excerpt_form,quote_form", [(COMPOSED, DECOMPOSED), (DECOMPOSED, COMPOSED)],
                         ids=["composed-excerpt-decomposed-quote", "decomposed-excerpt-composed-quote"])
def test_nfc_forms_accept_24_words(make_env, excerpt_form, quote_form):
    env = make_env(" ".join(accented(excerpt_form)))
    quote = quote_of(24, accented(quote_form))
    assert word_count(quote) == 24
    assert quote not in env.work["card"]["excerpts"][0]["text"], "forms must differ before NFC"
    res = env.svc.submit_result(env.ctx, submission(env, [membership(env, quote)]))
    assert_accepted(env, res, staged=1)


@pytest.mark.parametrize("excerpt_form,quote_form", [(COMPOSED, DECOMPOSED), (DECOMPOSED, COMPOSED)],
                         ids=["composed-excerpt-decomposed-quote", "decomposed-excerpt-composed-quote"])
def test_nfc_forms_reject_25_words(make_env, excerpt_form, quote_form):
    """Normalisation must not change the count: a combining mark is never its own word."""
    env = make_env(" ".join(accented(excerpt_form)))
    quote = quote_of(25, accented(quote_form))
    assert word_count(quote) == 25
    res = env.svc.submit_result(env.ctx, submission(env, [membership(env, quote)]))
    assert_rejected_on_quote(env, res, membership_index=0)


# ---------------------------------------------------------------------------------------
# Tabs, double spaces, newlines and surrounding whitespace collapse before counting.
# ---------------------------------------------------------------------------------------

SEPARATORS = [
    pytest.param("\t", id="tabs"),
    pytest.param("  ", id="double-spaces"),
    pytest.param(" \t ", id="space-tab-space"),
    pytest.param("\n", id="newlines"),
]


@pytest.mark.parametrize("sep", SEPARATORS)
def test_collapsed_whitespace_accepts_24_words(make_env, sep):
    """Separators are not words: 24 tab- or double-space-joined words stay 24."""
    env = make_env()
    quote = "  " + quote_of(24, sep=sep) + "\n"
    assert word_count(quote) == 24
    assert quote not in env.work["card"]["excerpts"][0]["text"], "raw form must differ from the excerpt"
    res = env.svc.submit_result(env.ctx, submission(env, [membership(env, quote)]))
    assert_accepted(env, res, staged=1)


@pytest.mark.parametrize("sep", SEPARATORS)
def test_collapsed_whitespace_rejects_25_words(make_env, sep):
    """A counter that splits on single spaces only would see one word here; 25 must be 25."""
    env = make_env()
    quote = quote_of(25, sep=sep)
    assert word_count(quote) == 25
    res = env.svc.submit_result(env.ctx, submission(env, [membership(env, quote)]))
    assert_rejected_on_quote(env, res, membership_index=0)


# ---------------------------------------------------------------------------------------
# Secondary memberships are validated too, and a rejection stages nothing at all.
# ---------------------------------------------------------------------------------------

def test_two_memberships_within_cap_are_both_staged(make_env):
    """Control for the secondary case: 24 + 24 words is accepted with one primary."""
    env = make_env()
    res = env.svc.submit_result(env.ctx, submission(env, [
        membership(env, quote_of(24)),
        membership(env, quote_of(24), shelf_id=SHELF_SECONDARY),
    ]))
    assert_accepted(env, res, staged=2)
    rows = env.idx._conn.execute(
        "SELECT shelf_id, is_primary FROM library_proposals WHERE run_id=? AND video_id=? ORDER BY is_primary DESC",
        (env.run_id, env.video_id)).fetchall()
    assert [tuple(r) for r in rows] == [(SHELF_PRIMARY, 1), (SHELF_SECONDARY, 0)]


def test_secondary_membership_over_cap_rejects_whole_submission(make_env):
    """A valid 24-word primary does not survive a 25-word secondary: nothing is staged."""
    env = make_env()
    res = env.svc.submit_result(env.ctx, submission(env, [
        membership(env, quote_of(24)),
        membership(env, quote_of(25), shelf_id=SHELF_SECONDARY),
    ]))
    entry = assert_rejected_on_quote(env, res, membership_index=1)
    assert env.count("library_proposals") == 0, entry


def test_primary_over_cap_with_valid_secondary_rejects_whole_submission(make_env):
    env = make_env()
    res = env.svc.submit_result(env.ctx, submission(env, [
        membership(env, quote_of(25)),
        membership(env, quote_of(24), shelf_id=SHELF_SECONDARY),
    ]))
    assert_rejected_on_quote(env, res, membership_index=0)


# ---------------------------------------------------------------------------------------
# The rejected submission is preserved verbatim; nothing is staged; the retry is open.
# ---------------------------------------------------------------------------------------

def test_rejected_submission_is_preserved_and_nothing_staged(make_env):
    env = make_env()
    raw_quote = quote_of(25, sep="  ")  # double spaces: the stored copy must not be normalised
    payload = submission(env, [membership(env, raw_quote)], key="key_preserved")
    res = env.svc.submit_result(env.ctx, payload)
    entry = assert_rejected_on_quote(env, res, membership_index=0)

    conn = env.idx._conn
    assert env.count("library_submissions") == 1
    row = conn.execute("SELECT * FROM library_submissions WHERE submission_key=?", ("key_preserved",)).fetchone()
    assert row["outcome"] == "rejected"
    assert row["attempt_token"] == env.work["attempt_token"]
    stored_result = json.loads(row["result_json"])
    assert stored_result["memberships"][0]["evidence"]["quote"] == raw_quote
    assert stored_result == payload["result"]
    assert json.loads(row["response_json"]) == res

    assert conn.execute("SELECT state FROM library_attempts WHERE attempt_token=?",
                        (env.work["attempt_token"],)).fetchone()[0] == "submitted"
    work_row = conn.execute("SELECT state, attempts FROM library_work WHERE work_id=?", (env.work["work_id"],)).fetchone()
    assert tuple(work_row) == ("ready", 1)
    manifest = conn.execute("SELECT disposition, reason FROM library_manifest WHERE run_id=? AND video_id=?",
                            (env.run_id, env.video_id)).fetchone()
    assert manifest["disposition"] == "rejected"
    assert "quote" in (manifest["reason"] or ""), manifest["reason"]
    assert entry["code"] in (manifest["reason"] or ""), (entry, manifest["reason"])
    assert env.count("library_proposals") == 0
    assert env.count("item_shelves") == 0
    assert env.count("library_previews") == 0


def test_retry_after_word_cap_rejection(make_env):
    """Identical resend replays the receipt; a fresh claim gives attempt 2; 24 words succeed."""
    env = make_env()
    first = env.work
    payload = submission(env, [membership(env, quote_of(25))], key="key_attempt_1")
    res = env.svc.submit_result(env.ctx, payload)
    assert_rejected_on_quote(env, res, membership_index=0)
    assert res["retryable"] is True

    # Same key, same bytes: the stored response, no new row, no extra attempt.
    again = env.svc.submit_result(env.ctx, payload)
    assert again == res
    assert env.count("library_submissions") == 1
    conn = env.idx._conn
    assert conn.execute("SELECT attempts FROM library_work WHERE work_id=?", (first["work_id"],)).fetchone()[0] == 1

    # The planned retry: a new claim on the same item, attempt 2, a different token.
    second = env.claim()
    assert second["work_id"] == first["work_id"]
    assert second["attempt_number"] == 2
    assert second["attempt_token"] != first["attempt_token"]
    assert second["packet_hash"] == first["packet_hash"]

    env.work = second
    ok = env.svc.submit_result(env.ctx, submission(env, [membership(env, quote_of(24))], key="key_attempt_2"))
    assert_accepted(env, ok, staged=1)
    assert env.count("library_submissions") == 2
    assert conn.execute("SELECT disposition FROM library_manifest WHERE run_id=? AND video_id=?",
                        (env.run_id, env.video_id)).fetchone()[0] == "accepted"
    states = {r[0]: r[1] for r in conn.execute("SELECT attempt_token, state FROM library_attempts")}
    assert states[first["attempt_token"]] == "submitted"
    assert states[second["attempt_token"]] == "submitted"


def test_validate_result_dry_run_enforces_cap_without_consuming_attempt(make_env):
    """The non-consuming endpoint shares the rule; the lease survives for a corrected submit."""
    env = make_env()
    dry = env.svc.validate_result(env.ctx, submission(env, [membership(env, quote_of(25))], key="key_dry"))
    assert dry.get("ok") is False, dry
    error = dry.get("error") or {}
    assert error.get("code") != "client_error", dry
    field = str((error.get("details") or {}).get("field", ""))
    assert "quote" in field, dry
    assert any(hint in str(error.get("message", "")).lower() for hint in WORD_CAP_HINTS), dry
    assert env.count("library_submissions") == 0
    assert env.count("library_proposals") == 0

    fine = env.svc.validate_result(env.ctx, submission(env, [membership(env, quote_of(24))], key="key_dry"))
    assert fine.get("ok") is True and len(fine["accepted_memberships"]) == 1, fine

    res = env.svc.submit_result(env.ctx, submission(env, [membership(env, quote_of(24))], key="key_after_dry"))
    assert_accepted(env, res, staged=1)


# ---------------------------------------------------------------------------------------
# The supported full-card path applies the same cap through the same service.
# ---------------------------------------------------------------------------------------

def test_fetched_full_card_path_accepts_24_words(make_env):
    env = make_env()
    card = full_card(env)
    res = env.svc.submit_result(env.ctx, submission(env, [
        membership(env, quote_of(24), basis="fetched_full", card_hash=card["card_hash"]),
    ]))
    assert_accepted(env, res, staged=1)


def test_fetched_full_card_path_rejects_25_words(make_env):
    env = make_env()
    card = full_card(env)
    res = env.svc.submit_result(env.ctx, submission(env, [
        membership(env, quote_of(25), basis="fetched_full", card_hash=card["card_hash"]),
    ]))
    assert_rejected_on_quote(env, res, membership_index=0)


# ---------------------------------------------------------------------------------------
# The 1,000-character defensive limit is retained alongside the word cap.
# ---------------------------------------------------------------------------------------

def test_character_limit_retained_alongside_word_cap(make_env):
    """One 1,000-character word passes both rules; 1,001 characters is still refused.

    The librarian packet truncates this excerpt to 240 characters, so the full-card path is
    the only one where a 1,000-character quote can occur verbatim; that isolates the
    character limit from the occurrence check.
    """
    long_word = "x" * 1001
    env = make_env(long_word, name="long", video_id="vid_cap_long")
    assert word_count(long_word) == 1
    card = full_card(env)
    assert card["excerpts"][0]["text"] == long_word

    refused = env.svc.submit_result(env.ctx, submission(env, [
        membership(env, long_word, basis="fetched_full", card_hash=card["card_hash"]),
    ], key="key_1001"))
    # Integrator note (2026-09-05): the 1,000-character ceiling is enforced by the
    # frozen result schema (maxLength on the quote) before the service's own
    # evidence checks run, so the rejection names the result shape rather than
    # the quote field. Either form is a rejection with nothing staged; the
    # quote-field wording is required only for the word cap, tested elsewhere.
    assert refused.get("ok") is True and refused.get("outcome") == "rejected", refused
    assert refused.get("accepted_memberships") == [], refused
    assert refused.get("retryable") is True, refused
    assert refused.get("rejected"), refused
    assert env.count("library_proposals") == 0
    assert env.count("item_shelves") == 0

    env.work = env.claim()
    accepted = env.svc.submit_result(env.ctx, submission(env, [
        membership(env, long_word[:1000], basis="fetched_full", card_hash=card["card_hash"]),
    ], key="key_1000"))
    assert_accepted(env, accepted, staged=1)
