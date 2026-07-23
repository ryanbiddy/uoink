"""Voice DNA — banned-phrase guard + system-prompt prepend.

Suite-split ownership: this is a live Uoink product surface. `server.py`,
`writing_studio.py`, and `uoink_mcp_tools.py` call it, and `build.ps1` stages
it into the installer. Writer has its own Voice DNA copy; removing this module
requires a decision to remove Uoink's writing surfaces.

Per `voice_dna/VOICE-DNA.md` (the canonical spec) + Ryan's locked answer #3
in PROMPT-V3.2-CC-BACKEND.md: voice DNA is a SOFT WARN, not an auto-block.
The agent path returns generated output AND a structured warning when
banned phrases appear. The dashboard surfaces a regenerate/use-as-is/
toggle-settings affordance. Settings keys:
  voice_dna_warnings_enabled               default True
  voice_dna_show_per_generation_toggle     default True

Canonical file: `voice_dna/VOICE-DNA.md` next to this module. Helper loads
at module import time; the constant is then read directly by writing
studio + scripts modules.

Banned phrases live in `_BANNED_PHRASES` as structured data so the scan
is O(n*phrases) over output text, not a per-call markdown parse. The
list IS sync'd from VOICE-DNA.md by hand at code review time; if Ryan
updates VOICE-DNA.md, the loader test in CI catches a drift.

Implementation note: phrase matching is case-INSENSITIVE substring match
against the LOWERCASED output, then position is computed in the original
output so the dashboard can highlight the original casing. Word-boundary
matching is intentionally LOOSE -- "delve into" should match "Delving
into" too. We treat each entry as a case-insensitive regex with manual
\\b word boundaries where needed (e.g., "in order to" needs spaces around).

The Big One (negation-then-corrected-assertion) is detected via a regex
that catches the dominant patterns. NOT exhaustive -- the spec says any
sentence that negates then asserts fails -- but the structured patterns
catch the most common ones."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

log = logging.getLogger("uoink.voice_dna")


# ---- canonical doc -----------------------------------------------------
def _load_voice_dna_prompt() -> str:
    """Load VOICE-DNA.md from the repo-vendored copy next to this module.
    Falls back to an empty string if missing (the helper still boots; the
    log line will surface in /diagnose). The structured banned-phrase
    list below is the authoritative scanning data; this constant is just
    the prepended system prompt."""
    here = Path(__file__).parent.resolve()
    candidates = [
        here / "voice_dna" / "VOICE-DNA.md",
        here / "VOICE-DNA.md",
    ]
    for candidate in candidates:
        if candidate.exists():
            try:
                return candidate.read_text(encoding="utf-8")
            except OSError as e:
                log.warning("voice_dna: could not read %s: %s", candidate, e)
    log.warning("voice_dna: VOICE-DNA.md not found in any of %s",
                  [str(c) for c in candidates])
    return ""


VOICE_DNA_PROMPT = _load_voice_dna_prompt()


# ---- banned-phrase structure -------------------------------------------
# Each entry: (regex, label, category). Regex is case-insensitive. The
# label is the user-facing phrase as it appears in VOICE-DNA.md. The
# category maps to the spec's section headings.
#
# When updating: sync this list with voice_dna/VOICE-DNA.md. A drift
# guard in the smoke test verifies every label substring is present in
# VOICE_DNA_PROMPT.

_DEAD_AI_LANGUAGE = [
    (r"\bin today'?s\b", "in today's", "Dead AI Language"),
    (r"\bit'?s important to note that\b", "it's important to note that",
     "Dead AI Language"),
    (r"\bit'?s worth noting\b", "it's worth noting", "Dead AI Language"),
    (r"\bdelv(?:e|ing|es|ed)\b", "delve", "Dead AI Language"),
    (r"\bdive into\b", "dive into", "Dead AI Language"),
    (r"\bunpack\b", "unpack", "Dead AI Language"),
    (r"\bharness\b", "harness", "Dead AI Language"),
    (r"\bleverag(?:e|ing|es|ed)\b", "leverage", "Dead AI Language"),
    (r"\butili(?:z|s)(?:e|ing|es|ed)\b", "utilize", "Dead AI Language"),
    (r"\blandscape\b", "landscape", "Dead AI Language"),
    (r"\brealm\b", "realm", "Dead AI Language"),
    (r"\brobust\b", "robust", "Dead AI Language"),
    (r"\bgame[- ]?changer\b", "game-changer", "Dead AI Language"),
    (r"\bcutting[- ]?edge\b", "cutting-edge", "Dead AI Language"),
    (r"\bstraightforward\b", "straightforward", "Dead AI Language"),
    (r"\bi'?d be happy to help\b", "i'd be happy to help",
     "Dead AI Language"),
    (r"\bin order to\b", "in order to", "Dead AI Language"),
]

_DEAD_TRANSITIONS = [
    (r"\bfurthermore\b", "furthermore", "Dead Transitions"),
    (r"\badditionally\b", "additionally", "Dead Transitions"),
    (r"\bmoreover\b", "moreover", "Dead Transitions"),
    (r"\bmoving forward\b", "moving forward", "Dead Transitions"),
    (r"\bat the end of the day\b", "at the end of the day",
     "Dead Transitions"),
    (r"\bto put this in perspective\b", "to put this in perspective",
     "Dead Transitions"),
    (r"\bwhat makes this particularly interesting is\b",
     "what makes this particularly interesting is", "Dead Transitions"),
    (r"\bthe implications here are\b", "the implications here are",
     "Dead Transitions"),
    (r"\bin other words\b", "in other words", "Dead Transitions"),
    (r"\bit goes without saying\b", "it goes without saying",
     "Dead Transitions"),
]

_ENGAGEMENT_BAIT = [
    (r"\blet that sink in\b", "let that sink in", "Engagement Bait"),
    (r"\bread that again\b", "read that again", "Engagement Bait"),
    (r"\bfull stop\b", "full stop", "Engagement Bait"),
    (r"\bthis changes everything\b", "this changes everything",
     "Engagement Bait"),
    (r"\bare you paying attention\b", "are you paying attention",
     "Engagement Bait"),
    (r"\byou'?re not ready for this\b", "you're not ready for this",
     "Engagement Bait"),
]

_AI_CRINGE = [
    (r"\bsupercharg(?:e|ing|es|ed)\b", "supercharge", "AI Cringe"),
    (r"\bunlock\b", "unlock", "AI Cringe"),
    (r"\bfuture[- ]?proof\b", "future-proof", "AI Cringe"),
    (r"\b10[- ]?x your productivity\b", "10x your productivity",
     "AI Cringe"),
    (r"\bthe ai revolution\b", "the ai revolution", "AI Cringe"),
    (r"\bin the age of ai\b", "in the age of ai", "AI Cringe"),
]

_GENERIC_INSIDER = [
    (r"here'?s the part nobody'?s talking about",
     "here's the part nobody's talking about", "Generic Insider Claims"),
    (r"\bwhat nobody tells you\b", "what nobody tells you",
     "Generic Insider Claims"),
    (r"\bmost people don'?t realize\b", "most people don't realize",
     "Generic Insider Claims"),
]

# "The Big One" — negation-then-corrected-assertion patterns. These are
# fatal per the spec: even ONE makes the output fail. Two-sentence form
# is the most common ("This isn't X. This is Y."); single-sentence
# negate-then-assert ("Forget X. This is Y." / "Not X. Y.") also caught.
#
# We deliberately make this STRICTER (more false positives accepted)
# than the other categories because the spec is unambiguous that any
# such construction must be deleted.
_THE_BIG_ONE = [
    (
        # "This isn't X. This is Y." / "It's not X. It's Y." family
        r"\b(?:this|it|that|we)'?(?:s|re)?\s+(?:isn'?t|is not|aren'?t|are not|wasn'?t|was not)\s+[^.!?]{3,80}[.!?]\s+(?:this|it|that|we|here)'?(?:s|re)?\s+(?:is|are|was)\b",
        "this isn't X. this is Y.", "The Big One",
    ),
    (
        # "Forget X. This is Y." family
        r"\bforget\s+[^.!?]{3,80}[.!?]\s+(?:this|it|that|here)'?(?:s|re)?\s+(?:is|are)\b",
        "forget X. this is Y.", "The Big One",
    ),
    (
        # "Not X. Y." (two-sentence)
        r"^[^a-z]*not\s+[^.!?]{3,80}[.!?]\s+",
        "Not X. Y.", "The Big One",
    ),
    (
        # "Less X, more Y."
        r"\bless\s+[^.,!?]{2,40}[,.]\s*more\s+",
        "less X, more Y.", "The Big One",
    ),
]

_BANNED_PHRASES: list[tuple[str, str, str]] = (
    _DEAD_AI_LANGUAGE
    + _DEAD_TRANSITIONS
    + _ENGAGEMENT_BAIT
    + _AI_CRINGE
    + _GENERIC_INSIDER
    + _THE_BIG_ONE
)


# Pre-compile for speed. The scan is hot per generation.
_COMPILED_BANNED: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(pattern, re.IGNORECASE | re.MULTILINE), label, category)
    for pattern, label, category in _BANNED_PHRASES
]


# ---- scan API ----------------------------------------------------------
def scan(text: str) -> list[dict[str, Any]]:
    """Return a list of {phrase, position, category} dicts, one per
    banned-phrase match. Empty list = clean output.

    The position is a [start, end] pair into the ORIGINAL text (so the
    dashboard can highlight in the original casing). Overlapping matches
    are kept (one phrase can land in multiple categories) so the
    dashboard can show the full picture; the dashboard de-dupes if it
    wants a tighter view."""
    if not text:
        return []
    out: list[dict[str, Any]] = []
    for pattern, label, category in _COMPILED_BANNED:
        for match in pattern.finditer(text):
            out.append({
                "phrase": label,
                "position": [match.start(), match.end()],
                "category": category,
                "matched_text": text[match.start():match.end()],
            })
    return out


def warning_copy() -> str:
    """The user-facing warning string the dashboard surfaces when scan()
    returns a non-empty list. Locked text per PROMPT-V3.2-CC-BACKEND.md
    Deliverable 1, Voice DNA enforcement section."""
    return (
        "Heads up — Uoink spotted some patterns that often read as "
        "AI-slop in your output. We just want you not to sound like a "
        "robot — up to you whether to keep them. Regenerate to try "
        "again, or toggle Voice DNA warnings off for this generation "
        "or forever in Settings."
    )


def prepend_system_prompt(user_system_prompt: str) -> str:
    """Build the prepend block that goes on top of any generation
    system prompt. Per the locked spec, the canonical voice DNA file
    contents are injected verbatim, then a separator, then the caller's
    own prompt. Caller is responsible for handing the result to its LLM
    client."""
    if not VOICE_DNA_PROMPT:
        return user_system_prompt
    return (
        VOICE_DNA_PROMPT.rstrip()
        + "\n\n---\n\n"
        + (user_system_prompt or "").lstrip()
    )


__all__ = [
    "VOICE_DNA_PROMPT",
    "scan",
    "warning_copy",
    "prepend_system_prompt",
]
