"""Regenerate Uoink's synthetic S6 provider-conformance fixture.

Run:
    python tests/regenerate_suite_integration_v1_fixture.py

Check:
    python tests/regenerate_suite_integration_v1_fixture.py --check
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import engagement_contract  # noqa: E402
import index as index_mod  # noqa: E402
import media_handoff  # noqa: E402
import suite_service  # noqa: E402

FIXTURE_PATH = (
    ROOT
    / "tests"
    / "fixtures"
    / "suite_integration_v1"
    / "uoink-provider.json"
)
SERVICE_VERSION = "3.6.0"
STARTED_AT = "2026-07-19T12:00:00Z"


def _insert_item(
    idx: index_mod.Index,
    root: Path,
    item_id: str,
    sidecar: dict,
) -> Path:
    folder = root / item_id
    folder.mkdir(parents=True)
    corpus = folder / f"{item_id}.md"
    sidecar_path = folder / f"{item_id}.json"
    corpus.write_text("# Suite fixture\n", encoding="utf-8")
    sidecar_path.write_text(
        json.dumps(sidecar, sort_keys=True),
        encoding="utf-8",
    )
    idx.upsert_yoink(
        {
            "video_id": item_id,
            "slug": item_id,
            "title": "Suite fixture",
            "yoinked_at": STARTED_AT,
            "corpus_path": str(corpus),
            "sidecar_path": str(sidecar_path),
            "metadata_json": json.dumps(
                {"url": "https://example.test/short/123"}
            ),
        },
        content="Suite fixture",
    )
    return folder


def _event(event_id: str, item_id: str = "short-123") -> dict:
    return {
        "event_id": event_id,
        "item_ref": f"uoink://item/{item_id}",
        "event_type": "cite",
        "source_product": "writer",
        "occurred_at": STARTED_AT,
    }


def _mutated(payload: dict, **changes) -> dict:
    result = copy.deepcopy(payload)
    result.update(changes)
    return result


def generate_fixture() -> dict:
    with tempfile.TemporaryDirectory() as raw_root:
        root = Path(raw_root)
        idx = index_mod.Index.open(root / "index.db")
        try:
            folder = _insert_item(
                idx,
                root,
                "short-123",
                {
                    "schema_version": 2,
                    "url": "https://example.test/short/123",
                    "media_file": "video.mp4",
                },
            )
            media_bytes = b"\x00\x00\x00\x18ftypmp4-suite-fixture"
            (folder / "video.mp4").write_bytes(media_bytes)
            _insert_item(
                idx,
                root,
                "not-kept",
                {"schema_version": 2},
            )
            _insert_item(
                idx,
                root,
                "missing-media",
                {"schema_version": 2, "media_file": "gone.mp4"},
            )
            _insert_item(
                idx,
                root,
                "traversal-media",
                {"schema_version": 2, "media_file": "../outside.mp4"},
            )

            available = media_handoff.resolve(idx, "short-123")
            available["data"]["media"]["path"] = (
                "${AUTHENTICATED_ABSOLUTE_MEDIA_PATH}"
            )
            not_kept = media_handoff.resolve(idx, "not-kept")
            missing = media_handoff.resolve(idx, "missing-media")
            traversal, _status = media_handoff.resolve_http(
                idx, "traversal-media"
            )
            unknown, _status = media_handoff.resolve_http(idx, "unknown")

            request = {
                "contract": engagement_contract.CONTRACT,
                "version": 1,
                "events": [
                    _event("writer-fixture-accepted"),
                    _event("writer-fixture-missing", "unknown"),
                ],
            }
            first = engagement_contract.success(
                idx.ingest_suite_engagement(
                    engagement_contract.parse_request(request)
                )
            )
            replay = engagement_contract.success(
                idx.ingest_suite_engagement(
                    engagement_contract.parse_request(request)
                )
            )
        finally:
            idx.close()

    manifest = suite_service.service_manifest(SERVICE_VERSION)
    lease = suite_service.runtime_lease(
        SERVICE_VERSION,
        pid=1234,
        started_at=STARTED_AT,
    )
    health_ready = suite_service.health_payload(
        SERVICE_VERSION,
        index_recovering=False,
        corpus_paths_ok=True,
    )
    health_busy = suite_service.health_payload(
        SERVICE_VERSION,
        index_recovering=True,
        corpus_paths_ok=True,
    )
    health_failed = suite_service.health_payload(
        SERVICE_VERSION,
        index_recovering=False,
        corpus_paths_ok=False,
    )

    wrong_service = copy.deepcopy(manifest)
    wrong_service["service"]["id"] = "writer"
    wrong_manifest_version = copy.deepcopy(manifest)
    wrong_manifest_version["version"] = 2
    manifest_unknown = copy.deepcopy(manifest)
    manifest_unknown["service"]["command"] = ["python", "server.py"]
    manifest_token = copy.deepcopy(manifest)
    manifest_token["service"]["token"] = "must-not-cross"

    wrong_health_identity = copy.deepcopy(health_ready)
    wrong_health_identity["service_id"] = "writer"
    inconsistent_health = copy.deepcopy(health_ready)
    inconsistent_health["ok"] = False
    health_path = copy.deepcopy(health_ready)
    health_path["checks"][0]["path"] = "C:\\private"
    unknown_health_state = copy.deepcopy(health_ready)
    unknown_health_state["state"] = "starting"

    return {
        "_fixture": {
            "contracts": [
                "ryan.suite.runtime-lease/1",
                "ryan.suite.service/1",
                "ryan.suite.health/1",
                "uoink.media.handoff/1",
                "uoink.engagement.ingest/1",
            ],
            "provider": "Uoink",
            "regenerate": (
                "python tests/regenerate_suite_integration_v1_fixture.py"
            ),
            "check": (
                "python tests/regenerate_suite_integration_v1_fixture.py --check"
            ),
            "data": "synthetic",
            "network": "none",
        },
        "valid": {
            "runtime_lease": lease,
            "service_manifest": manifest,
            "health": {
                "ready": health_ready,
                "busy": health_busy,
                "failed": health_failed,
            },
            "media_handoff": {
                "available": available,
                "not_kept": not_kept,
                "missing": missing,
            },
            "engagement": {
                "request": request,
                "first": first,
                "replay": replay,
            },
        },
        "negative": {
            "runtime_lease": {
                "unknown_key": _mutated(lease, surprise=True),
                "non_loopback_url": _mutated(
                    lease,
                    base_url="http://192.0.2.10:5179",
                ),
                "token_field": _mutated(lease, token="must-not-cross"),
                "path_field": _mutated(lease, corpus_path="C:\\private"),
                "command_field": _mutated(
                    lease,
                    command=["python", "server.py"],
                ),
                "wrong_identity": _mutated(lease, service_id="writer"),
                "dead_pid": _mutated(lease, pid=2147483647),
            },
            "service_manifest": {
                "wrong_service": wrong_service,
                "wrong_version": wrong_manifest_version,
                "unknown_key": manifest_unknown,
                "token_field": manifest_token,
            },
            "health": {
                "wrong_identity": wrong_health_identity,
                "inconsistent_ok": inconsistent_health,
                "path_field": health_path,
                "unknown_state": unknown_health_state,
            },
            "media_handoff": {
                "traversal": traversal,
                "unknown_item": unknown,
            },
            "engagement": {
                "unsupported_version": {
                    **request,
                    "version": 2,
                },
                "retryable_rejection": engagement_contract.success(
                    {
                        "submitted": 1,
                        "accepted": 0,
                        "duplicates": 0,
                        "rejected": [
                            {
                                "event_id": "writer-retryable",
                                "code": "unavailable",
                                "message": "engagement target is temporarily unavailable",
                                "retryable": True,
                            }
                        ],
                    }
                ),
                "transaction_failure": engagement_contract.failure(
                    engagement_contract.ContractError(
                        "unavailable",
                        "engagement ingestion is unavailable",
                        status=503,
                        retryable=True,
                    )
                ),
            },
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    actual = generate_fixture()
    rendered = json.dumps(actual, indent=2, ensure_ascii=False) + "\n"
    if args.check:
        if not FIXTURE_PATH.is_file():
            print(f"missing fixture: {FIXTURE_PATH}", file=sys.stderr)
            return 1
        expected = FIXTURE_PATH.read_text(encoding="utf-8")
        if expected != rendered:
            print(
                "suite integration fixture is stale; regenerate it",
                file=sys.stderr,
            )
            return 1
        print("ok  Uoink suite integration fixture is current")
        return 0
    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE_PATH.write_text(rendered, encoding="utf-8")
    print(f"wrote {FIXTURE_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
