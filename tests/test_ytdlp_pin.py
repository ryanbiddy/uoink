"""Keep the Windows and macOS bundled yt-dlp versions in lockstep."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
EXPECTED = "2026.07.04"


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
        ROOT / "build-mac.sh",
        r'(?m)^YTDLP_VERSION="([^"]+)"$',
    )

    assert windows == EXPECTED
    assert macos == EXPECTED
