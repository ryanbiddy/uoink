"""Uoink's SQLite/filesystem provider for corpus read contract v1."""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from urllib.parse import quote

import corpus_contract
import memory_layer

MAX_CONTENT_BYTES = 2 * 1024 * 1024
_IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def _json_object(value) -> dict:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _youtube_handle(metadata: dict) -> str | None:
    for name in ("creator_handle", "author_handle", "channel_handle"):
        value = str(metadata.get(name) or "").strip()
        if value:
            return value if value.startswith("@") else f"@{value}"
    channel_url = str(metadata.get("channel_url") or "")
    if "/@" in channel_url:
        value = channel_url.rsplit("/@", 1)[-1].strip("/").split("/", 1)[0]
        return f"@{value}" if value else None
    return None


class UoinkCorpusProvider:
    def __init__(self, idx, data_root: Path, *,
                 facet_labeler=None, vault_path: str | None = None):
        self.idx = idx
        self.data_root = Path(data_root)
        self.facet_labeler = facet_labeler or self._default_label
        self.vault_path = vault_path

    @staticmethod
    def _default_label(name: str, value: str) -> str:
        del name
        return str(value or "").replace("_", " ").replace("-", " ").title()

    def _item_ref(self, row: dict) -> dict:
        metadata = _json_object(row.get("metadata_json"))
        author = (
            row.get("author")
            or metadata.get("author")
            or row.get("channel")
            or None
        )
        source_url = (
            metadata.get("url")
            or metadata.get("source_url")
            or None
        )
        source_type = str(
            row.get("source_type")
            or metadata.get("source_type")
            or "unknown"
        )
        platform = str(
            row.get("platform")
            or metadata.get("platform")
            or source_type
        )
        duration = (
            metadata.get("duration_seconds")
            or metadata.get("duration")
        )
        return {
            "id": str(row.get("video_id") or ""),
            "title": str(row.get("title") or ""),
            "author": str(author) if author else None,
            "source_type": source_type,
            "platform": platform,
            "source_url": str(source_url) if source_url else None,
            "captured_at": (
                str(row.get("yoinked_at"))
                if row.get("yoinked_at") else None
            ),
            "duration_seconds": _number(duration),
            "credit": {
                "creator": str(author) if author else None,
                "handle": _youtube_handle(metadata),
                "source_url": str(source_url) if source_url else None,
            },
            "facets": {
                "topic": row.get("topic"),
                "hook_type": row.get("hook_type"),
                "format": row.get("format"),
                "performance_tier": row.get("performance_tier"),
                "length_bucket": row.get("length_bucket"),
            },
            "preview": self._thumbnail_descriptor(row),
        }

    def search(self, request: corpus_contract.SearchRequest) -> dict:
        try:
            result = self.idx.search_yoinks_for_memory(
                q=request.q,
                channel=request.channel,
                topic=request.topic,
                hook_type=request.hook_type,
                platform=request.platform,
                source_type=request.source_type,
                author=request.author,
                date_from=request.date_from,
                date_to=request.date_to,
                limit=request.limit,
                offset=request.offset,
            )
            corpus_total = self.idx.count_corpus()
        except Exception as error:
            raise corpus_contract.ContractError(
                "unavailable",
                "corpus search is unavailable",
                status=503,
                retryable=True,
            ) from error
        total = int(result.get("total") or 0)
        if total:
            state = "matches"
        elif corpus_total:
            state = "no_matches"
        else:
            state = "empty_corpus"
        return {
            "items": [
                self._item_ref(dict(row))
                for row in result.get("results") or []
            ],
            "page": {
                "state": state,
                "total": total,
                "corpus_total": int(corpus_total),
                "limit": request.limit,
                "offset": request.offset,
            },
        }

    def _live_row(self, item_id: str) -> dict:
        item_id = str(item_id or "").strip()
        if not item_id or len(item_id) > 200:
            raise corpus_contract.ContractError(
                "invalid_request", "item id is invalid")
        try:
            row = self.idx.get_yoink(item_id)
        except Exception as error:
            raise corpus_contract.ContractError(
                "unavailable",
                "corpus item lookup is unavailable",
                status=503,
                retryable=True,
            ) from error
        if not row or row.get("deleted_at"):
            raise corpus_contract.ContractError(
                "not_found", "corpus item not found", status=404)
        return dict(row)

    @staticmethod
    def _content(row: dict) -> dict:
        raw_path = row.get("corpus_path")
        path = Path(raw_path) if raw_path else None
        if path is None or not path.is_file():
            return {
                "available": False,
                "media_type": "text/markdown",
                "text": "",
                "byte_length": 0,
                "truncated": False,
            }
        try:
            data = path.read_bytes()
        except OSError:
            return {
                "available": False,
                "media_type": "text/markdown",
                "text": "",
                "byte_length": 0,
                "truncated": False,
            }
        truncated = len(data) > MAX_CONTENT_BYTES
        return {
            "available": True,
            "media_type": "text/markdown",
            "text": data[:MAX_CONTENT_BYTES].decode(
                "utf-8", errors="replace"),
            "byte_length": len(data),
            "truncated": truncated,
        }

    @staticmethod
    def _safe_file(folder: Path, raw_path) -> Path | None:
        if not raw_path or not isinstance(raw_path, (str, Path)):
            return None
        try:
            base = folder.resolve()
            candidate = Path(raw_path)
            if not candidate.is_absolute():
                candidate = folder / candidate
            candidate = candidate.resolve()
            candidate.relative_to(base)
        except (OSError, ValueError):
            return None
        return candidate if candidate.is_file() else None

    def _thumbnail_descriptor(self, row: dict) -> dict | None:
        raw_corpus = row.get("corpus_path")
        if not raw_corpus:
            return None
        path = self._safe_file(Path(raw_corpus).parent, "thumbnail.jpg")
        if path is None:
            return None
        media_type = mimetypes.guess_type(path.name)[0] or ""
        if media_type not in _IMAGE_MIMES:
            return None
        item_id = quote(str(row.get("video_id") or ""), safe="")
        return {
            "id": "thumbnail",
            "kind": "image",
            "role": "thumbnail",
            "media_type": media_type,
            "label": "thumbnail",
            "byte_length": path.stat().st_size,
            "href": (
                f"/api/corpus/v1/items/{item_id}/attachments/thumbnail"
            ),
        }

    def _attachment_records(self, row: dict) -> list[tuple[dict, Path]]:
        raw_corpus = row.get("corpus_path")
        if not raw_corpus:
            return []
        folder = Path(raw_corpus).parent
        sidecar = {}
        raw_sidecar = row.get("sidecar_path")
        sidecar_path = self._safe_file(folder, raw_sidecar)
        if sidecar_path:
            try:
                sidecar = _json_object(
                    sidecar_path.read_text(encoding="utf-8"))
            except OSError:
                sidecar = {}
        candidates: list[tuple[str, str, str, object]] = [
            ("thumbnail", "image", "thumbnail", "thumbnail.jpg"),
            (
                "primary",
                "image",
                "primary",
                sidecar.get("image_filename") or sidecar.get("image"),
            ),
            (
                "capture-screenshot",
                "image",
                "screenshot",
                sidecar.get("screenshot_path"),
            ),
        ]
        for index, shot in enumerate(sidecar.get("screenshots") or []):
            raw = shot.get("path") if isinstance(shot, dict) else shot
            candidates.append((
                f"screenshot-{index}",
                "image",
                "screenshot",
                raw,
            ))
        seen: set[str] = set()
        records: list[tuple[dict, Path]] = []
        item_id = quote(str(row.get("video_id") or ""), safe="")
        for attachment_id, kind, role, raw in candidates:
            path = self._safe_file(folder, raw)
            if path is None:
                continue
            key = str(path).casefold()
            if key in seen:
                continue
            seen.add(key)
            media_type = mimetypes.guess_type(path.name)[0] or ""
            if media_type not in _IMAGE_MIMES:
                continue
            descriptor = {
                "id": attachment_id,
                "kind": kind,
                "role": role,
                "media_type": media_type,
                "label": path.stem.replace("_", " ").replace("-", " "),
                "byte_length": path.stat().st_size,
                "href": (
                    f"/api/corpus/v1/items/{item_id}/attachments/"
                    f"{quote(attachment_id, safe='')}"
                ),
            }
            records.append((descriptor, path))
        return records

    def get(self, item_id: str) -> dict:
        row = self._live_row(item_id)
        return {
            "item": self._item_ref(row),
            "content": self._content(row),
            "attachments": [
                descriptor
                for descriptor, _path in self._attachment_records(row)
            ],
        }

    def attachment(self, item_id: str, attachment_id: str) -> tuple[Path, str]:
        row = self._live_row(item_id)
        for descriptor, path in self._attachment_records(row):
            if descriptor["id"] == attachment_id:
                return path, descriptor["media_type"]
        raise corpus_contract.ContractError(
            "not_found", "corpus attachment not found", status=404)

    def facets(self) -> dict:
        try:
            raw = self.idx.corpus_facets()
        except Exception as error:
            raise corpus_contract.ContractError(
                "unavailable",
                "corpus facets are unavailable",
                status=503,
                retryable=True,
            ) from error
        labelled = {}
        for name in corpus_contract.FACET_NAMES:
            labelled[name] = [
                {
                    "value": str(item["value"]),
                    "label": str(
                        self.facet_labeler(name, item["value"])),
                    "count": int(item["count"]),
                }
                for item in raw.get(name, [])
            ]
        bounds = raw.get("date_bounds") or {}
        return {
            "facets": labelled,
            "date_bounds": {
                "min": bounds.get("min"),
                "max": bounds.get("max"),
            },
        }

    def taste(self) -> dict:
        try:
            result = memory_layer.read_taste(
                self.idx,
                self.data_root,
                vault_path=self.vault_path,
            )
            raw_anchors = memory_layer.get_taste_anchors(self.idx)
        except Exception as error:
            raise corpus_contract.ContractError(
                "unavailable",
                "corpus taste is unavailable",
                status=503,
                retryable=True,
            ) from error
        if not result.get("ok"):
            raise corpus_contract.ContractError(
                "unavailable",
                "corpus taste is unavailable",
                status=503,
                retryable=True,
            )

        def anchor_items(name: str) -> list[dict]:
            out = []
            for item in raw_anchors.get(name) or []:
                if isinstance(item, dict):
                    item_id = str(
                        item.get("video_id") or item.get("id") or "")
                    title = str(item.get("title") or item_id)
                else:
                    item_id = str(item)
                    title = item_id
                if item_id:
                    out.append({"id": item_id, "title": title})
            return out

        admired = []
        for item in raw_anchors.get("admired_channels") or []:
            if isinstance(item, dict):
                value = str(item.get("name") or item.get("id") or "")
            else:
                value = str(item)
            if value:
                admired.append(value)
        return {
            "markdown": str(result.get("content") or ""),
            "anchors": {
                "best": anchor_items("best"),
                "worst": anchor_items("worst"),
                "admired_channels": admired,
            },
        }
