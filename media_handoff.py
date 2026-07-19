"""Authenticated kept-media handoff contract owned by Uoink."""

from __future__ import annotations

import hashlib
import json
import mimetypes
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import quote

import corpus_contract
import corpus_provider

CONTRACT = "uoink.media.handoff"
VERSION = 1
OPERATION = "resolve"
_SUPPORTED_MEDIA_TYPES = {
    "video/mp4",
    "video/mpeg",
    "video/quicktime",
    "video/webm",
    "video/x-matroska",
}


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
        "operation": OPERATION,
        "data": data,
    }


def failure(error: ContractError) -> dict:
    return {
        "ok": False,
        "contract": CONTRACT,
        "version": VERSION,
        "operation": OPERATION,
        "error": {
            "code": error.code,
            "message": error.message,
            "retryable": error.retryable,
        },
    }


def _provider_error(error: corpus_contract.ContractError) -> ContractError:
    return ContractError(
        error.code,
        error.message,
        status=error.status,
        retryable=error.retryable,
    )


def _json_object(value) -> dict:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _unsafe(message: str = "kept media sidecar is nonconformant") -> ContractError:
    return ContractError(
        "provider_nonconformant",
        message,
        status=500,
        retryable=False,
    )


def _safe_sidecar(folder: Path, raw_path) -> Path:
    if not isinstance(raw_path, str) or not raw_path:
        raise _unsafe("corpus sidecar is nonconformant")
    candidate = Path(raw_path)
    try:
        base = folder.resolve(strict=True)
        if candidate.is_symlink():
            raise _unsafe("corpus sidecar is nonconformant")
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(base)
    except ContractError:
        raise
    except (OSError, ValueError) as error:
        raise _unsafe("corpus sidecar is nonconformant") from error
    if not resolved.is_file():
        raise _unsafe("corpus sidecar is nonconformant")
    return resolved


def _relative_media_parts(raw_path: str) -> tuple[str, ...]:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise _unsafe()
    value = raw_path.strip()
    windows = PureWindowsPath(value)
    posix = PurePosixPath(value.replace("\\", "/"))
    if windows.is_absolute() or windows.drive or posix.is_absolute():
        raise _unsafe()
    parts = tuple(posix.parts)
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise _unsafe()
    return parts


def _resolve_media(folder: Path, raw_path: str) -> Path | None:
    parts = _relative_media_parts(raw_path)
    try:
        base = folder.resolve(strict=True)
    except OSError as error:
        raise _unsafe() from error
    candidate = base.joinpath(*parts)
    cursor = base
    for part in parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise _unsafe()
    if not candidate.exists():
        return None
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(base)
    except (OSError, ValueError) as error:
        raise _unsafe() from error
    if not resolved.is_file():
        raise _unsafe()
    return resolved


def _hash_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                size += len(chunk)
                digest.update(chunk)
    except OSError as error:
        raise ContractError(
            "unavailable",
            "kept media is unavailable",
            status=503,
            retryable=True,
        ) from error
    return size, digest.hexdigest()


def resolve(idx, item_id: str) -> dict:
    """Resolve one indexed item's explicitly retained video, without globbing."""
    provider = corpus_provider.UoinkCorpusProvider(idx, Path("."))
    try:
        row = provider._live_row(item_id)
    except corpus_contract.ContractError as error:
        raise _provider_error(error) from error
    raw_corpus_path = row.get("corpus_path")
    if not isinstance(raw_corpus_path, str) or not raw_corpus_path:
        raise _unsafe("corpus item path is nonconformant")
    folder = Path(raw_corpus_path).parent
    sidecar_path = _safe_sidecar(folder, row.get("sidecar_path"))
    try:
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _unsafe("corpus sidecar is nonconformant") from error
    if not isinstance(sidecar, dict):
        raise _unsafe("corpus sidecar is nonconformant")
    metadata = _json_object(row.get("metadata_json"))
    source_url = (
        sidecar.get("url")
        or sidecar.get("source_url")
        or metadata.get("url")
        or metadata.get("source_url")
        or None
    )
    if source_url is not None and not isinstance(source_url, str):
        source_url = None
    schema_version = sidecar.get("schema_version", 1)
    if not isinstance(schema_version, int) or isinstance(schema_version, bool):
        raise _unsafe()
    data = {
        "item_ref": f"uoink://item/{quote(str(item_id), safe='')}",
        "state": "not_kept",
        "source_url": source_url,
        "media": None,
        "provenance": {
            "kind": "uoink_sidecar",
            "sidecar_schema_version": schema_version,
            "field": "media_file",
        },
    }
    raw_media = sidecar.get("media_file")
    if raw_media is None:
        return success(data)
    media_path = _resolve_media(folder, raw_media)
    if media_path is None:
        data["state"] = "missing"
        return success(data)
    media_type = mimetypes.guess_type(media_path.name)[0] or ""
    if media_type not in _SUPPORTED_MEDIA_TYPES:
        raise _unsafe("kept media type is unsupported")
    byte_length, sha256 = _hash_file(media_path)
    data["state"] = "available"
    data["media"] = {
        "path": str(media_path),
        "media_type": media_type,
        "byte_length": byte_length,
        "sha256": sha256,
    }
    return success(data)


def resolve_http(idx, item_id: str) -> tuple[dict, int]:
    try:
        return resolve(idx, item_id), 200
    except ContractError as error:
        return failure(error), error.status
    except Exception:
        unavailable = ContractError(
            "unavailable",
            "kept media is unavailable",
            status=503,
            retryable=True,
        )
        return failure(unavailable), unavailable.status
