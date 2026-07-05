# Surface map: license compliance (C-02, AMBER)

CRIT-2. The product claims MIT but shipped AGPL/GPL-encumbered
dependencies: `whisper-timestamped` (AGPL-3.0) + `dtw-python` (GPL-3.0)
bundled and imported in-process, and a GPLv3 ffmpeg build redistributed
without its license text or a source offer. That blocks the Chrome Web
Store and any clean distribution. **AMBER: this is a draft PR parked for
Ryan** (the audit flagged it as needing a decision on approach); nothing
merges without his letter.

## What changed

### 1. Reliability detection: faster-whisper (MIT), not whisper-timestamped

`uoink_reliability.py` now sources per-word confidence from
`faster_whisper.WhisperModel(...).transcribe(..., word_timestamps=True)`,
whose `Word.probability` replaces the old library's `confidence`.
faster-whisper is MIT and whisperx already depends on it, so the bundle
doesn't grow. The public interface (`detect_unreliable_spans`,
`ensure_model`, `Span`) and every downstream caller (server.py:1716,
server.py:9814) are unchanged — only the confidence source and the import
moved. A `_transcribe` injection seam lets the clustering logic be tested
without pulling torch.

Dropped: `whisper-timestamped==1.15.9` (and its transitive `dtw-python`)
from `requirements.txt` and `build.ps1`. Added `faster-whisper==1.1.0`.

### 2. ffmpeg: BtbN win64-LGPL, not gyan.dev essentials

`build.ps1` `$FFMPEG_URL` now pulls BtbN's `win64-lgpl` build (a versioned
release tag, so the SHA pin stays meaningful). The gyan.dev "essentials"
build links GPL encoders (x264/x265) and shipped without meeting GPL
obligations. Uoink only needs ffmpeg to decode/extract audio, so the LGPL
build (no GPL encoders) is feature-sufficient.

**Builder action required before merge:** download the new artifact once,
paste its real SHA256 into `$FFMPEG_SHA256` (the current value is the old
gyan hash and will fail `Confirm-Hash` — deliberately, so a build can't
silently ship the wrong binary). This is a chief reason the PR is parked.

### 3. THIRD-PARTY-NOTICES.md, generated

`scripts/gen_third_party_notices.py` enumerates the installed dependency
tree (pip-licenses JSON when available; importlib.metadata fallback) and
appends a fixed ffmpeg LGPL block. `build.ps1` runs it against the
embeddable Python after the pip install, so the shipped notices match the
shipped bundle exactly, then strips pip-licenses back out (build-time
tool, not a runtime dep). The committed `THIRD-PARTY-NOTICES.md` is a
curated fallback listing the direct bundled deps and their licenses.

## Open decisions for Ryan

1. **Approach sign-off**: faster-whisper for reliability + BtbN LGPL
   ffmpeg is the recommended path; confirm before it ships.
2. **ffmpeg SHA**: must be filled from a real download (above).
3. **faster-whisper pin**: 1.1.0 chosen as current stable; a clean-install
   bundle test on the embeddable Python should confirm it loads the tiny
   model on CPU (int8) before release.

## Tests / proof

`tests/test_c02_reliability_faster_whisper.py`: no whisper-timestamped
reference survives in the module or requirements, faster-whisper +
word_timestamps present, public interface intact, correct clustering /
reasons / timings over an injected faster-whisper-shaped stream, missing
audio raises, and the build.ps1 + notices wiring is present. Full suite
178 passed. The real-model transcription path is a build/QA step, not a
unit test (the seam is how the logic is exercised here without torch).
