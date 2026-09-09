"""Shared record-identity contract for destructive boundaries.

One validator, used by both transports (`uoink_mcp_tools.py` for direct
MCP dispatch and `server.py` for the authenticated HTTP endpoints), so a
delete cannot select a row through a wrong-type alias.

`int()` is not a validator. In Python `int(True) == 1`, `int("1") == 1`,
and `int(1.9) == 1`, so a JSON `true`, a numeric string, or a float all
coerce to record 1 and delete it along with every cascaded child. This
module rejects those shapes instead, before any work happens.
"""

from __future__ import annotations

from typing import Any


def parse_record_id(value: Any, field: str) -> tuple[int | None, str | None]:
    """Return ``(record_id, None)`` for a real positive integer.

    Returns ``(None, error_message)`` for every other shape -- Booleans
    (which are ``int`` subclasses in Python), numeric strings, floats,
    ``None``, and non-positive integers. Callers must check the error and
    return before touching the database.
    """
    error = f"{field} must be a positive integer"
    # bool is a subclass of int, so this check must come first.
    if isinstance(value, bool):
        return None, error
    if not isinstance(value, int):
        return None, error
    if value < 1:
        return None, error
    return value, None
