"""The C22 receipt kit's schema target must track the newest migration.

The kit's replay scenarios only run on Windows (about 90 minutes of CI), so a
stale CURRENT_SCHEMA_TARGET used to surface late. This check runs everywhere.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from install_receipt.constants import CURRENT_SCHEMA_TARGET  # noqa: E402


def _newest_migration() -> int:
    numbers = [
        int(match.group(1))
        for path in (ROOT / "migrations").glob("*.sql")
        if (match := re.match(r"(\d{4})_", path.name))
    ]
    assert numbers, "no numbered migrations found"
    return max(numbers)


def test_schema_target_matches_newest_migration():
    newest = _newest_migration()
    assert CURRENT_SCHEMA_TARGET == newest, (
        f"scripts/install_receipt/constants.py CURRENT_SCHEMA_TARGET is "
        f"{CURRENT_SCHEMA_TARGET} but the newest migration is {newest:04d}; "
        f"bump it with the migration"
    )
