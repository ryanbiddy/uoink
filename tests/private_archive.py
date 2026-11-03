"""Gate tests that replay internal evaluation artifacts.

Some historical acceptance and proof tests were written against an internal
evaluation archive (receipts, manifests, measurement notes). That archive is
kept out of the public repository. When it is absent, those tests skip
instead of failing; everything else runs against synthetic fixtures.
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "docs" / "library"
REASON = "internal evaluation archive is not published in this repository"


def available(*relative: str) -> bool:
    """True when every archive-relative path exists."""
    return all((ARCHIVE / rel).exists() for rel in relative) if relative else ARCHIVE.exists()


def needs(*relative: str):
    """Mark a test to skip unless the named archive paths exist."""
    return pytest.mark.skipif(not available(*relative), reason=REASON)


def skip_module_unless(*relative: str) -> None:
    """Skip the calling test module unless the named archive paths exist."""
    if not available(*relative):
        pytest.skip(REASON, allow_module_level=True)
