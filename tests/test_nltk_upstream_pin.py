"""The installer uses upstream NLTK (>= 3.10.4), not the retired local patch."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _lock_pin(name: str) -> str:
    for line in (ROOT / "requirements-installer-lock.txt").read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([A-Za-z0-9_.-]+)==([^\s;]+)", line)
        if match and match.group(1).lower() == name:
            return match.group(2)
    raise AssertionError(f"{name} not in the installer lock")


def test_lock_pins_upstream_nltk_at_least_3_10_4():
    version = _lock_pin("nltk")
    assert "+" not in version, "local-version NLTK builds are retired"
    assert tuple(int(p) for p in version.split(".")) >= (3, 10, 4)


def test_lock_covers_nltk_requirements():
    for name in ("defusedxml", "click", "joblib", "regex", "tqdm"):
        assert _lock_pin(name)


def test_build_no_longer_uses_the_vendored_wheel():
    build = (ROOT / "build.ps1").read_text(encoding="utf-8-sig")
    assert "NltkPathsecWheel" not in build
    assert "NLTK_PATHSEC_SHA256" not in build
    assert "nltk-pathsec" not in build


def test_crawl4ai_is_not_pinned_by_default():
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        assert not line.strip().lower().startswith("crawl4ai"), line
