"""Deterministic in-memory stand-in for library_work.py (Astra's module).

Run J (Phase 2 stage 1, 2026-09-04): the adapters in uoink_mcp_tools.py reach
the service through one seam, `uoink_mcp_tools.set_library_service(...)`.
Until the real module lands, tests inject this object so transport parity,
envelope shape, the default-off apply gate, the health block and the
user-intent route can be exercised without a database, a network, a model or
the live index.

This is FIXTURE evidence only. It implements the calling convention the seam
proposes -- `method(arguments: dict, context: dict) -> dict` -- with the
minimum state needed to return contract-shaped answers. It performs no
domain validation beyond what a test asks for, writes nothing durable, and
must never be mistaken for the service under acceptance (contract, "Frozen-
copy product proof": a mocked completion never enters a measured denominator).

Every method records `(method, arguments, context)` in `calls` so a test can
assert what the adapters passed through, and returns a fresh dict so a test
mutating a response cannot leak into the next call.
"""
from __future__ import annotations

import copy
import hashlib
import json
import secrets
from typing import Any

SCHEMA_VERSION = 1


def canonical_hash(value: Any) -> str:
    """sha256 over canonical JSON (sorted keys, no whitespace, UTF-8)."""
    blob = json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


class FakeLibraryService:
    """A tiny, fully deterministic queue for adapter tests."""

    def __init__(self, *, run_id: str = "run-fixture", run_revision: int = 3,
                 projection_revision: int = 7, ready: int = 2, leased: int = 0,
                 recovery_state: str = "ready", token_seed: int = 1):
        self.run_id = run_id
        self.run_revision = run_revision
        self.projection_revision = projection_revision
        self.ready = ready
        self.leased = leased
        self.recovery_state = recovery_state
        self.calls: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
        self.submissions: dict[str, dict[str, Any]] = {}
        self.intents: dict[str, dict[str, Any]] = {}
        self.applied: list[str] = []
        self._token_seed = token_seed

    # -- helpers ------------------------------------------------------------
    def _record(self, method: str, arguments: dict[str, Any], context: dict[str, Any]) -> None:
        self.calls.append((method, copy.deepcopy(arguments), dict(context)))

    def _token(self) -> str:
        # Deterministic, 43 url-safe chars, matches ^[A-Za-z0-9_-]{43,128}$.
        self._token_seed += 1
        digest = hashlib.sha256(f"fake-token-{self._token_seed}".encode()).digest()
        import base64
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

    @staticmethod
    def _ok(**fields: Any) -> dict[str, Any]:
        return {"ok": True, "schema_version": SCHEMA_VERSION, **fields}

    @staticmethod
    def _error(code: str, message: str, *, retryable: bool = False,
               details: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"ok": False, "schema_version": SCHEMA_VERSION,
                "error": {"code": code, "message": message,
                          "retryable": retryable, "details": details or {}}}

    def waiting_for_client(self) -> bool:
        return self.ready > 0 and self.leased == 0

    # -- contract surface ---------------------------------------------------
    def list_work(self, arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        self._record("list_work", arguments, context)
        limit = arguments.get("limit", 25)
        items = [
            {"work_id": f"work-{i}", "video_id": f"video-{i}", "state": "ready",
             "attempts": 0, "disposition": "waiting"}
            for i in range(min(limit, self.ready))
        ]
        return self._ok(
            run_id=arguments.get("run_id", self.run_id),
            run_revision=self.run_revision,
            projection_revision=self.projection_revision,
            counts={"work": {"ready": self.ready, "leased": self.leased, "accepted": 0,
                             "unmapped": 0, "unsupported": 0, "blocked": 0, "cancelled": 0},
                    "manifest": {"waiting": self.ready, "accepted": 0, "rejected": 0}},
            items=items,
            next_cursor=None,
            waiting_for_client=self.waiting_for_client(),
            recovery_state=self.recovery_state,
        )

    def claim_work(self, arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        self._record("claim_work", arguments, context)
        count = min(arguments.get("max_items", 12), self.ready)
        lease_seconds = arguments.get("lease_seconds", 900)
        now_ms = context["now_ms"]
        work = []
        for i in range(count):
            work.append({
                "work_id": f"work-{i}", "video_id": f"video-{i}",
                "attempt_token": self._token(), "attempt_number": 1,
                "lease_expires_ms": now_ms + lease_seconds * 1000,
                "source_revision": "a" * 64, "taxonomy_revision": "b" * 64,
                "packet_hash": "c" * 64,
                "card": {"schema": 1, "profile": "librarian", "video_id": f"video-{i}",
                         "excerpts": []},
            })
        self.ready -= count
        self.leased += count
        return self._ok(run_id=arguments["run_id"], run_revision=self.run_revision,
                        work=work, taxonomy={"revision": "b" * 64, "shelves": []},
                        rules={"min_confidence": 0.6, "max_memberships": 3})

    def renew_attempt(self, arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        self._record("renew_attempt", arguments, context)
        return self._ok(work_id=arguments["work_id"], state="leased", attempt_number=1,
                        remaining_attempts=2,
                        lease_expires_ms=context["now_ms"] + arguments["lease_seconds"] * 1000)

    def release_attempt(self, arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        self._record("release_attempt", arguments, context)
        if self.leased:
            self.leased -= 1
            self.ready += 1
        return self._ok(work_id=arguments["work_id"], state="ready", remaining_attempts=2)

    def cancel_attempt(self, arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        self._record("cancel_attempt", arguments, context)
        if self.leased:
            self.leased -= 1
        return self._ok(work_id=arguments["work_id"], state="cancelled", remaining_attempts=2,
                        reason=arguments["reason"])

    def submit_result(self, arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        self._record("submit_result", arguments, context)
        key = arguments["submission_key"]
        request_hash = canonical_hash(arguments)
        recorded = self.submissions.get(key)
        if recorded is not None:
            if recorded["request_hash"] != request_hash:
                return self._error("idempotency_conflict",
                                   "a different request was already recorded under this key",
                                   details={"submission_key": key})
            return copy.deepcopy(recorded["response"])
        result = arguments["result"]
        if result["outcome"] == "assigned":
            outcome = "accepted"
            accepted = [m["shelf_id"] for m in result["memberships"]]
        else:
            outcome = result["outcome"]
            accepted = []
        response = self._ok(work_id=arguments["work_id"], video_id=arguments["video_id"],
                            outcome=outcome, accepted_memberships=accepted,
                            rejected=[], retryable=False)
        self.submissions[key] = {"request_hash": request_hash, "response": response}
        if self.leased:
            self.leased -= 1
        return copy.deepcopy(response)

    def preview_apply(self, arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        self._record("preview_apply", arguments, context)
        delta = {"additions": [], "replacements": [], "deletions": [], "primary_changes": [],
                 "activation": bool(arguments.get("activate_version", False)),
                 "unchanged": [], "preserved_pins": [], "exclusions": []}
        return self._ok(preview_id="preview-1", run_id=arguments["run_id"],
                        expected_projection_revision=arguments["expected_projection_revision"],
                        delta_hash=canonical_hash(delta), expires_ms=context["now_ms"] + 900_000,
                        delta=delta, baseline_items=0, changed_items=0, churn=0.0,
                        initial_filing=True, can_apply=False,
                        reasons=["preview approval required"])

    def apply_preview(self, arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        self._record("apply_preview", arguments, context)
        if not context.get("apply_enabled"):
            return self._error("apply_disabled", "librarian_apply_enabled is off")
        before = self.projection_revision
        self.projection_revision += 1
        self.applied.append(arguments["operation_key"])
        return self._ok(operation_key=arguments["operation_key"], apply_id="apply-1",
                        before_revision=before, after_revision=self.projection_revision,
                        delta_hash=arguments["delta_hash"], undo_target="apply-1")

    def pin_shelf(self, arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        self._record("pin_shelf", arguments, context)
        intent = self.intents.get(arguments["user_intent_token"])
        if intent is None:
            return self._error("invalid_user_intent", "unknown or expired user_intent_token")
        before = self.projection_revision
        self.projection_revision += 1
        return self._ok(operation_key=arguments["operation_key"], apply_id="pin-1",
                        before_revision=before, after_revision=self.projection_revision,
                        delta_hash="d" * 64, undo_target="pin-1")

    def undo_apply(self, arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        self._record("undo_apply", arguments, context)
        intent = self.intents.get(arguments["user_intent_token"])
        if intent is None:
            return self._error("invalid_user_intent", "unknown or expired user_intent_token")
        before = self.projection_revision
        self.projection_revision += 1
        return self._ok(operation_key=arguments["operation_key"], apply_id="undo-1",
                        before_revision=before, after_revision=self.projection_revision,
                        delta_hash="e" * 64, undo_target="undo-1")

    def mint_user_intent(self, arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        self._record("mint_user_intent", arguments, context)
        token = self._token()
        request_hash = canonical_hash(arguments)
        expires_ms = context["now_ms"] + context["intent_ttl_ms"]
        self.intents[token] = {"kind": arguments["kind"], "request_hash": request_hash,
                               "session_hash": context["session_hash"],
                               "expires_ms": expires_ms}
        return self._ok(user_intent_token=token, expires_ms=expires_ms,
                        kind=arguments["kind"], request_hash=request_hash)


class RaisingLibraryService(FakeLibraryService):
    """Every method raises with text that must never reach a client."""

    def __getattribute__(self, name: str):
        if name in ("list_work", "claim_work", "renew_attempt", "release_attempt",
                    "cancel_attempt", "submit_result", "preview_apply", "apply_preview",
                    "pin_shelf", "undo_apply", "mint_user_intent"):
            def boom(arguments, context):
                raise RuntimeError("sqlite3.OperationalError: C:\\Users\\someone\\index.db is locked")
            return boom
        return super().__getattribute__(name)


class StringErrorLibraryService(FakeLibraryService):
    """Returns the legacy string-error shape so the adapter's normalisation
    of a non-conforming service answer can be checked."""

    def list_work(self, arguments, context):
        self._record("list_work", arguments, context)
        return {"ok": False, "error": "run not found"}


def fresh_token() -> str:
    return secrets.token_urlsafe(32)
