"""Versioned read contract between Uoink and corpus consumers.

The contract owns request validation, response envelopes, and exact public
shapes. Providers own storage. Transports own authentication and status codes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Protocol, runtime_checkable

CONTRACT_NAME = "uoink.corpus.read"
CONTRACT_VERSION = 1
OPERATIONS = ("search", "get", "facets", "taste")
SEARCH_STATES = ("matches", "no_matches", "empty_corpus")
FACET_NAMES = (
    "platform",
    "source_type",
    "author",
    "channel",
    "format",
    "performance_tier",
    "length_bucket",
    "topic",
    "hook_type",
)
SEARCH_QUERY_KEYS = {
    "q",
    "channel",
    "topic",
    "hook_type",
    "platform",
    "source_type",
    "author",
    "date_from",
    "date_to",
    "limit",
    "offset",
}

_ITEM_KEYS = {
    "id",
    "title",
    "author",
    "source_type",
    "platform",
    "source_url",
    "captured_at",
    "duration_seconds",
    "credit",
    "facets",
    "preview",
}
_CREDIT_KEYS = {"creator", "handle", "source_url"}
_ITEM_FACET_KEYS = {
    "topic",
    "hook_type",
    "format",
    "performance_tier",
    "length_bucket",
}
_ATTACHMENT_KEYS = {
    "id",
    "kind",
    "role",
    "media_type",
    "label",
    "byte_length",
    "href",
}


class ContractError(ValueError):
    """A public, stable contract failure safe to send to a client."""

    def __init__(self, code: str, message: str, *,
                 status: int = 400, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.retryable = retryable


@dataclass(frozen=True)
class SearchRequest:
    q: str | None = None
    channel: str | None = None
    topic: str | None = None
    hook_type: str | None = None
    platform: str | None = None
    source_type: str | None = None
    author: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    limit: int = 50
    offset: int = 0

    @classmethod
    def from_query(cls, query: Mapping[str, Any]) -> "SearchRequest":
        unknown = sorted(set(query) - SEARCH_QUERY_KEYS)
        if unknown:
            raise ContractError(
                "invalid_request",
                "unknown search parameters: " + ", ".join(unknown),
            )

        def one(name: str) -> str | None:
            raw = query.get(name)
            if isinstance(raw, (list, tuple)):
                raw = raw[0] if raw else None
            if raw is None:
                return None
            value = str(raw).strip()
            return value or None

        values = {
            name: one(name)
            for name in (
                "q", "channel", "topic", "hook_type", "platform",
                "source_type", "author", "date_from", "date_to",
            )
        }
        for name, value in values.items():
            if value is None:
                continue
            maximum = 500 if name == "q" else 200
            if len(value) > maximum:
                raise ContractError(
                    "invalid_request",
                    f"{name} is too long (max {maximum} characters)",
                )
        try:
            limit = int(one("limit") or "50")
            offset = int(one("offset") or "0")
        except ValueError as error:
            raise ContractError(
                "invalid_request",
                "limit and offset must be integers",
            ) from error
        if not 1 <= limit <= 200:
            raise ContractError(
                "invalid_request", "limit must be between 1 and 200")
        if not 0 <= offset <= 1_000_000:
            raise ContractError(
                "invalid_request",
                "offset must be between 0 and 1000000",
            )
        for name in ("date_from", "date_to"):
            value = values[name]
            if value:
                try:
                    datetime.strptime(value, "%Y-%m-%d")
                except ValueError as error:
                    raise ContractError(
                        "invalid_request", f"{name} must be YYYY-MM-DD"
                    ) from error
        if (values["date_from"] and values["date_to"]
                and values["date_from"] > values["date_to"]):
            raise ContractError(
                "invalid_request", "date_from is after date_to")
        return cls(limit=limit, offset=offset, **values)


@runtime_checkable
class CorpusReadProvider(Protocol):
    def search(self, request: SearchRequest) -> dict:
        ...

    def get(self, item_id: str) -> dict:
        ...

    def facets(self) -> dict:
        ...

    def taste(self) -> dict:
        ...


def _exact_keys(value: Any, expected: set[str], label: str) -> dict:
    if not isinstance(value, dict):
        raise ContractError(
            "provider_nonconformant",
            f"{label} must be an object",
            status=500,
        )
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        detail = []
        if missing:
            detail.append("missing " + ", ".join(missing))
        if unknown:
            detail.append("unknown " + ", ".join(unknown))
        raise ContractError(
            "provider_nonconformant",
            f"{label} has invalid fields: {'; '.join(detail)}",
            status=500,
        )
    return value


def _nullable_string(value: Any, label: str) -> None:
    if value is not None and not isinstance(value, str):
        raise ContractError(
            "provider_nonconformant",
            f"{label} must be a string or null",
            status=500,
        )


def validate_item_ref(item: Any) -> None:
    item = _exact_keys(item, _ITEM_KEYS, "item")
    if not isinstance(item["id"], str) or not item["id"]:
        raise ContractError(
            "provider_nonconformant",
            "item.id must be a non-empty string",
            status=500,
        )
    if not isinstance(item["title"], str):
        raise ContractError(
            "provider_nonconformant",
            "item.title must be a string",
            status=500,
        )
    for name in (
        "author", "source_url", "captured_at", "source_type", "platform",
    ):
        _nullable_string(item[name], f"item.{name}")
    duration = item["duration_seconds"]
    if duration is not None and (
            isinstance(duration, bool)
            or not isinstance(duration, (int, float))):
        raise ContractError(
            "provider_nonconformant",
            "item.duration_seconds must be a number or null",
            status=500,
        )
    credit = _exact_keys(item["credit"], _CREDIT_KEYS, "item.credit")
    for name, value in credit.items():
        _nullable_string(value, f"item.credit.{name}")
    facets = _exact_keys(item["facets"], _ITEM_FACET_KEYS, "item.facets")
    for name, value in facets.items():
        _nullable_string(value, f"item.facets.{name}")
    if item["preview"] is not None:
        validate_attachment(item["preview"])


def validate_attachment(attachment: Any) -> None:
    attachment = _exact_keys(
        attachment, _ATTACHMENT_KEYS, "attachment")
    for name in ("id", "kind", "role", "media_type", "label", "href"):
        if not isinstance(attachment[name], str) or not attachment[name]:
            raise ContractError(
                "provider_nonconformant",
                f"attachment.{name} must be a non-empty string",
                status=500,
            )
    if not isinstance(attachment["byte_length"], int) \
            or attachment["byte_length"] < 0:
        raise ContractError(
            "provider_nonconformant",
            "attachment.byte_length must be a non-negative integer",
            status=500,
        )


def validate_data(operation: str, data: Any) -> None:
    if operation not in OPERATIONS:
        raise ContractError(
            "provider_nonconformant",
            f"unknown operation {operation!r}",
            status=500,
        )
    if operation == "search":
        data = _exact_keys(data, {"items", "page"}, "search data")
        if not isinstance(data["items"], list):
            raise ContractError(
                "provider_nonconformant",
                "search data.items must be a list",
                status=500,
            )
        for item in data["items"]:
            validate_item_ref(item)
        page = _exact_keys(
            data["page"],
            {"state", "total", "corpus_total", "limit", "offset"},
            "search data.page",
        )
        if page["state"] not in SEARCH_STATES:
            raise ContractError(
                "provider_nonconformant",
                "search data.page.state is invalid",
                status=500,
            )
        for name in ("total", "corpus_total", "limit", "offset"):
            if isinstance(page[name], bool) \
                    or not isinstance(page[name], int) or page[name] < 0:
                raise ContractError(
                    "provider_nonconformant",
                    f"search data.page.{name} must be non-negative",
                    status=500,
                )
        return
    if operation == "get":
        data = _exact_keys(
            data, {"item", "content", "attachments"}, "get data")
        validate_item_ref(data["item"])
        content = _exact_keys(
            data["content"],
            {
                "available", "media_type", "text", "byte_length",
                "truncated",
            },
            "get data.content",
        )
        if not isinstance(content["available"], bool):
            raise ContractError(
                "provider_nonconformant",
                "get data.content.available must be boolean",
                status=500,
            )
        if content["media_type"] != "text/markdown":
            raise ContractError(
                "provider_nonconformant",
                "get data.content.media_type must be text/markdown",
                status=500,
            )
        if not isinstance(content["text"], str):
            raise ContractError(
                "provider_nonconformant",
                "get data.content.text must be a string",
                status=500,
            )
        if not isinstance(content["byte_length"], int) \
                or content["byte_length"] < 0:
            raise ContractError(
                "provider_nonconformant",
                "get data.content.byte_length must be non-negative",
                status=500,
            )
        if not isinstance(content["truncated"], bool):
            raise ContractError(
                "provider_nonconformant",
                "get data.content.truncated must be boolean",
                status=500,
            )
        if not isinstance(data["attachments"], list):
            raise ContractError(
                "provider_nonconformant",
                "get data.attachments must be a list",
                status=500,
            )
        for attachment in data["attachments"]:
            validate_attachment(attachment)
        return
    if operation == "facets":
        data = _exact_keys(
            data, {"facets", "date_bounds"}, "facets data")
        facets = _exact_keys(
            data["facets"], set(FACET_NAMES), "facets data.facets")
        for name, items in facets.items():
            if not isinstance(items, list):
                raise ContractError(
                    "provider_nonconformant",
                    f"facets data.facets.{name} must be a list",
                    status=500,
                )
            for item in items:
                item = _exact_keys(
                    item, {"value", "label", "count"}, "facet item")
                if not isinstance(item["value"], str) \
                        or not isinstance(item["label"], str) \
                        or isinstance(item["count"], bool) \
                        or not isinstance(item["count"], int) \
                        or item["count"] < 0:
                    raise ContractError(
                        "provider_nonconformant",
                        "facet items require strings and non-negative count",
                        status=500,
                    )
        bounds = _exact_keys(
            data["date_bounds"], {"min", "max"}, "facets date_bounds")
        _nullable_string(bounds["min"], "facets date_bounds.min")
        _nullable_string(bounds["max"], "facets date_bounds.max")
        return
    data = _exact_keys(data, {"markdown", "anchors"}, "taste data")
    if not isinstance(data["markdown"], str):
        raise ContractError(
            "provider_nonconformant",
            "taste data.markdown must be a string",
            status=500,
        )
    anchors = _exact_keys(
        data["anchors"],
        {"best", "worst", "admired_channels"},
        "taste data.anchors",
    )
    for name in ("best", "worst"):
        if not isinstance(anchors[name], list):
            raise ContractError(
                "provider_nonconformant",
                f"taste data.anchors.{name} must be a list",
                status=500,
            )
        for item in anchors[name]:
            item = _exact_keys(item, {"id", "title"}, "taste anchor")
            if not isinstance(item["id"], str) \
                    or not isinstance(item["title"], str):
                raise ContractError(
                    "provider_nonconformant",
                    "taste anchors require string id and title",
                    status=500,
                )
    if not isinstance(anchors["admired_channels"], list) or any(
            not isinstance(value, str)
            for value in anchors["admired_channels"]):
        raise ContractError(
            "provider_nonconformant",
            "taste admired_channels must be a list of strings",
            status=500,
        )


def success(operation: str, data: dict) -> dict:
    validate_data(operation, data)
    return {
        "ok": True,
        "contract": CONTRACT_NAME,
        "version": CONTRACT_VERSION,
        "operation": operation,
        "data": data,
    }


def failure(operation: str, error: ContractError) -> dict:
    if operation not in OPERATIONS:
        operation = "get"
    return {
        "ok": False,
        "contract": CONTRACT_NAME,
        "version": CONTRACT_VERSION,
        "operation": operation,
        "error": {
            "code": error.code,
            "message": error.message,
            "retryable": error.retryable,
        },
    }
