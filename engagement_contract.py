"""Cross-product engagement ingestion contract v1."""

from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import unquote, urlparse

CONTRACT = "uoink.engagement.ingest"
VERSION = 1
_ENVELOPE_KEYS = {"contract", "version", "events"}
_EVENT_KEYS = {
    "event_id",
    "item_ref",
    "event_type",
    "source_product",
    "occurred_at",
}
_EVENT_TYPES = {"opened", "search_hit", "search_click", "paste", "cite"}
_SOURCE_PRODUCTS = {"writer", "zing"}
_UTC_TIMESTAMP = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$"
)


class ContractError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: int = 400,
        retryable: bool = False,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.retryable = retryable


def success(data: dict) -> dict:
    return {
        "ok": True,
        "contract": CONTRACT,
        "version": VERSION,
        "data": data,
    }


def failure(error: ContractError) -> dict:
    return {
        "ok": False,
        "contract": CONTRACT,
        "version": VERSION,
        "error": {
            "code": error.code,
            "message": error.message,
            "retryable": error.retryable,
        },
    }


def _invalid(message: str) -> ContractError:
    return ContractError("invalid_request", message)


def item_id_from_ref(item_ref: str) -> str:
    if not isinstance(item_ref, str):
        raise _invalid("item_ref must be a uoink item reference")
    parsed = urlparse(item_ref)
    if (
        parsed.scheme != "uoink"
        or parsed.netloc != "item"
        or not parsed.path.startswith("/")
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise _invalid("item_ref must be a uoink item reference")
    encoded = parsed.path[1:]
    if not encoded or "/" in encoded:
        raise _invalid("item_ref must identify one corpus item")
    try:
        item_id = unquote(encoded, errors="strict")
    except (UnicodeDecodeError, TypeError) as error:
        raise _invalid("item_ref must identify one corpus item") from error
    if not item_id or len(item_id) > 200 or "/" in item_id or "\\" in item_id:
        raise _invalid("item_ref must identify one corpus item")
    return item_id


def _validate_event(event, position: int) -> dict:
    if not isinstance(event, dict) or set(event) != _EVENT_KEYS:
        raise _invalid(f"events[{position}] must have the exact v1 keys")
    event_id = event["event_id"]
    if not isinstance(event_id, str) or not 1 <= len(event_id) <= 128:
        raise _invalid(f"events[{position}].event_id is invalid")
    try:
        event_id.encode("ascii")
    except UnicodeEncodeError as error:
        raise _invalid(f"events[{position}].event_id is invalid") from error
    item_id_from_ref(event["item_ref"])
    if event["event_type"] not in _EVENT_TYPES:
        raise _invalid(f"events[{position}].event_type is unsupported")
    if event["source_product"] not in _SOURCE_PRODUCTS:
        raise _invalid(f"events[{position}].source_product is unsupported")
    occurred_at = event["occurred_at"]
    if not isinstance(occurred_at, str) or not _UTC_TIMESTAMP.fullmatch(
        occurred_at
    ):
        raise _invalid(f"events[{position}].occurred_at must be RFC 3339 UTC")
    try:
        datetime.fromisoformat(occurred_at[:-1] + "+00:00")
    except ValueError as error:
        raise _invalid(
            f"events[{position}].occurred_at must be RFC 3339 UTC"
        ) from error
    return dict(event)


def parse_request(body) -> list[dict]:
    if not isinstance(body, dict) or set(body) != _ENVELOPE_KEYS:
        raise _invalid("request must have the exact v1 keys")
    if body.get("contract") != CONTRACT or body.get("version") != VERSION:
        raise _invalid("unsupported engagement contract or version")
    events = body.get("events")
    if not isinstance(events, list) or not 1 <= len(events) <= 100:
        raise _invalid("events must contain 1 through 100 entries")
    return [_validate_event(event, position) for position, event in enumerate(events)]
