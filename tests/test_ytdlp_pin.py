"""Keep the Windows and macOS bundled yt-dlp versions in lockstep."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
EXPECTED = "2026.08.19"


def _required_match(path: Path, pattern: str) -> str:
    match = re.search(pattern, path.read_text(encoding="utf-8"))
    assert match is not None, f"yt-dlp version pin missing from {path.name}"
    return match.group(1)


def test_ytdlp_build_pins_match_current_stable():
    windows = _required_match(
        ROOT / "build.ps1",
        r"(?m)^\$YTDLP_VERSION\s*=\s*'([^']+)'$",
    )
    macos = _required_match(
        ROOT / "requirements-installer-lock.txt",
        r'(?m)^yt-dlp==([^\s]+)$',
    )

    assert windows == EXPECTED
    # Wheel metadata normalizes zero-padded release components.
    assert tuple(map(int, macos.split("."))) == tuple(map(int, EXPECTED.split(".")))
    # The mac builder now installs the qualified wheel graph from this lock.
    qualification = (ROOT / "scripts/mac/qualify_deps.py").read_text(encoding="utf-8")
    assert 'default=ROOT / "requirements-installer-lock.txt"' in qualification
