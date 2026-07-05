"""C-02 (CRIT-2) -- reliability detection on faster-whisper (MIT), no
whisper-timestamped / dtw-python.

Run: python tests/test_c02_reliability_faster_whisper.py  (also pytest)

C-02 is AMBER (license compliance; parked as a draft for Ryan). These
tests pin the parts that don't need the heavy model: the module imports
faster-whisper (not whisper-timestamped), the public interface is
unchanged, and the clustering logic produces correct spans over an
injected segment stream shaped like faster-whisper's output
(Word.word/.start/.end/.probability).

The end-to-end path against a real model is a build/QA step, not a unit
test; the _transcribe seam is exactly how that logic gets exercised here
without pulling torch.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import uoink_reliability as rel  # noqa: E402


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


class _FakeWord:
    """Shaped like faster_whisper.transcribe's Word namedtuple."""
    def __init__(self, word, start, end, probability):
        self.word = word
        self.start = start
        self.end = end
        self.probability = probability


class _FakeSegment:
    def __init__(self, words):
        self.words = words


def test_no_whisper_timestamped_reference():
    src = (Path(__file__).resolve().parent.parent
           / "uoink_reliability.py").read_text(encoding="utf-8")
    _assert("whisper_timestamped" not in src and "whisper-timestamped" not in src,
            "the AGPL dependency must be gone from the module")
    _assert("faster_whisper" in src and "WhisperModel" in src,
            "reliability must use faster-whisper")
    _assert("word_timestamps=True" in src,
            "faster-whisper needs word_timestamps for per-word probability")
    reqs = (Path(__file__).resolve().parent.parent
            / "requirements.txt").read_text(encoding="utf-8")
    _assert("whisper-timestamped" not in reqs,
            "whisper-timestamped must be dropped from requirements")
    _assert("faster-whisper" in reqs, "faster-whisper must be pinned")
    print("ok  whisper-timestamped gone, faster-whisper in")


def test_public_interface_unchanged():
    for name in ("detect_unreliable_spans", "ensure_model", "Span",
                 "ReliabilityUnavailableError", "DEFAULT_MODEL",
                 "DEFAULT_THRESHOLD"):
        _assert(hasattr(rel, name), f"public symbol {name} must survive")
    print("ok  public interface unchanged")


def test_clustering_over_injected_faster_whisper_stream():
    # Two low-confidence runs separated by a confident word, plus a homophone
    # so the reason logic gets exercised.
    segments = [
        _FakeSegment([
            _FakeWord("The", 0.0, 0.2, 0.98),
            _FakeWord("their", 0.2, 0.5, 0.30),   # low + homophone
            _FakeWord("quarterly", 0.5, 1.1, 0.40),  # low, adjacent -> same span
            _FakeWord("results", 1.1, 1.6, 0.95),  # confident, breaks the run
            _FakeWord("Xanadu", 2.0, 2.6, 0.20),  # low, proper-noun-ish, new span
        ]),
    ]

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        audio = Path(f.name)
    try:
        spans = rel.detect_unreliable_spans(
            "irrelevant transcript", audio, threshold=0.5,
            _transcribe=lambda _path: segments)
        _assert(len(spans) == 2, f"two low-confidence clusters: {len(spans)}")
        first, second = spans
        _assert(first.start_word_idx == 1 and first.end_word_idx == 2,
                f"first span covers the adjacent low words: {first.to_dict()}")
        _assert("their quarterly" in first.text,
                f"first span text: {first.text}")
        _assert(first.reason == "homophone_likely",
                f"homophone reason: {first.reason}")
        _assert(abs(first.confidence - 0.35) < 1e-6,
                f"avg confidence of 0.30 and 0.40: {first.confidence}")
        _assert(first.start == 0.2 and first.end == 1.1,
                f"span carries faster-whisper timings: {first.to_dict()}")
        _assert(second.start_word_idx == 4 and "Xanadu" in second.text,
                f"second span is the isolated low word: {second.to_dict()}")
        print("ok  clustering + reasons + timings over the faster-whisper shape")
    finally:
        audio.unlink(missing_ok=True)


def test_missing_audio_raises():
    try:
        rel.detect_unreliable_spans("t", Path("does_not_exist.wav"),
                                    _transcribe=lambda _p: [])
        raise AssertionError("missing audio must raise")
    except FileNotFoundError:
        print("ok  missing audio raises FileNotFoundError")


def test_build_and_notices_wired():
    root = Path(__file__).resolve().parent.parent
    build = (root / "build.ps1").read_text(encoding="utf-8")
    _assert("win64-lgpl" in build and "BtbN" in build,
            "build.ps1 must pull the BtbN LGPL ffmpeg build")
    # The install invocation references faster-whisper's version var; the
    # dropped library's version var is gone entirely (only the historical
    # rationale comment mentions the old name).
    _assert("$FASTER_WHISPER_VERSION" in build,
            "build.ps1 must install faster-whisper")
    _assert("$WHISPER_TIMESTAMPED_VERSION" not in build,
            "the whisper-timestamped version variable must be gone")
    _assert("gen_third_party_notices.py" in build,
            "build.ps1 must regenerate THIRD-PARTY-NOTICES")
    _assert((root / "scripts" / "gen_third_party_notices.py").is_file(),
            "notices generator script must exist")
    _assert((root / "THIRD-PARTY-NOTICES.md").is_file(),
            "committed notices fallback must exist")
    print("ok  build.ps1 ffmpeg/faster-whisper/notices wired")


def main():
    test_no_whisper_timestamped_reference()
    test_public_interface_unchanged()
    test_clustering_over_injected_faster_whisper_stream()
    test_missing_audio_raises()
    test_build_and_notices_wired()
    print("\nall green")


if __name__ == "__main__":
    main()
